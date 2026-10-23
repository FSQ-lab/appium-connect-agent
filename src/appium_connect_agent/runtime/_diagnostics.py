"""Synchronous Runtime entry points and static installation inspection."""

from __future__ import annotations

import os
import platform
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import get_ident
from typing import TYPE_CHECKING
from uuid import uuid4

from appium_connect_agent.contracts import LocalSettings

from . import _coordination
from ._inspection import (
    Finding,
    Package,
    Reader,
    normalized,
    path_evidence,
)
from ._models import (
    DiagnosticCheck,
    DiagnosticReport,
    EnvironmentBusyError,
    InstallationResult,
    InstallRequest,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    ProgressEvent,
    RuntimeOperationError,
    Status,
)
from ._semver import constraint, satisfies

if TYPE_CHECKING:
    from ._connection import RuntimeConnection
    from ._installation import _Installer


class _Operation:
    def __init__(
        self,
        control: OperationControl,
        observer: Callable[[ProgressEvent], None] | None,
        phase: str = "diagnosing",
    ) -> None:
        self.control = control
        self.observer = observer
        self.phase = phase
        self.operation_id = uuid4().hex
        self.observed_at = datetime.now(UTC)
        self.deadline = time.monotonic() + control.timeout_seconds
        self.checks: list[DiagnosticCheck] = []
        self.observer_errors: list[str] = []
        self.reader = Reader(self.checkpoint)

    def report(self) -> DiagnosticReport:
        return DiagnosticReport(
            self.operation_id,
            self.observed_at,
            checks=tuple(self.checks),
            observer_errors=tuple(self.observer_errors),
        )

    def error(
        self, kind: type[RuntimeOperationError], code: str
    ) -> RuntimeOperationError:
        return kind(code, self.operation_id, self.report())

    def checkpoint(self) -> None:
        if self.control.cancellation is not None and self.control.cancellation.is_set():
            raise self.error(OperationCancelledError, "operation_cancelled")
        if time.monotonic() >= self.deadline:
            raise self.error(OperationTimeoutError, "operation_timeout")

    def add(
        self,
        check_id: str,
        status: Status,
        reason: str,
        evidence: tuple[str, ...] = (),
        remediation: str | None = None,
    ) -> None:
        self.checkpoint()
        if len(self.checks) >= 32:
            raise self.error(RuntimeOperationError, "check_limit")
        trimmed = tuple(
            text if len(text) <= 512 else text[:498] + "...[truncated]"
            for text in evidence[:8]
        )
        if len(evidence) > 8:
            trimmed = (*trimmed[:7], "[evidence truncated]")
        self.checks.append(
            DiagnosticCheck(check_id, status, reason, trimmed, remediation)
        )
        if self.observer is not None:
            try:
                self.observer(
                    ProgressEvent(self.operation_id, self.phase, check_id, reason)
                )
            except OperationCancelledError:
                raise
            except Exception:
                self.observer_errors.append("progress_callback_failed")
                self.observer = None
        self.checkpoint()

    def tool(
        self, name: str, explicit: Path | None, paths: tuple[str, ...]
    ) -> Package | None:
        check_id = "appium_installation" if name == "appium" else f"{name}_candidate"
        try:
            executable, evidence = self.reader.candidate(explicit, name, paths)
            if name == "node":
                self.add(
                    check_id,
                    "pass",
                    "candidate_observed",
                    (
                        *evidence,
                        path_evidence(executable),
                        "actual_version=unknown; not executed",
                    ),
                )
                return None
            package = self.reader.package(executable, name)
            self.add(
                check_id,
                "pass" if package.version else "unknown",
                "metadata_observed" if package.version else "version_unknown",
                (
                    *evidence,
                    path_evidence(package.root),
                    f"version={package.version or 'unknown'}",
                ),
            )
            return package
        except Finding as finding:
            self.add(
                check_id,
                "fail" if finding.reason == "missing" else "unknown",
                finding.reason,
                remediation="Supply an absolute path to an identifiable installation.",
            )
            return None

    def driver(self, settings: LocalSettings) -> Package | None:
        explicit = settings.appium_home is not None
        home = settings.appium_home or _coordination._account_home() / ".appium"
        source = "explicit" if explicit else "conventional_candidate"
        try:
            package = self.reader.driver(home)
            self.add(
                "driver_installation",
                "pass" if explicit and package.version else "unknown",
                "metadata_observed"
                if explicit and package.version
                else ("version_unknown" if explicit else "home_association_unknown"),
                (
                    f"source={source}",
                    path_evidence(package.root),
                    f"version={package.version or 'unknown'}",
                    "driverName=uiautomator2; automationName=UiAutomator2",
                ),
            )
            return package if explicit else None
        except Finding as finding:
            self.add(
                "driver_installation",
                "fail" if explicit and finding.reason == "missing" else "unknown",
                finding.reason if explicit else "home_association_unknown",
                (f"source={source}",),
            )
            return None

    def layouts(self, settings: LocalSettings) -> None:
        for check_id, root, files in (
            ("java_layout", settings.java_home, ("release", "bin/java")),
            (
                "android_sdk_layout",
                settings.android_sdk_root,
                ("platform-tools/adb", "platform-tools/source.properties"),
            ),
        ):
            if root is None:
                self.add(check_id, "unknown", "not_specified")
                continue
            try:
                root = normalized(root)
                for relative in files:
                    self.reader.ordinary(root / relative)
                # Only layout is claimed: do not return unfiltered release/properties.
                self.reader.read(root / files[0 if check_id == "java_layout" else 1])
                self.add(
                    check_id,
                    "pass",
                    "layout_observed",
                    (path_evidence(root), "execution=not_checked"),
                )
            except Finding as finding:
                self.add(
                    check_id,
                    "fail" if finding.reason == "missing" else "unknown",
                    finding.reason,
                )

    def compatibility(
        self, appium: Package | None, driver: Package | None, npm: Package | None
    ) -> None:
        results: list[bool | None] = []
        evidence: list[str] = []
        for label, package in (("appium", appium), ("driver", driver)):
            if package is None:
                results.append(None)
                continue
            if package.version is None:
                results.append(None)
            if package.engines is None or package.peers is None:
                results.append(None)
            engines = package.engines or {}
            for engine in ("node", "npm"):
                if engine not in engines:
                    continue
                declared = constraint(engines[engine])
                actual = npm.version if engine == "npm" and npm else None
                result = satisfies(actual, declared) if actual and declared else None
                results.append(result)
                evidence.append(
                    f"{label}.{engine}={declared or 'unsupported_constraint'}; observed={actual or 'unknown'}"
                )
        peers = driver.peers if driver else None
        if peers is not None and "appium" in peers:
            peer = constraint(peers["appium"])
            actual = appium.version if appium else None
            results.append(satisfies(actual, peer) if actual and peer else None)
            evidence.append(
                f"driver.appium={peer or 'unsupported_constraint'}; observed={actual or 'unknown'}"
            )
        if False in results:
            status: Status = "fail"
            reason = "declared_incompatible"
        elif not results or None in results:
            status, reason = "unknown", "compatibility_unknown"
        else:
            status, reason = "pass", "declarations_match"
        self.add("declared_compatibility", status, reason, tuple(evidence))
        self.add(
            "qualified_support",
            "unknown",
            "not_qualified",
            ("No Android Session qualification evidence is bundled.",),
        )


