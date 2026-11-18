from __future__ import annotations

import json
import os
import socket
import socketserver
import threading
import time
from collections import deque
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import FrozenInstanceError, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import appium_connect_agent.automation._session as session_module
import appium_connect_agent.automation._session_coordination as automation_coordination
from appium_connect_agent.automation import (
    AutomationError,
    CommandError,
    ElementValidationError,
    InvalidRequestError,
    InvalidSessionStateError,
    OperationCancelledError,
    OperationTimeoutError,
    ResourceStateError,
    Session,
    SessionBusyError,
    SessionInfo,
    create_mac2_session,
    create_session,
    create_xcuitest_session,
)
from appium_connect_agent.automation._session_client import (
    _new_connection,
    _RequestCancelled,
    _RequestTimedOut,
)
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import (
    InvalidStateError,
    OperationControl,
    Runtime,
    RuntimeConnection,
    RuntimeUsage,
    _coordination,
)


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    headers: Mapping[str, str]
    body: Mapping[str, Any] | None


@dataclass
class ResponsePlan:
    status: int = 200
    payload: object = field(default_factory=lambda: {"value": None})
    started: threading.Event | None = None
    release: threading.Event | None = None
    delay_seconds: float = 0
    disconnect: bool = False


class IntSubclass(int):
    pass


class ProtocolService:
    def __init__(self, base_path: str = "/wd/hub") -> None:
        self.base_path = base_path
        self.requests: list[Request] = []
        self.create_plans: deque[ResponsePlan] = deque()
        self.quit_plans: deque[ResponsePlan] = deque()
        self._lock = threading.Lock()
        self._session_number = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                owner._handle(self)

            def do_POST(self) -> None:
                owner._handle(self)

            def do_DELETE(self) -> None:
                owner._handle(self)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        class _LocalHTTPServer(ThreadingHTTPServer):
            def server_bind(self) -> None:
                socketserver.TCPServer.server_bind(self)
                self.server_name = "127.0.0.1"
                self.server_port = self.server_address[1]

        self._server = _LocalHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )

    @property
    def url(self) -> str:
        host, port = cast(tuple[str, int], self._server.server_address)
        return f"http://{host}:{port}{self.base_path}"

    def __enter__(self) -> ProtocolService:
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        del exc_type, exc, traceback
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        assert not self._thread.is_alive()

    def _read_body(self, handler: BaseHTTPRequestHandler) -> Mapping[str, Any] | None:
        length = int(handler.headers.get("Content-Length", "0"))
        if length == 0:
            return None
        value = json.loads(handler.rfile.read(length))
        assert isinstance(value, dict)
        return cast(Mapping[str, Any], value)

    def _record(self, handler: BaseHTTPRequestHandler) -> None:
        request = Request(
            handler.command,
            handler.path,
            {key.lower(): value for key, value in handler.headers.items()},
            self._read_body(handler),
        )
        with self._lock:
            self.requests.append(request)

    def _next_plan(self, method: str) -> ResponsePlan:
        with self._lock:
            if method == "POST" and self.create_plans:
                return self.create_plans.popleft()
            if method == "DELETE" and self.quit_plans:
                return self.quit_plans.popleft()
            if method == "POST":
                self._session_number += 1
                return ResponsePlan(
                    payload={
                        "value": {
                            "sessionId": f"session-{self._session_number}",
                            "capabilities": {},
                        }
                    }
                )
            return ResponsePlan()

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        self._record(handler)
        if handler.command == "GET" and handler.path == f"{self.base_path}/status":
            self._send(
                handler,
                ResponsePlan(
                    payload={
                        "value": {
                            "ready": True,
                            "build": {"version": "3.1.0"},
                        }
                    }
                ),
            )
            return
        if handler.command == "POST" and handler.path != f"{self.base_path}/session":
            self._send(handler, ResponsePlan(status=404))
            return
        if handler.command == "DELETE" and not handler.path.startswith(
            f"{self.base_path}/session/"
        ):
            self._send(handler, ResponsePlan(status=404))
            return
        self._send(handler, self._next_plan(handler.command))

    def _send(self, handler: BaseHTTPRequestHandler, plan: ResponsePlan) -> None:
        if plan.started is not None:
            plan.started.set()
        if plan.release is not None:
            assert plan.release.wait(timeout=5)
        if plan.delay_seconds:
            time.sleep(plan.delay_seconds)
        if plan.disconnect:
            handler.close_connection = True
            with suppress(OSError):
                handler.connection.shutdown(socket.SHUT_RDWR)
            handler.connection.close()
            return
        if isinstance(plan.payload, bytes):
            data = plan.payload
            content_type = "text/plain"
        elif isinstance(plan.payload, str):
            data = plan.payload.encode("utf-8")
            content_type = "text/plain"
        else:
            data = json.dumps(plan.payload).encode("utf-8")
            content_type = "application/json"
        try:
            handler.send_response(plan.status)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def lifecycle_requests(self) -> list[Request]:
        with self._lock:
            return [request for request in self.requests if request.method != "GET"]


@pytest.fixture(autouse=True)
def isolated_runtime_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path.resolve() / "runtime-account"
    home.mkdir()
    monkeypatch.setattr(_coordination, "_account_home", lambda: home)


@pytest.fixture
def service() -> Iterator[ProtocolService]:
    with ProtocolService() as current:
        yield current


@contextmanager
def connected(service: ProtocolService) -> Iterator[RuntimeConnection]:
    runtime = Runtime(LocalSettings(server_url=service.url))
    with runtime.connect() as connection:
        yield connection


class UsageOwner:
    def __init__(self, connection: RuntimeConnection) -> None:
        self.connection = connection
        self.connection_active = True
        self.accepting = True
        self.count = 0
        self.events: list[str] = []
        self.terminal_failures: deque[BaseException] = deque()

    def acquire_usage(self) -> RuntimeUsage:
        if not self.accepting:
            raise InvalidStateError(
                "connection_closing",
                self.connection.report.operation_id,
                self.connection.report,
            )
        self.count += 1
        self.events.append("acquire")

        def release() -> None:
            self.count -= 1
            self.events.append("release")

        def begin_terminal_disposal() -> None:
            assert self.count > 0
            self.count -= 1
            self.accepting = False
            self.events.append("dispose_begin")

        def continue_terminal_disposal(control: OperationControl) -> None:
            del control
            self.events.append("dispose_continue")
            if self.terminal_failures:
                raise self.terminal_failures.popleft()

        return RuntimeUsage(
            release,
            self.connection.report.operation_id,
            self.connection.report,
            begin_terminal_disposal=begin_terminal_disposal,
            continue_terminal_disposal=continue_terminal_disposal,
        )


@contextmanager
def managed_connection(
    service: ProtocolService,
) -> Iterator[tuple[RuntimeConnection, UsageOwner]]:
    with connected(service) as external:
        managed = RuntimeConnection(
            cast(Any, None),
            external.server_url,
            external.appium_version,
            external.compatibility,
            external.report,
            "managed",
        )
        owner = UsageOwner(managed)
        object.__setattr__(managed, "_scope", owner)
        yield managed, owner


def create_response(
    session_id: object = "appium-session",
    capabilities: object = None,
    *,
    direct: bool = False,
) -> dict[str, object]:
    caps: object = {} if capabilities is None else capabilities
    if direct and isinstance(caps, dict):
        caps = {
            **caps,
            "directConnectProtocol": "http",
            "directConnectHost": "127.0.0.1",
            "directConnectPort": 9,
            "directConnectPath": "/untrusted",
        }
    return {"value": {"sessionId": session_id, "capabilities": caps}}


def error_response(message: str = "failed") -> dict[str, object]:
    return {
        "value": {
            "error": "session not created",
            "message": message,
            "stacktrace": "",
        }
    }


def assert_error(
    error: AutomationError,
    error_type: type[AutomationError],
    code: str,
    request_state: str,
    *,
    completed_steps: tuple[str, ...] = (),
    retains_session: bool = False,
) -> None:
    assert type(error) is error_type
    assert error.code == code
    assert error.request_state == request_state
    assert error.completed_steps == completed_steps
    assert (error.session is not None) is retains_session
    assert len(error.operation_id) == 32
    int(error.operation_id, 16)


def capture_session_states(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[Session, str]]:
    observed: list[tuple[Session, str]] = []
    original = cast(Any, Session)._set_state

    def record_state(session: Session, state: str) -> None:
        original(session, state)
        observed.append((session, state))

    monkeypatch.setattr(Session, "_set_state", record_state)
    return observed


def patch_create_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cancel: bool = False,
    timeout: bool = False,
    program_error: Exception | None = None,
    cleanup_error: Exception | None = None,
) -> None:
    original = _new_connection
    injected = False

    def controlled_connection(server_url: str) -> Any:
        nonlocal injected
        client = original(server_url)
        if injected:
            return client
        injected = True
        if cancel or timeout:

            def stop_before_request() -> None:
                if cancel:
                    raise _RequestCancelled
                raise _RequestTimedOut

            monkeypatch.setattr(client, "_apply_request_control", stop_before_request)
        if program_error is not None:

            def fail_before_request(command: str, params: dict[str, Any]) -> Any:
                del command, params
                raise program_error

            monkeypatch.setattr(client, "execute", fail_before_request)
        if cleanup_error is not None:

            def fail_clear() -> None:
                raise cleanup_error

            monkeypatch.setattr(client._conn, "clear", fail_clear)
        return client

    monkeypatch.setattr(
        "appium_connect_agent.automation._session._new_connection",
        controlled_connection,
    )


def patch_flaky_client_close(
    monkeypatch: pytest.MonkeyPatch, *, failures: int
) -> list[Any]:
    original = _new_connection
    captured: list[Any] = []

    def controlled_connection(server_url: str) -> Any:
        client = original(server_url)
        original_clear = client._conn.clear
        remaining = failures

        def flaky_clear() -> None:
            nonlocal remaining
            if remaining:
                remaining -= 1
                raise OSError("pool close failed")
            original_clear()

        monkeypatch.setattr(client._conn, "clear", flaky_clear)
        captured.append(client)
        return client

    monkeypatch.setattr(session_module, "_new_connection", controlled_connection)
    return captured


