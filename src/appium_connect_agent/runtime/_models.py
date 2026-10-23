"""Immutable diagnostics and the operation error boundary."""

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Literal

from appium_connect_agent.contracts import LocalSettings

Status = Literal["pass", "fail", "unknown", "not_applicable"]
InstallationStatus = Literal["missing", "verified", "conflict", "damaged", "unknown"]
InstallationOutcome = Literal[
    "installed",
    "reused",
    "failed",
    "cancelled",
    "timed_out",
    "cleanup_pending",
    "recovery_required",
    "cleanup_completed",
]


@dataclass(frozen=True)
class InstallationCombination:
    combination_id: str
    host: str
    target: str
    driver: str
    appium_version: str
    driver_version: str
    node_range: str
    npm_range: str
    is_default: bool
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class InstallRequest:
    combination_id: str | None = None

    def __post_init__(self) -> None:
        value = self.combination_id
        if value is not None and (
            not isinstance(value, str) or value != "macos-android-uiautomator2"
        ):
            raise ValueError("combination_id must identify a supported combination")


@dataclass(frozen=True)
class InstallationComponent:
    name: str
    requested_version: str
    observed_version: str | None
    status: InstallationStatus
    reason_code: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstallationResult:
    operation_id: str
    observed_at: datetime
    combination_id: str
    root: Path
    node_version: str | None
    npm_version: str | None
    before: tuple[InstallationComponent, ...]
    after: tuple[InstallationComponent, ...]
    outcome: InstallationOutcome
    changed: bool
    warnings: tuple[str, ...]
    observer_errors: tuple[str, ...]
    settings: LocalSettings | None


@dataclass(frozen=True)
class DiagnosticCheck:
    check_id: str
    status: Status
    reason_code: str
    evidence: tuple[str, ...] = ()
    remediation: str | None = None


@dataclass(frozen=True)
class DiagnosticReport:
    operation_id: str
    observed_at: datetime
    host: str = "macOS"
    target: str = "Android"
    driver: str = "UiAutomator2"
    checks: tuple[DiagnosticCheck, ...] = ()
    observer_errors: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class OperationControl:
    timeout_seconds: float = 10.0
    cancellation: Event | None = None

    def __post_init__(self) -> None:
        timeout = self.timeout_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        if self.cancellation is not None and not isinstance(self.cancellation, Event):
            raise ValueError("cancellation must be a threading.Event or None")


@dataclass(frozen=True)
class ProgressEvent:
    operation_id: str
    phase: str
    check_id: str | None
    message: str


class RuntimeOperationError(Exception):
    """Execution failure; diagnostic findings themselves remain report checks."""

    def __init__(
        self,
        code: str,
        operation_id: str,
        partial_report: DiagnosticReport,
        installation_result: InstallationResult | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.operation_id = operation_id
        self.partial_report = partial_report
        self.installation_result = installation_result
        self.runtime_http_cleanup_error: BaseException | None = None
        self.runtime_installation_cleanup_error: BaseException | None = None


class EnvironmentBusyError(RuntimeOperationError):
    """Another operation holds this account's coordination resource."""


class OperationTimeoutError(RuntimeOperationError):
    """The total operation budget expired at a checkpoint."""


class OperationCancelledError(RuntimeOperationError):
    """The caller requested cancellation."""


class ServiceConnectionError(RuntimeOperationError):
    """The explicitly configured service could not be reused."""


class UnsupportedVersionError(RuntimeOperationError):
    """The observed service violates the confirmed major-version policy."""


class InvalidStateError(RuntimeOperationError):
    """A consumed scope or closed connection view was used."""


class InstallationError(RuntimeOperationError):
    """A managed installation could not safely complete."""