@contextmanager
def _diagnostic_lock(operation: _Operation, reuse: bool) -> Iterator[None]:
    if reuse:
        yield
        return
    lock = _coordination.account_lock()
    try:
        lock.__enter__()
    except _coordination.Busy:
        raise operation.error(EnvironmentBusyError, "environment_busy") from None
    except (_coordination.CoordinationFailure, OSError, KeyError):
        raise operation.error(
            RuntimeOperationError, "coordination_unavailable"
        ) from None
    try:
        yield
    except BaseException as original:
        try:
            lock.__exit__(type(original), original, original.__traceback__)
        except BaseException as cleanup:
            if cleanup is not original:
                original.__dict__["runtime_cleanup_error"] = cleanup
        raise
    else:
        try:
            lock.__exit__(None, None, None)
        except (_coordination.CoordinationFailure, OSError, KeyError):
            raise operation.error(
                RuntimeOperationError, "coordination_unavailable"
            ) from None


class Runtime:
    """Diagnose local metadata or reuse an explicitly configured external service."""

    def __init__(
        self,
        settings: LocalSettings,
        *,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> None:
        if not isinstance(settings, LocalSettings):
            raise ValueError("settings must be LocalSettings")
        if on_progress is not None and not callable(on_progress):
            raise ValueError("on_progress must be callable or None")
        self._settings = settings
        self._on_progress = on_progress
        self._active_thread: int | None = None
        self._diagnosing = False
        self._installing = False
        self._installation_cleanup: _Installer | None = None

    def connect(
        self, *, control: OperationControl | None = None
    ) -> AbstractContextManager[RuntimeConnection]:
        from ._connection import _ConnectionScope

        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        return _ConnectionScope(self, control or OperationControl())

    def install(
        self,
        request: InstallRequest,
        *,
        control: OperationControl | None = None,
    ) -> InstallationResult:
        if not isinstance(request, InstallRequest):
            raise ValueError("request must be InstallRequest")
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        if (
            self._settings.appium_executable is not None
            or self._settings.appium_home is not None
        ):
            raise ValueError(
                "managed installation cannot use appium_executable or appium_home"
            )
        from ._installation import install

        return install(
            self, request, control or OperationControl(timeout_seconds=600.0)
        )

    def cleanup_installation(
        self, *, control: OperationControl | None = None
    ) -> InstallationResult:
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        from ._installation import cleanup_installation

        return cleanup_installation(
            self, control or OperationControl(timeout_seconds=30.0)
        )

    def diagnose(self, *, control: OperationControl | None = None) -> DiagnosticReport:
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        operation = _Operation(control or OperationControl(), self._on_progress)
        operation.checkpoint()
        if self._diagnosing or self._active_thread not in (None, get_ident()):
            raise operation.error(EnvironmentBusyError, "environment_busy")
        self._diagnosing = True
        try:
            with _diagnostic_lock(operation, self._active_thread == get_ident()):
                operation.checkpoint()
                system = platform.system()
                operation.add(
                    "host",
                    "pass" if system == "Darwin" else "fail",
                    "host_observed" if system == "Darwin" else "unsupported_host",
                    (
                        f"system={'Darwin' if system == 'Darwin' else 'unsupported'}",
                        f"architecture={'arm64' if platform.machine() == 'arm64' else 'other'}",
                    ),
                )
                if system != "Darwin":
                    return operation.report()
                paths = tuple(os.environ.get("PATH", "").split(os.pathsep, 64))
                appium = operation.tool(
                    "appium", self._settings.appium_executable, paths
                )
                node = operation.tool("node", self._settings.node_executable, paths)
                del node
                npm = operation.tool("npm", self._settings.npm_executable, paths)
                driver = operation.driver(self._settings)
                operation.layouts(self._settings)
                operation.compatibility(appium, driver, npm)
                operation.add("service", "unknown", "not_checked")
                operation.add("device", "unknown", "not_checked")
                return operation.report()
        finally:
            self._diagnosing = False
