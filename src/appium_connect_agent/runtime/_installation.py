"""Conservative preparation of the one designated local Appium combination."""

from __future__ import annotations

import json
import os
import platform
import selectors
import signal
import stat
import subprocess
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from appium_connect_agent.contracts import LocalSettings

from . import _coordination
from ._diagnostics import _diagnostic_lock, _Operation
from ._models import (
    EnvironmentBusyError,
    InstallationCombination,
    InstallationComponent,
    InstallationError,
    InstallationOutcome,
    InstallationResult,
    InstallationStatus,
    InstallRequest,
    OperationCancelledError,
    OperationControl,
    OperationTimeoutError,
    RuntimeOperationError,
)
from ._semver import satisfies, version

if TYPE_CHECKING:
    from ._diagnostics import Runtime

_COMBINATION = InstallationCombination(
    combination_id="macos-android-uiautomator2",
    host="macOS",
    target="Android",
    driver="UiAutomator2",
    appium_version="3.7.0",
    driver_version="8.7.0",
    node_range="^20.19.0 || ^22.12.0 || >=24.0.0",
    npm_range=">=10",
    is_default=True,
    limitations=("optional_image_dependencies_unverified",),
)
_COMBINATIONS = (_COMBINATION,)
_WARNING = ("optional_image_dependencies_unverified",)
_OUTPUT_LIMIT = 64 * 1024
_RECORD_LIMIT = 64 * 1024
_METADATA_LIMIT = 1024 * 1024
_ALLOWED_ROOT = frozenset(
    {"managed.json", "appium", "driver-home", "records", "cache", "tmp"},
)
_CONTROL_ENV = (
    "node_options",
    "node_path",
    "npm_config_prefix",
    "npm_config_global",
    "npm_config_drivers",
    "npm_config_plugins",
    "appium_home",
    "appium_tmp_dir",
    "appium_omit_peer_deps",
    "java_tool_options",
    "_java_options",
    "jdk_java_options",
    "pythonpath",
    "pythonhome",
    "virtual_env",
)
_NPM_NETWORK_ENV = frozenset(
    {
        "npm_config_registry",
        "npm_config_proxy",
        "npm_config_https_proxy",
        "npm_config_noproxy",
        "npm_config_strict_ssl",
        "npm_config_cafile",
        "npm_config_ca",
        "npm_config_always_auth",
        "npm_config_userconfig",
        "npm_config_globalconfig",
        "npm_config_cert",
        "npm_config_key",
        "npm_config_local_address",
        "npm_config_maxsockets",
        "npm_config_fetch_retries",
        "npm_config_fetch_retry_factor",
        "npm_config_fetch_retry_mintimeout",
        "npm_config_fetch_retry_maxtimeout",
        "npm_config_fetch_timeout",
        "npm_config_offline",
        "npm_config_prefer_offline",
        "npm_config_prefer_online",
    }
)
_NPM_BEHAVIOR_ENV = {
    "npm_config_allow_scripts": "",
    "npm_config_strict_allow_scripts": "false",
    "npm_config_dangerously_allow_all_scripts": "true",
    "npm_config_allow_directory": "all",
    "npm_config_allow_file": "all",
    "npm_config_allow_git": "all",
    "npm_config_allow_remote": "all",
    "npm_config_before": "",
    "npm_config_min_release_age": "0",
    "npm_config_min_release_age_exclude": "",
    "npm_config_global": "false",
    "npm_config_ignore_scripts": "false",
    "npm_config_script_shell": "/bin/sh",
    "npm_config_omit": "",
    "npm_config_include": "",
    "npm_config_install_strategy": "hoisted",
    "npm_config_legacy_peer_deps": "false",
    "npm_config_strict_peer_deps": "false",
    "npm_config_force": "false",
    "npm_config_engine_strict": "false",
    "npm_config_os": "darwin",
    "npm_config_cpu": "arm64",
    "npm_config_prefer_dedupe": "false",
    "npm_config_rebuild_bundle": "true",
    "npm_config_node_options": "",
    "npm_config_shell": "/bin/sh",
    "npm_config_optional": "true",
    "npm_config_production": "false",
    "npm_config_only": "",
    "npm_config_also": "",
    "npm_config_global_style": "false",
    "npm_config_legacy_bundling": "false",
    "npm_config_bin_links": "true",
    "npm_config_install_links": "false",
    "npm_config_package_lock": "true",
    "npm_config_include_staged": "false",
    "npm_config_package_lock_only": "false",
    "npm_config_dry_run": "false",
    "npm_config_workspaces": "false",
    "npm_config_include_workspace_root": "false",
    "npm_config_foreground_scripts": "false",
    "npm_config_audit": "false",
    "npm_config_save": "true",
    "npm_config_save_exact": "true",
    "npm_config_fund": "false",
}
_NPM_EFFECTIVE_POLICY: dict[str, frozenset[str]] = {
    "dangerously-allow-all-scripts": frozenset({"true"}),
    "strict-allow-scripts": frozenset({"false"}),
    "allow-directory": frozenset({"all"}),
    "allow-file": frozenset({"all"}),
    "allow-git": frozenset({"all"}),
    "allow-remote": frozenset({"all"}),
    "before": frozenset({"null"}),
    "min-release-age": frozenset({"0"}),
    "min-release-age-exclude": frozenset({""}),
    "ignore-scripts": frozenset({"false"}),
    "omit": frozenset({""}),
    "include": frozenset({""}),
    "only": frozenset({"null"}),
    "production": frozenset({"false"}),
    "optional": frozenset({"true"}),
    "also": frozenset({"null"}),
    "install-strategy": frozenset({"hoisted"}),
    "legacy-peer-deps": frozenset({"false"}),
    "strict-peer-deps": frozenset({"false"}),
    "force": frozenset({"false"}),
    "engine-strict": frozenset({"false"}),
    "os": frozenset({"darwin"}),
    "cpu": frozenset({"arm64"}),
    "prefer-dedupe": frozenset({"false"}),
    "rebuild-bundle": frozenset({"true"}),
    "node-options": frozenset({"null", ""}),
    "global-style": frozenset({"false"}),
    "legacy-bundling": frozenset({"false"}),
    "bin-links": frozenset({"true"}),
    "install-links": frozenset({"false"}),
    "package-lock": frozenset({"true"}),
    "package-lock-only": frozenset({"false"}),
    "dry-run": frozenset({"false"}),
    "workspaces": frozenset({"false"}),
    "include-workspace-root": frozenset({"false"}),
    "include-staged": frozenset({"false"}),
}


