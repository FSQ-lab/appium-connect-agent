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
from typing import Any, cast
from urllib.parse import unquote

from appium_connect_agent.automation import AutomationError, Session, create_session
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import Runtime, RuntimeConnection

_ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"
_BASE = "/wd/hub"
_DEFAULT = object()


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
            if (
                request.body is not None
                and request.body.get("script") == "mobile: replaceElementValue"
            ):
                return "replace"
            return "action"
        if request.method == "POST" and path.endswith("/elements"):
            return "find"
        if request.method == "POST" and path.endswith("/value"):
            return "send"
        if request.method == "POST" and path.endswith("/clear"):
            return "clear"
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
        if kind in {
            "quit",
            "action",
            "send",
            "clear",
            "replace",
            "settings:post",
        }:
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
