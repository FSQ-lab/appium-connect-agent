from __future__ import annotations

import json
import socket
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Literal, cast
from urllib.parse import unquote

import pytest

from appium_connect_agent.automation import (
    AutomationError,
    CommandError,
    Element,
    ExecutionUnknownError,
    InvalidRequestError,
    InvalidSessionStateError,
    OperationCancelledError,
    OperationTimeoutError,
    ResourceStateError,
    Session,
    SessionBusyError,
    TargetError,
    create_session,
)
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import OperationControl, Runtime, RuntimeConnection

_ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"
_BASE = "/wd/hub"
_DEFAULT = object()
ActionKind = Literal["single", "double", "long"]


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    body: Mapping[str, Any] | None
    received_at: float


@dataclass
class ResponsePlan:
    status: int = 200
    payload: object = _DEFAULT
    started: threading.Event | None = None
    release: threading.Event | None = None
    header_delay_seconds: float = 0
    body_delay_seconds: float = 0
    body_started: threading.Event | None = None
    chunk_count: int = 1
    chunk_delay_seconds: float = 0
    disconnect: bool = False
    after_send: Callable[[], None] | None = None


class ActionProtocolService:
    def __init__(self) -> None:
        self.requests: list[Request] = []
        self.plans: dict[str, deque[ResponsePlan]] = {}
        self.matches: dict[tuple[str | None, str, str], list[str]] = {}
        self.states: dict[tuple[str, str], object] = {}
        self.create_package: str | None = "com.example"
        self.settings: dict[str, object] = {
            "allowInvisibleElements": False,
            "disableIdLocatorAutocompletion": False,
            "enableMultiWindows": True,
            "snapshotMaxDepth": 70,
        }
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
        return f"http://{host}:{port}{_BASE}"

    def __enter__(self) -> ActionProtocolService:
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

    def queue(self, kind: str, *plans: ResponsePlan) -> None:
        self.plans.setdefault(kind, deque()).extend(plans)

    def snapshot(self) -> list[Request]:
        with self._lock:
            return list(self.requests)

    def of_kind(self, kind: str) -> list[Request]:
        return [request for request in self.snapshot() if self._kind(request) == kind]

    def operation_kinds(self) -> list[str]:
        ignored = {"status", "create", "quit"}
        return [
            kind
            for request in self.snapshot()
            if (kind := self._kind(request)) not in ignored
        ]

    def _read_body(self, handler: BaseHTTPRequestHandler) -> Mapping[str, Any] | None:
        length = int(handler.headers.get("Content-Length", "0"))
        if length == 0:
            return None
        value = json.loads(handler.rfile.read(length))
        assert isinstance(value, dict)
        return cast(Mapping[str, Any], value)

    def _record(self, handler: BaseHTTPRequestHandler) -> Request:
        request = Request(
            handler.command,
            handler.path,
            self._read_body(handler),
            time.monotonic(),
        )
        with self._lock:
            self.requests.append(request)
        return request

    @staticmethod
    def _kind(request: Request) -> str:
        path = request.path
        if request.method == "GET" and path == f"{_BASE}/status":
            return "status"
        if request.method == "POST" and path == f"{_BASE}/session":
            return "create"
        if request.method == "DELETE":
            return "quit"
        if path.endswith("/appium/settings"):
            return f"settings:{request.method.lower()}"
        if request.method == "POST" and path.endswith("/execute/sync"):
            return "action"
        if request.method == "POST" and path.endswith("/elements"):
            return "find"
        if path.endswith("/displayed"):
            return "displayed"
        if path.endswith("/enabled"):
            return "enabled"
        if "/attribute/" in path or path.endswith("/text"):
            return "attribute"
        return "unknown"

    def _default_payload(self, request: Request, kind: str) -> object:
        if kind == "status":
            return {"value": {"ready": True, "build": {"version": "3.7.0"}}}
        if kind == "create":
            self._session_number += 1
            capabilities = (
                {}
                if self.create_package is None
                else {"appium:appPackage": self.create_package}
            )
            return {
                "value": {
                    "sessionId": f"appium-{self._session_number}",
                    "capabilities": capabilities,
                }
            }
        if kind in {"quit", "action", "settings:post"}:
            if kind == "settings:post":
                assert request.body is not None
                update = request.body.get("settings")
                assert isinstance(update, dict)
                self.settings.update(update)
            return {"value": None}
        if kind == "settings:get":
            return {"value": dict(self.settings)}
        if kind == "find":
            assert request.body is not None
            using = request.body["using"]
            value = request.body["value"]
            assert isinstance(using, str) and isinstance(value, str)
            parent = None
            if "/element/" in request.path:
                parent = unquote(request.path.split("/element/", 1)[1].split("/", 1)[0])
            ids = self.matches.get((parent, using, value), ["target"])
            return {"value": [{_ELEMENT_KEY: item} for item in ids]}
        element_id = unquote(request.path.split("/element/", 1)[1].split("/", 1)[0])
        if kind in {"displayed", "enabled"}:
            return {"value": self.states.get((element_id, kind), True)}
        if kind == "attribute":
            name = unquote(request.path.rsplit("/", 1)[1])
            return {"value": self.states.get((element_id, name))}
        return {"value": None}

    def _write_response(
        self,
        handler: BaseHTTPRequestHandler,
        plan: ResponsePlan,
        data: bytes,
    ) -> None:
        handler.send_response(plan.status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        if plan.body_started is not None:
            plan.body_started.set()
        if plan.body_delay_seconds:
            time.sleep(plan.body_delay_seconds)
        count = max(plan.chunk_count, 1)
        chunk_size = max((len(data) + count - 1) // count, 1)
        for offset in range(0, len(data), chunk_size):
            handler.wfile.write(data[offset : offset + chunk_size])
            handler.wfile.flush()
            if offset + chunk_size < len(data) and plan.chunk_delay_seconds:
                time.sleep(plan.chunk_delay_seconds)
        if plan.after_send is not None:
            plan.after_send()

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        request = self._record(handler)
        kind = self._kind(request)
        with self._lock:
            queued = self.plans.get(kind)
            plan = queued.popleft() if queued else ResponsePlan()
        if plan.started is not None:
            plan.started.set()
        if plan.release is not None:
            assert plan.release.wait(timeout=5)
        if plan.header_delay_seconds:
            time.sleep(plan.header_delay_seconds)
        if plan.disconnect:
            handler.close_connection = True
            with suppress(OSError):
                handler.connection.shutdown(socket.SHUT_RDWR)
            handler.connection.close()
            return
        payload = (
            self._default_payload(request, kind)
            if plan.payload is _DEFAULT
            else plan.payload
        )
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        with suppress(BrokenPipeError, ConnectionResetError):
            self._write_response(handler, plan, data)


@pytest.fixture
def service() -> Iterator[ActionProtocolService]:
    with ActionProtocolService() as current:
        yield current


@contextmanager
def connected(service: ActionProtocolService) -> Iterator[RuntimeConnection]:
    runtime = Runtime(LocalSettings(server_url=service.url))
    with runtime.connect() as connection:
        yield connection


def session_for(
    service: ActionProtocolService,
    connection: RuntimeConnection,
    device: str,
) -> Session:
    del service
    return create_session(connection, device, app_id="com.example")


def invoke(
    session: Session,
    element: Element,
    kind: ActionKind,
    *,
    duration_ms: int = 500,
    wait_timeout_seconds: float = 2.0,
    control: OperationControl | None = None,
) -> None:
    if kind == "single":
        session.click(
            element,
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )
    elif kind == "double":
        session.double_click(
            element,
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )
    else:
        session.long_click(
            element,
            duration_ms=duration_ms,
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )


def w3c_error(message: str = "failed") -> dict[str, object]:
    return {"value": {"error": "unknown error", "message": message, "stacktrace": ""}}


def stale_error() -> dict[str, object]:
    return {
        "value": {
            "error": "stale element reference",
            "message": "element is stale",
            "stacktrace": "",
        }
    }


def elements(*ids: str) -> dict[str, object]:
    return {"value": [{_ELEMENT_KEY: item} for item in ids]}


def assert_error(
    error: AutomationError,
    error_type: type[AutomationError],
    code: str,
    request_state: str,
    *,
    steps: tuple[str, ...] | None = None,
) -> None:
    assert type(error) is error_type
    assert error.code == code
    assert error.request_state == request_state
    assert len(error.operation_id) == 32
    int(error.operation_id, 16)
    if steps is not None:
        assert error.completed_steps == steps


@pytest.mark.parametrize(
    ("kind", "script", "args"),
    [
        ("single", "mobile: clickGesture", {"elementId": "target"}),
        ("double", "mobile: doubleClickGesture", {"elementId": "target"}),
        (
            "long",
            "mobile: longClickGesture",
            {"elementId": "target", "duration": 500},
        ),
    ],
)
def test_actions_use_exact_request_order_script_payload_and_one_action(
    service: ActionProtocolService,
    kind: ActionKind,
    script: str,
    args: dict[str, object],
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"exact-{kind}")
        service.matches[(None, "id", "com.example:id/form")] = ["form"]
        service.matches[("form", "id", "com.example:id/target")] = ["target"]
        parent = session.element("id", "form")
        target = session.element("id", "target", parent=parent)
        assert invoke(session, target, kind) is None  # type: ignore[func-returns-value]
        assert service.operation_kinds() == [
            "find",
            "find",
            "displayed",
            "enabled",
            "action",
        ]
        root, child = service.of_kind("find")
        assert root.path.endswith("/elements")
        assert child.path.endswith("/element/form/elements")
        assert root.body == {"using": "id", "value": "com.example:id/form"}
        assert child.body == {"using": "id", "value": "com.example:id/target"}
        action = service.of_kind("action")[0]
        assert action.path.endswith("/execute/sync")
        assert action.body == {"script": script, "args": [args]}
        assert "x" not in args and "y" not in args and "locator" not in args
        session.quit()


@pytest.mark.parametrize(
    ("kind", "plans", "expected"),
    [
        (
            "find",
            [ResponsePlan(payload=elements()), ResponsePlan()],
            ["find", "find", "displayed", "enabled", "action"],
        ),
        (
            "displayed",
            [ResponsePlan(payload={"value": False}), ResponsePlan()],
            ["find", "displayed", "find", "displayed", "enabled", "action"],
        ),
        (
            "enabled",
            [ResponsePlan(payload={"value": False}), ResponsePlan()],
            [
                "find",
                "displayed",
                "enabled",
                "find",
                "displayed",
                "enabled",
                "action",
            ],
        ),
    ],
)
def test_waits_for_missing_hidden_or_disabled_target_with_half_second_pacing(
    service: ActionProtocolService,
    kind: str,
    plans: list[ResponsePlan],
    expected: list[str],
) -> None:
    service.queue(kind, *plans)
    with connected(service) as connection:
        session = session_for(service, connection, f"wait-{kind}")
        session.click(session.element("id", "target"), wait_timeout_seconds=2)
        assert service.operation_kinds() == expected
        repeated = service.of_kind(kind)
        assert repeated[1].received_at - repeated[0].received_at >= 0.4
        assert len(service.of_kind("action")) == 1
        session.quit()


@pytest.mark.parametrize("stage", [0, 1, 2])
def test_ambiguity_at_every_chain_level_fails_immediately(
    service: ActionProtocolService, stage: int
) -> None:
    values = ["com.example:id/root", "com.example:id/middle", "com.example:id/target"]
    parents: list[str | None] = [None, "root", "middle"]
    ids = ["root", "middle", "target"]
    for index, value in enumerate(values):
        service.matches[(parents[index], "id", value)] = (
            [ids[index], f"duplicate-{index}"] if index == stage else [ids[index]]
        )
    with connected(service) as connection:
        session = session_for(service, connection, f"ambiguous-{stage}")
        root = session.element("id", "root")
        middle = session.element("id", "middle", parent=root)
        target = session.element("id", "target", parent=middle)
        with pytest.raises(TargetError) as caught:
            session.click(target)
        assert_error(
            caught.value,
            TargetError,
            "target_ambiguous",
            "response_received",
            steps=(),
        )
        assert len(service.of_kind("find")) == stage + 1
        assert service.of_kind("action") == []
        session.quit()


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("root", ["find", "find", "find", "displayed", "enabled", "action"]),
        (
            "child",
            ["find", "find", "find", "find", "displayed", "enabled", "action"],
        ),
        (
            "displayed",
            [
                "find",
                "find",
                "displayed",
                "find",
                "find",
                "displayed",
                "enabled",
                "action",
            ],
        ),
        (
            "enabled",
            [
                "find",
                "find",
                "displayed",
                "enabled",
                "find",
                "find",
                "displayed",
                "enabled",
                "action",
            ],
        ),
    ],
)
def test_each_pre_action_stale_phase_restarts_the_entire_chain(
    service: ActionProtocolService,
    stage: str,
    expected: list[str],
) -> None:
    service.matches[(None, "id", "com.example:id/form")] = ["form"]
    service.matches[("form", "id", "com.example:id/target")] = ["target"]
    stale = ResponsePlan(status=404, payload=stale_error())
    if stage == "child":
        service.queue("find", ResponsePlan(), stale)
    else:
        service.queue("find" if stage == "root" else stage, stale)
    with connected(service) as connection:
        session = session_for(service, connection, f"stale-{stage}")
        parent = session.element("id", "form")
        target = session.element("id", "target", parent=parent)
        session.click(target)
        assert service.operation_kinds() == expected
        assert len(service.of_kind("action")) == 1
        session.quit()


