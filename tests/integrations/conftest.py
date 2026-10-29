from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import StdioServerParameters

TOOL_NAMES = (
    "appium.capabilities.get",
    "appium.runtime.check",
    "appium.devices.list",
    "appium.session.open",
    "appium.session.status",
    "appium.session.close",
)
AUTOMATION_STATUS = {
    "feature_qualification": "aif_01_to_10_individually_done",
    "module_state": "device_validation_blocked_known_clean",
    "module_done": False,
    "automatic_retry_authorized": False,
}
CANARY = "ACA_PRIVATE_CANARY_20261029"
SECRET_PATH = "/private/aca-secret/config-and-adb"

_LAUNCHER = r"""from __future__ import annotations

import json
import secrets
import os
import sys
import threading
import time
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from importlib.metadata import entry_points
from pathlib import Path
from types import SimpleNamespace
from typing import Any

EVENTS = Path(os.environ["ACA_TEST_EVENTS"])
MODE = os.environ.get("ACA_TEST_MODE", "normal")
RELEASE = Path(os.environ.get("ACA_TEST_RELEASE", str(EVENTS) + ".release"))
RELEASE_FIRST = Path(str(RELEASE) + ".first")
RELEASE_SECOND = Path(str(RELEASE) + ".second")
CANARY = os.environ.get("ACA_TEST_CANARY", "ACA_PRIVATE_CANARY_20261029")
SECRET = os.environ.get("ACA_TEST_SECRET", "/private/aca-secret/config-and-adb")
STDERR = os.environ.get("ACA_TEST_STDERR")
_STDERR_STREAM = None
if STDERR:
    _STDERR_STREAM = open(STDERR, "a", encoding="utf-8")
    os.dup2(_STDERR_STREAM.fileno(), 2)
_FORCED_HANDLES = iter(json.loads(os.environ.get("ACA_TEST_HANDLES", "[]")))
_REAL_TOKEN_URLSAFE = secrets.token_urlsafe


def controlled_token_urlsafe(byte_count: int = 32) -> str:
    if byte_count != 24:
        return _REAL_TOKEN_URLSAFE(byte_count)
    try:
        return str(next(_FORCED_HANDLES))
    except StopIteration:
        return _REAL_TOKEN_URLSAFE(byte_count)


secrets.token_urlsafe = controlled_token_urlsafe
_WRITE_LOCK = threading.Lock()
_BUSY_LOCK = threading.Lock()
_DEVICE_CALLS = 0


def record(event: str, **values: object) -> None:
    with _WRITE_LOCK, EVENTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"event": event, **values}, sort_keys=True) + "\n")

if MODE in {
    "cancel_stalled",
    "cancel_twice",
    "eof_stalled",
    "limiter_timeout",
    "runtime_limiter_busy",
    "open_stalled",
    "close_stalled",
    "runtime_exit_stalled",
    "runtime_exit_failure_stalled",
    "shutdown_provisional_invariant",
}:
    import anyio

    _REAL_MOVE_ON_AFTER = anyio.move_on_after
    _REAL_RUN_SYNC = anyio.to_thread.run_sync

    def accelerated_move_on_after(
        delay: float | None, shield: bool = False
    ) -> anyio.CancelScope:
        effective = 0.05 if delay == 30.0 else delay
        return _REAL_MOVE_ON_AFTER(effective, shield=shield)

    async def controlled_run_sync(
        function: object,
        *args: object,
        **kwargs: object,
    ) -> object:
        is_product_worker = (
            kwargs.get("abandon_on_cancel") is False
            and getattr(function, "__module__", None)
            == "appium_connect_agent.integrations._bridge"
            and getattr(function, "__qualname__", "")
            == "WorkerRegistry.run_budget.<locals>.invoke"
        )
        if is_product_worker and MODE == "shutdown_provisional_invariant":
            record("provisional_worker_failed")
            raise RuntimeError(f"{CANARY} {SECRET}")
        if is_product_worker and MODE == "limiter_timeout":
            record("limiter_queued")
            await anyio.sleep(0.1)
        elif is_product_worker and MODE == "runtime_limiter_busy":
            record("limiter_queued")
            while not RELEASE.exists():
                await anyio.sleep(0.01)
        try:
            result = await _REAL_RUN_SYNC(function, *args, **kwargs)
        except BaseException:
            if is_product_worker:
                record("worker_returned", outcome="error")
            raise
        if is_product_worker:
            record("worker_returned", outcome="success")
        return result

    anyio.move_on_after = accelerated_move_on_after
    if MODE in {
        "limiter_timeout",
        "runtime_limiter_busy",
        "open_stalled",
        "close_stalled",
        "runtime_exit_stalled",
        "runtime_exit_failure_stalled",
        "shutdown_provisional_invariant",
    }:
        anyio.to_thread.run_sync = controlled_run_sync
    if MODE in {"cancel_stalled", "cancel_twice", "eof_stalled"}:
        record("server_started", pid=os.getpid())


import appium_connect_agent.automation as automation
import appium_connect_agent.runtime as runtime


def forbidden(*args: object, **kwargs: object) -> Any:
    record("forbidden_io")
    raise AssertionError("bootstrap reached a forbidden dependency")


if MODE == "forbid":
    runtime.Runtime.diagnose = forbidden
    runtime.Runtime.connect = forbidden
    automation.list_devices = forbidden
    import mcp.server as mcp_server

    class ForbiddenServer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            record("transport_constructed")
            raise AssertionError("bootstrap constructed MCP transport")

    mcp_server.MCPServer = ForbiddenServer
elif MODE != "passthrough":
    from appium_connect_agent.automation import (
        CommandError,
        DeviceInfo,
        OperationCancelledError as AutomationCancelledError,
        OperationTimeoutError as AutomationTimeoutError,
        ResourceStateError,
        SessionInfo,
    )
    from appium_connect_agent.runtime import (
        DiagnosticCheck,
        DiagnosticReport,
        EnvironmentBusyError,
        OperationTimeoutError as RuntimeTimeoutError,
    )

    def report(maximum: bool = False) -> DiagnosticReport:
        observed = datetime(2026, 10, 29, 12, 30, tzinfo=UTC)
        if MODE.startswith("invalid_report_"):
            check_id = "c" * (129 if MODE == "invalid_report_check_id" else 1)
            reason = "r" * (129 if MODE == "invalid_report_reason" else 1)
            evidence_count = 9 if MODE == "invalid_report_evidence_count" else 1
            evidence_size = 513 if MODE == "invalid_report_evidence_item" else 1
            remediation_size = 513 if MODE == "invalid_report_remediation" else 1
            evidence_value = (
                "\ud800"
                if MODE == "invalid_report_evidence_utf8"
                else "e" * evidence_size
            )
            remediation_value = (
                "\ud800"
                if MODE == "invalid_report_remediation_utf8"
                else "m" * remediation_size
            )
            status = "broken" if MODE == "invalid_report_status" else "unknown"
            check = DiagnosticCheck(
                check_id,
                status,
                reason,
                tuple(evidence_value for _ in range(evidence_count)),
                remediation_value,
            )
            checks_count = 33 if MODE == "invalid_report_checks_count" else 1
            observer_count = 9 if MODE == "invalid_report_observer_count" else 1
            observer_size = 513 if MODE == "invalid_report_observer_item" else 1
            observer_value = (
                "\ud800"
                if MODE == "invalid_report_observer_utf8"
                else "x" * observer_size
            )
            return DiagnosticReport(
                operation_id=(
                    "o" * 129
                    if MODE == "invalid_report_operation_id"
                    else "\ud800"
                    if MODE == "invalid_report_operation_utf8"
                    else "op_runtime_1"
                ),
                observed_at=observed,
                host="Linux" if MODE == "invalid_report_platform" else "macOS",
                checks=tuple(check for _ in range(checks_count)),
                observer_errors=tuple(
                    observer_value for _ in range(observer_count)
                ),
            )
        if not maximum:
            return DiagnosticReport(
                operation_id="op_runtime_1",
                observed_at=observed,
                checks=(
                    DiagnosticCheck(
                        "service", "pass", "service_ready", ("safe evidence",), None
                    ),
                ),
            )
        checks = tuple(
            DiagnosticCheck(
                ("c" * 124) + f"{index:04d}",
                "unknown",
                ("r" * 124) + f"{index:04d}",
                tuple("\U00010000" * 512 for _ in range(8)),
                "\U00010000" * 512,
            )
            for index in range(32)
        )
        return DiagnosticReport(
            operation_id="\U00010000" * 128,
            observed_at=observed,
            checks=checks,
            observer_errors=tuple("\U00010000" * 512 for _ in range(8)),
        )

    def control_values(control: object) -> dict[str, object]:
        return {
            "timeout": getattr(control, "timeout_seconds", None),
            "has_cancellation": isinstance(
                getattr(control, "cancellation", None), threading.Event
            ),
        }

    def diagnose(self: object, control: object = None) -> DiagnosticReport:
        record("runtime_diagnose", **control_values(control))
        if MODE == "runtime_known":
            current = report()
            error = RuntimeTimeoutError(
                "operation_timeout", current.operation_id, current
            )
            error.runtime_http_cleanup_error = RuntimeError(f"{CANARY} {SECRET}")
            raise error
        if MODE == "busy":
            if not _BUSY_LOCK.acquire(blocking=False):
                current = report()
                raise EnvironmentBusyError(
                    "environment_busy", current.operation_id, current
                )
            try:
                record("runtime_busy_entered")
                while not RELEASE.exists():
                    time.sleep(0.01)
            finally:
                _BUSY_LOCK.release()
        return report(MODE == "maximum")

    class ConnectionScope(AbstractContextManager[object]):
        def __init__(self, control: object) -> None:
            self.control = control

        def __enter__(self) -> object:
            record(
                "runtime_connect_enter",
                thread=threading.get_ident(),
                **control_values(self.control),
            )
            current = report(MODE == "maximum")
            if MODE == "runtime_enter_failure":
                raise RuntimeTimeoutError(
                    "operation_timeout", current.operation_id, current
                )
            return SimpleNamespace(
                ownership="external",
                appium_version=(
                    "v" * 129
                    if MODE == "invalid_connection_version"
                    else "\ud800"
                    if MODE == "invalid_connection_utf8"
                    else "\U00010000" * 128
                    if MODE == "maximum"
                    else "3.7.0"
                ),
                compatibility=(
                    "broken"
                    if MODE == "invalid_connection_compatibility"
                    else "declared_compatible"
                ),
                report=current,
            )

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            traceback: object,
        ) -> None:
            if MODE in {"runtime_exit_stalled", "runtime_exit_failure_stalled"}:
                record(
                    "runtime_connect_exit_entered",
                    thread=threading.get_ident(),
                    error=exc_type is not None,
                )
                while not RELEASE.exists():
                    time.sleep(0.01)
            record(
                "runtime_connect_exit",
                thread=threading.get_ident(),
                error=exc_type is not None,
            )
            if MODE in {"runtime_exit_failure", "runtime_exit_failure_stalled"}:
                raise RuntimeError(f"{CANARY} {SECRET}")

    def connect(self: object, control: object = None) -> ConnectionScope:
        record("runtime_connect", **control_values(control))
        return ConnectionScope(control)

    def devices(maximum: bool = False) -> tuple[DeviceInfo, ...]:
        if MODE == "empty":
            return ()
        if MODE == "invalid_device":
            return (DeviceInfo("d" * 1025, None, "connected"),)
        if MODE == "invalid_device_name":
            return (DeviceInfo("device", "n" * 1025, "connected"),)
        if MODE == "invalid_device_count":
            return tuple(
                DeviceInfo(f"device-{index}", None, "connected")
                for index in range(257)
            )
        if MODE == "invalid_device_id_whitespace":
            return (DeviceInfo("bad id", None, "connected"),)
        if MODE == "invalid_device_name_control":
            return (DeviceInfo("device", "bad\x00name", "connected"),)
        if MODE == "invalid_device_id_utf8":
            return (DeviceInfo("\ud800", None, "connected"),)
        if MODE == "invalid_device_name_utf8":
            return (DeviceInfo("device", "\ud800", "connected"),)
        if MODE == "invalid_device_state":
            return (DeviceInfo("device", None, "broken"),)
        if not maximum:
            return (
                DeviceInfo("alpha", "Pixel_8", "connected"),
                DeviceInfo("zeta", None, "unauthorized"),
            )
        return tuple(
            DeviceInfo(
                "\U00010000" * 1024,
                "\U00010000" * 1024,
                "connected",
            )
            for index in range(256)
        )

    def list_devices(adb_executable: Path, control: object = None) -> tuple[DeviceInfo, ...]:
        record(
            "list_devices",
            adb=str(adb_executable),
            **control_values(control),
        )
        if MODE == "unknown":
            raise RuntimeError(f"{CANARY} {SECRET}")
        if MODE == "known":
            raise CommandError(
                "adb_command_failed",
                "op_devices_1",
                "response_received",
                completed_steps=("adb_launched",),
                cleanup_errors=(RuntimeError(f"{CANARY} {SECRET}"),),
            )
        if MODE == "response_unknown":
            raise CommandError(
                "adb_response_unknown",
                "op_devices_unknown",
                "response_unknown",
                completed_steps=("adb_launched",),
            )
        if MODE == "timeout":
            timeout = float(getattr(control, "timeout_seconds"))
            time.sleep(min(timeout, 0.05))
            raise AutomationTimeoutError(
                "operation_timeout", "op_devices_timeout", "response_unknown"
            )
        if MODE in {
            "cancel",
            "late_success",
            "stalled",
            "cancel_stalled",
            "cancel_twice",
            "eof_stalled",
        }:
            global _DEVICE_CALLS
            _DEVICE_CALLS += 1
            call_index = _DEVICE_CALLS
            token = getattr(control, "cancellation")
            record("worker_entered", call_index=call_index)
            if MODE == "cancel_twice":
                release = RELEASE_FIRST if call_index == 1 else RELEASE_SECOND
            else:
                release = RELEASE
            while not token.is_set() and not release.exists():
                time.sleep(0.01)
            record(
                "worker_cancel_observed",
                call_index=call_index,
                cancelled=token.is_set(),
            )
            if MODE in {
                "stalled",
                "cancel_stalled",
                "cancel_twice",
                "eof_stalled",
            }:
                while not release.exists():
                    time.sleep(0.01)
            if MODE == "late_success":
                return devices()
            raise AutomationCancelledError(
                "operation_cancelled", "op_devices_cancel", "response_unknown"
            )
        return devices(MODE == "maximum")

    class FakeSession:
        def __init__(self, device_id: str, target_app_id: str | None) -> None:
            self.device_id = device_id
            self.target_app_id = target_app_id
            self.state = "active"
            self.busy = False

        def session_info(self) -> SessionInfo:
            record("session_info", state=self.state, busy=self.busy)
            return SessionInfo(
                id=f"automation-{CANARY}",
                appium_session_id=f"appium-{CANARY}",
                device_id=self.device_id,
                target_app_id=self.target_app_id,
                state=self.state,
                busy=self.busy,
            )

        def quit(self, *, control: object = None) -> None:
            record("session_quit", **control_values(control))
            self.busy = True
            if MODE in {"close_stalled", "shutdown_close_stalled"}:
                token = getattr(control, "cancellation")
                record("worker_entered", call_index=1)
                while not token.is_set() and not RELEASE.exists():
                    time.sleep(0.01)
                record("worker_cancel_observed", call_index=1, cancelled=token.is_set())
                while not RELEASE.exists():
                    time.sleep(0.01)
            if MODE == "shutdown_closing_invariant":
                self.state = "closing"
                raise RuntimeError(f"{CANARY} {SECRET}")
            if MODE in {"close_not_sent", "shutdown_close_cancelled"}:
                self.busy = False
                raise AutomationCancelledError(
                    "operation_cancelled",
                    "op-close-not-sent",
                    "not_sent",
                )
            if MODE == "shutdown_close_timeout":
                self.busy = False
                raise AutomationTimeoutError(
                    "operation_timeout",
                    "op-close-timeout",
                    "not_sent",
                )
            record("session_delete")
            if MODE in {"close_unknown", "shutdown_close_unknown"}:
                self.state = "uncertain"
                self.busy = False
                raise ResourceStateError(
                    "session_close_unknown",
                    "op-close-unknown",
                    "response_unknown",
                    session=self,
                    completed_steps=("quit_requested",),
                )
            if MODE in {"close_known", "shutdown_close_known"}:
                self.busy = False
                raise CommandError(
                    "session_quit_failed",
                    "op-close-known",
                    "response_received",
                    completed_steps=("quit_requested",),
                )
            if MODE in {"close_cleanup_failed", "shutdown_close_cleanup_failed"}:
                self.state = "uncertain"
                self.busy = False
                raise ResourceStateError(
                    "cleanup_failed",
                    "op-close-cleanup",
                    "response_unknown",
                    session=self,
                    completed_steps=("quit_requested",),
                    cleanup_errors=(RuntimeError(f"{CANARY} {SECRET}"),),
                )
            self.state = "closed"
            self.busy = False

    def create_session(
        connection: object,
        device_id: str,
        *,
        app_id: str | None = None,
        app_path: Path | None = None,
        auto_launch: bool = False,
        force_app_launch: bool = False,
        no_reset: bool = True,
        full_reset: bool = False,
        should_terminate_app: bool = False,
        new_command_timeout_seconds: float = 500,
        capabilities: object = None,
        control: object = None,
    ) -> FakeSession:
        del connection
        record(
            "create_session",
            device_id=device_id,
            app_id=app_id,
            app_path=None if app_path is None else str(app_path),
            auto_launch=auto_launch,
            force_app_launch=force_app_launch,
            no_reset=no_reset,
            full_reset=full_reset,
            should_terminate_app=should_terminate_app,
            new_command_timeout_seconds=new_command_timeout_seconds,
            capabilities=capabilities,
            **control_values(control),
        )
        target = app_id
        if app_path is not None:
            target = "resolved.from.path"
        session = FakeSession(device_id, target)
        if MODE == "open_stalled":
            token = getattr(control, "cancellation")
            record("worker_entered", call_index=1)
            while not token.is_set() and not RELEASE.exists():
                time.sleep(0.01)
            record("worker_cancel_observed", call_index=1, cancelled=token.is_set())
            while not RELEASE.exists():
                time.sleep(0.01)
        if MODE == "open_unknown":
            session.state = "uncertain"
            raise ResourceStateError(
                "session_create_unknown",
                "op-open-unknown",
                "response_unknown",
                session=session,
                completed_steps=("create_requested",),
            )
        if MODE == "open_not_sent":
            raise AutomationCancelledError(
                "operation_cancelled", "op-open-not-sent", "not_sent"
            )
        if MODE == "open_retained_not_sent":
            session.state = "uncertain"
            raise ResourceStateError(
                "cleanup_failed",
                "op-open-retained",
                "not_sent",
                session=session,
                cleanup_errors=(RuntimeError(f"{CANARY} {SECRET}"),),
            )
        if MODE == "open_known":
            raise CommandError(
                "session_not_created",
                "op-open-known",
                "response_received",
                completed_steps=("create_requested",),
            )
        return session

    automation.create_session = create_session
    runtime.Runtime.diagnose = diagnose
    runtime.Runtime.connect = connect
    automation.list_devices = list_devices

matches = [
    item
    for item in entry_points(group="console_scripts")
    if item.name == "appium-connect-agent-mcp"
]
if len(matches) != 1:
    raise RuntimeError("installed MCP entrypoint is not unique")
main = matches[0].load()
result = main()
if MODE in {"cancel_stalled", "cancel_twice", "eof_stalled"} or MODE.startswith(
    ("session_", "shutdown_", "open_", "close_", "runtime_exit_")
):
    record("server_stopped", result=result)
raise SystemExit(0 if result is None else result)
"""


