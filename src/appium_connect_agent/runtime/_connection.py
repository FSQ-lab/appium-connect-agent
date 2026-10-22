"""External connection preparation and lifetime; never owns a server or Session."""

from __future__ import annotations

import json
import platform
import re
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from threading import Lock, get_ident
from types import TracebackType
from typing import Literal

from . import _coordination
from ._diagnostics import Runtime, _Operation
from ._http import HTTPFailure, get_status
from ._models import (
    DiagnosticReport,
    EnvironmentBusyError,
    InvalidStateError,
    OperationControl,
    RuntimeOperationError,
    ServiceConnectionError,
    UnsupportedVersionError,
)
from ._semver import _VERSION

Compatibility = Literal["declared_compatible", "unverified"]


def _version(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 128:
        return None
    match = re.fullmatch(
        _VERSION + r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?",
        value,
    )
    if match is None:
        return None
    if match[4] and any(
        part.isdigit() and len(part) > 1 and part.startswith("0")
        for part in match[4].split(".")
    ):
        return None
    return value


def _reject_constant(value: str) -> None:
    raise HTTPFailure()


@dataclass(frozen=True)
class RuntimeConnection:
    _scope: _ConnectionScope = field(repr=False)
    _url: str = field(repr=False)
    appium_version: str | None
    compatibility: Compatibility
    report: DiagnosticReport
    ownership: Literal["external"] = field(default="external", init=False)

    @property
    def server_url(self) -> str:
        if not self._scope.active:
            raise InvalidStateError(
                "connection_closed", self.report.operation_id, self.report
            )
        return self._url


class _ConnectionScope(AbstractContextManager[RuntimeConnection]):
    def __init__(self, runtime: Runtime, control: OperationControl) -> None:
        self.runtime, self.control = runtime, control
        self.active = False
        self._entry = Lock()
        self.operation: _Operation | None = None
        self.lock: AbstractContextManager[None] | None = None

    def __enter__(self) -> RuntimeConnection:
        # A permanently acquired token makes consumption atomic across threads.
        if not self._entry.acquire(blocking=False):
            # Do not replace a live scope's report or release its lock.
            operation = self.operation or _Operation(self.control, None)
            raise operation.error(InvalidStateError, "connection_scope_consumed")
        operation = self.operation = _Operation(
            self.control, self.runtime._on_progress, phase="connecting"
        )
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
                body = get_status(url, operation.checkpoint, operation.deadline)
                operation.checkpoint()
                try:
                    value = json.loads(body, parse_constant=_reject_constant)
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
            version = _version(
                build.get("version") if isinstance(build, dict) else None
            )
            compatible = version is not None and int(version.split(".")[0]) == 3
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