def test_automation_error_defaults_to_no_session() -> None:
    error = AutomationError("example", "0" * 32, "not_sent")

    assert error.session is None


def appium_caps(request: Request) -> Mapping[str, Any]:
    assert request.body is not None
    envelope = request.body["capabilities"]
    assert isinstance(envelope, dict)
    always_match = envelope["alwaysMatch"]
    assert isinstance(always_match, dict)
    return cast(Mapping[str, Any], always_match)


@pytest.mark.parametrize(
    ("use_app_id", "use_app_path"),
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_four_app_inputs_exact_capabilities_and_local_snapshot(
    service: ProtocolService,
    tmp_path: Path,
    use_app_id: bool,
    use_app_path: bool,
) -> None:
    apk = tmp_path / "sample.apk"
    apk.write_bytes(b"not parsed by Automation")
    app_id = "com.example.app" if use_app_id else None
    app_path = apk if use_app_path else None
    response_package = "com.detected.app"
    service.create_plans.append(
        ResponsePlan(
            payload=create_response(
                capabilities={"appium:appPackage": response_package},
                direct=True,
            )
        )
    )

    with connected(service) as connection:
        session = create_session(
            connection,
            "device-1",
            app_id=app_id,
            app_path=app_path,
            auto_launch=False,
            force_app_launch=True,
            no_reset=False,
            full_reset=True,
            should_terminate_app=True,
            new_command_timeout_seconds=0,
            capabilities={
                "appium:deviceName": "Pixel",
                "appium:platformVersion": "16",
            },
        )
        info = session.session_info()
        assert isinstance(session, Session)
        assert info == SessionInfo(
            id=info.id,
            appium_session_id="appium-session",
            device_id="device-1",
            target_app_id=app_id or response_package,
            state="active",
            busy=False,
        )
        with pytest.raises(FrozenInstanceError):
            info.state = "closed"  # type: ignore[misc]
        session.quit()

    create_request, quit_request = service.lifecycle_requests()
    assert create_request.method == "POST"
    assert create_request.path == "/wd/hub/session"
    assert "x-idempotency-key" in create_request.headers
    assert quit_request.method == "DELETE"
    assert quit_request.path == "/wd/hub/session/appium-session"
    assert "x-idempotency-key" not in quit_request.headers
    caps = appium_caps(create_request)
    assert caps == {
        "platformName": "Android",
        "appium:automationName": "UiAutomator2",
        "appium:udid": "device-1",
        "appium:autoLaunch": False,
        "appium:forceAppLaunch": True,
        "appium:noReset": False,
        "appium:fullReset": True,
        "appium:shouldTerminateApp": True,
        "appium:newCommandTimeout": 0.0,
        "appium:systemPort": 8200,
        "appium:settings[enableMultiWindows]": True,
        "appium:deviceName": "Pixel",
        "appium:platformVersion": "16",
        **({"appium:appPackage": app_id} if app_id is not None else {}),
        **({"appium:app": str(apk)} if app_path is not None else {}),
    }


@pytest.mark.parametrize(
    "idle_timeout",
    [0, 1, 1_000, 10_000, 9_007_199_254_740_991],
)
def test_wait_for_idle_timeout_is_an_exact_initial_setting(
    service: ProtocolService, idle_timeout: int
) -> None:
    with connected(service) as connection:
        session = create_session(
            connection,
            "device-1",
            uiautomator2_wait_for_idle_timeout_ms=idle_timeout,
        )
        session.quit()

    assert [(request.method, request.path) for request in service.requests] == [
        ("GET", "/wd/hub/status"),
        ("POST", "/wd/hub/session"),
        ("DELETE", "/wd/hub/session/session-1"),
    ]
    create_request = service.lifecycle_requests()[0]
    value = appium_caps(create_request)["appium:settings[waitForIdleTimeout]"]
    assert type(value) is int
    assert value == idle_timeout


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"device_id": ""}, "invalid_argument"),
        ({"device_id": "has space"}, "invalid_argument"),
        ({"device_id": "x" * 1025}, "invalid_argument"),
        ({"device_id": "ok", "app_id": "bad\n"}, "invalid_argument"),
        ({"device_id": "ok", "auto_launch": 1}, "invalid_argument"),
        ({"device_id": "ok", "force_app_launch": None}, "invalid_argument"),
        ({"device_id": "ok", "no_reset": True, "full_reset": True}, "invalid_argument"),
        ({"device_id": "ok", "new_command_timeout_seconds": -1}, "invalid_argument"),
        (
            {"device_id": "ok", "uiautomator2_wait_for_idle_timeout_ms": True},
            "invalid_argument",
        ),
        (
            {
                "device_id": "ok",
                "uiautomator2_wait_for_idle_timeout_ms": IntSubclass(1),
            },
            "invalid_argument",
        ),
        (
            {"device_id": "ok", "uiautomator2_wait_for_idle_timeout_ms": 1.0},
            "invalid_argument",
        ),
        (
            {"device_id": "ok", "uiautomator2_wait_for_idle_timeout_ms": "1"},
            "invalid_argument",
        ),
        (
            {"device_id": "ok", "uiautomator2_wait_for_idle_timeout_ms": -1},
            "invalid_argument",
        ),
        (
            {
                "device_id": "ok",
                "uiautomator2_wait_for_idle_timeout_ms": 9_007_199_254_740_992,
            },
            "invalid_argument",
        ),
        (
            {"device_id": "ok", "new_command_timeout_seconds": float("nan")},
            "invalid_argument",
        ),
        (
            {"device_id": "ok", "capabilities": {"appium:systemPort": 9000}},
            "unsupported_operation",
        ),
        (
            {
                "device_id": "ok",
                "capabilities": {"appium:settings[waitForIdleTimeout]": "1000"},
            },
            "unsupported_operation",
        ),
        (
            {"device_id": "ok", "capabilities": {"platformName": "Android"}},
            "unsupported_operation",
        ),
        (
            {"device_id": "ok", "capabilities": {"appium:deviceName": ""}},
            "invalid_argument",
        ),
    ],
)
def test_invalid_values_and_capabilities_never_send_create(
    service: ProtocolService, kwargs: dict[str, Any], code: str
) -> None:
    invalid_connection = cast(RuntimeConnection, object())
    with pytest.raises(InvalidRequestError) as caught:
        create_session(invalid_connection, **kwargs)
    assert_error(caught.value, InvalidRequestError, code, "not_sent")

    with connected(service) as connection:
        with pytest.raises(InvalidRequestError) as caught:
            create_session(connection, **kwargs)
        assert_error(caught.value, InvalidRequestError, code, "not_sent")
    assert service.lifecycle_requests() == []


@pytest.mark.parametrize("name", ["relative.apk", "bundle.apks", "UPPER.APK"])
def test_invalid_app_paths_are_rejected_before_request(
    service: ProtocolService, tmp_path: Path, name: str
) -> None:
    path = Path(name) if name == "relative.apk" else tmp_path / name
    if path.is_absolute():
        path.write_bytes(b"content")
    with connected(service) as connection:
        with pytest.raises(InvalidRequestError) as caught:
            create_session(connection, "device", app_path=path)
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
    assert service.lifecycle_requests() == []


def test_missing_directory_and_unreadable_app_paths_are_rejected(
    service: ProtocolService, tmp_path: Path
) -> None:
    missing = tmp_path / "missing.apk"
    directory = tmp_path / "directory.apk"
    directory.mkdir()
    unreadable = tmp_path / "unreadable.apk"
    unreadable.write_bytes(b"content")
    unreadable.chmod(0)
    try:
        with connected(service) as connection:
            for path in (missing, directory, unreadable):
                with pytest.raises(InvalidRequestError):
                    create_session(connection, "device", app_path=path)
    finally:
        unreadable.chmod(0o600)
    assert service.lifecycle_requests() == []


def test_same_device_is_busy_and_ports_are_unique_then_reused(
    service: ProtocolService,
) -> None:
    with connected(service) as connection:
        first = create_session(connection, "device-a")
        with pytest.raises(ResourceStateError) as caught:
            create_session(connection, "device-a")
        assert_error(caught.value, ResourceStateError, "device_busy", "not_sent")
        assert caught.value.session is None
        second = create_session(connection, "device-b")
        requests = [
            request
            for request in service.lifecycle_requests()
            if request.method == "POST"
        ]
        assert [appium_caps(request)["appium:systemPort"] for request in requests] == [
            8200,
            8201,
        ]
        first.quit()
        replacement = create_session(connection, "device-a")
        requests = [
            request
            for request in service.lifecycle_requests()
            if request.method == "POST"
        ]
        assert appium_caps(requests[-1])["appium:systemPort"] == 8200
        replacement.quit()
        second.quit()


def test_all_one_hundred_system_ports_are_reserved_before_failure(
    service: ProtocolService,
) -> None:
    sessions: list[Session] = []
    with connected(service) as connection:
        for index in range(100):
            sessions.append(create_session(connection, f"device-{index}"))
        with pytest.raises(ResourceStateError) as caught:
            create_session(connection, "device-overflow")
        assert_error(
            caught.value,
            ResourceStateError,
            "system_port_unavailable",
            "not_sent",
        )
        create_requests = [
            request
            for request in service.lifecycle_requests()
            if request.method == "POST"
        ]
        assert len(create_requests) == 100
        assert {
            appium_caps(request)["appium:systemPort"] for request in create_requests
        } == set(range(8200, 8300))
        for session in sessions:
            session.quit()