@pytest.mark.parametrize(
    ("stage", "plan"),
    [
        ("find", ResponsePlan(status=500, payload=w3c_error("find"))),
        ("displayed", ResponsePlan(payload={"value": "true"})),
        ("enabled", ResponsePlan(payload={"value": 1})),
    ],
)
def test_other_pre_action_errors_fail_immediately_without_poll_or_action(
    service: ActionProtocolService, stage: str, plan: ResponsePlan
) -> None:
    service.queue(stage, plan)
    with connected(service) as connection:
        session = session_for(service, connection, f"known-{stage}")
        with pytest.raises(CommandError) as caught:
            session.click(session.element("id", "target"))
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=(),
        )
        assert len(service.of_kind(stage)) == 1
        assert service.of_kind("action") == []
        session.quit()


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (404, stale_error()),
        (500, w3c_error("action")),
        (200, {"value": "unexpected"}),
    ],
)
def test_action_stale_error_or_non_null_return_is_never_replayed(
    service: ActionProtocolService,
    status: int,
    payload: dict[str, object],
) -> None:
    service.queue("action", ResponsePlan(status=status, payload=payload))
    with connected(service) as connection:
        session = session_for(service, connection, f"action-error-{status}")
        with pytest.raises(CommandError) as caught:
            session.double_click(session.element("id", "target"))
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=("target_resolved", "target_displayed", "target_enabled"),
        )
        assert len(service.of_kind("find")) == 1
        assert len(service.of_kind("action")) == 1
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("value", [True, 0, -1, float("inf"), float("nan"), "1"])
def test_invalid_wait_values_are_rejected_before_protocol_io(
    service: ActionProtocolService, value: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"wait-value-{value!r}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.click(
                session.element("id", "target"),
                wait_timeout_seconds=cast(Any, value),
            )
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("value", [True, 1.0, 0, -1, 60_001])
def test_invalid_durations_are_rejected_before_protocol_io(
    service: ActionProtocolService, value: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"duration-value-{value!r}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.long_click(
                session.element("id", "target"), duration_ms=cast(Any, value)
            )
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("duration", [1, 500, 60_000])
def test_long_duration_boundaries_are_sent_as_exact_integers(
    service: ActionProtocolService, duration: int
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"duration-{duration}")
        session.long_click(session.element("id", "target"), duration_ms=duration)
        action = service.of_kind("action")[0]
        assert action.body == {
            "script": "mobile: longClickGesture",
            "args": [{"elementId": "target", "duration": duration}],
        }
        session.quit()


