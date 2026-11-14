"""Synchronous Runtime entry points and static installation inspection."""

from __future__ import annotations

import os
import platform
import stat
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, get_ident
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from appium_connect_agent.contracts import LocalSettings

from . import _coordination
from ._inspection import (
    Finding,
    Package,
    Reader,
    mapping,
    normalized,
    package_value,
    path_evidence,
)
from ._models import (
    DiagnosticCheck,
    DiagnosticReport,
    DriverDoctorResult,
    DriverMaintenanceResult,
    EnvironmentBusyError,
    InstallationResult,
    InstallRequest,
    OfficialDriver,
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
    from ._maintenance import _MaintenanceRunner
    from ._managed import _ManagedScope


_XCODE_SELECT_LINK = Path("/var/db/xcode_select_link")
_APPLICATIONS_ROOT = Path("/Applications")


def _managed_root_state(operation: _Operation, root: Path) -> str:
    from ._installation import (
        _installation_record_state,
        _maintenance_record_state,
        _service_record_state,
        _StateFailure,
        _validate_root,
    )

    operation.checkpoint()
    try:
        if not _validate_root(root):
            return "missing"
    except _StateFailure:
        raise Finding("managed_root_conflict") from None
    records = root / "records"
    try:
        names = {entry.name for entry in records.iterdir()}
    except OSError:
        raise Finding("managed_recovery_required") from None
    if "installation.json" not in names or names - {
        "installation.json",
        "service.json",
        "maintenance.json",
    }:
        raise Finding("managed_recovery_required")
    try:
        if _installation_record_state(root) != "complete":
            raise Finding("managed_recovery_required")
        service = _service_record_state(root)
        if service == "active":
            raise Finding("managed_service_active")
        if service not in ("absent", "stopped"):
            raise Finding("managed_recovery_required")
        if _maintenance_record_state(root) not in ("absent", "complete", "failed"):
            raise Finding("managed_recovery_required")
    except _StateFailure:
        raise Finding("managed_recovery_required") from None
    operation.checkpoint()
    return "managed_root_ready"


def _managed_package(
    operation: _Operation,
    base: Path,
    root: Path,
    *,
    package_name: str,
    driver_name: str | None = None,
    automation_name: str | None = None,
) -> Package:
    try:
        base_info = base.lstat()
        info = root.lstat()
        resolved_base = base.resolve(strict=True)
        resolved_root = root.resolve(strict=True)
        metadata_info = (root / "package.json").lstat()
    except FileNotFoundError:
        raise Finding("missing") from None
    except (OSError, RuntimeError):
        raise Finding("path_unreadable") from None
    if (
        not stat.S_ISDIR(base_info.st_mode)
        or stat.S_ISLNK(base_info.st_mode)
        or base_info.st_uid != os.getuid()
        or base_info.st_mode & 0o022
        or not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o022
        or not resolved_root.is_relative_to(resolved_base)
        or not stat.S_ISREG(metadata_info.st_mode)
        or stat.S_ISLNK(metadata_info.st_mode)
        or metadata_info.st_uid != os.getuid()
        or metadata_info.st_mode & 0o022
    ):
        raise Finding("path_untrusted")
    data = operation.reader.metadata(root / "package.json")
    if data.get("name") != package_name:
        raise Finding("unrecognized_layout")
    if driver_name is not None:
        appium = mapping(data.get("appium"))
        if (
            appium.get("driverName") != driver_name
            or appium.get("automationName") != automation_name
        ):
            raise Finding("unrecognized_driver")
    package = package_value(resolved_root, data)
    if package.version is None:
        raise Finding("version_unknown")
    return package


def _lexical_absolute(link: Path, target: str) -> Path:
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = link.parent / candidate
    return Path(os.path.normpath(candidate))


def _valid_xcode_bundle(operation: _Operation, bundle: Path) -> bool:
    required = (
        (_APPLICATIONS_ROOT, stat.S_ISDIR),
        (bundle, stat.S_ISDIR),
        (bundle / "Contents", stat.S_ISDIR),
        (bundle / "Contents/Info.plist", stat.S_ISREG),
        (bundle / "Contents/Developer", stat.S_ISDIR),
        (bundle / "Contents/Developer/usr", stat.S_ISDIR),
        (bundle / "Contents/Developer/usr/bin", stat.S_ISDIR),
        (bundle / "Contents/Developer/usr/bin/xcodebuild", stat.S_ISREG),
    )
    try:
        for path, predicate in required:
            operation.checkpoint()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not predicate(info.st_mode):
                return False
        operation.reader.read(bundle / "Contents/Info.plist")
    except FileNotFoundError:
        return False
    return True


def _xcode_layout(operation: _Operation) -> None:
    try:
        link_info = _XCODE_SELECT_LINK.lstat()
    except FileNotFoundError:
        try:
            root_info = _APPLICATIONS_ROOT.lstat()
            if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
                operation.add("xcode_layout", "fail", "missing")
                return
            candidates = sorted(_APPLICATIONS_ROOT.glob("Xcode*.app"))[:16]
            if any(
                _valid_xcode_bundle(operation, candidate) for candidate in candidates
            ):
                operation.add("xcode_layout", "unknown", "active_developer_dir_unknown")
            else:
                operation.add("xcode_layout", "fail", "missing")
        except (OSError, Finding):
            operation.add("xcode_layout", "unknown", "path_unreadable")
        return
    except OSError:
        operation.add("xcode_layout", "unknown", "path_unreadable")
        return
    if not stat.S_ISLNK(link_info.st_mode):
        operation.add("xcode_layout", "fail", "invalid_developer_directory")
        return
    try:
        target = _lexical_absolute(_XCODE_SELECT_LINK, os.readlink(_XCODE_SELECT_LINK))
    except OSError:
        operation.add("xcode_layout", "unknown", "path_unreadable")
        return
    command_line_tools = Path("/Library/Developer/CommandLineTools")
    if target == command_line_tools or target.is_relative_to(command_line_tools):
        operation.add("xcode_layout", "fail", "command_line_tools_only")
        return
    try:
        relative = target.relative_to(_APPLICATIONS_ROOT)
    except ValueError:
        operation.add("xcode_layout", "fail", "invalid_developer_directory")
        return
    try:
        valid = (
            len(relative.parts) == 3
            and relative.parts[0].startswith("Xcode")
            and relative.parts[0].endswith(".app")
            and relative.parts[1:] == ("Contents", "Developer")
            and _valid_xcode_bundle(operation, _APPLICATIONS_ROOT / relative.parts[0])
        )
    except (OSError, Finding):
        operation.add("xcode_layout", "unknown", "path_unreadable")
        return
    if not valid:
        operation.add("xcode_layout", "fail", "invalid_developer_directory")
        return
    operation.add(
        "xcode_layout",
        "pass",
        "xcode_developer_dir_observed",
        (path_evidence(target),),
    )


class _Operation:
    def __init__(
        self,
        control: OperationControl,
        observer: Callable[[ProgressEvent], None] | None,
        phase: str = "diagnosing",
        target_driver: Literal["uiautomator2", "mac2"] = "uiautomator2",
    ) -> None:
        self.control = control
        self.observer = observer
        self.phase = phase
        self.target_driver = target_driver
        self.operation_id = uuid4().hex
        self.observed_at = datetime.now(UTC)
        self.deadline = time.monotonic() + control.timeout_seconds
        self.checks: list[DiagnosticCheck] = []
        self.observer_errors: list[str] = []
        self.reader = Reader(self.checkpoint)

    def report(self) -> DiagnosticReport:
        if self.target_driver == "mac2":
            return DiagnosticReport(
                self.operation_id,
                self.observed_at,
                host="macOS",
                target="macOS",
                driver="Mac2",
                checks=tuple(self.checks),
                observer_errors=tuple(self.observer_errors),
            )
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

    def driver(
        self,
        settings: LocalSettings,
        target_driver: Literal["uiautomator2", "mac2"] = "uiautomator2",
    ) -> Package | None:
        explicit = settings.appium_home is not None
        home = settings.appium_home or _coordination._account_home() / ".appium"
        source = "explicit" if explicit else "conventional_candidate"
        package_name = (
            "appium-mac2-driver"
            if target_driver == "mac2"
            else "appium-uiautomator2-driver"
        )
        driver_name = "mac2" if target_driver == "mac2" else "uiautomator2"
        automation_name = "Mac2" if target_driver == "mac2" else "UiAutomator2"
        try:
            package = self.reader.driver(
                home,
                package_name=package_name,
                driver_name=driver_name,
                automation_name=automation_name,
            )
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
                    f"driverName={driver_name}; automationName={automation_name}",
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

    def managed_components(self, root: Path) -> tuple[Package | None, Package | None]:
        try:
            state = _managed_root_state(self, root)
            self.add(
                "managed_root",
                "pass" if state == "managed_root_ready" else "fail",
                state,
                ("source=managed_root",),
            )
        except Finding as finding:
            self.add(
                "managed_root", "unknown", finding.reason, ("source=managed_root",)
            )
        packages: list[Package | None] = []
        specs = (
            (
                "appium_installation",
                root / "appium",
                root / "appium/node_modules/appium",
                "appium",
                None,
                None,
            ),
            (
                "driver_installation",
                root / "driver-home",
                root / "driver-home/node_modules/appium-mac2-driver",
                "appium-mac2-driver",
                "mac2",
                "Mac2",
            ),
        )
        for (
            check_id,
            base,
            package_root,
            package_name,
            driver_name,
            automation_name,
        ) in specs:
            try:
                package = _managed_package(
                    self,
                    base,
                    package_root,
                    package_name=package_name,
                    driver_name=driver_name,
                    automation_name=automation_name,
                )
                evidence = [
                    "source=managed_root",
                    path_evidence(package.root),
                    f"version={package.version}",
                ]
                if driver_name is not None:
                    evidence.append("driverName=mac2; automationName=Mac2")
                self.add(check_id, "pass", "metadata_observed", tuple(evidence))
                packages.append(package)
            except Finding as finding:
                self.add(
                    check_id,
                    "fail" if finding.reason == "missing" else "unknown",
                    finding.reason,
                    ("source=managed_root",),
                )
                packages.append(None)
        return packages[0], packages[1]

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
        self,
        appium: Package | None,
        driver: Package | None,
        npm: Package | None,
        *,
        target_driver: Literal["uiautomator2", "mac2"] = "uiautomator2",
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
        target = "macOS" if target_driver == "mac2" else "Android"
        self.add(
            "qualified_support",
            "unknown",
            "not_qualified",
            (f"No {target} Session qualification evidence is bundled.",),
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
    """Diagnose, connect to, install, or own one local Appium runtime."""

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
        self._installation_cleanup: _Installer | _MaintenanceRunner | None = None
        self._managed_guard = Lock()
        with self._managed_guard:
            self._managed_scope: _ManagedScope | None = None
            self._managed_cleanup: _ManagedScope | None = None

    def _set_managed_cleanup(self, scope: _ManagedScope | None) -> None:
        with self._managed_guard:
            self._managed_cleanup = scope

    def _snapshot_managed_state(
        self,
    ) -> tuple[_ManagedScope | None, _ManagedScope | None]:
        with self._managed_guard:
            return self._managed_scope, self._managed_cleanup

    def _register_managed_scope(
        self, scope: _ManagedScope, operation: _Operation
    ) -> None:
        with self._managed_guard:
            if self._managed_scope is not None:
                raise operation.error(EnvironmentBusyError, "environment_busy")
            self._managed_scope = scope

    def _clear_managed_scope(self, scope: _ManagedScope) -> None:
        with self._managed_guard:
            if self._managed_scope is scope:
                self._managed_scope = None

    def _owns_managed_scope(self, scope: _ManagedScope) -> bool:
        with self._managed_guard:
            return self._managed_scope is scope

    @property
    def managed_cleanup_pending(self) -> bool:
        """Whether this instance retains an owned service needing cleanup."""
        _, cleanup = self._snapshot_managed_state()
        return cleanup is not None

    def connect(
        self, *, control: OperationControl | None = None
    ) -> AbstractContextManager[RuntimeConnection]:
        from ._connection import _ConnectionScope

        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        return _ConnectionScope(self, control or OperationControl())

    def start_managed(
        self,
        *,
        host: Literal["127.0.0.1", "::1"],
        port: int,
        base_path: str = "",
        control: OperationControl | None = None,
    ) -> AbstractContextManager[RuntimeConnection]:
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        from ._managed import _ManagedScope

        return _ManagedScope(
            self,
            host,
            port,
            base_path,
            control or OperationControl(timeout_seconds=60.0),
        )

    def cleanup_managed(self, *, control: OperationControl | None = None) -> None:
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        from ._managed import cleanup_managed

        cleanup_managed(self, control or OperationControl(timeout_seconds=30.0))

    def stop_managed(
        self,
        connection: RuntimeConnection,
        *,
        control: OperationControl | None = None,
    ) -> None:
        from ._connection import RuntimeConnection as RuntimeConnectionType

        if not isinstance(connection, RuntimeConnectionType):
            raise ValueError("connection must be RuntimeConnection")
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        from ._managed import stop_managed

        stop_managed(
            self, connection, control or OperationControl(timeout_seconds=30.0)
        )

    def restart_managed(
        self,
        connection: RuntimeConnection,
        *,
        control: OperationControl | None = None,
    ) -> RuntimeConnection:
        from ._connection import RuntimeConnection as RuntimeConnectionType

        if not isinstance(connection, RuntimeConnectionType):
            raise ValueError("connection must be RuntimeConnection")
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        from ._managed import restart_managed

        return restart_managed(
            self, connection, control or OperationControl(timeout_seconds=90.0)
        )

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

    def ensure_managed_driver(
        self,
        driver: OfficialDriver,
        *,
        control: OperationControl | None = None,
    ) -> DriverMaintenanceResult:
        from ._maintenance import ensure_managed_driver, official_driver

        selected = official_driver(driver)
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        return ensure_managed_driver(
            self,
            selected,
            control or OperationControl(timeout_seconds=600.0),
        )

    def run_driver_doctor(
        self,
        driver: OfficialDriver,
        *,
        control: OperationControl | None = None,
    ) -> DriverDoctorResult:
        from ._maintenance import official_driver, run_driver_doctor

        selected = official_driver(driver)
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        return run_driver_doctor(
            self,
            selected,
            control or OperationControl(timeout_seconds=600.0),
        )

    def cleanup_installation(
        self, *, control: OperationControl | None = None
    ) -> InstallationResult | DriverMaintenanceResult | DriverDoctorResult:
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        selected = control or OperationControl(timeout_seconds=30.0)
        from ._maintenance import cleanup_maintenance

        maintenance = cleanup_maintenance(self, selected)
        if maintenance is not None:
            return maintenance
        from ._installation import cleanup_installation

        return cleanup_installation(self, selected)

    def diagnose(
        self,
        *,
        target_driver: OfficialDriver = "uiautomator2",
        control: OperationControl | None = None,
    ) -> DiagnosticReport:
        if type(target_driver) is not str:
            raise ValueError("target_driver must be 'uiautomator2' or 'mac2'")
        if target_driver == "xcuitest":
            raise ValueError("target_driver 'xcuitest' diagnostics are not yet enabled")
        if target_driver not in ("uiautomator2", "mac2"):
            raise ValueError("target_driver must be 'uiautomator2' or 'mac2'")
        if control is not None and not isinstance(control, OperationControl):
            raise ValueError("control must be OperationControl or None")
        selected: Literal["uiautomator2", "mac2"] = target_driver
        operation = _Operation(
            control or OperationControl(), self._on_progress, target_driver=selected
        )
        operation.checkpoint()
        managed_scope, _ = self._snapshot_managed_state()
        if (
            self._diagnosing
            or managed_scope is not None
            or self._active_thread not in (None, get_ident())
        ):
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
                if selected == "uiautomator2":
                    appium = operation.tool(
                        "appium", self._settings.appium_executable, paths
                    )
                    node = operation.tool("node", self._settings.node_executable, paths)
                    del node
                    npm = operation.tool("npm", self._settings.npm_executable, paths)
                    driver = operation.driver(self._settings)
                    operation.layouts(self._settings)
                    operation.compatibility(appium, driver, npm)
                else:
                    root = _coordination._account_home() / ".appium-connect-agent"
                    root_present = False
                    try:
                        root.lstat()
                        root_present = True
                    except FileNotFoundError:
                        pass
                    managed = self._settings.server_mode == "managed" or (
                        self._settings.appium_executable is None
                        and self._settings.appium_home is None
                        and root_present
                    )
                    if managed:
                        appium, driver = operation.managed_components(root)
                    else:
                        appium = operation.tool(
                            "appium", self._settings.appium_executable, paths
                        )
                        driver = operation.driver(self._settings, "mac2")
                    node = operation.tool("node", self._settings.node_executable, paths)
                    del node
                    npm = operation.tool("npm", self._settings.npm_executable, paths)
                    _xcode_layout(operation)
                    operation.add(
                        "java_layout",
                        "not_applicable",
                        "not_applicable_for_driver",
                    )
                    operation.add(
                        "android_sdk_layout",
                        "not_applicable",
                        "not_applicable_for_driver",
                    )
                    operation.compatibility(appium, driver, npm, target_driver="mac2")
                operation.add("service", "unknown", "not_checked")
                operation.add("device", "unknown", "not_checked")
                return operation.report()
        finally:
            self._diagnosing = False