def test_session_identity_error_precedes_reservation_and_client(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    defect = OSError("session identity failed")
    original_uuid4 = cast(Any, session_module).uuid4
    original_connection = _new_connection
    uuid_injected = False
    client_calls = 0

    def fail_first_identity() -> Any:
        nonlocal uuid_injected
        if not uuid_injected:
            uuid_injected = True
            raise defect
        return original_uuid4()

    def observe_connection(server_url: str) -> Any:
        nonlocal client_calls
        client_calls += 1
        return original_connection(server_url)

    monkeypatch.setattr(session_module, "uuid4", fail_first_identity)
    monkeypatch.setattr(
        "appium_connect_agent.automation._session._new_connection",
        observe_connection,
    )
    with connected(service) as connection:
        with pytest.raises(OSError) as caught:
            create_session(connection, "identity-error-device")
        assert caught.value is defect
        assert caught.value.__cause__ is None
        assert not hasattr(caught.value, "automation_cleanup_errors")
        assert client_calls == 0
        assert service.lifecycle_requests() == []

        replacement = create_session(connection, "identity-error-device")
        replacement.quit()
        assert client_calls == 1
        requests = service.lifecycle_requests()
        assert [request.method for request in requests] == ["POST", "DELETE"]
        assert appium_caps(requests[0])["appium:systemPort"] == 8200


def test_connection_factory_error_releases_reserved_resources(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    defect = RuntimeError("connection factory failed")
    original = _new_connection
    injected = False

    def fail_first_factory(server_url: str) -> Any:
        nonlocal injected
        if not injected:
            injected = True
            raise defect
        return original(server_url)

    monkeypatch.setattr(
        "appium_connect_agent.automation._session._new_connection",
        fail_first_factory,
    )
    with connected(service) as connection:
        with pytest.raises(RuntimeError) as caught:
            create_session(connection, "factory-error-device")
        assert caught.value is defect
        assert caught.value.__cause__ is None
        assert not hasattr(caught.value, "automation_cleanup_errors")
        assert service.lifecycle_requests() == []

        replacement = create_session(connection, "factory-error-device")
        replacement.quit()
        requests = service.lifecycle_requests()
        assert [request.method for request in requests] == ["POST", "DELETE"]
        assert appium_caps(requests[0])["appium:systemPort"] == 8200


@pytest.mark.parametrize("stage", ["device", "options", "prepare"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_stable_session_setup_error_cleanup_resource_outcome(
    service: ProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    cleanup_fails: bool,
) -> None:
    defect = RuntimeError(f"{stage} setup failed")
    cleanup = OSError("pool clear failed")
    original_connection = _new_connection
    captured_clients: list[Any] = []
    connection_injected = False

    def controlled_connection(server_url: str) -> Any:
        nonlocal connection_injected
        client = original_connection(server_url)
        if connection_injected:
            return client
        connection_injected = True
        captured_clients.append(client)
        if stage == "prepare":

            def fail_prepare(cancellation: Any, deadline: Any) -> None:
                del cancellation, deadline
                raise defect

            monkeypatch.setattr(client, "prepare_request", fail_prepare)
        if cleanup_fails:

            def fail_clear() -> None:
                raise cleanup

            monkeypatch.setattr(client._conn, "clear", fail_clear)
        return client

    monkeypatch.setattr(
        "appium_connect_agent.automation._session._new_connection",
        controlled_connection,
    )
    stage_injected = False
    if stage == "device":
        original_device = cast(Any, session_module)._create_device

        def fail_device(session: Session) -> Any:
            nonlocal stage_injected
            if not stage_injected:
                stage_injected = True
                raise defect
            return original_device(session)

        monkeypatch.setattr(
            "appium_connect_agent.automation._session._create_device", fail_device
        )
    elif stage == "options":
        original_options = session_module._build_options

        def fail_options(*args: Any, **kwargs: Any) -> Any:
            nonlocal stage_injected
            if not stage_injected:
                stage_injected = True
                raise defect
            return original_options(*args, **kwargs)

        monkeypatch.setattr(
            "appium_connect_agent.automation._session._build_options", fail_options
        )

    session_states = capture_session_states(monkeypatch)
    with connected(service) as connection:
        if not cleanup_fails:
            with pytest.raises(RuntimeError) as program_error_caught:
                create_session(connection, "setup-error-device")
            assert program_error_caught.value is defect
            assert program_error_caught.value.__cause__ is None
            assert not hasattr(program_error_caught.value, "automation_cleanup_errors")
            assert session_states[-1][1] == "closed"
            assert captured_clients[0]._closed is True
            assert captured_clients[0].cleanup_errors == ()
            assert service.lifecycle_requests() == []

            replacement = create_session(connection, "setup-error-device")
            replacement.quit()
            requests = service.lifecycle_requests()
            assert [request.method for request in requests] == ["POST", "DELETE"]
            assert appium_caps(requests[0])["appium:systemPort"] == 8200
            return

        with pytest.raises(ResourceStateError) as resource_error_caught:
            create_session(connection, "setup-error-device")
        assert_error(
            resource_error_caught.value,
            ResourceStateError,
            "cleanup_failed",
            "not_sent",
            retains_session=True,
        )
        assert resource_error_caught.value.cleanup_errors == (cleanup,)
        assert resource_error_caught.value.__cause__ is defect
        retained = resource_error_caught.value.session
        assert retained is not None
        assert session_states[-1] == (retained, "uncertain")
        assert retained.session_info().state == "uncertain"
        assert captured_clients[0]._closed is False
        assert captured_clients[0].cleanup_errors == (cleanup,)
        assert service.lifecycle_requests() == []

        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "setup-error-device")
        assert_error(busy.value, ResourceStateError, "device_busy", "not_sent")
        other = create_session(connection, "other-device")
        create_requests = [
            request
            for request in service.lifecycle_requests()
            if request.method == "POST"
        ]
        assert len(create_requests) == 1
        assert appium_caps(create_requests[0])["appium:systemPort"] == 8201
        other.quit()


def test_terminal_create_error_closes_client_and_releases_ownership(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_states = capture_session_states(monkeypatch)
    service.create_plans.append(
        ResponsePlan(status=500, payload=error_response("cannot create"))
    )
    with connected(service) as connection:
        with pytest.raises(CommandError) as caught:
            create_session(connection, "terminal-device")
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        assert caught.value.cleanup_errors == ()
        assert caught.value.__cause__ is not None
        assert session_states[-1][1] == "closed"
        replacement = create_session(connection, "terminal-device")
        replacement.quit()
        create_requests = [
            request
            for request in service.lifecycle_requests()
            if request.method == "POST"
        ]
        assert [
            appium_caps(request)["appium:systemPort"] for request in create_requests
        ] == [8200, 8200]
        assert [request.method for request in service.lifecycle_requests()] == [
            "POST",
            "POST",
            "DELETE",
        ]


def test_terminal_create_error_keeps_ownership_when_client_cleanup_fails(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleanup = OSError("pool clear failed")
    patch_create_client(monkeypatch, cleanup_error=cleanup)
    service.create_plans.append(
        ResponsePlan(status=500, payload=error_response("cannot create"))
    )
    with connected(service) as connection:
        with pytest.raises(CommandError) as caught:
            create_session(connection, "create-cleanup-device")
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            retains_session=True,
        )
        assert caught.value.cleanup_errors == (cleanup,)
        assert caught.value.__cause__ is not None
        retained = caught.value.session
        assert retained is not None
        assert retained.session_info().state == "uncertain"
        with pytest.raises(InvalidSessionStateError) as invalid:
            retained.quit()
        assert_error(
            invalid.value,
            InvalidSessionStateError,
            "session_invalid",
            "not_sent",
        )
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "create-cleanup-device")
        assert_error(busy.value, ResourceStateError, "device_busy", "not_sent")
        assert len(service.lifecycle_requests()) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"value": {"capabilities": {}}},
        create_response(session_id=7, capabilities={}),
        create_response(session_id="known-id", capabilities=[]),
    ],
)
def test_malformed_success_is_uncertain_and_keeps_ownership(
    service: ProtocolService, payload: object
) -> None:
    service.create_plans.append(ResponsePlan(payload=payload))
    with connected(service) as connection:
        with pytest.raises(ResourceStateError) as caught:
            create_session(connection, "unknown-shape-device")
        error = caught.value
        assert_error(
            error,
            ResourceStateError,
            "session_create_unknown",
            "response_received",
            retains_session=True,
        )
        assert error.session is not None
        assert error.cleanup_errors == ()
        assert error.__cause__ is not None
        assert error.session.session_info().state == "uncertain"
        with pytest.raises(InvalidSessionStateError):
            error.session.quit()
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "unknown-shape-device")
        assert busy.value.code == "device_busy"
        assert len(service.lifecycle_requests()) == 1


@pytest.mark.parametrize(
    ("status", "payload"),
    [(401, "Authorization Required"), (500, b"<html>failure</html>")],
)
def test_non_w3c_http_error_is_unknown_and_keeps_ownership(
    service: ProtocolService, status: int, payload: str | bytes
) -> None:
    service.create_plans.append(ResponsePlan(status=status, payload=payload))
    with connected(service) as connection:
        with pytest.raises(ResourceStateError) as caught:
            create_session(connection, "non-w3c-device")
        assert_error(
            caught.value,
            ResourceStateError,
            "session_create_unknown",
            "response_unknown",
            retains_session=True,
        )
        assert caught.value.session is not None
        assert caught.value.session.session_info().state == "uncertain"
        assert caught.value.cleanup_errors == ()
        assert caught.value.__cause__ is not None
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "non-w3c-device")
        assert busy.value.code == "device_busy"
        assert len(service.lifecycle_requests()) == 1


@pytest.mark.parametrize(
    "plan",
    [ResponsePlan(disconnect=True), ResponsePlan(delay_seconds=0.2)],
)
def test_unknown_create_transport_is_not_retried_or_released(
    service: ProtocolService, plan: ResponsePlan
) -> None:
    service.create_plans.append(plan)
    with connected(service) as connection:
        with pytest.raises(ResourceStateError) as caught:
            create_session(
                connection,
                "transport-device",
                control=OperationControl(timeout_seconds=0.05),
            )
        assert_error(
            caught.value,
            ResourceStateError,
            "session_create_unknown",
            "response_unknown",
            retains_session=True,
        )
        assert caught.value.session is not None
        assert caught.value.session.session_info().state == "uncertain"
        assert caught.value.cleanup_errors == ()
        assert caught.value.__cause__ is not None
        assert len(service.lifecycle_requests()) == 1
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "transport-device")
        assert busy.value.code == "device_busy"