def test_long_duration_must_be_strictly_less_than_remaining_operation_budget(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        succeeds = session_for(service, connection, "duration-less")
        succeeds.long_click(
            succeeds.element("id", "target"),
            duration_ms=1,
            control=OperationControl(timeout_seconds=0.5),
        )
        succeeds.quit()
        for name, duration, budget in (
            ("equal", 100, 0.1),
            ("greater", 200, 0.1),
        ):
            session = session_for(service, connection, f"duration-{name}")
            before = len(service.of_kind("action"))
            with pytest.raises(OperationTimeoutError) as caught:
                session.long_click(
                    session.element("id", "target"),
                    duration_ms=duration,
                    control=OperationControl(timeout_seconds=budget),
                )
            assert_error(
                caught.value,
                OperationTimeoutError,
                "operation_timeout",
                "not_sent",
            )
            assert len(service.of_kind("action")) == before
            session.quit()


@pytest.mark.parametrize(
    ("control", "wait", "error_type", "code"),
    [
        (None, 0.06, TargetError, "condition_timeout"),
        (
            OperationControl(timeout_seconds=0.06),
            0.5,
            OperationTimeoutError,
            "operation_timeout",
        ),
    ],
)
def test_condition_and_operation_deadline_precedence_between_requests(
    service: ActionProtocolService,
    control: OperationControl | None,
    wait: float,
    error_type: type[AutomationError],
    code: str,
) -> None:
    service.matches[(None, "id", "com.example:id/missing")] = []
    with connected(service) as connection:
        session = session_for(service, connection, f"deadline-{code}")
        with pytest.raises(error_type) as caught:
            session.click(
                session.element("id", "missing"),
                wait_timeout_seconds=wait,
                control=control,
            )
        assert_error(caught.value, error_type, code, "not_sent", steps=())
        assert len(service.of_kind("find")) == 1
        assert service.of_kind("action") == []
        session.quit()


def test_condition_deadline_after_complete_response_is_response_received(
    service: ActionProtocolService,
) -> None:
    payload = {"value": [{_ELEMENT_KEY: "target"}], "padding": "x" * 80_000}
    service.queue(
        "find",
        ResponsePlan(
            payload=payload,
            chunk_count=8,
            chunk_delay_seconds=0.01,
        ),
    )
    with connected(service) as connection:
        session = session_for(service, connection, "condition-post-response")
        with pytest.raises(TargetError) as caught:
            session.click(session.element("id", "target"), wait_timeout_seconds=0.04)
        assert_error(
            caught.value,
            TargetError,
            "condition_timeout",
            "response_received",
            steps=(),
        )
        assert service.of_kind("displayed") == []
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("phase", ["header", "body"])
def test_condition_deadline_in_flight_is_unknown_and_closes_local_path(
    service: ActionProtocolService, phase: str
) -> None:
    plan = (
        ResponsePlan(header_delay_seconds=0.2)
        if phase == "header"
        else ResponsePlan(body_delay_seconds=0.2)
    )
    service.queue("find", plan)
    with connected(service) as connection:
        session = session_for(service, connection, f"condition-unknown-{phase}")
        target = session.element("id", "target")
        with pytest.raises(TargetError) as caught:
            session.click(target, wait_timeout_seconds=0.05)
        assert_error(
            caught.value,
            TargetError,
            "condition_timeout",
            "response_unknown",
            steps=(),
        )
        assert session.session_info().state == "uncertain"
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError):
            session.click(target)
        assert service.snapshot() == before


