from __future__ import annotations

import json
import socket
import threading
import time
from collections import deque
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import FrozenInstanceError, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

from appium_connect_agent.automation import (
    AutomationError,
    CommandError,
    InvalidRequestError,
    InvalidSessionStateError,
    OperationCancelledError,
    ResourceStateError,
    Session,
    SessionBusyError,
    SessionInfo,
    create_session,
)
from appium_connect_agent.automation._session_client import _new_connection
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import OperationControl, Runtime, RuntimeConnection


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

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

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


@pytest.fixture
def service() -> Iterator[ProtocolService]:
    with ProtocolService() as current:
        yield current


@contextmanager
def connected(service: ProtocolService) -> Iterator[RuntimeConnection]:
    runtime = Runtime(LocalSettings(server_url=service.url))
    with runtime.connect() as connection:
        yield connection


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
) -> None:
    assert type(error) is error_type
    assert error.code == code
    assert error.request_state == request_state
    assert error.completed_steps == completed_steps
    assert len(error.operation_id) == 32
    int(error.operation_id, 16)


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
            {"device_id": "ok", "new_command_timeout_seconds": float("nan")},
            "invalid_argument",
        ),
        (
            {"device_id": "ok", "capabilities": {"appium:systemPort": 9000}},
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


def test_terminal_create_error_closes_client_and_releases_ownership(
    service: ProtocolService,
) -> None:
    service.create_plans.append(
        ResponsePlan(status=500, payload=error_response("cannot create"))
    )
    with connected(service) as connection:
        with pytest.raises(CommandError) as caught:
            create_session(connection, "terminal-device")
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        assert caught.value.cleanup_errors == ()
        assert caught.value.__cause__ is not None
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


def test_terminal_create_error_keeps_ownership_when_client_cleanup_fails(
    service: ProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:

    cleanup = OSError("pool clear failed")
    original = _new_connection

    def connection_with_failing_close(server_url: str) -> Any:
        client = original(server_url)

        def fail_clear() -> None:
            raise cleanup

        monkeypatch.setattr(client._conn, "clear", fail_clear)
        return client

    monkeypatch.setattr(
        "appium_connect_agent.automation._session._new_connection",
        connection_with_failing_close,
    )
    service.create_plans.append(
        ResponsePlan(status=500, payload=error_response("cannot create"))
    )
    with connected(service) as connection:
        with pytest.raises(CommandError) as caught:
            create_session(connection, "create-cleanup-device")
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        assert caught.value.cleanup_errors == (cleanup,)
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "create-cleanup-device")
        assert busy.value.code == "device_busy"


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
        )
        assert error.session is not None
        assert error.session.session_info().state == "uncertain"
        with pytest.raises(InvalidSessionStateError):
            error.session.quit()
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "unknown-shape-device")
        assert busy.value.code == "device_busy"


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
        )
        assert caught.value.session is not None
        assert caught.value.session.session_info().state == "uncertain"
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
        )
        assert caught.value.session is not None
        assert caught.value.session.session_info().state == "uncertain"
        assert len(service.lifecycle_requests()) == 1
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, "transport-device")
        assert busy.value.code == "device_busy"


def test_pre_request_cancel_wins_and_releases_reserved_resources(
    service: ProtocolService,
) -> None:
    cancellation = threading.Event()
    cancellation.set()
    with connected(service) as connection:
        with pytest.raises(OperationCancelledError) as caught:
            create_session(
                connection,
                "cancel-device",
                control=OperationControl(
                    timeout_seconds=0.001, cancellation=cancellation
                ),
            )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
        )
        replacement = create_session(connection, "cancel-device")
        replacement.quit()
    assert [request.method for request in service.lifecycle_requests()] == [
        "POST",
        "DELETE",
    ]


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
        assert caught.value.session is session
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


def test_session_constructor_is_not_a_public_creation_path() -> None:
    with pytest.raises(TypeError):
        Session()