@pytest.mark.parametrize(
    ("preflight", "error_type", "code", "cause_type"),
    [
        (
            "cancel",
            OperationCancelledError,
            "operation_cancelled",
            _RequestCancelled,
        ),
        ("timeout", OperationTimeoutError, "operation_timeout", _RequestTimedOut),
    ],
)
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_pre_request_cancel_or_timeout_cleanup_resource_outcome(
    service: ProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    preflight: str,
    error_type: type[AutomationError],
    code: str,
    cause_type: type[Exception],
    cleanup_fails: bool,
) -> None:
    session_states = capture_session_states(monkeypatch)
    cancellation = threading.Event()
    cleanup = OSError("pool clear failed")
    patch_create_client(
        monkeypatch,
        cancel=preflight == "cancel",
        timeout=preflight == "timeout",
        cleanup_error=cleanup if cleanup_fails else None,
    )
    control = OperationControl(timeout_seconds=1, cancellation=cancellation)
    with connected(service) as connection:
        with pytest.raises(error_type) as caught:
            create_session(connection, "preflight-device", control=control)
        assert_error(
            caught.value,
            error_type,
            code,
            "not_sent",
            retains_session=cleanup_fails,
        )
        assert caught.value.cleanup_errors == ((cleanup,) if cleanup_fails else ())
        assert type(caught.value.__cause__) is cause_type
        assert session_states[-1][1] == ("uncertain" if cleanup_fails else "closed")
        assert service.lifecycle_requests() == []
        if cleanup_fails:
            retained = caught.value.session
            assert retained is not None
            assert session_states[-1][0] is retained
            assert retained.session_info().state == "uncertain"
            with pytest.raises(ResourceStateError) as busy:
                create_session(connection, "preflight-device")
            assert_error(busy.value, ResourceStateError, "device_busy", "not_sent")
            assert service.lifecycle_requests() == []
        else:
            replacement = create_session(connection, "preflight-device")
            replacement.quit()
            assert [request.method for request in service.lifecycle_requests()] == [
                "POST",
                "DELETE",
            ]


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_pre_request_program_error_cleanup_resource_outcome(
    service: ProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_fails: bool,
) -> None:
    session_states = capture_session_states(monkeypatch)
    defect = RuntimeError("driver setup failed")
    cleanup = OSError("pool clear failed")
    patch_create_client(
        monkeypatch,
        program_error=defect,
        cleanup_error=cleanup if cleanup_fails else None,
    )
    with connected(service) as connection:
        if not cleanup_fails:
            with pytest.raises(RuntimeError) as program_error_caught:
                create_session(connection, "program-error-device")
            assert program_error_caught.value is defect
            assert not hasattr(program_error_caught.value, "automation_cleanup_errors")
            assert service.lifecycle_requests() == []
            assert session_states[-1][1] == "closed"
            replacement = create_session(connection, "program-error-device")
            replacement.quit()
            assert [request.method for request in service.lifecycle_requests()] == [
                "POST",
                "DELETE",
            ]
            return

        with pytest.raises(ResourceStateError) as resource_error_caught:
            create_session(connection, "program-error-device")
        assert_error(
            resource_error_caught.value,
            ResourceStateError,
            "cleanup_failed",
            "not_sent",
            retains_session=True,
        )
        assert resource_error_caught.value.cleanup_errors == (cleanup,)
        assert resource_error_caught.value.__cause__ is defect
        retained = resource_error_caught.value.session
        assert retained is not None
        assert session_states[-1][0] is retained
        assert retained.session_info().state == "uncertain"
        assert service.lifecycle_requests() == []
        assert session_states[-1][1] == "uncertain"
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "program-error-device")
        assert_error(busy.value, ResourceStateError, "device_busy", "not_sent")
        assert service.lifecycle_requests() == []


def test_cancellation_after_successful_response_does_not_erase_create(
    service: ProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    cancellation = threading.Event()
    service.create_plans.append(
        ResponsePlan(
            payload=create_response(),
            started=started,
            release=release,
        )
    )
    result: list[Session] = []
    failures: list[BaseException] = []

    with connected(service) as connection:

        def create() -> None:
            try:
                result.append(
                    create_session(
                        connection,
                        "cancel-after-response",
                        control=OperationControl(
                            timeout_seconds=2, cancellation=cancellation
                        ),
                    )
                )
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=create)
        worker.start()
        assert started.wait(timeout=1)
        cancellation.set()
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert failures == []
        assert result[0].session_info().state == "active"
        result[0].quit()


def test_creating_state_is_local_while_real_create_request_is_in_flight(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.create_plans.append(
        ResponsePlan(payload=create_response(), started=started, release=release)
    )
    captured: list[Session] = []
    result: list[Session] = []
    failures: list[BaseException] = []
    original = Session._creating

    def capture(cls: type[Session], *args: Any, **kwargs: Any) -> Session:
        del cls
        session = original(*args, **kwargs)
        captured.append(session)
        return session

    monkeypatch.setattr(Session, "_creating", classmethod(capture))
    with connected(service) as connection:

        def create() -> None:
            try:
                result.append(create_session(connection, "creating-device"))
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=create)
        worker.start()
        assert started.wait(timeout=1)
        assert captured[0].session_info().state == "creating"
        assert captured[0].session_info().busy is False
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert failures == []
        assert result[0] is captured[0]
        assert result[0].session_info().state == "active"
        result[0].quit()


def test_session_info_is_network_free_and_closed_quit_is_idempotent(
    service: ProtocolService,
) -> None:
    with connected(service) as connection:
        session = create_session(connection, "snapshot-device")
        count = len(service.lifecycle_requests())
        first = session.session_info()
        second = session.session_info()
        assert first == second
        assert len(service.lifecycle_requests()) == count
        session.quit()
        client = cast(Any, session)._client
        assert session.session_info().state == "closed"
        assert client._closed is True
        session.quit()
        assert len(service.lifecycle_requests()) == count + 1
    session.quit()
    assert session.session_info().state == "closed"


@pytest.mark.parametrize(
    "plan",
    [
        ResponsePlan(status=500, payload=error_response("delete failed")),
        ResponsePlan(disconnect=True),
        ResponsePlan(delay_seconds=0.2),
    ],
)
def test_quit_failure_or_unknown_retains_uncertain_session_and_ownership(
    service: ProtocolService, plan: ResponsePlan
) -> None:
    service.quit_plans.append(plan)
    with connected(service) as connection:
        session = create_session(connection, "quit-unknown-device")
        with pytest.raises(ResourceStateError) as caught:
            session.quit(control=OperationControl(timeout_seconds=0.05))
        expected_state = (
            "response_received" if plan.status == 500 else "response_unknown"
        )
        assert_error(
            caught.value,
            ResourceStateError,
            "session_quit_unknown",
            expected_state,
        )
        assert caught.value.session is None
        assert session.session_info().state == "uncertain"
        with pytest.raises(InvalidSessionStateError) as second:
            session.quit()
        assert_error(
            second.value,
            InvalidSessionStateError,
            "session_invalid",
            "not_sent",
        )
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "quit-unknown-device")
        assert busy.value.code == "device_busy"
        assert (
            len(
                [
                    request
                    for request in service.lifecycle_requests()
                    if request.method == "DELETE"
                ]
            )
            == 1
        )


def test_successful_delete_with_cleanup_failure_preserves_completed_fact(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = OSError("pool clear failed")
    with connected(service) as connection:
        session = create_session(connection, "cleanup-device")
        client = cast(Any, session)._client

        def fail_clear() -> None:
            raise failure

        monkeypatch.setattr(client._conn, "clear", fail_clear)
        with pytest.raises(ResourceStateError) as caught:
            session.quit()
        assert_error(
            caught.value,
            ResourceStateError,
            "cleanup_failed",
            "response_received",
            completed_steps=("session_deleted",),
        )
        assert caught.value.cleanup_errors == (failure,)
        assert session.session_info().state == "uncertain"
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "cleanup-device")
        assert busy.value.code == "device_busy"