def test_cancellation_wakes_poll_and_wins_at_a_shared_deadline(
    service: ActionProtocolService,
) -> None:
    service.matches[(None, "id", "com.example:id/missing")] = []
    cancellation = threading.Event()
    timer = threading.Timer(0.05, cancellation.set)
    with connected(service) as connection:
        session = session_for(service, connection, "cancel-wakeup")
        timer.start()
        started = time.monotonic()
        with pytest.raises(OperationCancelledError) as caught:
            session.click(
                session.element("id", "missing"),
                wait_timeout_seconds=0.5,
                control=OperationControl(
                    timeout_seconds=1.0,
                    cancellation=cancellation,
                ),
            )
        elapsed = time.monotonic() - started
        timer.join(timeout=1)
        assert not timer.is_alive()
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
        )
        assert elapsed < 0.4
        session.quit()

        already_cancelled = threading.Event()
        already_cancelled.set()
        precedence = session_for(service, connection, "cancel-precedence")
        before = service.snapshot()
        with pytest.raises(OperationCancelledError) as simultaneous:
            precedence.click(
                precedence.element("id", "missing"),
                wait_timeout_seconds=0.5,
                control=OperationControl(
                    timeout_seconds=5e-324,
                    cancellation=already_cancelled,
                ),
            )
        assert_error(
            simultaneous.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
        )
        assert service.snapshot() == before
        precedence.quit()


