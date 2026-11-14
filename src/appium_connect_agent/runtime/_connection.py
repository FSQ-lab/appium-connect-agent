"""External connection preparation and lifetime; never owns a server or Session."""

from __future__ import annotations

import json
import platform
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from threading import Lock, get_ident
from types import TracebackType
from typing import Literal, Protocol

import httpcore
import httpx

from . import _coordination
from ._diagnostics import Runtime, _Operation
from ._http import HTTPFailure, HTTPResult, get_status
from ._models import (
    DiagnosticReport,
    EnvironmentBusyError,
    InvalidStateError,
    OperationControl,
    OperationTimeoutError,
    RuntimeOperationError,
    ServiceConnectionError,
    UnsupportedVersionError,
)
from ._semver import version as parse_version

Compatibility = Literal["declared_compatible", "unverified"]


def _reject_constant(value: str) -> None:
    raise HTTPFailure()


def _http_error(error: BaseException, operation: _Operation) -> BaseException:
    if isinstance(error, (httpx.TimeoutException, httpcore.TimeoutException)):
        return operation.error(OperationTimeoutError, "operation_timeout")
    if isinstance(error, (httpx.RemoteProtocolError, httpcore.RemoteProtocolError)):
        return HTTPFailure()
    if isinstance(error, (httpx.NetworkError, httpx.ProxyError, httpcore.NetworkError)):
        return HTTPFailure("service_unavailable")
    return error


def _http_cleanup(result: HTTPResult, operation: _Operation) -> BaseException | None:
    errors: list[BaseException] = []
    known = False
    for error in result.cleanup_errors:
        if isinstance(error, httpx.CloseError):
            known = True
            errors.append(operation.error(RuntimeOperationError, "http_cleanup_failed"))
        else:
            errors.append(error)
    if not errors:
        return None
    if len(errors) == 1:
        return errors[0]
    group = BaseExceptionGroup("HTTP resource cleanup failures", errors)
    if known:
        failure = operation.error(RuntimeOperationError, "http_cleanup_failed")
        failure.runtime_http_cleanup_error = group
        return failure
    return group


class RuntimeUsage:
    """One opaque, one-shot in-memory lease against a Runtime connection."""

    __slots__ = (
        "_begin_terminal_disposal",
        "_continue_terminal_disposal",
        "_lock",
        "_operation_id",
        "_release",
        "_released",
        "_report",
        "_terminal_disposal_started",
    )

    def __init__(
        self,
        release: Callable[[], None],
        operation_id: str,
        report: DiagnosticReport,
        *,
        begin_terminal_disposal: Callable[[], None] | None = None,
        continue_terminal_disposal: Callable[[OperationControl], None] | None = None,
    ) -> None:
        self._release = release
        self._operation_id = operation_id
        self._report = report
        self._begin_terminal_disposal = begin_terminal_disposal
        self._continue_terminal_disposal = continue_terminal_disposal
        self._terminal_disposal_started = False
        self._released = False
        self._lock = Lock()

    @property
    def _supports_terminal_disposal(self) -> bool:
        return (
            self._begin_terminal_disposal is not None
            and self._continue_terminal_disposal is not None
        )

    def _terminal_dispose(self, control: OperationControl) -> None:
        with self._lock:
            if self._released:
                raise InvalidStateError(
                    "usage_released", self._operation_id, self._report
                )
            begin = self._begin_terminal_disposal
            continuation = self._continue_terminal_disposal
            if begin is None or continuation is None:
                raise InvalidStateError(
                    "unsupported_connection_ownership",
                    self._operation_id,
                    self._report,
                )
            if not self._terminal_disposal_started:
                begin()
                self._terminal_disposal_started = True
            continuation(control)
            self._released = True

    def release(self) -> None:
        """Release this lease once without process, network, or filesystem I/O."""
        with self._lock:
            if self._released or self._terminal_disposal_started:
                code = (
                    "usage_disposal_started"
                    if self._terminal_disposal_started and not self._released
                    else "usage_released"
                )
                raise InvalidStateError(code, self._operation_id, self._report)
            self._released = True
            self._release()


class _ConnectionOwner(Protocol):
    @property
    def connection_active(self) -> bool: ...

    def acquire_usage(self) -> RuntimeUsage: ...


@dataclass(frozen=True)
class RuntimeConnection:
    _scope: _ConnectionOwner = field(repr=False)
    _url: str = field(repr=False)
    appium_version: str | None
    compatibility: Compatibility
    report: DiagnosticReport
    ownership: Literal["external", "managed"] = "external"

    @property
    def server_url(self) -> str:
        if not self._scope.connection_active:
            raise InvalidStateError(
                "connection_closed", self.report.operation_id, self.report
            )
        return self._url

    def acquire_usage(self) -> RuntimeUsage:
        """Acquire one opaque lease while this connection accepts new work."""
        return self._scope.acquire_usage()