def test_primary_quit_error_is_not_replaced_by_cleanup_error(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.quit_plans.append(
        ResponsePlan(status=500, payload=error_response("delete failed"))
    )
    cleanup = OSError("pool clear failed")
    with connected(service) as connection:
        session = create_session(connection, "double-error-device")
        client = cast(Any, session)._client

        def fail_clear() -> None:
            raise cleanup

        monkeypatch.setattr(client._conn, "clear", fail_clear)
        with pytest.raises(ResourceStateError) as caught:
            session.quit()
        assert_error(
            caught.value,
            ResourceStateError,
            "session_quit_unknown",
            "response_received",
        )
        assert caught.value.cleanup_errors == (cleanup,)
        assert caught.value.__cause__ is not None


def test_overlapping_quit_is_immediately_busy_and_sends_no_second_delete(
    service: ProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.quit_plans.append(ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = create_session(connection, "busy-session-device")

        def quit_first() -> None:
            try:
                session.quit()
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=quit_first)
        worker.start()
        assert started.wait(timeout=1)
        info = session.session_info()
        assert info.state == "closing"
        assert info.busy is True
        with pytest.raises(SessionBusyError) as caught:
            session.quit()
        assert_error(caught.value, SessionBusyError, "session_busy", "not_sent")
        assert (
            len(
                [
                    request
                    for request in service.lifecycle_requests()
                    if request.method == "DELETE"
                ]
            )
            == 1
        )
        release.set()
        worker.join(timeout=2)
        assert failures == []
        assert session.session_info().state == "closed"


def test_different_sessions_have_independent_lifecycle_gates(
    service: ProtocolService,
) -> None:
    started_a = threading.Event()
    started_b = threading.Event()
    release = threading.Event()
    service.quit_plans.extend(
        [
            ResponsePlan(started=started_a, release=release),
            ResponsePlan(started=started_b, release=release),
        ]
    )
    failures: list[BaseException] = []
    with connected(service) as connection:
        first = create_session(connection, "parallel-a")
        second = create_session(connection, "parallel-b")

        def quit(session: Session) -> None:
            try:
                session.quit()
            except BaseException as error:
                failures.append(error)

        workers = [
            threading.Thread(target=quit, args=(first,)),
            threading.Thread(target=quit, args=(second,)),
        ]
        assert first.session_info().id != second.session_info().id
        assert (
            first.session_info().appium_session_id
            != second.session_info().appium_session_id
        )
        for worker in workers:
            worker.start()
        assert started_a.wait(timeout=1)
        assert started_b.wait(timeout=1)
        release.set()
        for worker in workers:
            worker.join(timeout=2)
            assert not worker.is_alive()
        assert failures == []
        assert first.session_info().state == "closed"
        assert second.session_info().state == "closed"


def test_pre_request_quit_cancel_keeps_session_active_for_later_quit(
    service: ProtocolService,
) -> None:
    cancellation = threading.Event()
    cancellation.set()
    with connected(service) as connection:
        session = create_session(connection, "quit-cancel-device")
        with pytest.raises(OperationCancelledError) as caught:
            session.quit(
                control=OperationControl(timeout_seconds=1, cancellation=cancellation)
            )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
        )
        assert session.session_info().state == "active"
        assert (
            len(
                [
                    request
                    for request in service.lifecycle_requests()
                    if request.method == "DELETE"
                ]
            )
            == 0
        )
        session.quit()
        assert session.session_info().state == "closed"


def test_create_and_existing_session_reject_closed_runtime_without_request(
    service: ProtocolService,
) -> None:
    runtime = Runtime(LocalSettings(server_url=service.url))
    with runtime.connect() as connection:
        session = create_session(connection, "closed-runtime-existing")
    before = len(service.lifecycle_requests())

    with pytest.raises(InvalidSessionStateError) as existing:
        session.quit()
    assert_error(
        existing.value,
        InvalidSessionStateError,
        "session_invalid",
        "not_sent",
    )
    assert session.session_info().state == "uncertain"
    assert len(service.lifecycle_requests()) == before

    with pytest.raises(InvalidSessionStateError) as new:
        create_session(connection, "closed-runtime-new")
    assert_error(
        new.value,
        InvalidSessionStateError,
        "session_invalid",
        "not_sent",
    )
    assert len(service.lifecycle_requests()) == before


def test_direct_connection_response_never_switches_runtime_endpoint(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setenv("NO_PROXY", "")
    service.create_plans.append(ResponsePlan(payload=create_response(direct=True)))
    with connected(service) as connection:
        session = create_session(connection, "direct-response-device")
        session.quit()
    assert [request.path for request in service.lifecycle_requests()] == [
        "/wd/hub/session",
        "/wd/hub/session/appium-session",
    ]


def test_managed_usage_is_acquired_before_reservation_and_released_after_quit(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    with managed_connection(service) as (connection, owner):
        original = cast(Any, session_module)._reserve

        def reserve(device_id: str) -> Any:
            assert owner.count == 1
            owner.events.append("reserve")
            return original(device_id)

        monkeypatch.setattr(session_module, "_reserve", reserve)
        session = create_session(connection, "managed-device")
        assert owner.count == 1
        session.quit()
        assert owner.count == 0
        assert owner.events == ["acquire", "reserve", "release"]


@pytest.mark.parametrize(
    ("stage", "failure"),
    [
        ("creating", RuntimeError("identity construction failed")),
        ("creating", KeyboardInterrupt()),
        ("reservation", RuntimeError("reservation initialization failed")),
    ],
    ids=("creating-error", "creating-keyboard-interrupt", "reservation-error"),
)
def test_managed_zero_request_create_failures_release_usage(
    service: ProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    failure: BaseException,
) -> None:
    if stage == "creating":

        def fail_creating(*args: object, **kwargs: object) -> Session:
            del args, kwargs
            raise failure

        monkeypatch.setattr(Session, "_creating", classmethod(fail_creating))
    else:

        def fail_reservation(device_id: str) -> Any:
            del device_id
            raise failure

        monkeypatch.setattr(session_module, "_reserve", fail_reservation)

    with managed_connection(service) as (connection, owner):
        with pytest.raises(type(failure)) as caught:
            create_session(connection, "managed-zero-request-failure")
        assert caught.value is failure
        assert owner.count == 0
        assert owner.events == ["acquire", "release"]
        assert service.lifecycle_requests() == []


@pytest.mark.parametrize("preflight", ["cancel", "timeout"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_managed_preflight_failure_usage_count(
    service: ProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    preflight: str,
    cleanup_fails: bool,
) -> None:
    cleanup = OSError("pool close failed")
    patch_create_client(
        monkeypatch,
        cancel=preflight == "cancel",
        timeout=preflight == "timeout",
        cleanup_error=cleanup if cleanup_fails else None,
    )
    expected = (
        OperationCancelledError if preflight == "cancel" else OperationTimeoutError
    )
    with managed_connection(service) as (connection, owner):
        with pytest.raises(expected) as caught:
            create_session(connection, f"managed-{preflight}")
        assert owner.count == (1 if cleanup_fails else 0)
        assert (caught.value.session is not None) is cleanup_fails
        assert service.lifecycle_requests() == []


def test_managed_terminal_not_created_cleanup_failure_retains_usage(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleanup = OSError("pool close failed")
    service.create_plans.append(
        ResponsePlan(status=500, payload=error_response("terminal"))
    )
    patch_create_client(monkeypatch, cleanup_error=cleanup)
    with managed_connection(service) as (connection, owner):
        with pytest.raises(CommandError) as caught:
            create_session(connection, "managed-terminal-cleanup")
        assert caught.value.request_state == "response_received"
        assert caught.value.cleanup_errors == (cleanup,)
        assert caught.value.session is not None
        assert owner.count == 1


def test_managed_terminal_create_releases_but_unknown_retains_usage(
    service: ProtocolService,
) -> None:
    service.create_plans.extend(
        [
            ResponsePlan(status=500, payload=error_response("terminal")),
            ResponsePlan(disconnect=True),
        ]
    )
    with managed_connection(service) as (connection, owner):
        with pytest.raises(CommandError):
            create_session(connection, "managed-terminal")
        assert owner.count == 0

        with pytest.raises(ResourceStateError) as unknown:
            create_session(connection, "managed-unknown")
        assert unknown.value.code == "session_create_unknown"
        assert unknown.value.session is not None
        assert owner.count == 1


def test_managed_cleanup_failure_and_closing_mapping_retain_usage(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleanup = OSError("pool close failed")
    with managed_connection(service) as (connection, owner):
        session = create_session(connection, "managed-cleanup")
        client = cast(Any, session)._client

        def fail_clear() -> None:
            raise cleanup

        monkeypatch.setattr(client._conn, "clear", fail_clear)
        with pytest.raises(ResourceStateError) as failed:
            session.quit()
        assert failed.value.code == "cleanup_failed"
        assert owner.count == 1

        owner.accepting = False
        with pytest.raises(InvalidSessionStateError) as closing:
            create_session(connection, "managed-closing")
        assert closing.value.code == "session_invalid"
        assert closing.value.request_state == "not_sent"
        assert owner.count == 1
        assert [request.method for request in service.lifecycle_requests()].count(
            "POST"
        ) == 1


def test_uncertain_managed_session_dispose_is_terminal_and_idempotent(
    service: ProtocolService,
) -> None:
    service.create_plans.append(ResponsePlan(disconnect=True))
    with managed_connection(service) as (connection, owner):
        with pytest.raises(ResourceStateError) as unknown:
            create_session(connection, "managed-dispose")
        session = unknown.value.session
        assert session is not None
        assert session.session_info().state == "uncertain"

        session.dispose()

        assert session.session_info().state == "disposed"
        assert owner.count == 0
        assert owner.events == ["acquire", "dispose_begin", "dispose_continue"]
        assert [request.method for request in service.lifecycle_requests()] == ["POST"]
        session.dispose()
        assert owner.events == ["acquire", "dispose_begin", "dispose_continue"]


def test_managed_session_dispose_retries_cleanup_without_releasing_twice(
    service: ProtocolService,
) -> None:
    service.quit_plans.append(ResponsePlan(disconnect=True))
    with managed_connection(service) as (connection, owner):
        session = create_session(connection, "managed-dispose-retry")
        with pytest.raises(ResourceStateError):
            session.quit()
        owner.terminal_failures.append(
            InvalidStateError(
                "cleanup_pending",
                connection.report.operation_id,
                connection.report,
            )
        )

        with pytest.raises(ResourceStateError) as pending:
            session.dispose()
        assert pending.value.code == "terminal_disposal_pending"
        assert session.session_info().state == "disposing"
        assert owner.count == 0

        session.dispose()

        assert session.session_info().state == "disposed"
        assert owner.events == [
            "acquire",
            "dispose_begin",
            "dispose_continue",
            "dispose_continue",
        ]
        assert [request.method for request in service.lifecycle_requests()] == [
            "POST",
            "DELETE",
        ]


def test_external_uncertain_session_rejects_terminal_disposal_without_request(
    service: ProtocolService,
) -> None:
    service.create_plans.append(ResponsePlan(disconnect=True))
    with connected(service) as connection:
        with pytest.raises(ResourceStateError) as unknown:
            create_session(connection, "external-dispose")
        session = unknown.value.session
        assert session is not None

        with pytest.raises(InvalidSessionStateError) as unsupported:
            session.dispose()

        assert unsupported.value.code == "unsupported_connection_ownership"
        assert session.session_info().state == "uncertain"
        assert [request.method for request in service.lifecycle_requests()] == ["POST"]


def test_dispose_pre_cancel_preserves_uncertain_session_and_usage(
    service: ProtocolService,
) -> None:
    service.create_plans.append(ResponsePlan(disconnect=True))
    cancellation = threading.Event()
    cancellation.set()
    with managed_connection(service) as (connection, owner):
        with pytest.raises(ResourceStateError) as unknown:
            create_session(connection, "managed-dispose-cancel")
        session = unknown.value.session
        assert session is not None

        with pytest.raises(OperationCancelledError) as cancelled:
            session.dispose(control=OperationControl(cancellation=cancellation))

        assert cancelled.value.session is session
        assert session.session_info().state == "uncertain"
        assert owner.count == 1
        assert owner.events == ["acquire"]


def test_dispose_pre_timeout_retains_session_and_usage(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.create_plans.append(ResponsePlan(disconnect=True))
    with managed_connection(service) as (connection, owner):
        with pytest.raises(ResourceStateError) as unknown:
            create_session(connection, "managed-dispose-timeout")
        session = unknown.value.session
        assert session is not None
        ticks = iter((10.0, 12.0))
        session_time = cast(Any, session_module).time
        monkeypatch.setattr(session_time, "monotonic", lambda: next(ticks))

        with pytest.raises(OperationTimeoutError) as timed_out:
            session.dispose(control=OperationControl(timeout_seconds=1))

        assert timed_out.value.session is session
        assert session.session_info().state == "uncertain"
        assert owner.count == 1
        assert owner.events == ["acquire"]


def test_dispose_retries_failed_local_client_close_before_runtime_cleanup(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = patch_flaky_client_close(monkeypatch, failures=2)
    service.create_plans.append(ResponsePlan(disconnect=True))
    with managed_connection(service) as (connection, owner):
        with pytest.raises(ResourceStateError) as unknown:
            create_session(connection, "managed-dispose-local-close")
        session = unknown.value.session
        assert session is not None
        assert len(captured) == 1
        assert captured[0].locally_closed is False

        with pytest.raises(ResourceStateError) as pending:
            session.dispose()

        assert pending.value.code == "terminal_disposal_pending"
        assert pending.value.session is session
        assert len(pending.value.cleanup_errors) == 1
        assert session.session_info().state == "disposing"
        assert owner.count == 1
        assert owner.events == ["acquire"]

        session.dispose()

        assert captured[0].locally_closed is True
        assert session.session_info().state == "disposed"
        assert owner.count == 0
        assert owner.events == ["acquire", "dispose_begin", "dispose_continue"]


def test_dispose_timeout_after_local_close_stays_disposing_and_retries(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = patch_flaky_client_close(monkeypatch, failures=1)
    service.create_plans.append(ResponsePlan(disconnect=True))
    with managed_connection(service) as (connection, owner):
        with pytest.raises(ResourceStateError) as unknown:
            create_session(connection, "managed-dispose-close-timeout")
        session = unknown.value.session
        assert session is not None
        original_monotonic = time.monotonic
        ticks = iter((10.0, 10.0, 12.0))
        session_time = cast(Any, session_module).time
        monkeypatch.setattr(session_time, "monotonic", lambda: next(ticks))

        with pytest.raises(OperationTimeoutError) as timed_out:
            session.dispose(control=OperationControl(timeout_seconds=1))

        assert timed_out.value.session is session
        assert captured[0].locally_closed is True
        assert session.session_info().state == "disposing"
        assert owner.count == 1
        assert owner.events == ["acquire"]

        monkeypatch.setattr(session_time, "monotonic", original_monotonic)
        session.dispose()

        assert session.session_info().state == "disposed"
        assert owner.count == 0


def test_session_constructor_is_not_a_public_creation_path() -> None:
    with pytest.raises(TypeError):
        Session()


def test_mac2_capabilities_single_host_and_android_independence(
    service: ProtocolService,
) -> None:
    service.create_plans.append(
        ResponsePlan(
            payload=create_response(
                capabilities={"CFBundleIdentifier": "com.apple.Calculator"}
            )
        )
    )
    with connected(service) as connection:
        mac = create_mac2_session(
            connection,
            arguments=["--safe"],
            bundle_id="com.apple.Calculator",
            no_reset=False,
            skip_app_kill=True,
            show_server_logs=True,
            server_startup_timeout_ms=12_000,
            new_command_timeout_seconds=0,
        )
        android = create_session(connection, "android-device")
        assert mac.platform == "macos"
        assert mac.session_info().platform == "macos"
        assert mac.session_info().device_id == "macos:local"
        assert mac.session_info().target_app_id == "com.apple.Calculator"
        assert android.session_info().platform == "android"
        with pytest.raises(ResourceStateError) as busy:
            create_mac2_session(connection)
        assert_error(busy.value, ResourceStateError, "device_busy", "not_sent")
        mac.quit()
        replacement = create_mac2_session(connection)
        replacement.quit()
        android.quit()

    creates = [
        request for request in service.lifecycle_requests() if request.method == "POST"
    ]
    assert appium_caps(creates[0]) == {
        "platformName": "Mac",
        "appium:automationName": "Mac2",
        "appium:arguments": ["--safe"],
        "appium:bundleId": "com.apple.Calculator",
        "appium:newCommandTimeout": 0.0,
        "appium:noReset": False,
        "appium:serverStartupTimeout": 12000,
        "appium:showServerLogs": True,
        "appium:skipAppKill": True,
        "appium:systemHost": "127.0.0.1",
        "appium:systemPort": 10100,
    }
    assert appium_caps(creates[1])["appium:systemPort"] == 8200
    assert appium_caps(creates[2])["appium:systemPort"] == 10100


@pytest.mark.parametrize(
    ("capabilities", "expected"),
    [
        (
            {
                "CFBundleIdentifier": "/Applications/Calculator.app",
                "appium:bundleId": "com.apple.Fallback",
                "bundleId": "com.apple.Last",
            },
            "com.apple.Fallback",
        ),
        (
            {
                "CFBundleIdentifier": "bad/value",
                "appium:bundleId": "应用.计算器",
                "bundleId": "com.apple.Last",
            },
            "com.apple.Last",
        ),
        (
            {
                "CFBundleIdentifier": "relative/path",
                "appium:bundleId": "com.apple/Calculator",
                "bundleId": "应用",
            },
            None,
        ),
    ],
)
def test_mac2_response_target_requires_ascii_bundle_grammar_and_falls_back(
    service: ProtocolService,
    capabilities: dict[str, object],
    expected: str | None,
) -> None:
    service.create_plans.append(
        ResponsePlan(payload=create_response(capabilities=capabilities))
    )
    with connected(service) as connection:
        session = create_mac2_session(connection)
        assert session.session_info().target_app_id == expected
        session.quit()


def test_mac2_app_bundle_and_inputs_are_validated_before_request(
    service: ProtocolService, tmp_path: Path
) -> None:
    app = tmp_path.resolve() / "Sample.app"
    contents = app / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(b"plist")
    with connected(service) as connection:
        session = create_mac2_session(connection, app_path=app, arguments=[])
        session.quit()
        before = list(service.lifecycle_requests())
        invalid = [
            {"bundle_id": "bad/value"},
            {"app_path": str(app)},
            {"arguments": []},
            {"arguments": ["x"], "bundle_id": None},
            {"no_reset": 1},
            {"skip_app_kill": 0},
            {"show_server_logs": 0},
            {"server_startup_timeout_ms": 999},
            {"new_command_timeout_seconds": True},
            {"new_command_timeout_seconds": 86_401},
        ]
        for kwargs in invalid:
            with pytest.raises(InvalidRequestError) as caught:
                create_mac2_session(connection, **kwargs)  # type: ignore[arg-type]
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
        assert service.lifecycle_requests() == before

    create = service.lifecycle_requests()[0]
    assert appium_caps(create)["appium:appPath"] == str(app)


def test_mac2_rejects_symlinked_app_ancestor_without_echo(
    service: ProtocolService, tmp_path: Path
) -> None:
    real = tmp_path.resolve() / "real"
    contents = real / "Sample.app" / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_bytes(b"plist")
    link = tmp_path.resolve() / "linked"
    link.symlink_to(real, target_is_directory=True)
    app = link / "Sample.app"
    with connected(service) as connection, pytest.raises(InvalidRequestError) as caught:
        create_mac2_session(connection, app_path=app)
    assert caught.value.code == "invalid_argument"
    assert str(app) not in str(caught.value)
    assert service.lifecycle_requests() == []


def test_mac2_locator_rules_and_android_only_device_action_are_zero_request(
    service: ProtocolService,
) -> None:
    with connected(service) as connection:
        session = create_mac2_session(connection)
        element = session.element("name", "result", predicate="label == 'Result'")
        assert element.predicate == "label == 'Result'"
        with pytest.raises(ElementValidationError) as packaged:
            session.element("id", "value", package="com.example")
        assert packaged.value.code == "unsupported_operation"
        with pytest.raises(ElementValidationError) as raw:
            session.element("id", "value", raw_id=True)
        assert raw.value.code == "unsupported_operation"
        with pytest.raises(ElementValidationError) as child_xpath:
            session.element("xpath", "//Button", parent=element)
        assert child_xpath.value.code == "unsupported_operation"
        before = list(service.lifecycle_requests())
        with pytest.raises(InvalidRequestError) as device:
            session.device.back()
        assert_error(
            device.value, InvalidRequestError, "unsupported_operation", "not_sent"
        )
        assert service.lifecycle_requests() == before
        session.quit()


def test_default_new_command_timeout_is_900_and_overrides_take_precedence(
    service: ProtocolService,
) -> None:
    with connected(service) as connection:
        default_session = create_session(connection, "timeout-default")
        default_session.quit()

        explicit_session = create_session(
            connection, "timeout-explicit", new_command_timeout_seconds=1200
        )
        explicit_session.quit()

        cap_session = create_session(
            connection,
            "timeout-cap",
            new_command_timeout_seconds=None,
            capabilities={"appium:newCommandTimeout": 1500},
        )
        cap_session.quit()

        bare_cap_session = create_session(
            connection,
            "timeout-bare-cap",
            new_command_timeout_seconds=None,
            capabilities={"newCommandTimeout": 1800, "deviceName": "Pixel"},
        )
        bare_cap_session.quit()

        both_session = create_session(
            connection,
            "timeout-both",
            new_command_timeout_seconds=600,
            capabilities={"appium:newCommandTimeout": 1500},
        )
        both_session.quit()

    creates = [
        request for request in service.lifecycle_requests() if request.method == "POST"
    ]
    assert [appium_caps(req)["appium:newCommandTimeout"] for req in creates] == [
        900.0,
        1200.0,
        1500.0,
        1800.0,
        600.0,
    ]
    assert appium_caps(creates[3])["appium:deviceName"] == "Pixel"


def configure_private_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    private_tmp = tmp_path / "private-tmp"
    private_tmp.mkdir(mode=0o700)
    private_tmp.chmod(0o1700)
    monkeypatch.setattr(automation_coordination, "_PRIVATE_TMP_OPEN_PATH", private_tmp)
    monkeypatch.setattr(automation_coordination, "_ROOT_UID", os.getuid())
    return private_tmp


def test_xcuitest_capabilities_coordination_and_release(
    service: ProtocolService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_tmp = configure_private_tmp(tmp_path, monkeypatch)
    app = tmp_path / "Sample.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(b"plist")
    service.create_plans.extend(
        [
            ResponsePlan(payload=create_response()),
            ResponsePlan(payload=create_response()),
        ]
    )

    with connected(service) as connection:
        session = create_xcuitest_session(
            connection,
            "00008030-TEST",
            bundle_id="com.example.ios",
            app_path=app,
            arguments=("--safe",),
            xcode_org_id="ORG_1",
            xcode_signing_id="Apple Development",
            updated_wda_bundle_id="com.example.wda",
            show_xcode_log=True,
            wda_launch_timeout_ms=60_000,
        )
        create = service.lifecycle_requests()[0]
        caps = appium_caps(create)
        assert caps == {
            "platformName": "iOS",
            "appium:automationName": "XCUITest",
            "appium:udid": "00008030-TEST",
            "appium:bundleId": "com.example.ios",
            "appium:app": str(app),
            "appium:processArguments": {"args": ["--safe"]},
            "appium:autoLaunch": True,
            "appium:forceAppLaunch": False,
            "appium:shouldTerminateApp": False,
            "appium:noReset": True,
            "appium:fullReset": False,
            "appium:showXcodeLog": True,
            "appium:newCommandTimeout": 300.0,
            "appium:wdaLocalPort": 8100,
            "appium:derivedDataPath": (
                f"/private/tmp/appium-connect-agent-{os.getuid()}"
                "/wda-derived-data/port-8100"
            ),
            "appium:xcodeOrgId": "ORG_1",
            "appium:xcodeSigningId": "Apple Development",
            "appium:updatedWDABundleId": "com.example.wda",
            "appium:wdaLaunchTimeout": 60_000,
        }
        assert session.session_info().platform == "ios"
        assert (
            private_tmp
            / f"appium-connect-agent-{os.getuid()}"
            / "wda-derived-data"
            / "port-8100"
        ).stat().st_mode & 0o777 == 0o700
        with pytest.raises(ResourceStateError) as busy:
            create_xcuitest_session(connection, "00008030-TEST")
        assert_error(busy.value, ResourceStateError, "device_busy", "not_sent")
        session.quit()
        replacement = create_xcuitest_session(connection, "00008030-TEST")
        replacement.quit()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"udid": "auto"},
        {"udid": "bad value"},
        {"udid": "valid", "bundle_id": "bad bundle"},
        {"udid": "valid", "wda_launch_timeout_ms": 999},
        {"udid": "valid", "show_xcode_log": 1},
        {"udid": "valid", "arguments": ("arg",)},
    ],
)
def test_xcuitest_invalid_values_are_private_and_zero_request(
    service: ProtocolService, kwargs: dict[str, Any]
) -> None:
    with connected(service) as connection, pytest.raises(InvalidRequestError) as caught:
        create_xcuitest_session(connection, **kwargs)
    assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
    assert str(caught.value) == "invalid_argument"
    assert service.lifecycle_requests() == []


def test_xcuitest_coordination_rejects_untrusted_private_tmp_and_releases(
    service: ProtocolService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_tmp = configure_private_tmp(tmp_path, monkeypatch)
    private_tmp.chmod(0o700)
    with connected(service) as connection, pytest.raises(ResourceStateError) as caught:
        create_xcuitest_session(connection, "DEVICE-A")
    assert_error(
        caught.value, ResourceStateError, "coordination_unavailable", "not_sent"
    )
    assert service.lifecycle_requests() == []


def test_xcuitest_app_paths_reject_symlink_ancestors_without_echo(
    service: ProtocolService, tmp_path: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    app = real / "Secret.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(b"plist")
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    secret = linked / "Secret.app"

    with connected(service) as connection, pytest.raises(InvalidRequestError) as caught:
        create_xcuitest_session(connection, "DEVICE", app_path=secret)

    assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
    assert str(secret) not in str(caught.value)
    assert service.lifecycle_requests() == []


def test_xcuitest_coordinator_has_exact_independent_hundred_port_pool() -> None:
    coordinator = automation_coordination._Coordinator(8100, 8199)
    reservations = [coordinator.reserve(f"device-{index}") for index in range(100)]
    assert [item.system_port for item in reservations] == list(range(8100, 8200))
    with pytest.raises(automation_coordination._SystemPortUnavailable):
        coordinator.reserve("overflow")
    for reservation in reservations:
        reservation.release()


def assert_private_exception_chain(
    error: BaseException, canaries: tuple[str, ...]
) -> None:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        text = f"{current!s}\n{current!r}"
        assert all(canary not in text for canary in canaries)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
        if isinstance(current, AutomationError):
            pending.extend(current.cleanup_errors)


def test_xcuitest_accepts_regular_ipa_and_rejects_wrong_ipa_kinds(
    service: ProtocolService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_private_tmp(tmp_path, monkeypatch)
    ipa = tmp_path / "Sample.ipa"
    ipa.write_bytes(b"signed")
    with connected(service) as connection:
        session = create_xcuitest_session(connection, "DEVICE", app_path=ipa)
        session.quit()

        directory = tmp_path / "Directory.ipa"
        directory.mkdir()
        target = tmp_path / "Target.ipa"
        target.write_bytes(b"signed")
        symlink = tmp_path / "Linked.ipa"
        symlink.symlink_to(target)
        unreadable = tmp_path / "Unreadable.ipa"
        unreadable.write_bytes(b"signed")
        original_access = cast(Any, session_module).os.access
        for invalid in (directory, symlink, unreadable):
            if invalid == unreadable:
                monkeypatch.setattr(
                    cast(Any, session_module).os,
                    "access",
                    lambda path, mode: (
                        False if path == unreadable else original_access(path, mode)
                    ),
                )
            with pytest.raises(InvalidRequestError) as caught:
                create_xcuitest_session(connection, "DEVICE", app_path=invalid)
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
            assert str(invalid) not in str(caught.value)
            monkeypatch.setattr(cast(Any, session_module).os, "access", original_access)
    assert [request.method for request in service.lifecycle_requests()] == [
        "POST",
        "DELETE",
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"udid": cast(Any, None)},
        {"udid": ""},
        {"udid": "A" * 129},
        {"udid": "dévïce"},
        {"udid": "AuTo"},
        {"udid": "DEVICE", "bundle_id": cast(Any, 1)},
        {"udid": "DEVICE", "updated_wda_bundle_id": "bad bundle"},
        {"udid": "DEVICE", "app_path": cast(Any, "/tmp/Test.ipa")},
        {"udid": "DEVICE", "app_path": Path("Test.ipa")},
        {"udid": "DEVICE", "arguments": cast(Any, "arg")},
        {"udid": "DEVICE", "arguments": ["arg"] * 65, "bundle_id": "com.a"},
        {"udid": "DEVICE", "arguments": [cast(Any, 1)], "bundle_id": "com.a"},
        {"udid": "DEVICE", "arguments": ["bad\0arg"], "bundle_id": "com.a"},
        {"udid": "DEVICE", "arguments": ["\ud800"], "bundle_id": "com.a"},
        {"udid": "DEVICE", "auto_launch": cast(Any, 1)},
        {"udid": "DEVICE", "force_app_launch": cast(Any, 0)},
        {"udid": "DEVICE", "should_terminate_app": cast(Any, "false")},
        {"udid": "DEVICE", "no_reset": cast(Any, None)},
        {"udid": "DEVICE", "show_xcode_log": cast(Any, 1)},
        {"udid": "DEVICE", "xcode_org_id": cast(Any, 1)},
        {"udid": "DEVICE", "xcode_org_id": ""},
        {"udid": "DEVICE", "xcode_org_id": "A" * 65},
        {"udid": "DEVICE", "xcode_org_id": "bad.id"},
        {"udid": "DEVICE", "xcode_signing_id": cast(Any, 1)},
        {"udid": "DEVICE", "xcode_signing_id": ""},
        {"udid": "DEVICE", "xcode_signing_id": "A" * 129},
        {"udid": "DEVICE", "xcode_signing_id": "bad\nvalue"},
        {"udid": "DEVICE", "wda_launch_timeout_ms": cast(Any, True)},
        {"udid": "DEVICE", "wda_launch_timeout_ms": 999},
        {"udid": "DEVICE", "wda_launch_timeout_ms": 600_001},
        {"udid": "DEVICE", "new_command_timeout_seconds": cast(Any, True)},
        {"udid": "DEVICE", "new_command_timeout_seconds": float("nan")},
        {"udid": "DEVICE", "new_command_timeout_seconds": -1},
        {"udid": "DEVICE", "new_command_timeout_seconds": 86_401},
        {"udid": "DEVICE", "control": cast(Any, object())},
    ],
)
def test_xcuitest_all_parameter_boundaries_are_private_and_not_sent(
    service: ProtocolService, kwargs: dict[str, Any]
) -> None:
    with connected(service) as connection, pytest.raises(InvalidRequestError) as caught:
        create_xcuitest_session(connection, **kwargs)
    assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert service.lifecycle_requests() == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "udid": "A",
            "bundle_id": "a.b",
            "arguments": [],
            "xcode_org_id": "A",
            "xcode_signing_id": "A",
            "wda_launch_timeout_ms": 1_000,
            "new_command_timeout_seconds": 0,
        },
        {
            "udid": "A" * 128,
            "bundle_id": "a.b",
            "arguments": ["x" * 4_096] * 64,
            "auto_launch": False,
            "force_app_launch": True,
            "should_terminate_app": True,
            "no_reset": False,
            "xcode_org_id": "A" * 64,
            "xcode_signing_id": "A" * 128,
            "updated_wda_bundle_id": "a.updated",
            "show_xcode_log": True,
            "wda_launch_timeout_ms": 600_000,
            "new_command_timeout_seconds": 86_400,
        },
    ],
    ids=("minimums", "maximums"),
)
def test_xcuitest_accepts_parameter_boundaries(
    service: ProtocolService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, Any],
) -> None:
    configure_private_tmp(tmp_path, monkeypatch)
    with connected(service) as connection:
        session = create_xcuitest_session(connection, **kwargs)
        session.quit()
    create = service.lifecycle_requests()[0]
    caps = appium_caps(create)
    assert caps["appium:wdaLaunchTimeout"] == kwargs["wda_launch_timeout_ms"]
    assert caps["appium:newCommandTimeout"] == float(
        kwargs["new_command_timeout_seconds"]
    )
    assert caps["appium:processArguments"] == {"args": kwargs["arguments"]}


def test_xcuitest_acquires_usage_before_reserving_wda_port(
    service: ProtocolService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_private_tmp(tmp_path, monkeypatch)
    with managed_connection(service) as (connection, owner):
        original = cast(Any, session_module)._reserve_xcuitest

        def reserve(udid: str) -> Any:
            assert owner.count == 1
            owner.events.append("reserve")
            return original(udid)

        monkeypatch.setattr(session_module, "_reserve_xcuitest", reserve)
        session = create_xcuitest_session(connection, "ORDER-DEVICE")
        session.quit()
        assert owner.events == ["acquire", "reserve", "release"]


@pytest.mark.parametrize("fault", ["symlink", "owner", "mode"])
@pytest.mark.parametrize("depth", [0, 1, 2])
def test_xcuitest_derived_data_rejects_untrusted_mutable_segments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    depth: int,
) -> None:
    private_tmp = configure_private_tmp(tmp_path, monkeypatch)
    segments = (
        f"appium-connect-agent-{os.getuid()}",
        "wda-derived-data",
        "port-8100",
    )
    parent = private_tmp
    for segment in segments[:depth]:
        parent /= segment
        parent.mkdir(mode=0o700)
    untrusted = parent / segments[depth]
    if fault == "symlink":
        target = tmp_path / f"target-{depth}"
        target.mkdir()
        untrusted.symlink_to(target, target_is_directory=True)
    elif fault == "mode":
        untrusted.mkdir(mode=0o755)
        untrusted.chmod(0o755)
        monkeypatch.setattr(
            cast(Any, automation_coordination).os,
            "fchmod",
            lambda fd, mode: None,
        )
    else:
        real_fstat = os.fstat
        calls = 0

        def foreign_owner(descriptor: int) -> Any:
            nonlocal calls
            calls += 1
            metadata = real_fstat(descriptor)
            if calls == 2 + depth:
                return SimpleNamespace(
                    st_mode=metadata.st_mode, st_uid=metadata.st_uid + 1
                )
            return metadata

        monkeypatch.setattr(
            cast(Any, automation_coordination).os, "fstat", foreign_owner
        )

    with pytest.raises(ResourceStateError) as caught:
        automation_coordination._prepare_xcuitest_derived_data(8100, "operation")
    assert caught.value.code == "coordination_unavailable"


@pytest.mark.parametrize("fault", ["fstat", "close", "fstat_close"])
def test_xcuitest_derived_data_descriptor_faults_close_every_open_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    configure_private_tmp(tmp_path, monkeypatch)
    real_open, real_fstat, real_close = os.open, os.fstat, os.close
    opened: list[int] = []
    close_attempts: list[int] = []
    leaked: list[int] = []
    fstat_calls = 0

    def tracked_open(*args: Any, **kwargs: Any) -> int:
        descriptor = real_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def controlled_fstat(descriptor: int) -> os.stat_result:
        nonlocal fstat_calls
        fstat_calls += 1
        if fault in {"fstat", "fstat_close"} and fstat_calls == 2:
            raise OSError("injected fstat failure")
        return real_fstat(descriptor)

    def controlled_close(descriptor: int) -> None:
        close_attempts.append(descriptor)
        if fault in {"close", "fstat_close"} and not leaked:
            leaked.append(descriptor)
            raise OSError("injected close fault containing SECRET_CANARY")
        real_close(descriptor)

    coordination_os = cast(Any, automation_coordination).os
    monkeypatch.setattr(coordination_os, "open", tracked_open)
    monkeypatch.setattr(coordination_os, "fstat", controlled_fstat)
    monkeypatch.setattr(coordination_os, "close", controlled_close)
    try:
        with pytest.raises(ResourceStateError) as caught:
            automation_coordination._prepare_xcuitest_derived_data(8100, "operation")
        error = caught.value
        assert error.code == "coordination_unavailable"
        assert error.request_state == "not_sent"
        if fault == "fstat":
            assert error.cleanup_errors == ()
        else:
            assert [str(item) for item in error.cleanup_errors] == [
                "descriptor_close_failed"
            ]
            assert error.__cause__ is None
            assert error.__context__ is None
            assert "SECRET_CANARY" not in repr(error.cleanup_errors)
        assert sorted(close_attempts) == sorted(opened)
    finally:
        for descriptor in leaked:
            real_close(descriptor)
    for descriptor in opened:
        with pytest.raises(OSError):
            real_fstat(descriptor)


def test_xcuitest_close_failure_releases_usage_and_reservation(
    service: ProtocolService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_private_tmp(tmp_path, monkeypatch)
    real_close = os.close
    leaked: list[int] = []
    close_attempts: list[int] = []

    def controlled_close(descriptor: int) -> None:
        close_attempts.append(descriptor)
        if not leaked:
            leaked.append(descriptor)
            raise OSError("injected close fault containing SECRET_CANARY")
        real_close(descriptor)

    coordination_os = cast(Any, automation_coordination).os
    monkeypatch.setattr(coordination_os, "close", controlled_close)
    try:
        with managed_connection(service) as (connection, owner):
            with pytest.raises(ResourceStateError) as caught:
                create_xcuitest_session(connection, "CLOSE-FAIL-DEVICE")
            error = caught.value
            assert_error(
                error,
                ResourceStateError,
                "coordination_unavailable",
                "not_sent",
            )
            assert error.cleanup_errors
            assert "SECRET_CANARY" not in repr(error.cleanup_errors)
            assert error.__cause__ is None and error.__context__ is None
            assert owner.count == 0
            assert owner.events == ["acquire", "release"]
            assert service.lifecycle_requests() == []

            monkeypatch.setattr(coordination_os, "close", real_close)
            replacement = create_xcuitest_session(connection, "CLOSE-FAIL-DEVICE")
            replacement.quit()
            assert owner.count == 0
    finally:
        for descriptor in leaked:
            real_close(descriptor)
    assert len(close_attempts) == 4


def xcuitest_private_kwargs(tmp_path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    app = tmp_path / "APP_PATH_CANARY.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(b"plist")
    canaries = (
        "UDID_CANARY",
        str(app),
        "ARGUMENT_CANARY",
        "ORG_CANARY",
        "SIGNING_CANARY",
        "com.example.updatedwdacanary",
    )
    return (
        {
            "udid": canaries[0],
            "app_path": app,
            "arguments": (canaries[2],),
            "xcode_org_id": canaries[3],
            "xcode_signing_id": canaries[4],
            "updated_wda_bundle_id": canaries[5],
        },
        canaries,
    )


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_xcuitest_terminal_create_redacts_full_exception_chain_and_cleanup(
    service: ProtocolService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_fails: bool,
) -> None:
    configure_private_tmp(tmp_path, monkeypatch)
    kwargs, canaries = xcuitest_private_kwargs(tmp_path)
    cleanup_canary = "CLEANUP_CANARY"
    service.create_plans.append(
        ResponsePlan(status=500, payload=error_response("|".join(canaries)))
    )

    with managed_connection(service) as (connection, owner):
        if cleanup_fails:
            original_new_connection = cast(Any, session_module)._new_connection
            injected = False

            def add_cleanup_canary(server_url: str) -> Any:
                nonlocal injected
                client = original_new_connection(server_url)
                if not injected:
                    injected = True
                    remaining = 1
                    original_clear_method = client._conn.clear

                    def clear() -> None:
                        nonlocal remaining
                        if remaining:
                            remaining -= 1
                            raise OSError(cleanup_canary)
                        original_clear_method()

                    monkeypatch.setattr(client._conn, "clear", clear)
                return client

            monkeypatch.setattr(session_module, "_new_connection", add_cleanup_canary)
        with pytest.raises(CommandError) as caught:
            create_xcuitest_session(connection, **kwargs)
        error = caught.value
        assert_private_exception_chain(error, (*canaries, cleanup_canary))
        assert error.__cause__ is None and error.__context__ is None
        if cleanup_fails:
            assert [str(item) for item in error.cleanup_errors] == [
                "transport_cleanup_failed"
            ]
            retained = error.session
            assert retained is not None and owner.count == 1
            retained.dispose()
            assert retained.session_info().state == "disposed"
            assert owner.count == 0
        else:
            assert error.cleanup_errors == ()
            assert error.session is None and owner.count == 0


@pytest.mark.parametrize("outcome", ["malformed_success", "response_unknown"])
def test_xcuitest_unknown_create_redacts_chain_and_disposes_retained_session(
    service: ProtocolService,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    configure_private_tmp(tmp_path, monkeypatch)
    kwargs, canaries = xcuitest_private_kwargs(tmp_path)
    echoed = "|".join(canaries)
    if outcome == "malformed_success":
        service.create_plans.append(
            ResponsePlan(payload=create_response(session_id=echoed, capabilities=[]))
        )
    else:
        service.create_plans.append(ResponsePlan(status=500, payload=echoed))

    with managed_connection(service) as (connection, owner):
        with pytest.raises(ResourceStateError) as caught:
            create_xcuitest_session(connection, **kwargs)
        error = caught.value
        assert error.code == "session_create_unknown"
        assert_private_exception_chain(error, canaries)
        assert error.__cause__ is None and error.__context__ is None
        retained = error.session
        assert retained is not None and retained.session_info().state == "uncertain"
        retained.dispose()
        assert retained.session_info().state == "disposed"
        assert owner.count == 0