def test_valid_upstream_error_and_final_success_each_beat_later_cancellation(
    service: ActionProtocolService,
) -> None:
    cancellation = threading.Event()
    service.queue(
        "find",
        ResponsePlan(
            status=500,
            payload=w3c_error("known"),
            after_send=cancellation.set,
        ),
    )
    with connected(service) as connection:
        known = session_for(service, connection, "known-priority")
        with pytest.raises(CommandError) as caught:
            known.click(
                known.element("id", "target"),
                control=OperationControl(timeout_seconds=1, cancellation=cancellation),
            )
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        known.quit()

        cancellation.clear()
        service.queue("action", ResponsePlan(after_send=cancellation.set))
        success = session_for(service, connection, "success-priority")
        assert (
            success.click(  # type: ignore[func-returns-value]
                success.element("id", "target"),
                control=OperationControl(timeout_seconds=1, cancellation=cancellation),
            )
            is None
        )
        assert cancellation.is_set()
        success.quit()


def test_condition_deadline_no_longer_limits_an_action_already_started(
    service: ActionProtocolService,
) -> None:
    service.queue("action", ResponsePlan(header_delay_seconds=0.35))
    with connected(service) as connection:
        session = session_for(service, connection, "condition-action-separation")
        assert (
            session.click(  # type: ignore[func-returns-value]
                session.element("id", "target"), wait_timeout_seconds=0.3
            )
            is None
        )
        assert len(service.of_kind("action")) == 1
        session.quit()