def _base_environment() -> dict[str, str]:
    environment: dict[str, str] = {}
    for key, value in os.environ.items():
        normalized = key.lower()
        if normalized in _CONTROL_ENV:
            continue
        auth_setting = any(
            marker in normalized
            for marker in (
                "_auth",
                "authtoken",
                "username",
                "password",
                "always-auth",
            )
        )
        if normalized.startswith("npm_config_") and not (
            normalized in _NPM_NETWORK_ENV
            or normalized.endswith("_registry")
            or auth_setting
        ):
            continue
        environment[key] = value
    environment.update(_NPM_BEHAVIOR_ENV)
    return environment


def supported_combinations() -> tuple[InstallationCombination, ...]:
    """Return the immutable, packaged combination catalog without performing I/O."""

    return _COMBINATIONS


class _StateFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code


class _CleanupIncomplete(Exception):
    pass


def _cleanup_checkpoint(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise _CleanupIncomplete


@dataclass(frozen=True)
class _Tool:
    path: Path
    launcher: Path


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: bytes
    stdout_truncated: bool


class _ProcessHandle:
    """One owned process group and its continuously drained bounded streams."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self.process = process
        self.group_id = process.pid
        self._group_gone = False
        self.selector = selectors.DefaultSelector()
        self.buffers: dict[Literal["stdout", "stderr"], bytearray] = {
            "stdout": bytearray(),
            "stderr": bytearray(),
        }
        self.truncated = {"stdout": False, "stderr": False}
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            assert stream is not None
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream.fileno(), selectors.EVENT_READ, name)

    def _read_ready(self, descriptor: int, name: Literal["stdout", "stderr"]) -> None:
        while True:
            try:
                block = os.read(descriptor, 16 * 1024)
            except BlockingIOError:
                return
            if not block:
                with suppress(KeyError):
                    self.selector.unregister(descriptor)
                return
            target = self.buffers[name]
            available = _OUTPUT_LIMIT - len(target)
            if available:
                target.extend(block[:available])
            if len(block) > available:
                self.truncated[name] = True

    def _group_state(self) -> Literal["alive", "gone", "unknown"]:
        self.process.poll()
        if self._group_gone:
            return "gone"
        try:
            os.killpg(self.group_id, 0)
        except ProcessLookupError:
            self._group_gone = True
            return "gone"
        except OSError:
            return "unknown"
        return "alive"

    def wait(self, checkpoint: Callable[[], None], deadline: float) -> _CommandResult:
        while (
            self.process.poll() is None
            or self.selector.get_map()
            or self._group_state() != "gone"
        ):
            checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                checkpoint()
            events = self.selector.select(min(0.1, max(0.0, remaining)))
            for key, _ in events:
                self._read_ready(key.fd, key.data)
        return self.result()

    def _drain_until(self, deadline: float) -> None:
        while self.selector.get_map() and time.monotonic() < deadline:
            events = self.selector.select(min(0.05, deadline - time.monotonic()))
            for key, _ in events:
                self._read_ready(key.fd, key.data)

    def cleanup(
        self,
        deadline: float,
        checkpoint: Callable[[], None] | None = None,
    ) -> bool:
        def check() -> None:
            if checkpoint is not None:
                checkpoint()

        check()
        state = self._group_state()
        if state == "unknown":
            return False
        if state == "alive":
            with suppress(ProcessLookupError):
                os.killpg(self.group_id, signal.SIGTERM)
            gentle = min(deadline, time.monotonic() + 2.0)
            while self._group_state() == "alive" and time.monotonic() < gentle:
                check()
                self._drain_until(min(gentle, time.monotonic() + 0.05))
                time.sleep(min(0.05, max(0.0, gentle - time.monotonic())))
            check()
            if self._group_state() == "alive" and time.monotonic() < deadline:
                with suppress(ProcessLookupError):
                    os.killpg(self.group_id, signal.SIGKILL)
        while self._group_state() == "alive" and time.monotonic() < deadline:
            check()
            self._drain_until(min(deadline, time.monotonic() + 0.05))
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        if self.process.poll() is None and time.monotonic() < deadline:
            with suppress(subprocess.TimeoutExpired):
                self.process.wait(timeout=max(0.0, deadline - time.monotonic()))
        check()
        self._drain_until(deadline)
        check()
        complete = (
            self._group_state() == "gone"
            and self.process.poll() is not None
            and not self.selector.get_map()
        )
        if complete:
            self.close()
        return complete

    def result(self) -> _CommandResult:
        returncode = self.process.returncode
        assert returncode is not None
        return _CommandResult(
            returncode,
            bytes(self.buffers["stdout"]),
            self.truncated["stdout"],
        )

    def close(self) -> None:
        self.selector.close()
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


class _InstallOperation(_Operation):
    def __init__(
        self,
        runtime: Runtime,
        control: OperationControl,
        *,
        phase: str = "installing",
    ) -> None:
        super().__init__(control, runtime._on_progress, phase)
        self.runtime = runtime
        self.root = _coordination._account_home() / ".appium-connect-agent"
        self.node_version: str | None = None
        self.npm_version: str | None = None
        missing = (
            _missing("Appium", _COMBINATION.appium_version),
            _missing("UiAutomator2", _COMBINATION.driver_version),
        )
        self.before: tuple[InstallationComponent, ...] = missing
        self.after: tuple[InstallationComponent, ...] = missing
        self.changed = False
        self.settings: LocalSettings | None = None

    def result(self, outcome: InstallationOutcome) -> InstallationResult:
        return InstallationResult(
            self.operation_id,
            self.observed_at,
            _COMBINATION.combination_id,
            self.root,
            self.node_version,
            self.npm_version,
            self.before,
            self.after,
            outcome,
            self.changed,
            _WARNING,
            tuple(self.observer_errors[:8]),
            self.settings if outcome in ("installed", "reused") else None,
        )

    def error(
        self,
        kind: type[RuntimeOperationError],
        code: str,
        outcome: InstallationOutcome = "failed",
    ) -> RuntimeOperationError:
        if outcome == "failed" and kind is OperationCancelledError:
            outcome = "cancelled"
        elif outcome == "failed" and kind is OperationTimeoutError:
            outcome = "timed_out"
        return kind(code, self.operation_id, self.report(), self.result(outcome))

    def progress(self, check_id: str | None, message: str) -> None:
        self.add(check_id or "installation", "unknown", message)


def _component(
    name: str,
    requested: str,
    observed: str | None,
    status: Literal["missing", "verified", "conflict", "damaged", "unknown"],
    reason: str,
    evidence: tuple[str, ...] = (),
) -> InstallationComponent:
    bounded = tuple(
        value if len(value) <= 512 else value[:498] + "...[truncated]"
        for value in evidence[:8]
    )
    return InstallationComponent(name, requested, observed, status, reason, bounded)


def _missing(name: str, requested: str) -> InstallationComponent:
    return _component(name, requested, None, "missing", "not_observed")


def _unknown(component: InstallationComponent) -> InstallationComponent:
    return _component(
        component.name, component.requested_version, None, "unknown", "state_unknown"
    )


def _owned_regular(path: Path, limit: int) -> bytes:
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise _StateFailure("installation_state_unknown") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or info.st_size > limit
    ):
        raise _StateFailure("installation_state_unknown")
    try:
        data = path.read_bytes()
    except OSError:
        raise _StateFailure("installation_state_unknown") from None
    if len(data) > limit:
        raise _StateFailure("installation_state_unknown")
    return data


def _json_file(path: Path, limit: int = _METADATA_LIMIT) -> Any:
    try:
        return json.loads(_owned_regular(path, limit))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise _StateFailure("installation_damaged") from None


def _atomic_json(
    path: Path,
    value: object,
    checkpoint: Callable[[], None] | None = None,
) -> None:
    def check() -> None:
        if checkpoint is not None:
            checkpoint()

    check()
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    if len(encoded) > _RECORD_LIMIT:
        raise _StateFailure("installation_state_unknown")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    check()
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        check()
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        check()
    except BaseException:
        with suppress(OSError):
            temporary.unlink()
        raise


def _safe_directory(path: Path) -> None:
    info = path.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_uid != os.getuid()
    ):
        raise _StateFailure("installation_root_conflict")


def _inspect_package(
    base: Path,
    package: Path,
    expected_name: str,
    requested: str,
    display_name: str,
    entry: Path | None = None,
) -> InstallationComponent:
    def snapshot(
        status: InstallationStatus,
        reason: str,
        observed: str | None = None,
        evidence: tuple[str, ...] = (),
    ) -> InstallationComponent:
        return _component(display_name, requested, observed, status, reason, evidence)

    metadata = package / "package.json"
    if not metadata.exists():
        try:
            nonempty = base.exists() and any(base.iterdir())
        except OSError:
            return snapshot("unknown", "path_unreadable")
        if package.exists() or nonempty:
            return snapshot("damaged", "package_missing")
        return snapshot("missing", "component_missing")
    try:
        package_info = package.lstat()
        package_root = package.resolve(strict=True)
        base_root = base.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return snapshot("unknown", "path_unreadable")
    if (
        not stat.S_ISDIR(package_info.st_mode)
        or stat.S_ISLNK(package_info.st_mode)
        or package_info.st_uid != os.getuid()
        or not package_root.is_relative_to(base_root)
    ):
        return snapshot("unknown", "path_untrusted")
    try:
        value = _json_file(metadata)
    except _StateFailure as failure:
        status: Literal["unknown", "damaged"] = (
            "unknown" if failure.code == "installation_state_unknown" else "damaged"
        )
        return snapshot(status, "metadata_invalid")
    if not isinstance(value, dict):
        return snapshot("damaged", "metadata_invalid")
    name, observed = value.get("name"), value.get("version")
    if name != expected_name or not isinstance(observed, str):
        return snapshot("damaged", "identity_mismatch")
    if version(observed) is None:
        return snapshot("damaged", "version_invalid")
    if observed != requested:
        evidence = (
            f"observed_version={observed}",
            f"requested_version={requested}",
        )
        return snapshot("conflict", "version_conflict", observed, evidence)
    if entry is not None:
        try:
            info = entry.lstat()
            resolved = entry.resolve(strict=True)
        except (FileNotFoundError, OSError):
            return snapshot("damaged", "entry_missing", observed)
        if (
            not (stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode))
            or not resolved.is_relative_to(package_root)
            or not resolved.is_file()
        ):
            return snapshot("damaged", "entry_invalid", observed)
    return snapshot(
        "verified", "component_verified", observed, (f"version={observed}",)
    )


def _paths(root: Path) -> tuple[Path, Path, Path, Path]:
    appium = root / "appium"
    driver = root / "driver-home"
    appium_package = appium / "node_modules" / "appium"
    driver_package = driver / "node_modules" / "appium-uiautomator2-driver"
    return appium, driver, appium_package, driver_package


def _inspect_components(root: Path) -> tuple[InstallationComponent, ...]:
    appium, driver, appium_package, driver_package = _paths(root)
    return (
        _inspect_package(
            appium,
            appium_package,
            "appium",
            _COMBINATION.appium_version,
            "Appium",
            appium_package / "index.js",
        ),
        _inspect_package(
            driver,
            driver_package,
            "appium-uiautomator2-driver",
            _COMBINATION.driver_version,
            "UiAutomator2",
        ),
    )


def _validate_root(root: Path) -> bool:
    try:
        _safe_directory(root)
        names = {entry.name for entry in root.iterdir()}
    except FileNotFoundError:
        return False
    except OSError:
        raise _StateFailure("installation_state_unknown") from None
    if names - _ALLOWED_ROOT:
        raise _StateFailure("installation_state_unknown")
    marker = root / "managed.json"
    if not marker.exists():
        if names:
            raise _StateFailure("installation_root_conflict")
        return False
    value = _json_file(marker, _RECORD_LIMIT)
    if value != {"owner": "appium-connect-agent", "schema": 1}:
        raise _StateFailure("installation_root_conflict")
    try:
        for name in names - {"managed.json"}:
            _safe_directory(root / name)
    except OSError:
        raise _StateFailure("installation_state_unknown") from None
    return True


def _record_state(
    root: Path, components: tuple[InstallationComponent, ...]
) -> Literal["complete", "failed"]:
    records = root / "records"
    record = records / "installation.json"
    if not records.exists():
        raise _StateFailure("installation_recovery_required")
    try:
        entries = {entry.name for entry in records.iterdir()}
    except OSError:
        raise _StateFailure("installation_recovery_required") from None
    if entries != {"installation.json"}:
        raise _StateFailure("installation_recovery_required")
    try:
        value = _json_file(record, _RECORD_LIMIT)
    except _StateFailure:
        raise _StateFailure("installation_recovery_required") from None
    fields = {
        "schema",
        "state",
        "operation_id",
        "combination_id",
        "changed",
    }
    if (
        not isinstance(value, dict)
        or set(value) != fields
        or not isinstance(value["schema"], int)
        or isinstance(value["schema"], bool)
        or value["schema"] != 1
        or not isinstance(value["operation_id"], str)
        or not value["operation_id"]
        or value["combination_id"] != _COMBINATION.combination_id
        or not isinstance(value["changed"], bool)
    ):
        raise _StateFailure("installation_recovery_required")
    state = value["state"]
    statuses = {component.status for component in components}
    if state == "complete":
        if "missing" in statuses and statuses <= {"missing", "verified"}:
            raise _StateFailure("installation_damaged")
        return "complete"
    if state == "failed":
        return "failed"
    raise _StateFailure("installation_recovery_required")


def _record_value(operation: _InstallOperation, state: str) -> dict[str, object]:
    return {
        "schema": 1,
        "state": state,
        "operation_id": operation.operation_id,
        "combination_id": _COMBINATION.combination_id,
        "changed": operation.changed,
    }


def _write_record(operation: _InstallOperation, state: str) -> None:
    operation.checkpoint()
    _atomic_json(
        operation.root / "records" / "installation.json",
        _record_value(operation, state),
        operation.checkpoint,
    )
    operation.checkpoint()


def _tool(explicit: Path | None, name: str, paths: tuple[str, ...]) -> _Tool:
    candidates: list[tuple[Path, Path]] = []
    locations = (str(explicit.parent),) if explicit is not None else paths[:64]
    for raw in locations:
        directory = Path(raw)
        if not directory.is_absolute():
            continue
        launcher = explicit if explicit is not None else directory / name
        try:
            resolved = launcher.resolve(strict=True)
            info = resolved.stat()
        except (FileNotFoundError, OSError):
            if explicit is not None:
                raise _StateFailure("tool_not_found") from None
            continue
        if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.R_OK | os.X_OK):
            if explicit is not None:
                raise _StateFailure("tool_not_executable")
            continue
        if all(existing[0] != resolved for existing in candidates):
            candidates.append((resolved, launcher))
    if not candidates:
        raise _StateFailure("tool_not_found")
    if len(candidates) != 1:
        raise _StateFailure("installation_state_unknown")
    return _Tool(*candidates[0])


def _paired_bin(node: _Tool, npm: _Tool, paths: tuple[str, ...]) -> Path:
    directories = [node.launcher.parent, npm.launcher.parent]
    directories.extend(Path(value) for value in paths[:64] if Path(value).is_absolute())
    observed: set[Path] = set()
    for directory in directories:
        try:
            if (directory / "node").resolve(strict=True) != node.path:
                continue
            if (directory / "npm").resolve(strict=True) != npm.path:
                continue
        except (FileNotFoundError, OSError):
            continue
        resolved = directory.resolve()
        if resolved in observed:
            continue
        observed.add(resolved)
        return resolved
    raise _StateFailure("tool_version_incompatible")


class _Installer:
    def __init__(self, operation: _InstallOperation) -> None:
        self.operation = operation
        self.runtime = operation.runtime
        self.lock: AbstractContextManager[None] | None = None
        self.handle: _ProcessHandle | None = None
        self.intent_written = False
        self.node: _Tool | None = None
        self.npm: _Tool | None = None
        self.bin_dir: Path | None = None

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
        env: dict[str, str],
        *,
        component_writer: bool = False,
        notify_progress: bool = True,
    ) -> _CommandResult:
        if notify_progress:
            self.operation.progress(label, "command_starting")
        else:
            self.operation.checkpoint()
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=(
                    self.operation.root
                    if self.operation.root.exists()
                    else self.operation.root.parent
                ),
                env=env,
                shell=False,
                start_new_session=True,
            )
        except OSError:
            code = (
                "tool_not_executable"
                if label in ("node_version", "npm_version")
                else "component_install_failed"
            )
            raise self.operation.error(InstallationError, code) from None
        if component_writer:
            self.operation.changed = True
        self.handle = _ProcessHandle(process)
        self.operation.checkpoint()
        result = self.handle.wait(self.operation.checkpoint, self.operation.deadline)
        self.handle.close()
        self.handle = None
        if notify_progress:
            self.operation.progress(label, "command_completed")
        else:
            self.operation.checkpoint()
        return result

    def _checked(
        self,
        label: str,
        command: list[str],
        env: dict[str, str],
        *,
        verification: bool = False,
        component_writer: bool = False,
    ) -> _CommandResult:
        result = self._spawn(label, command, env, component_writer=component_writer)
        if result.returncode != 0:
            code = (
                "component_verification_failed"
                if verification
                else "component_install_failed"
            )
            raise self.operation.error(InstallationError, code)
        if result.stdout_truncated and verification:
            raise self.operation.error(
                InstallationError, "component_verification_failed"
            )
        return result

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
        return environment

    def _preflight(self, paths: tuple[str, ...]) -> None:
        settings = self.runtime._settings
        self.node = _tool(settings.node_executable, "node", paths)
        self.npm = _tool(settings.npm_executable, "npm", paths)
        self.bin_dir = _paired_bin(self.node, self.npm, paths)
        base_env = _base_environment()
        base_env["PATH"] = f"{self.bin_dir}:/usr/bin:/bin"
        node_result = self._spawn(
            "node_version", [str(self.node.path), "--version"], base_env
        )
        npm_result = self._spawn(
            "npm_version",
            [str(self.node.path), str(self.npm.path), "--version"],
            base_env,
        )
        if (
            node_result.returncode != 0
            or npm_result.returncode != 0
            or node_result.stdout_truncated
            or npm_result.stdout_truncated
        ):
            raise self.operation.error(InstallationError, "tool_version_invalid")
        try:
            raw_node = node_result.stdout.decode("ascii").strip()
            raw_npm = npm_result.stdout.decode("ascii").strip()
        except UnicodeDecodeError:
            raise self.operation.error(
                InstallationError, "tool_version_invalid"
            ) from None
        node_text = raw_node[1:] if raw_node.startswith("v") else raw_node
        if version(node_text) is None or version(raw_npm) is None:
            raise self.operation.error(InstallationError, "tool_version_invalid")
        self.operation.node_version = node_text
        self.operation.npm_version = raw_npm
        node_match = satisfies(node_text, _COMBINATION.node_range)
        npm_match = satisfies(raw_npm, _COMBINATION.npm_range)
        if node_match is None or npm_match is None:
            raise self.operation.error(InstallationError, "tool_version_invalid")
        if not node_match or not npm_match:
            raise self.operation.error(InstallationError, "tool_version_incompatible")
        self._verify_npm_policy(base_env)

    def _verify_npm_policy(self, environment: dict[str, str]) -> None:
        assert self.node is not None and self.npm is not None
        for key, expected in _NPM_EFFECTIVE_POLICY.items():
            result = self._spawn(
                f"npm_config_{key.replace('-', '_')}",
                [
                    str(self.node.path),
                    str(self.npm.path),
                    "config",
                    "get",
                    key,
                ],
                environment,
                notify_progress=False,
            )
            if result.returncode != 0 or result.stdout_truncated:
                raise self.operation.error(
                    InstallationError, "installation_state_unknown"
                )
            try:
                observed = result.stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                raise self.operation.error(
                    InstallationError, "installation_state_unknown"
                ) from None
            if observed not in expected:
                raise self.operation.error(
                    InstallationError, "installation_state_unknown"
                )

    def _prepare_root(self) -> None:
        root = self.operation.root
        if not root.exists():
            root.mkdir(mode=0o700)
        _safe_directory(root)
        os.chmod(root, 0o700)
        marker = root / "managed.json"
        if not marker.exists():
            _atomic_json(
                marker,
                {"owner": "appium-connect-agent", "schema": 1},
                self.operation.checkpoint,
            )
        (root / "records").mkdir(mode=0o700, exist_ok=True)
        _write_record(self.operation, "incomplete")
        self.intent_written = True
        for name in ("driver-home", "cache", "tmp"):
            path = root / name
            path.mkdir(mode=0o700, exist_ok=True)
            _safe_directory(path)

    def _verification_error(self) -> RuntimeOperationError:
        return self.operation.error(InstallationError, "component_verification_failed")

    def _verify_appium(self, environment: dict[str, str]) -> Path:
        assert self.node is not None
        appium_entry = _paths(self.operation.root)[2] / "index.js"
        observed = self._checked(
            "appium_verification",
            [str(self.node.path), str(appium_entry), "--version"],
            environment,
            verification=True,
        )
        try:
            appium_version = observed.stdout.decode("ascii").strip()
        except UnicodeDecodeError:
            appium_version = ""
        if appium_version != _COMBINATION.appium_version:
            raise self._verification_error()
        return appium_entry

    def _driver_listing(
        self, appium_entry: Path, environment: dict[str, str]
    ) -> dict[str, Any]:
        assert self.node is not None
        listed = self._checked(
            "driver_verification",
            [
                str(self.node.path),
                str(appium_entry),
                "driver",
                "list",
                "--installed",
                "--json",
            ],
            environment,
            verification=True,
        )
        try:
            document = json.loads(listed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            raise self._verification_error() from None
        if not isinstance(document, dict):
            raise self._verification_error()
        return document

    def _verify_partial(self, environment: dict[str, str]) -> None:
        appium_entry = self._verify_appium(environment)
        if "uiautomator2" in self._driver_listing(appium_entry, environment):
            raise self.operation.error(InstallationError, "installation_state_unknown")

    def _verify(self, environment: dict[str, str]) -> None:
        _, driver_home, _, driver_package = _paths(self.operation.root)
        self.operation.after = _inspect_components(self.operation.root)
        if any(component.status != "verified" for component in self.operation.after):
            raise self._verification_error()
        appium_entry = self._verify_appium(environment)
        item = self._driver_listing(appium_entry, environment).get("uiautomator2")
        try:
            expected_path = driver_package.resolve(strict=True)
        except (OSError, RuntimeError):
            raise self._verification_error() from None
        if (
            not isinstance(item, dict)
            or item.get("pkgName") != "appium-uiautomator2-driver"
            or item.get("version") != _COMBINATION.driver_version
            or item.get("installed") is not True
            or not isinstance(item.get("installPath"), str)
        ):
            raise self._verification_error()
        try:
            installed_path = Path(item["installPath"]).resolve(strict=True)
            resolved_home = driver_home.resolve(strict=True)
        except (OSError, RuntimeError):
            raise self._verification_error() from None
        if installed_path != expected_path or not installed_path.is_relative_to(
            resolved_home
        ):
            raise self._verification_error()
        settings = self.runtime._settings
        self.operation.settings = LocalSettings(
            appium_executable=appium_entry,
            appium_home=driver_home,
            node_executable=self.node.path if self.node is not None else None,
            npm_executable=self.npm.path if self.npm is not None else None,
            java_home=settings.java_home,
            android_sdk_root=settings.android_sdk_root,
            server_url=settings.server_url,
        )

    def _classify(
        self, record_state: Literal["absent", "complete", "failed"]
    ) -> Literal["full", "driver", "reuse", "promote"]:
        statuses = tuple(component.status for component in self.operation.before)
        for status, code in (
            ("conflict", "installation_version_conflict"),
            ("unknown", "installation_state_unknown"),
            ("damaged", "installation_damaged"),
        ):
            if status in statuses:
                raise self.operation.error(InstallationError, code)
        if statuses == ("missing", "missing"):
            return "full"
        if statuses == ("verified", "verified"):
            return "promote" if record_state == "failed" else "reuse"
        if statuses == ("verified", "missing") and record_state == "failed":
            return "driver"
        if set(statuses) == {"missing", "verified"}:
            raise self.operation.error(InstallationError, "installation_partial")
        raise self.operation.error(InstallationError, "installation_state_unknown")

    def _install_driver(self, environment: dict[str, str]) -> None:
        assert self.node is not None
        appium_entry = _paths(self.operation.root)[2] / "index.js"
        driver_environment = dict(environment)
        driver_environment["APPIUM_OMIT_PEER_DEPS"] = "1"
        self._checked(
            "driver_installation",
            [
                str(self.node.path),
                str(appium_entry),
                "driver",
                "install",
                f"uiautomator2@{_COMBINATION.driver_version}",
            ],
            driver_environment,
            component_writer=True,
        )

    def execute(self) -> InstallationResult:
        operation = self.operation
        operation.checkpoint()
        self._acquire()
        try:
            operation.checkpoint()
            if platform.system() != "Darwin":
                raise operation.error(InstallationError, "unsupported_host")
            exists = _validate_root(operation.root)
            operation.before = operation.after = _inspect_components(operation.root)
            record_state: Literal["absent", "complete", "failed"] = "absent"
            if exists:
                record_state = _record_state(operation.root, operation.before)
            action = self._classify(record_state)
            paths = tuple(os.environ.get("PATH", "").split(os.pathsep, 64))
            self._preflight(paths)
            environment = self._environment()
            if action in ("reuse", "promote"):
                self._verify(environment)
                if action == "promote":
                    _write_record(operation, "complete")
                result = operation.result("reused")
                self._release(None)
                return result
            if action == "driver":
                self._verify_partial(environment)
                self._prepare_root()
                self._install_driver(environment)
            else:
                self._prepare_root()
                assert self.node is not None and self.npm is not None
                self._checked(
                    "appium_installation",
                    [
                        str(self.node.path),
                        str(self.npm.path),
                        "install",
                        "--global=false",
                        "--prefix",
                        str(operation.root / "appium"),
                        "--save-exact",
                        "--no-audit",
                        "--no-fund",
                        f"appium@{_COMBINATION.appium_version}",
                    ],
                    environment,
                    component_writer=True,
                )
                self._install_driver(environment)
            self._verify(environment)
            _write_record(operation, "complete")
            result = operation.result("installed")
            self._release(None)
            return result
        except _StateFailure as failure:
            error = operation.error(
                InstallationError,
                failure.code,
                "recovery_required"
                if failure.code == "installation_recovery_required"
                else "failed",
            )
            return self._fail(error)
        except BaseException as error:
            return self._fail(error)

    def _best_effort_after(self) -> None:
        try:
            self.operation.after = _inspect_components(self.operation.root)
        except (OSError, _StateFailure):
            self.operation.after = tuple(
                _unknown(component) for component in self.operation.before
            )

    def _fail(self, error: BaseException) -> InstallationResult:
        cleanup_deadline = time.monotonic() + 30.0
        cleanup_error: BaseException | None = None
        cleanup_pending = False
        recovery_required = False

        def check_cleanup() -> None:
            _cleanup_checkpoint(cleanup_deadline)

        try:
            check_cleanup()
            if self.handle is not None:
                if not self.handle.cleanup(cleanup_deadline, check_cleanup):
                    raise _CleanupIncomplete
                self.handle = None
            check_cleanup()
            self._best_effort_after()
            check_cleanup()
            recovery_required = any(
                component.status == "unknown" for component in self.operation.after
            )
            if self.intent_written:
                _atomic_json(
                    self.operation.root / "records" / "installation.json",
                    _record_value(
                        self.operation,
                        "recovery_required" if recovery_required else "failed",
                    ),
                    check_cleanup,
                )
            check_cleanup()
        except _CleanupIncomplete:
            cleanup_pending = True
            cleanup_error = self.operation.error(
                InstallationError, "installation_cleanup_pending", "cleanup_pending"
            )
        except BaseException as failure:
            cleanup_error = failure
            recovery_required = True
            cleanup_pending = self.handle is not None
        if cleanup_pending:
            self.runtime._installation_cleanup = self
        else:
            self._release(error)
            self.runtime._installing = False
        if isinstance(error, RuntimeOperationError):
            prior = error.installation_result
            outcome: InstallationOutcome
            if cleanup_pending:
                outcome = "cleanup_pending"
            elif recovery_required:
                outcome = "recovery_required"
            elif isinstance(error, OperationCancelledError):
                outcome = "cancelled"
            elif isinstance(error, OperationTimeoutError):
                outcome = "timed_out"
            elif prior is not None and prior.outcome == "recovery_required":
                outcome = "recovery_required"
            else:
                outcome = "failed"
            error.installation_result = self.operation.result(outcome)
        else:
            outcome = (
                "cleanup_pending"
                if cleanup_pending
                else "recovery_required"
                if recovery_required
                else "failed"
            )
            error.__dict__["installation_result"] = self.operation.result(outcome)
        if cleanup_error is not None:
            error.__dict__["runtime_installation_cleanup_error"] = cleanup_error
        raise error

    def cleanup(self, control: OperationControl) -> InstallationResult:
        operation = _InstallOperation(
            self.runtime, control, phase="cleaning_installation"
        )
        operation.before = self.operation.after
        operation.changed = self.operation.changed
        try:
            operation.checkpoint()
            if self.handle is not None:
                if not self.handle.cleanup(operation.deadline, operation.checkpoint):
                    raise operation.error(
                        InstallationError,
                        "installation_cleanup_pending",
                        "cleanup_pending",
                    )
                self.handle = None
            operation.checkpoint()
            operation.after = _inspect_components(operation.root)
            operation.checkpoint()
            recovery_required = any(
                component.status == "unknown" for component in operation.after
            )
            if self.intent_written:
                _atomic_json(
                    operation.root / "records" / "installation.json",
                    _record_value(
                        operation,
                        "recovery_required" if recovery_required else "failed",
                    ),
                    operation.checkpoint,
                )
            operation.checkpoint()
        except (OperationTimeoutError, OperationCancelledError) as primary:
            primary.installation_result = operation.result("cleanup_pending")
            raise
        except InstallationError as primary:
            if primary.code == "installation_cleanup_pending":
                primary.installation_result = operation.result("cleanup_pending")
                raise
            raise
        except BaseException as cleanup:
            recovery_error = operation.error(
                InstallationError,
                "installation_recovery_required",
                "recovery_required",
            )
            recovery_error.runtime_installation_cleanup_error = cleanup
            self._release(recovery_error)
            self.runtime._installation_cleanup = None
            self.runtime._installing = False
            raise recovery_error from None
        self._release(None)
        self.runtime._installation_cleanup = None
        self.runtime._installing = False
        return operation.result(
            "recovery_required" if recovery_required else "cleanup_completed"
        )


def install(
    runtime: Runtime, request: InstallRequest, control: OperationControl
) -> InstallationResult:
    operation = _InstallOperation(runtime, control)
    _ = request.combination_id
    if runtime._installing or runtime._active_thread is not None or runtime._diagnosing:
        raise operation.error(EnvironmentBusyError, "environment_busy")
    runtime._installing = True
    installer = _Installer(operation)
    try:
        return installer.execute()
    finally:
        if runtime._installation_cleanup is None:
            runtime._installing = False


def cleanup_installation(
    runtime: Runtime, control: OperationControl
) -> InstallationResult:
    pending = runtime._installation_cleanup
    if pending is not None:
        runtime._installation_cleanup = None
        try:
            return pending.cleanup(control)
        finally:
            if runtime._installing:
                runtime._installation_cleanup = pending
    operation = _InstallOperation(runtime, control, phase="cleaning_installation")
    if runtime._installing or runtime._active_thread is not None or runtime._diagnosing:
        raise operation.error(EnvironmentBusyError, "environment_busy")
    try:
        with _diagnostic_lock(operation, False):
            operation.checkpoint()
            if operation.root.exists() or operation.root.is_symlink():
                _validate_root(operation.root)
                operation.before = operation.after = _inspect_components(operation.root)
            outcome: InstallationOutcome = (
                "recovery_required"
                if any(component.status == "unknown" for component in operation.after)
                else "cleanup_completed"
            )
            return operation.result(outcome)
    except _StateFailure as failure:
        error = operation.error(
            InstallationError,
            failure.code,
            "recovery_required"
            if failure.code == "installation_recovery_required"
            else "failed",
        )
        cleanup = failure.__dict__.get("runtime_cleanup_error")
        if isinstance(cleanup, BaseException):
            error.__dict__["runtime_cleanup_error"] = cleanup
        raise error from None