class _ConnectionScope(AbstractContextManager[RuntimeConnection]):
    def __init__(self, runtime: Runtime, control: OperationControl) -> None:
        self.runtime, self.control = runtime, control
        self.active = False
        self._entry = Lock()
        self.operation: _Operation | None = None
        self.lock: AbstractContextManager[None] | None = None

    @property
    def connection_active(self) -> bool:
        return self.active

    def acquire_usage(self) -> RuntimeUsage:
        operation = self.operation
        if not self.active or operation is None:
            if operation is None:
                operation = _Operation(self.control, None)
            raise operation.error(InvalidStateError, "connection_closed")
        report = operation.report()
        return RuntimeUsage(lambda: None, operation.operation_id, report)

    def __enter__(self) -> RuntimeConnection:
        # A permanently acquired token makes consumption atomic across threads.
        if not self._entry.acquire(blocking=False):
            # Do not replace a live scope's report or release its lock.
            operation = self.operation or _Operation(self.control, None)
            raise operation.error(InvalidStateError, "connection_scope_consumed")
        operation = self.operation = _Operation(
            self.control, self.runtime._on_progress, phase="connecting"
        )
        http_result = HTTPResult()
        operation.checkpoint()
        try:
            lock = _coordination.account_lock()
            try:
                lock.__enter__()
            except _coordination.Busy:
                raise operation.error(
                    EnvironmentBusyError, "environment_busy"
                ) from None
            except (_coordination.CoordinationFailure, OSError, KeyError):
                raise operation.error(
                    RuntimeOperationError, "coordination_unavailable"
                ) from None
            self.lock = lock
            operation.checkpoint()
            url = self.runtime._settings.server_url
            if url is None:
                operation.add("service", "fail", "endpoint_not_configured")
                raise operation.error(ServiceConnectionError, "endpoint_not_configured")
            supported = platform.system() == "Darwin"
            operation.add(
                "host",
                "pass" if supported else "fail",
                "host_observed" if supported else "unsupported_host",
            )
            if not supported:
                raise operation.error(RuntimeOperationError, "unsupported_host")
            try:
                http_result = get_status(url, operation.checkpoint, operation.deadline)
                if http_result.error is not None:
                    raise _http_error(http_result.error, operation)
                operation.checkpoint()
                try:
                    value = json.loads(
                        http_result.body, parse_constant=_reject_constant
                    )
                except (ValueError, RecursionError):
                    raise HTTPFailure() from None
                if not isinstance(value, dict) or not isinstance(
                    value.get("value"), dict
                ):
                    raise HTTPFailure()
                value = value["value"]
                if type(value.get("ready")) is not bool:
                    raise HTTPFailure()
                if not value["ready"]:
                    raise HTTPFailure("service_not_ready")
            except HTTPFailure as error:
                failure = error.code
            else:
                failure = ""
            if failure:
                operation.add("service", "fail", failure)
                raise operation.error(ServiceConnectionError, failure)
            operation.add("service", "pass", "service_ready")
            build = value.get("build")
            observed = parse_version(
                build.get("version") if isinstance(build, dict) else None
            )
            version = observed.text if observed is not None else None
            compatible = observed is not None and observed.major == 3
            operation.add(
                "declared_compatibility",
                "pass" if compatible else "unknown" if version is None else "fail",
                "declared_compatible"
                if compatible
                else "version_unknown"
                if version is None
                else "unsupported_server_version",
                (f"version={version}",) if version is not None else (),
            )
            if version is not None and not compatible:
                raise operation.error(
                    UnsupportedVersionError, "unsupported_server_version"
                )
            operation.add("qualified_support", "unknown", "not_qualified")
            operation.add("device", "unknown", "not_checked")
            cleanup = _http_cleanup(http_result, operation)
            if cleanup is not None:
                http_result.cleanup_errors.clear()
                raise cleanup
            self.runtime._active_thread = get_ident()
            self.active = True
            return RuntimeConnection(
                self,
                url,
                version,
                "declared_compatible" if compatible else "unverified",
                operation.report(),
            )
        except BaseException as error:
            cleanup = _http_cleanup(http_result, operation)
            if cleanup is not None:
                error.__dict__["runtime_http_cleanup_error"] = cleanup
            self._release(error)
            raise

    def _release(self, original: BaseException | None) -> None:
        self.active = False
        if self.lock is None:
            return
        lock, self.lock = self.lock, None
        self.runtime._active_thread = None
        try:
            lock.__exit__(None, None, None)
        except Exception:
            assert self.operation is not None
            failure = self.operation.error(
                RuntimeOperationError, "coordination_unavailable"
            )
            if original is None:
                raise failure from None
            original.__dict__["runtime_cleanup_error"] = failure

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._release(exc_value)