@pytest.mark.parametrize("phase", ["disconnect", "header", "body", "cancel"])
def test_action_unknown_is_never_replayed_and_retains_session_ownership(
    service: ActionProtocolService, phase: str
) -> None:
    control: OperationControl | None = None
    error_type: type[AutomationError] = ExecutionUnknownError
    code = "execution_unknown"
    cancellation = threading.Event()
    worker: threading.Thread | None = None
    if phase == "disconnect":
        plan = ResponsePlan(disconnect=True)
    elif phase == "cancel":
        started = threading.Event()
        release = threading.Event()
        plan = ResponsePlan(started=started, release=release, disconnect=True)
        control = OperationControl(timeout_seconds=1, cancellation=cancellation)
        error_type = OperationCancelledError
        code = "operation_cancelled"

        def cancel_inflight() -> None:
            assert started.wait(timeout=2)
            cancellation.set()
            release.set()

        worker = threading.Thread(target=cancel_inflight)
        worker.start()
    else:
        plan = ResponsePlan(
            header_delay_seconds=0.2 if phase == "header" else 0,
            body_delay_seconds=0.2 if phase == "body" else 0,
        )
        control = OperationControl(timeout_seconds=0.08)
        error_type = OperationTimeoutError
        code = "operation_timeout"
    service.queue("action", plan)
    with connected(service) as connection:
        session = session_for(service, connection, f"action-unknown-{phase}")
        with pytest.raises(error_type) as caught:
            session.click(session.element("id", "target"), control=control)
        assert_error(
            caught.value,
            error_type,
            code,
            "response_unknown",
            steps=("target_resolved", "target_displayed", "target_enabled"),
        )
        if worker is not None:
            worker.join(timeout=2)
            assert not worker.is_alive()
        assert len(service.of_kind("action")) == 1
        assert session.session_info().state == "uncertain"
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, f"action-unknown-{phase}")
        assert busy.value.code == "device_busy"
        assert service.of_kind("quit") == []


