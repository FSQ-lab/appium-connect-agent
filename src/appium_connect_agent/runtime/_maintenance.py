"""Allowlisted managed driver installation and official Driver Doctor execution."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from contextlib import AbstractContextManager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NoReturn, cast

from . import _coordination
from ._diagnostics import _Operation
from ._installation import (
    _COMBINATION,
    _METADATA_LIMIT,
    _NPM_EFFECTIVE_POLICY,
    _atomic_json,
    _base_environment,
    _cleanup_checkpoint,
    _installation_record_state,
    _json_file,
    _managed_appium,
    _paired_bin,
    _ProcessHandle,
    _record_namespace_state,
    _StateFailure,
    _Tool,
    _tool,
    _validate_root,
)
from ._models import (
    DiagnosticReport,
    DriverComponent,
    DriverDoctorError,
    DriverDoctorOutcome,
    DriverDoctorResult,
    DriverMaintenanceError,
    DriverMaintenanceOutcome,
    DriverMaintenanceResult,
    EnvironmentBusyError,
    InstallationResult,
    OfficialDriver,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    ProgressEvent,
    RuntimeOperationError,
)
from ._semver import satisfies, version

if TYPE_CHECKING:
    from ._diagnostics import Runtime

_MAINTENANCE_RECORD = "maintenance.json"
_STRUCTURED_LIMIT = 1024 * 1024
_CHECK_COUNT_LIMIT = 1_000_000
_PACKAGES: dict[OfficialDriver, str] = {
    "uiautomator2": "appium-uiautomator2-driver",
    "xcuitest": "appium-xcuitest-driver",
    "mac2": "appium-mac2-driver",
}
_MaintenanceKind = Literal["driver_install", "driver_doctor"]
_MaintenanceResult = DriverMaintenanceResult | DriverDoctorResult
_CleanupResult = InstallationResult | _MaintenanceResult


def official_driver(value: object) -> OfficialDriver:
    """Validate the closed public driver name set without performing I/O."""

    if not isinstance(value, str) or value not in _PACKAGES:
        raise ValueError("driver must be uiautomator2, xcuitest, or mac2")
    return value


def _driver_component(
    driver: OfficialDriver,
    observed: str | None,
    status: Literal["missing", "verified", "damaged", "unknown"],
    reason: str,
    evidence: tuple[str, ...] = (),
) -> DriverComponent:
    bounded = tuple(
        item if len(item) <= 512 else item[:498] + "...[truncated]"
        for item in evidence[:8]
    )
    return DriverComponent(driver, observed, status, reason, bounded)


class _MaintenanceOperation(_Operation):
    def __init__(
        self,
        runtime: Runtime,
        control: OperationControl,
        driver: OfficialDriver,
        kind: _MaintenanceKind,
        *,
        phase: str | None = None,
    ) -> None:
        super().__init__(
            control,
            runtime._on_progress,
            phase
            or ("ensuring_driver" if kind == "driver_install" else "running_doctor"),
        )
        self.runtime = runtime
        self.root = _coordination._account_home() / ".appium-connect-agent"
        self.driver_name = driver
        self.kind = kind
        self.appium_version: str | None = None
        missing = _driver_component(driver, None, "missing", "not_observed")
        self.before = missing
        self.after = missing
        self.changed = False
        self.doctor_started = False
        self.executed_check_count: int | None = None

    def report(self) -> DiagnosticReport:
        target = {
            "uiautomator2": "Android",
            "xcuitest": "iOS",
            "mac2": "macOS",
        }[self.driver_name]
        return DiagnosticReport(
            self.operation_id,
            self.observed_at,
            target=target,
            driver=self.driver_name,
            checks=tuple(self.checks),
            observer_errors=tuple(self.observer_errors),
        )

    def driver_result(
        self, outcome: DriverMaintenanceOutcome
    ) -> DriverMaintenanceResult:
        assert self.appium_version is not None
        return DriverMaintenanceResult(
            self.operation_id,
            self.observed_at,
            self.driver_name,
            self.appium_version,
            self.before,
            self.after,
            outcome,
            self.changed,
            (),
            tuple(self.observer_errors[:8]),
        )

    def doctor_result(self, outcome: DriverDoctorOutcome) -> DriverDoctorResult:
        assert self.appium_version is not None
        return DriverDoctorResult(
            self.operation_id,
            self.observed_at,
            self.driver_name,
            self.appium_version,
            outcome,
            self.executed_check_count if outcome == "accepted" else None,
            self.doctor_started,
            (),
            tuple(self.observer_errors[:8]),
        )

    def result(
        self,
        outcome: DriverMaintenanceOutcome | DriverDoctorOutcome,
    ) -> _MaintenanceResult:
        if self.kind == "driver_install":
            return self.driver_result(cast(DriverMaintenanceOutcome, outcome))
        return self.doctor_result(cast(DriverDoctorOutcome, outcome))

    def error(
        self,
        kind: type[RuntimeOperationError],
        code: str,
        outcome: DriverMaintenanceOutcome | DriverDoctorOutcome = "failed",
    ) -> RuntimeOperationError:
        error = kind(code, self.operation_id, self.report())
        if self.appium_version is not None:
            if isinstance(error, OperationCancelledError):
                outcome = "cancelled"
            elif isinstance(error, OperationTimeoutError):
                outcome = "timed_out"
            if self.kind == "driver_install":
                error.driver_result = self.driver_result(
                    cast(DriverMaintenanceOutcome, outcome)
                )
            else:
                error.doctor_result = self.doctor_result(
                    cast(DriverDoctorOutcome, outcome)
                )
        return error

    def progress(self, check_id: str, message: str) -> None:
        self.checkpoint()
        if self.observer is not None:
            try:
                self.observer(
                    ProgressEvent(self.operation_id, self.phase, check_id, message)
                )
            except OperationCancelledError:
                raise
            except Exception:
                if not self.observer_errors:
                    self.observer_errors.append("progress_callback_failed")
                self.observer = None
        self.checkpoint()


class _MaintenanceRunner:
    """One locked maintenance operation and any retained owned process handle."""

    def __init__(self, operation: _MaintenanceOperation) -> None:
        self.operation = operation
        self.runtime = operation.runtime
        self.lock: AbstractContextManager[None] | None = None
        self.handle: _ProcessHandle | None = None
        self.intent_written = False
        self.node: _Tool | None = None
        self.npm: _Tool | None = None
        self.bin_dir: Path | None = None
        self.environment: dict[str, str] | None = None
        self.appium_entry: Path | None = None
        self.static_appium_version: str | None = None

    @property
    def kind(self) -> _MaintenanceKind:
        return self.operation.kind

    def _error_type(self) -> type[RuntimeOperationError]:
        return (
            DriverMaintenanceError
            if self.kind == "driver_install"
            else DriverDoctorError
        )

    def _error(
        self,
        code: str,
        outcome: DriverMaintenanceOutcome | DriverDoctorOutcome = "failed",
    ) -> RuntimeOperationError:
        return self.operation.error(self._error_type(), code, outcome)

    def _acquire(self) -> None:
        lock = _coordination.account_lock()
        try:
            lock.__enter__()
        except _coordination.Busy:
            raise self.operation.error(
                EnvironmentBusyError, "environment_busy"
            ) from None
        except (_coordination.CoordinationFailure, OSError, KeyError):
            raise self.operation.error(
                RuntimeOperationError, "coordination_unavailable"
            ) from None
        self.lock = lock

    def _release(self, original: BaseException | None) -> None:
        if self.lock is None:
            return
        lock, self.lock = self.lock, None
        try:
            lock.__exit__(
                type(original) if original is not None else None,
                original,
                original.__traceback__ if original is not None else None,
            )
        except BaseException as cleanup:
            if original is not None:
                original.__dict__["runtime_cleanup_error"] = cleanup
            else:
                raise self.operation.error(
                    RuntimeOperationError, "coordination_unavailable"
                ) from None

    def _spawn(
        self,
        label: str,
        command: list[str],
        environment: dict[str, str],
        *,
        structured: bool = False,
        writer: bool = False,
    ) -> tuple[int, bytearray, bool]:
        self.operation.progress(label, "command_starting")
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.operation.root,
                env=environment,
                shell=False,
                start_new_session=True,
            )
        except OSError:
            code = (
                "tool_not_executable"
                if not writer
                else (
                    "driver_install_failed"
                    if self.kind == "driver_install"
                    else "driver_doctor_failed"
                )
            )
            raise self._error(code) from None
        if writer:
            if self.kind == "driver_install":
                self.operation.changed = True
            else:
                self.operation.doctor_started = True
        self.handle = _ProcessHandle(
            process, stdout_limit=_STRUCTURED_LIMIT if structured else 64 * 1024
        )
        self.operation.checkpoint()
        result = self.handle.wait(self.operation.checkpoint, self.operation.deadline)
        self.handle.close()
        self.handle = None
        self.operation.progress(label, "command_completed")
        return result.returncode, result.stdout, result.stdout_truncated

    def _cleanup_spawn(
        self,
        command: list[str],
        environment: dict[str, str],
        deadline: float,
    ) -> tuple[int, bytearray, bool]:
        def check() -> None:
            _cleanup_checkpoint(deadline)

        check()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.operation.root,
                env=environment,
                shell=False,
                start_new_session=True,
            )
        except OSError:
            raise _StateFailure("installation_state_unknown") from None
        self.handle = _ProcessHandle(process, stdout_limit=_STRUCTURED_LIMIT)
        try:
            result = self.handle.wait(check, deadline)
        except BaseException:
            if self.handle.cleanup(deadline, check):
                self.handle = None
            raise
        self.handle.close()
        self.handle = None
        return result.returncode, result.stdout, result.stdout_truncated

    def _environment(self) -> dict[str, str]:
        assert self.bin_dir is not None
        environment = _base_environment()
        environment.update(
            PATH=f"{self.bin_dir}:/usr/bin:/bin",
            APPIUM_HOME=str(self.operation.root / "driver-home"),
            APPIUM_TMP_DIR=str(self.operation.root / "tmp"),
            TMPDIR=str(self.operation.root / "tmp"),
            npm_config_cache=str(self.operation.root / "cache"),
        )
        settings = self.operation.runtime._settings
        if settings.java_home is not None:
            environment["JAVA_HOME"] = str(settings.java_home)
        if settings.android_sdk_root is not None:
            environment["ANDROID_HOME"] = str(settings.android_sdk_root)
            environment["ANDROID_SDK_ROOT"] = str(settings.android_sdk_root)
        return environment

    def _preflight(self) -> None:
        paths = tuple(os.environ.get("PATH", "").split(os.pathsep, 64))
        settings = self.runtime._settings
        try:
            self.node = _tool(settings.node_executable, "node", paths)
            self.npm = _tool(settings.npm_executable, "npm", paths)
            self.bin_dir = _paired_bin(self.node, self.npm, paths)
        except _StateFailure as failure:
            raise self._error(failure.code) from None
        base = _base_environment()
        base["PATH"] = f"{self.bin_dir}:/usr/bin:/bin"
        node_result = self._spawn(
            "node_version", [str(self.node.path), "--version"], base
        )
        npm_result = self._spawn(
            "npm_version", [str(self.node.path), str(self.npm.path), "--version"], base
        )
        if any((node_result[0], npm_result[0], node_result[2], npm_result[2])):
            raise self._error("tool_version_invalid")
        try:
            raw_node = node_result[1].decode("ascii").strip()
            raw_npm = npm_result[1].decode("ascii").strip()
        except UnicodeDecodeError:
            raise self._error("tool_version_invalid") from None
        node_text = raw_node[1:] if raw_node.startswith("v") else raw_node
        if version(node_text) is None or version(raw_npm) is None:
            raise self._error("tool_version_invalid")
        node_match = satisfies(node_text, _COMBINATION.node_range)
        npm_match = satisfies(raw_npm, _COMBINATION.npm_range)
        if node_match is None or npm_match is None:
            raise self._error("tool_version_invalid")
        if not node_match or not npm_match:
            raise self._error("tool_version_incompatible")
        for key, expected in _NPM_EFFECTIVE_POLICY.items():
            observed = self._spawn(
                "npm_policy",
                [str(self.node.path), str(self.npm.path), "config", "get", key],
                base,
            )
            if observed[0] != 0 or observed[2]:
                raise self._error("driver_state_unknown")
            try:
                value = observed[1].decode("utf-8").strip()
            except UnicodeDecodeError:
                raise self._error("driver_state_unknown") from None
            if value not in expected:
                raise self._error("driver_state_unknown")
        self.environment = self._environment()

    def _validate_root(self) -> None:
        try:
            if not _validate_root(self.operation.root):
                raise self._error("managed_installation_not_ready")
            _record_namespace_state(self.operation.root)
            if _installation_record_state(self.operation.root) != "complete":
                raise self._error("managed_installation_not_ready")
            self.appium_entry, self.static_appium_version = _managed_appium(
                self.operation.root
            )
        except _StateFailure as failure:
            code = (
                "maintenance_recovery_required"
                if failure.code
                in ("installation_recovery_required", "installation_state_unknown")
                else "managed_installation_not_ready"
            )
            raise self._error(code, "recovery_required") from None

    def _verify_appium(self) -> None:
        assert self.node is not None and self.environment is not None
        assert self.appium_entry is not None and self.static_appium_version is not None
        result = self._spawn(
            "appium_version",
            [str(self.node.path), str(self.appium_entry), "--version"],
            self.environment,
        )
        if result[0] != 0 or result[2]:
            raise self._error("managed_installation_not_ready")
        try:
            text = result[1].decode("ascii").strip()
        except UnicodeDecodeError:
            raise self._error("managed_installation_not_ready") from None
        observed = version(text)
        if observed is None or observed.text != self.static_appium_version:
            raise self._error("managed_installation_not_ready")
        if observed.major != 3:
            raise self.operation.error(
                RuntimeOperationError, "unsupported_server_version"
            )
        self.operation.appium_version = observed.text

    def _list_command(self) -> list[str]:
        assert self.node is not None and self.appium_entry is not None
        return [
            str(self.node.path),
            str(self.appium_entry),
            "driver",
            "list",
            "--installed",
            "--json",
        ]

    def _listing(self, cleanup_deadline: float | None = None) -> dict[str, Any]:
        assert self.environment is not None
        if cleanup_deadline is None:
            result = self._spawn(
                "driver_listing",
                self._list_command(),
                self.environment,
                structured=True,
            )
        else:
            result = self._cleanup_spawn(
                self._list_command(), self.environment, cleanup_deadline
            )
        if result[0] != 0 or result[2]:
            raise _StateFailure("installation_state_unknown")
        try:
            document = json.loads(result[1])
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            raise _StateFailure("installation_state_unknown") from None
        if not isinstance(document, dict):
            raise _StateFailure("installation_state_unknown")
        return cast(dict[str, Any], document)

    def _snapshot(self, cleanup_deadline: float | None = None) -> DriverComponent:
        document = self._listing(cleanup_deadline)
        if self.operation.driver_name not in document:
            return _driver_component(
                self.operation.driver_name, None, "missing", "not_installed"
            )
        item = document[self.operation.driver_name]
        if not isinstance(item, dict):
            return _driver_component(
                self.operation.driver_name, None, "damaged", "driver_manifest_invalid"
            )
        package_name = _PACKAGES[self.operation.driver_name]
        observed_text = item.get("version")
        observed = version(observed_text)
        install_path = item.get("installPath")
        install_type = item.get("installType")
        appium_range = item.get("appiumVersion")
        if (
            item.get("installed") is not True
            or item.get("pkgName") != package_name
            or observed is None
            or not isinstance(install_path, str)
            or (install_type is not None and install_type != "npm")
            or (appium_range is not None and not isinstance(appium_range, str))
        ):
            return _driver_component(
                self.operation.driver_name,
                observed.text if observed is not None else None,
                "damaged",
                "driver_manifest_invalid",
            )
        if appium_range is not None:
            assert self.operation.appium_version is not None
            compatible = satisfies(self.operation.appium_version, appium_range)
            if compatible is not True:
                return _driver_component(
                    self.operation.driver_name,
                    observed.text,
                    "damaged",
                    "driver_appium_range_invalid",
                )
        expected = self.operation.root / "driver-home" / "node_modules" / package_name
        try:
            resolved = Path(install_path).resolve(strict=True)
            driver_home = (self.operation.root / "driver-home").resolve(strict=True)
            expected_resolved = expected.resolve(strict=True)
        except (OSError, RuntimeError):
            return _driver_component(
                self.operation.driver_name,
                observed.text,
                "damaged",
                "driver_path_invalid",
            )
        if resolved != expected_resolved or not resolved.is_relative_to(driver_home):
            return _driver_component(
                self.operation.driver_name,
                observed.text,
                "damaged",
                "driver_path_invalid",
            )
        try:
            package = _json_file(resolved / "package.json", _METADATA_LIMIT)
        except _StateFailure:
            return _driver_component(
                self.operation.driver_name,
                observed.text,
                "damaged",
                "driver_package_invalid",
            )
        appium = package.get("appium") if isinstance(package, dict) else None
        if (
            not isinstance(package, dict)
            or package.get("name") != package_name
            or package.get("version") != observed.text
            or not isinstance(appium, dict)
            or appium.get("driverName") != self.operation.driver_name
        ):
            return _driver_component(
                self.operation.driver_name,
                observed.text,
                "damaged",
                "driver_package_invalid",
            )
        return _driver_component(
            self.operation.driver_name,
            observed.text,
            "verified",
            "driver_verified",
            (f"version={observed.text}",),
        )

    def _record_value(self, state: str) -> dict[str, object]:
        return {
            "schema": 1,
            "state": state,
            "operation_id": self.operation.operation_id,
            "operation": self.kind,
            "driver": self.operation.driver_name,
            "may_have_changed": True,
        }

    def _write_record(self, state: str, checkpoint: Any | None = None) -> None:
        _atomic_json(
            self.operation.root / "records" / _MAINTENANCE_RECORD,
            self._record_value(state),
            checkpoint or self.operation.checkpoint,
        )

    def _prepare_intent(self) -> None:
        self._write_record("incomplete")
        self.intent_written = True

    def _ensure(self) -> DriverMaintenanceResult:
        before = self.operation.before
        if before.status == "verified":
            return self.operation.driver_result("reused")
        if before.status == "damaged":
            raise self._error("driver_damaged")
        if before.status == "unknown":
            raise self._error("driver_state_unknown")
        self._prepare_intent()
        assert self.node is not None
        assert self.appium_entry is not None
        assert self.environment is not None
        result = self._spawn(
            "driver_installing",
            [
                str(self.node.path),
                str(self.appium_entry),
                "driver",
                "install",
                self.operation.driver_name,
                "--json",
            ],
            self.environment,
            structured=True,
            writer=True,
        )
        if result[0] != 0:
            raise self._error("driver_install_failed")
        if result[2]:
            raise self._error("driver_verification_failed")
        try:
            installed = json.loads(result[1])
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            raise self._error("driver_verification_failed") from None
        if not isinstance(installed, dict):
            raise self._error("driver_verification_failed")
        try:
            self.operation.after = self._snapshot()
        except _StateFailure:
            raise self._error("driver_verification_failed") from None
        if self.operation.after.status != "verified":
            raise self._error("driver_verification_failed")
        self._write_record("complete")
        return self.operation.driver_result("installed")

    def _doctor(self) -> DriverDoctorResult:
        before = self.operation.before
        if before.status == "missing":
            raise self._error("driver_not_installed")
        if before.status == "damaged":
            raise self._error("driver_damaged")
        if before.status == "unknown":
            raise self._error("driver_state_unknown")
        self._prepare_intent()
        assert self.node is not None
        assert self.appium_entry is not None
        assert self.environment is not None
        result = self._spawn(
            "driver_doctor_running",
            [
                str(self.node.path),
                str(self.appium_entry),
                "driver",
                "doctor",
                self.operation.driver_name,
                "--json",
            ],
            self.environment,
            structured=True,
            writer=True,
        )
        if result[0] != 0:
            raise self._error("driver_doctor_failed")
        if result[2]:
            raise self._error("driver_doctor_output_invalid")
        try:
            count = json.loads(result[1])
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            raise self._error("driver_doctor_output_invalid") from None
        if type(count) is not int or not 0 <= count <= _CHECK_COUNT_LIMIT:
            raise self._error("driver_doctor_output_invalid")
        self.operation.executed_check_count = count
        try:
            self.operation.after = self._snapshot()
        except _StateFailure:
            raise self._error("driver_state_unknown") from None
        if self.operation.after.status != "verified":
            raise self._error("driver_state_unknown")
        self._write_record("complete")
        return self.operation.doctor_result("accepted")

    def execute(self) -> _MaintenanceResult:
        operation = self.operation
        operation.checkpoint()
        self._acquire()
        try:
            operation.checkpoint()
            if platform.system() != "Darwin":
                raise operation.error(RuntimeOperationError, "unsupported_host")
            self._validate_root()
            self._preflight()
            self._verify_appium()
            try:
                operation.before = operation.after = self._snapshot()
            except _StateFailure:
                raise self._error("driver_state_unknown") from None
            result = self._ensure() if self.kind == "driver_install" else self._doctor()
            self._release(None)
            return result
        except BaseException as error:
            self._fail(error)

    def _attach_result(
        self,
        error: BaseException,
        outcome: DriverMaintenanceOutcome | DriverDoctorOutcome,
    ) -> None:
        if self.operation.appium_version is None:
            return
        result = self.operation.result(outcome)
        if self.kind == "driver_install":
            error.__dict__["driver_result"] = result
        else:
            error.__dict__["doctor_result"] = result

    def _fail(self, error: BaseException) -> NoReturn:
        deadline = time.monotonic() + 30.0
        cleanup_error: BaseException | None = None
        cleanup_pending = False
        recovery_required = False

        def check() -> None:
            _cleanup_checkpoint(deadline)

        try:
            check()
            if self.handle is not None:
                if not self.handle.cleanup(deadline, check):
                    raise RuntimeError("cleanup incomplete")
                self.handle = None
            check()
            if self.intent_written:
                try:
                    self.operation.after = self._snapshot(deadline)
                except BaseException:
                    recovery_required = True
                check()
                self._write_record(
                    "recovery_required" if recovery_required else "failed", check
                )
            check()
        except BaseException as failure:
            cleanup_error = failure
            cleanup_pending = self.handle is not None
            recovery_required = not cleanup_pending
        if cleanup_pending:
            with suppress(BaseException):
                self._write_record("cleanup_pending", check)
            self.runtime._installation_cleanup = self
        else:
            if self.intent_written and recovery_required:
                with suppress(BaseException):
                    self._write_record("recovery_required")
            self._release(error)
            self.runtime._installing = False
        if cleanup_pending:
            outcome: DriverMaintenanceOutcome | DriverDoctorOutcome = "cleanup_pending"
        elif recovery_required:
            outcome = "recovery_required"
        elif isinstance(error, OperationCancelledError):
            outcome = "cancelled"
        elif isinstance(error, OperationTimeoutError):
            outcome = "timed_out"
        else:
            outcome = "failed"
        self._attach_result(error, outcome)
        if cleanup_error is not None:
            error.__dict__["runtime_installation_cleanup_error"] = cleanup_error
        raise error

    def cleanup(self, control: OperationControl) -> _MaintenanceResult:
        operation = _MaintenanceOperation(
            self.runtime,
            control,
            self.operation.driver_name,
            self.kind,
            phase="cleaning_installation",
        )
        operation.appium_version = self.operation.appium_version
        operation.before = self.operation.after
        operation.after = self.operation.after
        operation.changed = self.operation.changed
        operation.doctor_started = self.operation.doctor_started
        original_operation = self.operation
        self.operation = operation
        try:
            operation.checkpoint()
            if self.handle is not None:
                if not self.handle.cleanup(operation.deadline, operation.checkpoint):
                    raise self._error("maintenance_cleanup_pending", "cleanup_pending")
                self.handle = None
            operation.after = self._snapshot()
            self._write_record("failed")
            result = operation.result("cleanup_completed")
        except (OperationTimeoutError, OperationCancelledError) as error:
            self._attach_result(error, "cleanup_pending")
            raise
        except RuntimeOperationError:
            raise
        except BaseException as error:
            outcome: DriverMaintenanceOutcome | DriverDoctorOutcome
            outcome = (
                "cleanup_pending" if self.handle is not None else "recovery_required"
            )
            record_error: BaseException | None = None
            try:
                self._write_record(outcome)
            except BaseException as failure:
                record_error = failure
            if self.handle is not None:
                self.runtime._installation_cleanup = self
            else:
                self._release(error)
                self.runtime._installation_cleanup = None
                self.runtime._installing = False
            self._attach_result(error, outcome)
            if record_error is not None:
                error.__dict__["runtime_installation_cleanup_error"] = record_error
            raise
        finally:
            if self.runtime._installation_cleanup is self:
                self.operation = original_operation
        self._release(None)
        self.runtime._installation_cleanup = None
        self.runtime._installing = False
        return result


def _start(
    runtime: Runtime,
    driver: OfficialDriver,
    control: OperationControl,
    kind: _MaintenanceKind,
) -> _MaintenanceResult:
    operation = _MaintenanceOperation(runtime, control, driver, kind)
    if (
        runtime._installing
        or runtime._active_thread is not None
        or runtime._diagnosing
        or runtime._managed_scope is not None
    ):
        raise operation.error(EnvironmentBusyError, "environment_busy")
    runtime._installing = True
    runner = _MaintenanceRunner(operation)
    try:
        return runner.execute()
    finally:
        if runtime._installation_cleanup is None:
            runtime._installing = False


def ensure_managed_driver(
    runtime: Runtime, driver: OfficialDriver, control: OperationControl
) -> DriverMaintenanceResult:
    result = _start(runtime, driver, control, "driver_install")
    assert isinstance(result, DriverMaintenanceResult)
    return result


def run_driver_doctor(
    runtime: Runtime, driver: OfficialDriver, control: OperationControl
) -> DriverDoctorResult:
    result = _start(runtime, driver, control, "driver_doctor")
    assert isinstance(result, DriverDoctorResult)
    return result


def cleanup_maintenance(
    runtime: Runtime, control: OperationControl
) -> DriverMaintenanceResult | DriverDoctorResult | None:
    pending = runtime._installation_cleanup
    if not isinstance(pending, _MaintenanceRunner):
        return None
    runtime._installation_cleanup = None
    try:
        return pending.cleanup(control)
    finally:
        if runtime._installing:
            runtime._installation_cleanup = pending