@dataclass(frozen=True)
class McpHarness:
    root: Path
    launcher: Path
    config: Path
    adb: Path
    events_file: Path
    stderr_file: Path
    release_file: Path

    @property
    def python_command(self) -> str:
        return os.environ.get("ACA_MCP_TEST_PYTHON", sys.executable)

    def environment(self, mode: str = "normal") -> dict[str, str]:
        return {
            "ACA_TEST_MODE": mode,
            "ACA_TEST_EVENTS": str(self.events_file),
            "ACA_TEST_RELEASE": str(self.release_file),
            "ACA_TEST_CANARY": CANARY,
            "ACA_TEST_RELEASE_FIRST": str(self.release_file) + ".first",
            "ACA_TEST_RELEASE_SECOND": str(self.release_file) + ".second",
            "ACA_TEST_HANDLES": "[]",
            "ACA_TEST_SECRET": SECRET_PATH,
            "ACA_TEST_STDERR": str(self.stderr_file),
            "HOME": str(self.root / "home"),
            "PATH": os.environ.get("PATH", ""),
        }

    def arguments(
        self,
        *,
        config: Path | None = None,
        adb: Path | None = None,
        reverse: bool = False,
    ) -> list[str]:
        values = [
            "--config",
            str(config or self.config),
            "--adb-executable",
            str(adb or self.adb),
        ]
        return values[2:] + values[:2] if reverse else values

    def parameters(
        self,
        *,
        mode: str = "normal",
        args: list[str] | None = None,
        environment: dict[str, str] | None = None,
    ) -> StdioServerParameters:
        env = self.environment(mode)
        if environment:
            env.update(environment)
        return StdioServerParameters(
            command=self.python_command,
            args=[str(self.launcher), *(args or self.arguments())],
            env=env,
            cwd=self.root,
        )

    def run(
        self,
        args: list[str],
        *,
        mode: str = "forbid",
        environment: dict[str, str] | None = None,
        timeout: float = 5,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(self.environment(mode))
        if environment:
            env.update(environment)
        return subprocess.run(
            [self.python_command, str(self.launcher), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=self.root,
            env=env,
        )

    def events(self) -> list[dict[str, Any]]:
        if not self.events_file.exists():
            return []
        return [
            cast(dict[str, Any], json.loads(line))
            for line in self.events_file.read_text().splitlines()
        ]

    def reset_records(self) -> None:
        self.events_file.unlink(missing_ok=True)
        self.stderr_file.unlink(missing_ok=True)
        self.release_file.unlink(missing_ok=True)
        Path(str(self.release_file) + ".first").unlink(missing_ok=True)
        Path(str(self.release_file) + ".second").unlink(missing_ok=True)


@pytest.fixture
def mcp_harness(tmp_path: Path) -> McpHarness:
    launcher = tmp_path / "launch_mcp.py"
    launcher.write_text(_LAUNCHER, encoding="utf-8")
    config = tmp_path / "project.toml"
    config.write_text(
        '[runtime]\nserver_url = "http://127.0.0.1:4723"\n', encoding="utf-8"
    )
    adb = tmp_path / "adb"
    adb.write_text(
        "#!" + sys.executable + "\nraise SystemExit('unexpected real adb call')\n",
        encoding="utf-8",
    )
    adb.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    home = tmp_path / "home"
    home.mkdir()
    return McpHarness(
        root=tmp_path,
        launcher=launcher,
        config=config,
        adb=adb,
        events_file=tmp_path / "events.jsonl",
        stderr_file=tmp_path / "stderr.log",
        release_file=tmp_path / "release",
    )