@pytest.mark.parametrize("initial", [False, True])
def test_raw_setting_guard_wraps_all_waits_and_restores_exact_initial_value(
    service: ActionProtocolService, initial: bool
) -> None:
    service.settings["disableIdLocatorAutocompletion"] = initial
    service.queue(
        "find",
        ResponsePlan(payload=elements()),
        ResponsePlan(status=404, payload=stale_error()),
        ResponsePlan(),
    )
    raw_value = "vendor/odd@id"
    with connected(service) as connection:
        session = session_for(service, connection, f"raw-{initial}")
        session.click(
            session.element("id", raw_value, raw_id=True),
            wait_timeout_seconds=2,
        )
        expected = ["settings:get"]
        if not initial:
            expected.append("settings:post")
        expected.extend(["find", "find", "find", "displayed", "enabled", "action"])
        if not initial:
            expected.append("settings:post")
        assert service.operation_kinds() == expected
        assert len(service.of_kind("settings:get")) == 1
        assert service.settings["disableIdLocatorAutocompletion"] is initial
        session.quit()


def test_raw_mixed_unresolved_chain_is_rejected_before_any_request(
    service: ActionProtocolService,
) -> None:
    service.create_package = None
    with connected(service) as connection:
        session = create_session(connection, "raw-mixed")
        raw = session.element("id", "vendor/odd@id", raw_id=True)
        unresolved = session.element("id", "short", parent=raw)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.click(unresolved)
        assert_error(
            caught.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


def test_raw_timeout_restores_setting_and_reports_only_actual_steps(
    service: ActionProtocolService,
) -> None:
    raw_value = "vendor/odd@id"
    service.matches[(None, "id", raw_value)] = []
    with connected(service) as connection:
        session = session_for(service, connection, "raw-timeout")
        with pytest.raises(TargetError) as caught:
            session.click(
                session.element("id", raw_value, raw_id=True),
                wait_timeout_seconds=0.06,
            )
        assert_error(
            caught.value,
            TargetError,
            "condition_timeout",
            "not_sent",
            steps=("settings_read", "settings_changed", "settings_restored"),
        )
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert service.of_kind("action") == []
        session.quit()


def test_raw_primary_action_error_survives_restore_error_and_never_replays(
    service: ActionProtocolService,
) -> None:
    service.queue("action", ResponsePlan(status=500, payload=w3c_error("action")))
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(status=500, payload=w3c_error("restore")),
    )
    with connected(service) as connection:
        session = session_for(service, connection, "raw-double-error")
        target = session.element("id", "vendor/odd@id", raw_id=True)
        with pytest.raises(CommandError) as caught:
            session.long_click(target)
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=(
                "settings_read",
                "settings_changed",
                "target_resolved",
                "target_displayed",
                "target_enabled",
            ),
        )
        assert len(caught.value.cleanup_errors) == 1
        assert len(service.of_kind("action")) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


