"""Synchronous static inspection, with no executable or network invocation."""

import os
import platform
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from appium_connect_agent.contracts import LocalSettings

from . import _coordination
from ._inspection import Finding, Package, Reader, constraint, path_evidence
from ._models import (
    DiagnosticCheck,
    DiagnosticReport,
    EnvironmentBusyError,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    ProgressEvent,
    RuntimeOperationError,
    Status,
)
from ._semver import satisfies


class _Operation:
    def __init__(
        self,
        control: OperationControl,
        observer: Callable[[ProgressEvent], None] | None,
    ) -> None:
        self.control = control
        self.observer = observer
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
                    ProgressEvent(self.operation_id, "diagnosing", check_id, reason)
                )
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
            for engine in ("node", "npm"):
                raw = package.engines.get(engine)
                if raw is None:
                    continue
                declared = constraint(raw)
                actual = npm.version if engine == "npm" and npm else None
                result = satisfies(actual, declared) if actual and declared else None
                results.append(result)
                evidence.append(
                    f"{label}.{engine}={declared or 'unsupported_constraint'}; observed={actual or 'unknown'}"
                )
        raw_peer = driver.peers.get("appium") if driver else None
        if raw_peer is not None:
            peer = constraint(raw_peer)
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


class Runtime:
    """Inspect a local macOS installation without executing its components."""

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

    def diagnose(self, *, control: OperationControl | None = None) -> DiagnosticReport:
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        operation = _Operation(control or OperationControl(), self._on_progress)
        operation.checkpoint()
        try:
            with _coordination.account_lock():
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
        except _coordination.Busy:
            raise operation.error(EnvironmentBusyError, "environment_busy") from None
        except (_coordination.CoordinationFailure, OSError, KeyError):
            raise operation.error(
                RuntimeOperationError, "coordination_unavailable"
            ) from None