@pytest.mark.parametrize("unknown", [False, True])
def test_raw_action_success_restore_failure_preserves_action_completed(
    service: ActionProtocolService, unknown: bool
) -> None:
    restore = (
        ResponsePlan(disconnect=True)
        if unknown
        else ResponsePlan(status=500, payload=w3c_error("restore"))
    )
    service.queue("settings:post", ResponsePlan(), restore)
    expected_type: type[AutomationError] = (
        ExecutionUnknownError if unknown else ResourceStateError
    )
    expected_code = "execution_unknown" if unknown else "cleanup_failed"
    expected_state = "response_unknown" if unknown else "response_received"
    with connected(service) as connection:
        session = session_for(service, connection, f"raw-restore-{unknown}")
        with pytest.raises(expected_type) as caught:
            session.click(session.element("id", "vendor/odd@id", raw_id=True))
        assert_error(
            caught.value,
            expected_type,
            expected_code,
            expected_state,
            steps=(
                "settings_read",
                "settings_changed",
                "target_resolved",
                "target_displayed",
                "target_enabled",
                "action_completed",
            ),
        )
        assert len(caught.value.cleanup_errors) == (0 if unknown else 1)
        assert len(service.of_kind("action")) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


def test_raw_setting_unknown_never_finds_or_attempts_restore(
    service: ActionProtocolService,
) -> None:
    service.queue("settings:get", ResponsePlan(disconnect=True))
    with connected(service) as connection:
        session = session_for(service, connection, "raw-setting-unknown")
        with pytest.raises(ExecutionUnknownError) as caught:
            session.click(session.element("id", "vendor/odd@id", raw_id=True))
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
            steps=(),
        )
        assert service.of_kind("find") == []
        assert service.of_kind("settings:post") == []
        assert session.session_info().state == "uncertain"


def test_foreign_forged_busy_closed_and_connection_invalid_are_request_free(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        owner = session_for(service, connection, "owner")
        other = session_for(service, connection, "other")
        foreign = owner.element("id", "target")
        for element, code in (
            (foreign, "element_session_mismatch"),
            (object.__new__(Element), "invalid_argument"),
        ):
            before = service.snapshot()
            with pytest.raises(InvalidRequestError) as caught:
                other.click(element)
            assert_error(caught.value, InvalidRequestError, code, "not_sent")
            assert service.snapshot() == before
        owner.quit()
        other.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as closed:
            other.click(other.element("id", "target"))
        assert_error(
            closed.value,
            InvalidSessionStateError,
            "session_closed",
            "not_sent",
        )
        assert service.snapshot() == before

    runtime = Runtime(LocalSettings(server_url=service.url))
    with runtime.connect() as connection:
        invalid = session_for(service, connection, "connection-invalid")
        target = invalid.element("id", "target")
    before = service.snapshot()
    with pytest.raises(InvalidSessionStateError) as invalid_error:
        invalid.click(target)
    assert_error(
        invalid_error.value,
        InvalidSessionStateError,
        "session_invalid",
        "not_sent",
    )
    assert invalid.session_info().state == "uncertain"
    assert service.snapshot() == before


def test_overlapping_action_is_immediately_busy_and_sends_no_second_action(
    service: ActionProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.queue("action", ResponsePlan(started=started, release=release))
    result: list[BaseException | None] = []
    with connected(service) as connection:
        session = session_for(service, connection, "action-busy")
        target = session.element("id", "target")

        def run() -> None:
            try:
                session.click(target)
            except BaseException as error:
                result.append(error)
            else:
                result.append(None)

        worker = threading.Thread(target=run)
        worker.start()
        assert started.wait(timeout=2)
        before = len(service.of_kind("action"))
        with pytest.raises(SessionBusyError) as caught:
            session.double_click(target)
        assert_error(caught.value, SessionBusyError, "session_busy", "not_sent")
        assert len(service.of_kind("action")) == before
        assert session.session_info().busy is True
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert result == [None]
        assert session.session_info().busy is False
        session.quit()


def test_actions_preserve_aif02_lifecycle_and_aif03_fresh_resolution(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "regression")
        target = session.element("id", "target")
        session.click(target)
        inspection = session.inspect_element(target, attributes=("text",))
        assert inspection.attributes[0].state == "missing"
        assert service.operation_kinds() == [
            "find",
            "displayed",
            "enabled",
            "action",
            "find",
            "attribute",
        ]
        assert session.session_info().state == "active"
        session.quit()
        assert session.session_info().state == "closed"
        assert len(service.of_kind("quit")) == 1
