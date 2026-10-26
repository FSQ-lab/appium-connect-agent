from __future__ import annotations

import json
import socket
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import FrozenInstanceError, dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import unquote

import pytest

from appium_connect_agent.automation import (
    AutomationError,
    CommandError,
    Element,
    ElementAttribute,
    ElementInspection,
    ElementValidationError,
    ExecutionUnknownError,
    InvalidRequestError,
    InvalidSessionStateError,
    OperationCancelledError,
    OperationTimeoutError,
    RawStructureObservation,
    ResourceStateError,
    Session,
    SessionBusyError,
    TargetError,
    TreeObservation,
    create_session,
)
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import OperationControl, Runtime, RuntimeConnection

_ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"
_BASE = "/wd/hub"
_DEFAULT = object()


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    body: Mapping[str, Any] | None


@dataclass
class ResponsePlan:
    status: int = 200
    payload: object = _DEFAULT
    started: threading.Event | None = None
    release: threading.Event | None = None
    delay_seconds: float = 0
    disconnect: bool = False
    after_send: Callable[[], None] | None = None
    sending_at: datetime | None = None
    responded_at: datetime | None = None


class CheckpointCancellation(threading.Event):
    def __init__(self, false_checks_after_arm: int) -> None:
        super().__init__()
        self._armed = False
        self._remaining = false_checks_after_arm
        self._counter_lock = threading.Lock()

    def arm(self) -> None:
        with self._counter_lock:
            self._armed = True

    def is_set(self) -> bool:
        with self._counter_lock:
            if not self._armed:
                return False
            if self._remaining:
                self._remaining -= 1
                return False
            return True


class RaisingCancellation(threading.Event):
    def __init__(self, failure: BaseException) -> None:
        super().__init__()
        self._failure = failure
        self._armed = False

    def arm(self) -> None:
        self._armed = True

    def is_set(self) -> bool:
        if self._armed:
            raise self._failure
        return False


class ElementProtocolService:
    def __init__(self) -> None:
        self.requests: list[Request] = []
        self.plans: dict[str, deque[ResponsePlan]] = {}
        self.matches: dict[tuple[str | None, str, str], list[str]] = {}
        self.attributes: dict[tuple[str, str], object] = {}
        self.rects: dict[str, object] = {}
        self.create_package: str | None = "com.example"
        self.settings: dict[str, object] = {
            "allowInvisibleElements": False,
            "disableIdLocatorAutocompletion": False,
            "enableMultiWindows": True,
            "snapshotMaxDepth": 70,
        }
        self.source = basic_xml()
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

    def __enter__(self) -> ElementProtocolService:
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

    def _read_body(self, handler: BaseHTTPRequestHandler) -> Mapping[str, Any] | None:
        length = int(handler.headers.get("Content-Length", "0"))
        if length == 0:
            return None
        value = json.loads(handler.rfile.read(length))
        assert isinstance(value, dict)
        return cast(Mapping[str, Any], value)

    def _record(self, handler: BaseHTTPRequestHandler) -> Request:
        request = Request(handler.command, handler.path, self._read_body(handler))
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
        if path.endswith("/source"):
            return "source"
        if request.method == "POST" and path.endswith("/elements"):
            return "find"
        if "/attribute/" in path:
            return "attribute"
        if path.endswith("/text"):
            return "text"
        if path.endswith("/rect"):
            return "rect"
        if path.endswith("/displayed"):
            return "displayed"
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
        if kind in {"quit", "settings:post"}:
            if kind == "settings:post":
                assert request.body is not None
                update = request.body.get("settings")
                assert isinstance(update, dict)
                self.settings.update(update)
            return {"value": None}
        if kind == "settings:get":
            return {"value": dict(self.settings)}
        if kind == "source":
            return {"value": self.source}
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
        if kind == "attribute":
            name = unquote(request.path.rsplit("/", 1)[1])
            return {"value": self.attributes.get((element_id, name))}
        if kind == "text":
            return {"value": self.attributes.get((element_id, "text"))}
        if kind == "rect":
            return {
                "value": self.rects.get(
                    element_id, {"x": 1, "y": 2, "width": 30, "height": 40}
                )
            }
        if kind == "displayed":
            return {"value": self.attributes.get((element_id, "displayed"))}
        return {"value": None}

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
        if plan.delay_seconds:
            time.sleep(plan.delay_seconds)
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
        data = (
            plan.payload
            if isinstance(plan.payload, bytes)
            else json.dumps(payload, ensure_ascii=False).encode()
        )
        assert isinstance(data, bytes)
        try:
            plan.sending_at = datetime.now(UTC)
            handler.send_response(plan.status)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
            plan.responded_at = datetime.now(UTC)
            if plan.after_send is not None:
                plan.after_send()
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture
def service() -> Iterator[ElementProtocolService]:
    with ElementProtocolService() as current:
        yield current


@contextmanager
def connected(service: ElementProtocolService) -> Iterator[RuntimeConnection]:
    runtime = Runtime(LocalSettings(server_url=service.url))
    with runtime.connect() as connection:
        yield connection


def session_for(
    service: ElementProtocolService,
    connection: RuntimeConnection,
    device: str,
    *,
    app_id: str | None = "com.example",
) -> Session:
    del service
    return create_session(connection, device, app_id=app_id)


def w3c_error(message: str = "failed") -> dict[str, object]:
    return {"value": {"error": "unknown error", "message": message, "stacktrace": ""}}


def assert_error(
    error: AutomationError,
    error_type: type[AutomationError],
    code: str,
    request_state: str,
) -> None:
    assert type(error) is error_type
    assert error.code == code
    assert error.request_state == request_state
    assert len(error.operation_id) == 32
    int(error.operation_id, 16)


def document(
    value: ElementInspection | TreeObservation | RawStructureObservation,
) -> Any:
    encoded = value.to_json()
    assert encoded is value.to_json()
    assert len(encoded) <= 65_536
    decoded = json.loads(encoded)
    assert (
        json.dumps(
            decoded,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        == encoded
    )
    return decoded


def basic_xml(children: str = "") -> str:
    return f'<hierarchy rotation="0" width="1080" height="2400">{children}</hierarchy>'


def node_xml(
    *,
    tag: str = "android.widget.Button",
    resource_id: str = "",
    desc: str = "",
    text: str = "",
    package: str = "com.example",
    displayed: str = "true",
    bounds: str = "[0,0][100,100]",
    extra: str = "",
    children: str = "",
) -> str:
    return (
        f'<{tag} resource-id="{resource_id}" content-desc="{desc}" text="{text}" '
        f'package="{package}" class="{tag}" enabled="true" focused="false" '
        f'checkable="false" checked="false" selected="false" '
        f'bounds="{bounds}" displayed="{displayed}" {extra}>'
        f"{children}</{tag}>"
    )


def sized_xml(size: int) -> str:
    prefix = "<hierarchy><!--"
    suffix = "--></hierarchy>"
    assert size >= len(prefix) + len(suffix)
    return prefix + ("x" * (size - len(prefix) - len(suffix))) + suffix


def sibling_nodes(count: int) -> str:
    return "<hierarchy>" + ('<n displayed="false"/>' * (count - 1)) + "</hierarchy>"


def create_port(request: Request) -> int:
    assert request.body is not None
    capabilities = request.body["capabilities"]
    assert isinstance(capabilities, dict)
    always_match = capabilities["alwaysMatch"]
    assert isinstance(always_match, dict)
    return cast(int, always_match["appium:systemPort"])


def test_element_factory_is_pure_normalizes_ids_and_exposes_only_values(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "element-pure")
        before = service.snapshot()
        short = session.element("id", "save", package="com.example")
        defaulted = session.element("id", "title")
        complete = session.element("id", "com.other:id/name")
        accessibility = session.element("accessibility id", " 保存 ")
        xpath = session.element("xpath", "//*[@text='保存']")
        raw = session.element("id", "custom/resource@id", raw_id=True)
        assert service.snapshot() == before
        assert (short.by, short.value, short.package, short.raw_id, short.parent) == (
            "id",
            "com.example:id/save",
            "com.example",
            False,
            None,
        )
        assert defaulted.value == "com.example:id/title"
        assert complete.value == "com.other:id/name"
        assert accessibility.value == " 保存 "
        assert xpath.value == "//*[@text='保存']"
        assert raw.value == "custom/resource@id" and raw.raw_id
        assert not hasattr(short, "element_id")
        assert not hasattr(short, "operation_id")
        with pytest.raises(FrozenInstanceError):
            short.value = "changed"  # type: ignore[misc]
        session.quit()
        assert session.element("id", "after_close").value.endswith("after_close")


@pytest.mark.parametrize(
    ("by", "value", "kwargs", "code"),
    [
        ("css selector", "x", {}, "invalid_argument"),
        ("ID", "x", {}, "invalid_argument"),
        ("id", "", {}, "invalid_argument"),
        ("id", "x" * 4097, {}, "invalid_argument"),
        ("accessibility id", "a\0b", {}, "invalid_argument"),
        ("id", "bad-shape", {}, "invalid_argument"),
        ("id", "x", {"package": "bad..package"}, "invalid_argument"),
        ("id", "p.one:id/x", {"package": "p.two"}, "invalid_argument"),
        ("xpath", "//*", {"package": "com.example"}, "invalid_argument"),
        ("accessibility id", "x", {"raw_id": True}, "invalid_argument"),
        ("id", "x", {"raw_id": 1}, "invalid_argument"),
        ("id", "bad\nraw", {"raw_id": True}, "invalid_argument"),
    ],
)
def test_element_grammar_failures_have_no_operation_identity_or_io(
    service: ElementProtocolService,
    by: str,
    value: str,
    kwargs: dict[str, Any],
    code: str,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"grammar-{len(service.snapshot())}")
        before = service.snapshot()
        with pytest.raises(ElementValidationError) as caught:
            session.element(by, value, **kwargs)
        assert type(caught.value) is ElementValidationError
        assert caught.value.code == code
        assert not hasattr(caught.value, "operation_id")
        assert not hasattr(caught.value, "request_state")
        assert service.snapshot() == before
        session.quit()


def test_element_parent_owner_depth_xpath_and_invalid_target_default(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        first = session_for(service, connection, "owner-a")
        second = session_for(service, connection, "owner-b", app_id="bad/package")
        foreign = first.element("id", "root")
        with pytest.raises(ElementValidationError) as mismatch:
            second.element("id", "child", parent=foreign)
        assert mismatch.value.code == "element_session_mismatch"
        with pytest.raises(InvalidRequestError) as operation_mismatch:
            second.inspect_element(foreign, attributes=("text",))
        assert operation_mismatch.value.code == "element_session_mismatch"
        assert operation_mismatch.value.request_state == "not_sent"
        first.element("xpath", "//root")
        with pytest.raises(ElementValidationError) as child_xpath:
            first.element("xpath", "//child", parent=foreign)
        assert child_xpath.value.code == "unsupported_operation"
        parent: Element | None = None
        for index in range(16):
            parent = first.element("id", f"n{index}", parent=parent)
        with pytest.raises(ElementValidationError) as too_deep:
            first.element("id", "overflow", parent=parent)
        assert too_deep.value.code == "invalid_argument"
        assert second.element("id", "unresolved").value == "unresolved"
        first.quit()
        second.quit()


def test_element_constructor_and_forged_chains_are_rejected_before_io(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        first = session_for(service, connection, "forged-a")
        second = session_for(service, connection, "forged-b")

        with pytest.raises(TypeError):
            cast(Any, Element)("id", "x", None, False, None, object())

        def rejected(element: Element, code: str | None = None) -> None:
            before = service.snapshot()
            with pytest.raises(InvalidRequestError) as caught:
                second.inspect_element(element, attributes=("text",))
            if code is not None:
                assert caught.value.code == code
            assert caught.value.request_state == "not_sent"
            assert service.snapshot() == before

        forged_ancestor = object.__new__(Element)
        trusted_outer = second.element("id", "trusted_outer")
        object.__setattr__(trusted_outer, "parent", forged_ancestor)
        rejected(trusted_outer, "invalid_argument")
        forged = object.__new__(Element)
        rejected(forged, "invalid_argument")

        foreign_parent = first.element("id", "foreign")
        foreign_outer = second.element("id", "child")
        object.__setattr__(foreign_outer, "parent", foreign_parent)
        rejected(foreign_outer, "element_session_mismatch")

        invalid_strategy = second.element("id", "invalid_strategy")
        object.__setattr__(invalid_strategy, "by", "css selector")
        rejected(invalid_strategy, "invalid_argument")

        overdepth: list[Element] = []
        parent: Element | None = None
        for index in range(16):
            parent = second.element("id", f"deep_{index}", parent=parent)
            overdepth.append(parent)
        object.__setattr__(overdepth[0], "parent", second.element("id", "extra"))
        rejected(overdepth[-1], "invalid_argument")

        cycle: list[Element] = []
        parent = None
        for index in range(3):
            parent = second.element("id", f"cycle_{index}", parent=parent)
            cycle.append(parent)
        object.__setattr__(cycle[0], "parent", cycle[-1])
        rejected(cycle[-1], "invalid_argument")

        first.quit()
        second.quit()


@pytest.mark.parametrize(
    "attributes",
    [(), ("text", "text"), ("invalid",), ("text",) * 19],
)
def test_attribute_request_validation_precedes_io(
    service: ElementProtocolService, attributes: tuple[str, ...]
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"attributes-{len(attributes)}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.inspect_element(
                session.element("id", "target"), attributes=cast(Any, attributes)
            )
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    ("count", "code"), [(0, "target_not_found"), (2, "target_ambiguous")]
)
def test_unique_resolver_rejects_zero_and_multiple_root_matches(
    service: ElementProtocolService, count: int, code: str
) -> None:
    service.matches[(None, "id", "com.example:id/target")] = [
        f"match-{index}" for index in range(count)
    ]
    with connected(service) as connection:
        session = session_for(service, connection, f"unique-root-{count}")
        with pytest.raises(TargetError) as caught:
            session.inspect_element(
                session.element("id", "target"), attributes=("text",)
            )
        assert_error(caught.value, TargetError, code, "response_received")
        assert len(service.of_kind("find")) == 1
        session.quit()


@pytest.mark.parametrize(
    ("stage", "matches", "code"),
    [
        ("parent", [], "target_not_found"),
        ("parent", ["a", "b"], "target_ambiguous"),
        ("target", [], "target_not_found"),
        ("target", ["a", "b"], "target_ambiguous"),
    ],
)
def test_unique_resolver_checks_every_parent_and_target_layer(
    service: ElementProtocolService,
    stage: str,
    matches: list[str],
    code: str,
) -> None:
    parent_value = "com.example:id/form"
    target_value = "com.example:id/label"
    service.matches[(None, "id", parent_value)] = (
        matches if stage == "parent" else ["form"]
    )
    service.matches[("form", "id", target_value)] = (
        matches if stage == "target" else ["label"]
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"unique-{stage}-{len(matches)}")
        parent = session.element("id", "form")
        target = session.element("id", "label", parent=parent)
        with pytest.raises(TargetError) as caught:
            session.inspect_element(target, attributes=("text",))
        assert_error(caught.value, TargetError, code, "response_received")
        expected_requests = 1 if stage == "parent" else 2
        assert len(service.of_kind("find")) == expected_requests
        session.quit()


def test_unique_resolver_uses_root_then_child_find_elements_only(
    service: ElementProtocolService,
) -> None:
    service.matches[(None, "accessibility id", "Form")] = ["form"]
    service.matches[("form", "id", "com.example:id/row")] = ["row"]
    service.matches[("row", "id", "com.example:id/label")] = ["label"]
    service.attributes[("label", "text")] = "current"
    with connected(service) as connection:
        session = session_for(service, connection, "unique-chain")
        form = session.element("accessibility id", "Form")
        row = session.element("id", "row", parent=form)
        label = session.element("id", "label", parent=row)
        result = session.inspect_element(label, attributes=("text",))
        assert result.attributes[0].value == "current"
        assert [request.path for request in service.of_kind("find")] == [
            f"{_BASE}/session/appium-1/elements",
            f"{_BASE}/session/appium-1/element/form/elements",
            f"{_BASE}/session/appium-1/element/row/elements",
        ]
        session.quit()


def test_inspect_element_preserves_attribute_order_states_and_bounds(
    service: ElementProtocolService,
) -> None:
    service.attributes.update(
        {
            ("target", "resource-id"): None,
            ("target", "text"): "",
            ("target", "content-desc"): "说明",
            ("target", "class"): "android.widget.Button",
            ("target", "package"): "com.example",
            ("target", "enabled"): "false",
            ("target", "focused"): "TRUE",
            ("target", "checkable"): "false",
            ("target", "selected"): "false",
            ("target", "window-id"): 0,
        }
    )
    service.rects["target"] = {"x": -1, "y": 0, "width": 30, "height": 40}
    requested: tuple[ElementAttribute, ...] = (
        "text",
        "id",
        "desc",
        "type",
        "package",
        "enabled",
        "focused",
        "checked",
        "selected",
        "window_id",
        "bounds",
    )
    with connected(service) as connection:
        session = session_for(service, connection, "attribute-states")
        result = session.inspect_element(
            session.element("id", "target"), attributes=requested
        )
        assert tuple(item.name for item in result.attributes) == requested
        assert [(item.state, item.value) for item in result.attributes[:-1]] == [
            ("value", ""),
            ("missing", None),
            ("value", "说明"),
            ("value", "android.widget.Button"),
            ("value", "com.example"),
            ("value", False),
            ("value", True),
            ("not_applicable", None),
            ("value", False),
            ("value", 0),
        ]
        bounds = cast(Any, result.attributes[-1].value)
        assert bounds is not None and (bounds.x, bounds.width) == (-1, 30)
        assert (
            sum(
                request.path.endswith("/checkable")
                for request in service.of_kind("attribute")
            )
            == 1
        )
        target = session.element("id", "target")
        service.attributes[("target", "enabled")] = "yes"
        with pytest.raises(CommandError) as invalid_bool:
            session.inspect_element(target, attributes=("enabled",))
        service.rects["target"] = {"x": 0, "y": 0, "width": -1, "height": 1}
        with pytest.raises(CommandError) as invalid_bounds:
            session.inspect_element(target, attributes=("bounds",))
        assert invalid_bool.value.code == invalid_bounds.value.code == "source_invalid"
        assert session.session_info().state == "active"
        session.quit()


def test_element_inspection_schema_is_canonical_immutable_and_reference_free(
    service: ElementProtocolService,
) -> None:
    service.attributes[("target", "text")] = "保存"
    with connected(service) as connection:
        session = session_for(service, connection, "schema")
        element = session.element("id", "save", package="com.example")
        result = session.inspect_element(element, attributes=("text",))
        data = document(result)
        assert data == {
            "complete_for_requested_scope": True,
            "consistency": "sequential_non_atomic",
            "coverage": "requested_scope",
            "kind": "element",
            "observed_at": data["observed_at"],
            "operation_id": result.operation_id,
            "payload": {
                "attributes": [{"name": "text", "state": "value", "value": "保存"}]
            },
            "schema": 1,
            "scope": {
                "kind": "element",
                "locator": {
                    "by": "id",
                    "package": "com.example",
                    "parent": None,
                    "raw_id": False,
                    "value": "com.example:id/save",
                },
                "range_locator": {
                    "by": "id",
                    "package": "com.example",
                    "parent": None,
                    "raw_id": False,
                    "value": "com.example:id/save",
                },
            },
            "upstream_completeness": "unknown",
        }
        observed = data["observed_at"]
        assert len(observed) == 27 and observed.endswith("Z")
        assert observed[19] == "." and observed[20:26].isdigit()
        assert "保存".encode() in result.to_json()
        assert b"\\u4fdd" not in result.to_json()
        assert _ELEMENT_KEY.encode() not in result.to_json()
        with pytest.raises(FrozenInstanceError):
            result.coverage = "changed"  # type: ignore[misc, assignment]
        session.quit()


def test_element_inspection_complete_document_65536_and_65537(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "json-edge")
        element = session.element("id", "target")

        def inspect(text: str) -> ElementInspection:
            service.attributes[("target", "text")] = text
            return session.inspect_element(element, attributes=("text",))

        baseline = inspect("")
        padding = 65_536 - len(baseline.to_json())
        assert padding > 0
        exact = inspect("x" * padding)
        assert len(exact.to_json()) == 65_536
        with pytest.raises(CommandError) as caught:
            inspect("x" * (padding + 1))
        assert caught.value.code == "observation_too_large"
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("initial", [False, True])
def test_raw_id_settings_transaction_and_locator_are_exact(
    service: ElementProtocolService, initial: bool
) -> None:
    service.settings["disableIdLocatorAutocompletion"] = initial
    raw_value = "vendor/custom@id"
    service.matches[(None, "id", raw_value)] = ["raw"]
    service.attributes[("raw", "text")] = "raw value"
    with connected(service) as connection:
        session = session_for(service, connection, f"settings-raw-{initial}")
        raw = session.element("id", raw_value, raw_id=True)
        result = session.inspect_element(raw, attributes=("text",))
        assert result.attributes[0].value == "raw value"
        assert service.of_kind("find")[0].body == {
            "using": "id",
            "value": raw_value,
        }
        posts = service.of_kind("settings:post")
        assert len(posts) == (0 if initial else 2)
        if not initial:
            assert [request.body for request in posts] == [
                {"settings": {"disableIdLocatorAutocompletion": True}},
                {"settings": {"disableIdLocatorAutocompletion": False}},
            ]
        assert service.settings["disableIdLocatorAutocompletion"] is initial
        session.quit()


def test_raw_id_mixed_with_unresolved_short_id_is_rejected_before_io(
    service: ElementProtocolService,
) -> None:
    service.create_package = None
    with connected(service) as connection:
        session = session_for(service, connection, "raw-mixed", app_id=None)
        unresolved = session.element("id", "parent")
        raw = session.element("id", "odd/raw@id", parent=unresolved, raw_id=True)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.inspect_element(raw, attributes=("text",))
        assert_error(
            caught.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


def test_invalid_raw_id_setting_fails_before_find(
    service: ElementProtocolService,
) -> None:
    service.settings["disableIdLocatorAutocompletion"] = "false"
    with connected(service) as connection:
        session = session_for(service, connection, "raw-setting-invalid")
        raw = session.element("id", "odd/raw@id", raw_id=True)
        with pytest.raises(CommandError) as caught:
            session.inspect_element(raw, attributes=("text",))
        assert caught.value.code == "source_settings_invalid"
        assert service.of_kind("find") == []
        assert service.of_kind("settings:post") == []
        assert session.session_info().state == "active"
        session.quit()


def test_known_attribute_failure_restores_raw_setting_and_remains_active(
    service: ElementProtocolService,
) -> None:
    service.queue(
        "attribute", ResponsePlan(status=500, payload=w3c_error("attribute failed"))
    )
    with connected(service) as connection:
        session = session_for(service, connection, "raw-known-failure")
        raw = session.element("id", "odd/raw@id", raw_id=True)
        with pytest.raises(CommandError) as caught:
            session.inspect_element(raw, attributes=("enabled",))
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert len(service.of_kind("settings:post")) == 2
        assert session.session_info().state == "active"
        assert session.inspect_element(raw, attributes=("text",)).attributes
        session.quit()


@pytest.mark.parametrize("kind", ["settings:post", "find", "attribute"])
def test_response_unknown_closes_local_path_retains_ownership_and_never_deletes(
    service: ElementProtocolService, kind: str
) -> None:
    service.queue(kind, ResponsePlan(disconnect=True))
    with connected(service) as connection:
        device = f"unknown-{kind}"
        session = session_for(service, connection, device)
        element = (
            session.element("id", "odd/raw@id", raw_id=True)
            if kind == "settings:post"
            else session.element("id", "target")
        )
        attribute: ElementAttribute = "enabled" if kind == "attribute" else "text"
        with pytest.raises(ExecutionUnknownError) as caught:
            session.inspect_element(element, attributes=(attribute,))
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
        )
        assert session.session_info().state == "uncertain"
        requests_after_failure = service.snapshot()
        assert service.of_kind("quit") == []
        with pytest.raises(InvalidSessionStateError):
            session.inspect_element(element, attributes=(attribute,))
        assert service.snapshot() == requests_after_failure
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, device)
        assert busy.value.code == "device_busy"


def test_raw_restore_unknown_preserves_work_and_makes_session_uncertain(
    service: ElementProtocolService,
) -> None:
    service.queue("settings:post", ResponsePlan(), ResponsePlan(disconnect=True))
    with connected(service) as connection:
        session = session_for(service, connection, "raw-restore-unknown")
        raw = session.element("id", "odd/raw@id", raw_id=True)
        with pytest.raises(ExecutionUnknownError) as caught:
            session.inspect_element(raw, attributes=("text",))
        assert caught.value.request_state == "response_unknown"
        assert "attributes_read" in caught.value.completed_steps
        assert session.session_info().state == "uncertain"
        assert len(service.of_kind("settings:post")) == 2
        assert service.of_kind("quit") == []


def test_restore_failure_does_not_replace_primary_attribute_error(
    service: ElementProtocolService,
) -> None:
    service.queue("attribute", ResponsePlan(status=500, payload=w3c_error()))
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(status=500, payload=w3c_error("restore failed")),
    )
    with connected(service) as connection:
        session = session_for(service, connection, "raw-primary-cleanup")
        raw = session.element("id", "odd/raw@id", raw_id=True)
        with pytest.raises(CommandError) as caught:
            session.inspect_element(raw, attributes=("enabled",))
        assert caught.value.code == "command_failed"
        assert caught.value.cleanup_errors
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


def test_validation_busy_state_cancel_and_deadline_precedence(
    service: ElementProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.queue("find", ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    cancellation = threading.Event()
    cancellation.set()
    with connected(service) as connection:
        session = session_for(service, connection, "precedence")
        element = session.element("id", "target")

        def inspect() -> None:
            try:
                session.inspect_element(element, attributes=("text",))
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=inspect)
        worker.start()
        assert started.wait(timeout=1)
        with pytest.raises(InvalidRequestError) as pure:
            session.inspect_element(element, attributes=())
        assert pure.value.code == "invalid_argument"
        with pytest.raises(SessionBusyError) as busy:
            session.inspect_element(
                element,
                attributes=("text",),
                control=OperationControl(
                    timeout_seconds=1e-12, cancellation=cancellation
                ),
            )
        assert_error(busy.value, SessionBusyError, "session_busy", "not_sent")
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive() and failures == []
        before = service.snapshot()
        with pytest.raises(OperationCancelledError) as cancelled:
            session.inspect_element(
                element,
                attributes=("text",),
                control=OperationControl(
                    timeout_seconds=1e-12, cancellation=cancellation
                ),
            )
        assert_error(
            cancelled.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()
        with pytest.raises(InvalidSessionStateError) as closed:
            session.inspect_element(
                element,
                attributes=("text",),
                control=OperationControl(
                    timeout_seconds=1e-12, cancellation=cancellation
                ),
            )
        assert closed.value.code == "session_closed"


def test_timeout_during_find_is_unknown_and_holds_resources(
    service: ElementProtocolService,
) -> None:
    service.queue("find", ResponsePlan(delay_seconds=0.2))
    with connected(service) as connection:
        session = session_for(service, connection, "find-timeout")
        with pytest.raises(OperationTimeoutError) as caught:
            session.inspect_element(
                session.element("id", "target"),
                attributes=("text",),
                control=OperationControl(timeout_seconds=0.05),
            )
        assert_error(
            caught.value,
            OperationTimeoutError,
            "operation_timeout",
            "response_unknown",
        )
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []
        with pytest.raises(ResourceStateError):
            create_session(connection, "find-timeout")


def test_cancellation_after_attribute_success_restores_raw_setting(
    service: ElementProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    cancellation = threading.Event()
    service.queue("text", ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "cancel-after-attribute")
        raw = session.element("id", "odd/raw@id", raw_id=True)

        def inspect() -> None:
            try:
                session.inspect_element(
                    raw,
                    attributes=("text",),
                    control=OperationControl(
                        timeout_seconds=2, cancellation=cancellation
                    ),
                )
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=inspect)
        worker.start()
        assert started.wait(timeout=1)
        cancellation.set()
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert len(failures) == 1
        error = failures[0]
        assert isinstance(error, OperationCancelledError)
        assert error.request_state == "response_received"
        assert "target_resolved" in error.completed_steps
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert session.session_info().state == "active"
        session.quit()


def test_cancellation_visible_during_restore_finishes_restore_then_fails(
    service: ElementProtocolService,
) -> None:
    restore_started = threading.Event()
    restore_release = threading.Event()
    cancellation = threading.Event()
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(started=restore_started, release=restore_release),
    )
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "cancel-during-restore")
        raw = session.element("id", "odd/raw@id", raw_id=True)

        def inspect() -> None:
            try:
                session.inspect_element(
                    raw,
                    attributes=("text",),
                    control=OperationControl(
                        timeout_seconds=2, cancellation=cancellation
                    ),
                )
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=inspect)
        worker.start()
        assert restore_started.wait(timeout=1)
        cancellation.set()
        restore_release.set()
        worker.join(timeout=2)
        assert not worker.is_alive() and len(failures) == 1
        error = failures[0]
        assert isinstance(error, OperationCancelledError)
        assert error.request_state == "response_received"
        assert "attributes_read" in error.completed_steps
        assert "settings_restored" in error.completed_steps
        assert "observation_built" not in error.completed_steps
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert session.session_info().state == "active"
        session.quit()


def test_deadline_expires_during_restore_finishes_restore_then_fails(
    service: ElementProtocolService,
) -> None:
    restore_started = threading.Event()
    restore_release = threading.Event()
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(started=restore_started, release=restore_release),
    )
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "deadline-during-restore")
        raw = session.element("id", "odd/raw@id", raw_id=True)

        def inspect() -> None:
            try:
                session.inspect_element(
                    raw,
                    attributes=("text",),
                    control=OperationControl(timeout_seconds=0.5),
                )
            except BaseException as error:
                failures.append(error)

        operation_started = time.monotonic()
        worker = threading.Thread(target=inspect)
        worker.start()
        assert restore_started.wait(timeout=1)
        remaining = 0.5 - (time.monotonic() - operation_started)
        assert remaining > 0
        time.sleep(remaining + 0.01)
        restore_release.set()
        worker.join(timeout=2)
        assert not worker.is_alive() and len(failures) == 1
        error = failures[0]
        assert isinstance(error, OperationTimeoutError)
        assert error.request_state == "response_received"
        assert "attributes_read" in error.completed_steps
        assert "settings_restored" in error.completed_steps
        assert "observation_built" not in error.completed_steps
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert session.session_info().state == "active"
        session.quit()


def test_cancellation_becomes_visible_during_canonical_measurement(
    service: ElementProtocolService,
) -> None:
    cancellation = CheckpointCancellation(false_checks_after_arm=1)
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(after_send=cancellation.arm),
    )
    service.attributes[("target", "text")] = "x" * 10_000
    with connected(service) as connection:
        session = session_for(service, connection, "cancel-during-canonical")
        raw = session.element("id", "odd/raw@id", raw_id=True)
        with pytest.raises(OperationCancelledError) as caught:
            session.inspect_element(
                raw,
                attributes=("text",),
                control=OperationControl(timeout_seconds=2, cancellation=cancellation),
            )
        assert caught.value.request_state == "response_received"
        assert "attributes_read" in caught.value.completed_steps
        assert "settings_restored" in caught.value.completed_steps
        assert "observation_built" not in caught.value.completed_steps
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert session.session_info().state == "active"
        session.quit()


def test_raw_observed_at_is_last_attribute_time_not_restore_time(
    service: ElementProtocolService,
) -> None:
    attribute_plan = ResponsePlan()
    restore_started = threading.Event()
    restore_release = threading.Event()
    restore_plan = ResponsePlan(started=restore_started, release=restore_release)
    service.queue("text", attribute_plan)
    service.queue("settings:post", ResponsePlan(), restore_plan)
    results: list[ElementInspection] = []
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "observed-before-restore")
        raw = session.element("id", "odd/raw@id", raw_id=True)

        def inspect() -> None:
            try:
                results.append(session.inspect_element(raw, attributes=("text",)))
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=inspect)
        worker.start()
        assert restore_started.wait(timeout=1)
        restore_started_at = datetime.now(UTC)
        assert attribute_plan.responded_at is not None
        restore_release.set()
        worker.join(timeout=2)
        assert not worker.is_alive() and failures == [] and len(results) == 1
        assert restore_plan.responded_at is not None
        result = results[0]
        assert attribute_plan.sending_at is not None
        assert attribute_plan.sending_at <= result.observed_at <= restore_started_at
        assert result.observed_at < restore_plan.responded_at
        encoded_time = document(result)["observed_at"]
        assert isinstance(encoded_time, str)
        assert datetime.fromisoformat(encoded_time.replace("Z", "+00:00")) == (
            result.observed_at
        )
        session.quit()


def test_different_session_inspection_gates_are_independent(
    service: ElementProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.queue(
        "find",
        ResponsePlan(started=started, release=release),
        ResponsePlan(),
    )
    first_failures: list[BaseException] = []
    with connected(service) as connection:
        first = session_for(service, connection, "gate-a")
        second = session_for(service, connection, "gate-b")

        def inspect_first() -> None:
            try:
                first.inspect_element(
                    first.element("id", "target"), attributes=("text",)
                )
            except BaseException as error:
                first_failures.append(error)

        worker = threading.Thread(target=inspect_first)
        worker.start()
        assert started.wait(timeout=1)
        assert second.inspect_element(
            second.element("id", "target"), attributes=("text",)
        ).attributes
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive() and first_failures == []
        first.quit()
        second.quit()


def test_elements_and_results_are_not_cached_across_calls(
    service: ElementProtocolService,
) -> None:
    service.attributes[("target", "text")] = "first"
    with connected(service) as connection:
        session = session_for(service, connection, "no-cache")
        element = session.element("id", "target")
        first = session.inspect_element(element, attributes=("text",))
        service.attributes[("target", "text")] = "second"
        second = session.inspect_element(element, attributes=("text",))
        assert (first.attributes[0].value, second.attributes[0].value) == (
            "first",
            "second",
        )
        before_json = len(service.snapshot())
        assert first.to_json() is first.to_json()
        assert len(service.snapshot()) == before_json
        assert len(service.of_kind("find")) == 2
        session.quit()


def test_known_error_keeps_client_active_and_releases_resources_after_quit(
    service: ElementProtocolService,
) -> None:
    service.queue("attribute", ResponsePlan(status=500, payload=w3c_error()))
    with connected(service) as connection:
        device = "safe-resource-reuse"
        session = session_for(service, connection, device)
        original_port = create_port(service.of_kind("create")[-1])
        with pytest.raises(CommandError):
            session.inspect_element(
                session.element("id", "target"), attributes=("enabled",)
            )
        service.attributes[("target", "text")] = "usable"
        assert (
            session.inspect_element(
                session.element("id", "target"), attributes=("text",)
            )
            .attributes[0]
            .value
            == "usable"
        )
        session.quit()
        replacement = session_for(service, connection, device)
        assert create_port(service.of_kind("create")[-1]) == original_port
        replacement.quit()


def test_aif02_capabilities_session_snapshot_and_single_quit_are_unchanged(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "regression-invariants")
        create = service.of_kind("create")[0]
        assert create.body is not None
        always_match = cast(dict[str, Any], create.body["capabilities"])["alwaysMatch"]
        assert always_match["appium:settings[enableMultiWindows]"] is True
        assert always_match["appium:noReset"] is True
        before = len(service.snapshot())
        first = session.session_info()
        assert session.session_info() == first
        assert len(service.snapshot()) == before
        session.element("id", "pure")
        assert len(service.snapshot()) == before
        session.quit()
        session.quit()
        assert len(service.of_kind("quit")) == 1
        assert session.session_info().state == "closed"


def test_tree_schema_settings_restore_and_public_values(
    service: ElementProtocolService,
) -> None:
    child = node_xml(
        resource_id="com.example:id/save",
        desc="保存",
        text="",
        extra='window-id="7"',
    )
    service.source = basic_xml(child)
    with connected(service) as connection:
        session = session_for(service, connection, "tree-schema")
        result = session.observe_tree()
        data = document(result)
        assert data["schema"] == 1 and data["kind"] == "tree"
        assert data["coverage"] == "requested_scope"
        assert data["complete_for_requested_scope"] is True
        assert data["upstream_completeness"] == "unknown"
        assert data["scope"] == {
            "kind": "root",
            "locator": None,
            "range_locator": None,
        }
        assert data["source"] == {
            "allow_invisible_elements": True,
            "enable_multi_windows": True,
            "snapshot_max_depth": 70,
        }
        assert data["payload"]["viewport"] == {
            "height": {"state": "value", "value": 2400},
            "rotation": {"state": "value", "value": 0},
            "width": {"state": "value", "value": 1080},
        }
        node = data["payload"]["roots"][0]
        assert node["type"] == "Button" and node["type_ns"] == "android.widget"
        assert node["id"] == "save" and node["text"] == ""
        assert node["bounds"] == [0, 0, 100, 100]
        assert node["window_id"] == 7 and node["children"] == []
        assert "保存".encode() in result.to_json()
        assert b"\\u4fdd" not in result.to_json()
        assert len(data["observed_at"]) == 27 and data["observed_at"].endswith("Z")
        assert [request.body for request in service.of_kind("settings:post")] == [
            {"settings": {"allowInvisibleElements": True}},
            {"settings": {"allowInvisibleElements": False}},
        ]
        assert len(service.of_kind("source")) == 1
        assert service.settings["allowInvisibleElements"] is False
        with pytest.raises(FrozenInstanceError):
            result.coverage = "changed"  # type: ignore[misc, assignment]
        session.quit()


@pytest.mark.parametrize("initial", [False, True])
def test_allow_invisible_setting_preserves_exact_initial_value(
    service: ElementProtocolService, initial: bool
) -> None:
    service.settings["allowInvisibleElements"] = initial
    service.source = basic_xml()
    with connected(service) as connection:
        session = session_for(service, connection, f"tree-setting-{initial}")
        result = session.observe_tree()
        assert result.roots == ()
        posts = service.of_kind("settings:post")
        assert len(posts) == (0 if initial else 2)
        assert service.settings["allowInvisibleElements"] is initial
        session.quit()


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("enableMultiWindows", False),
        ("enableMultiWindows", "true"),
        ("allowInvisibleElements", "false"),
    ],
)
def test_invalid_source_settings_fail_before_source_without_repair(
    service: ElementProtocolService, setting: str, value: object
) -> None:
    service.settings[setting] = value
    with connected(service) as connection:
        session = session_for(service, connection, f"bad-tree-setting-{setting}")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert caught.value.code == "source_settings_invalid"
        assert caught.value.request_state == "response_received"
        assert service.of_kind("source") == []
        assert service.of_kind("settings:post") == []
        assert session.session_info().state == "active"
        session.quit()


def test_parent_scope_maps_resolved_id_and_accessibility_chain_locally(
    service: ElementProtocolService,
) -> None:
    target = node_xml(resource_id="com.example:id/target", desc="Target")
    parent_xml = node_xml(
        tag="android.view.ViewGroup",
        resource_id="com.example:id/form",
        children=target,
    )
    duplicate_outside = node_xml(resource_id="com.example:id/target", desc="Target")
    service.source = basic_xml(parent_xml + duplicate_outside)
    with connected(service) as connection:
        session = session_for(service, connection, "tree-parent")
        form = session.element("id", "form")
        target_element = session.element("accessibility id", "Target", parent=form)
        result = session.observe_tree(parent=target_element)
        data = document(result)
        assert result.roots[0].id.value == "target"
        assert data["scope"]["kind"] == "element"
        assert data["scope"]["locator"]["value"] == "Target"
        assert data["scope"]["locator"]["parent"]["value"] == ("com.example:id/form")
        assert data["scope"]["range_locator"] == data["scope"]["locator"]
        assert service.of_kind("find") == []
        session.quit()


def test_parent_scope_supports_raw_id_exact_local_match(
    service: ElementProtocolService,
) -> None:
    raw_value = "vendor/odd@id"
    service.source = basic_xml(node_xml(resource_id=raw_value))
    with connected(service) as connection:
        session = session_for(service, connection, "tree-raw-parent")
        raw = session.element("id", raw_value, raw_id=True)
        data = document(session.observe_tree(parent=raw))
        assert data["scope"]["locator"]["raw_id"] is True
        assert data["scope"]["locator"]["value"] == raw_value
        assert data["payload"]["roots"][0]["id"] == raw_value
        assert "disableIdLocatorAutocompletion" not in {
            key
            for request in service.of_kind("settings:post")
            if request.body is not None
            for key in cast(dict[str, object], request.body["settings"])
        }
        session.quit()


@pytest.mark.parametrize("locator", ["unresolved", "xpath"])
def test_unavailable_parent_scope_rejected_before_settings_and_source(
    service: ElementProtocolService, locator: str
) -> None:
    service.create_package = None
    with connected(service) as connection:
        session = session_for(
            service, connection, f"tree-unavailable-{locator}", app_id=None
        )
        parent = (
            session.element("id", "short")
            if locator == "unresolved"
            else session.element("xpath", "//*[@text='x']")
        )
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.observe_tree(parent=parent)
        assert_error(
            caught.value,
            InvalidRequestError,
            "structure_scope_unavailable",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


def test_foreign_parent_scope_is_rejected_before_protocol_io(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        first = session_for(service, connection, "tree-owner-a")
        second = session_for(service, connection, "tree-owner-b")
        foreign = first.element("id", "target")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            second.observe_tree(parent=foreign)
        assert_error(
            caught.value,
            InvalidRequestError,
            "element_session_mismatch",
            "not_sent",
        )
        assert service.snapshot() == before
        first.quit()
        second.quit()


@pytest.mark.parametrize(
    ("stage", "count", "code"),
    [
        ("parent", 0, "target_not_found"),
        ("parent", 2, "target_ambiguous"),
        ("target", 0, "target_not_found"),
        ("target", 2, "target_ambiguous"),
    ],
)
def test_parent_scope_requires_unique_match_at_each_local_layer(
    service: ElementProtocolService, stage: str, count: int, code: str
) -> None:
    target_nodes = "".join(
        node_xml(resource_id="com.example:id/target")
        for _ in range(count if stage == "target" else 1)
    )
    parent_nodes = "".join(
        node_xml(
            tag="android.view.ViewGroup",
            resource_id="com.example:id/form",
            children=target_nodes,
        )
        for _ in range(count if stage == "parent" else 1)
    )
    service.source = basic_xml(parent_nodes)
    with connected(service) as connection:
        session = session_for(service, connection, f"tree-local-{stage}-{count}")
        form = session.element("id", "form")
        target = session.element("id", "target", parent=form)
        with pytest.raises(TargetError) as caught:
            session.observe_tree(parent=target)
        assert_error(caught.value, TargetError, code, "response_received")
        session.quit()


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("<hierarchy><broken></hierarchy>", "source_invalid"),
        ("<!DOCTYPE hierarchy><hierarchy/>", "source_forbidden_xml"),
        (
            '<!DOCTYPE hierarchy [<!ENTITY x "boom">]><hierarchy>&x;</hierarchy>',
            "source_forbidden_xml",
        ),
        (
            '<!DOCTYPE hierarchy SYSTEM "http://127.0.0.1:9/a"><hierarchy/>',
            "source_forbidden_xml",
        ),
        ("<wrong-root/>", "source_invalid"),
    ],
)
def test_xml_syntax_and_forbidden_resources_fail_without_partial_tree(
    service: ElementProtocolService, source: str, code: str
) -> None:
    service.source = source
    with connected(service) as connection:
        session = session_for(service, connection, f"tree-xml-{code}-{len(source)}")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert caught.value.code == code
        assert caught.value.request_state == "response_received"
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("extra", [0, 1])
def test_raw_xml_four_mib_boundary(service: ElementProtocolService, extra: int) -> None:
    service.source = sized_xml(4_194_304 + extra)
    with connected(service) as connection:
        session = session_for(service, connection, f"tree-xml-size-{extra}")
        if extra == 0:
            assert session.observe_tree().roots == ()
        else:
            with pytest.raises(CommandError) as caught:
                session.observe_tree()
            assert caught.value.code == "source_too_large"
        session.quit()


@pytest.mark.parametrize(
    ("limit", "builder"),
    [
        (20_000, sibling_nodes),
        (
            128,
            lambda count: (
                "<hierarchy>"
                + ("<n>" * (count - 1))
                + ("</n>" * (count - 1))
                + "</hierarchy>"
            ),
        ),
    ],
)
def test_xml_node_and_depth_exact_and_plus_one_limits(
    service: ElementProtocolService,
    limit: int,
    builder: Callable[[int], str],
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"tree-resource-{limit}")
        service.source = builder(limit)
        assert len(session.observe_tree().to_json()) <= 65_536
        service.source = builder(limit + 1)
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert caught.value.code == "source_resource_limit"
        session.quit()


@pytest.mark.parametrize("kind", ["attributes", "tag_name", "attribute_name"])
def test_xml_attribute_count_and_name_exact_plus_one_limits(
    service: ElementProtocolService, kind: str
) -> None:
    if kind == "attributes":
        exact = " ".join(f'a{i}=""' for i in range(64))
        accepted = f"<hierarchy><n {exact}/></hierarchy>"
        rejected = f'<hierarchy><n {exact} overflow=""/></hierarchy>'
    elif kind == "tag_name":
        accepted = f"<hierarchy><{'a' * 256}/></hierarchy>"
        rejected = f"<hierarchy><{'a' * 257}/></hierarchy>"
    else:
        accepted = f'<hierarchy><n {"a" * 256}=""/></hierarchy>'
        rejected = f'<hierarchy><n {"a" * 257}=""/></hierarchy>'
    with connected(service) as connection:
        session = session_for(service, connection, f"tree-{kind}")
        service.source = accepted
        assert session.observe_tree().coverage == "requested_scope"
        service.source = rejected
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert caught.value.code == "source_resource_limit"
        session.quit()


def test_xml_attribute_value_exact_and_plus_one_limit(
    service: ElementProtocolService,
) -> None:
    value = "x" * 1_048_576
    with connected(service) as connection:
        session = session_for(service, connection, "tree-value-limit")
        service.source = f'<hierarchy><n extra="{value}"/></hierarchy>'
        assert session.observe_tree().coverage == "requested_scope"
        service.source = f'<hierarchy><n extra="{value}x"/></hierarchy>'
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert caught.value.code == "source_resource_limit"
        session.quit()


def test_tree_complete_document_65536_and_65537_boundaries(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "tree-json-edge")

        def observe(text: str) -> TreeObservation:
            service.source = basic_xml(
                node_xml(resource_id="com.example:id/target", text=text)
            )
            return session.observe_tree()

        baseline = observe("")
        padding = 65_536 - len(baseline.to_json())
        assert padding > 0
        exact = observe("x" * padding)
        assert len(exact.to_json()) == 65_536
        with pytest.raises(CommandError) as caught:
            observe("x" * (padding + 1))
        assert caught.value.code == "observation_too_large"
        assert session.session_info().state == "active"
        session.quit()


def test_tree_full_to_visible_keeps_unknown_empty_container_and_ancestors(
    service: ElementProtocolService,
) -> None:
    hidden_large = node_xml(
        resource_id="com.example:id/hidden",
        text="x" * 66_000,
        displayed="false",
    )
    partial = node_xml(
        resource_id="com.example:id/partial",
        bounds="[-10,0][50,100]",
    )
    unknown = node_xml(resource_id="com.example:id/unknown", displayed="")
    empty = node_xml(
        tag="android.view.ViewGroup",
        resource_id="com.example:id/empty",
        displayed="true",
    )
    container = node_xml(
        tag="android.view.ViewGroup",
        resource_id="com.example:id/container",
        displayed="false",
        children=hidden_large + partial + unknown + empty,
    )
    service.source = basic_xml(container)
    with connected(service) as connection:
        session = session_for(service, connection, "tree-visible-fallback")
        data = document(session.observe_tree())
        assert data["coverage"] == "visible_with_ancestors"
        assert data["complete_for_requested_scope"] is False
        roots = data["payload"]["roots"]
        assert [root["id"] for root in roots] == ["container"]
        assert roots[0]["visible"] == "not_visible"
        children = roots[0]["children"]
        assert [child["id"] for child in children] == ["partial", "unknown", "empty"]
        assert children[0]["visible"] == "partially_visible"
        assert children[1]["visible"] == "unknown"
        assert children[2]["children"] == []
        session.quit()


def test_visible_set_still_over_limit_fails_without_truncation(
    service: ElementProtocolService,
) -> None:
    visible = node_xml(
        resource_id="com.example:id/visible",
        text="x" * 66_000,
        displayed="true",
    )
    service.source = basic_xml(visible)
    with connected(service) as connection:
        session = session_for(service, connection, "tree-visible-too-large")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert caught.value.code == "observation_too_large"
        assert session.session_info().state == "active"
        session.quit()


def test_multiple_windows_preserve_all_root_order_and_missing_window_id(
    service: ElementProtocolService,
) -> None:
    first = node_xml(
        tag="android.view.FrameLayout",
        resource_id="com.first:id/root",
        package="com.first",
        extra='window-id="4"',
    )
    second = node_xml(
        tag="custom.Widget",
        resource_id="com.second:id/root",
        package="com.second",
        text="other",
    )
    service.source = basic_xml(first + second)
    with connected(service) as connection:
        session = session_for(service, connection, "tree-multi-window")
        roots = document(session.observe_tree())["payload"]["roots"]
        assert [root["package"] for root in roots] == ["com.first", "com.second"]
        assert roots[0]["window_id"] == 4
        assert "window_id" in roots[1]["missing"]
        assert roots[1]["type"] == "custom.Widget" and "type_ns" not in roots[1]
        session.quit()


def test_known_source_failure_restores_setting_and_session_remains_active(
    service: ElementProtocolService,
) -> None:
    service.queue("source", ResponsePlan(status=500, payload=w3c_error("source")))
    with connected(service) as connection:
        session = session_for(service, connection, "tree-known-source-error")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        assert service.settings["allowInvisibleElements"] is False
        assert len(service.of_kind("settings:post")) == 2
        assert session.session_info().state == "active"
        service.source = basic_xml()
        assert session.observe_tree().roots == ()
        session.quit()


@pytest.mark.parametrize("kind", ["settings:post", "source"])
def test_tree_response_unknown_closes_client_without_restore_or_delete(
    service: ElementProtocolService, kind: str
) -> None:
    service.queue(kind, ResponsePlan(disconnect=True))
    with connected(service) as connection:
        device = f"tree-unknown-{kind}"
        session = session_for(service, connection, device)
        with pytest.raises(ExecutionUnknownError) as caught:
            session.observe_tree()
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
        )
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []
        assert not any(
            request.body == {"settings": {"allowInvisibleElements": False}}
            for request in service.of_kind("settings:post")
        )
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError):
            session.observe_tree()
        assert service.snapshot() == before
        with pytest.raises(ResourceStateError):
            create_session(connection, device)


def test_tree_restore_unknown_retains_completed_source_and_ownership(
    service: ElementProtocolService,
) -> None:
    service.queue("settings:post", ResponsePlan(), ResponsePlan(disconnect=True))
    service.source = basic_xml()
    with connected(service) as connection:
        session = session_for(service, connection, "tree-restore-unknown")
        with pytest.raises(ExecutionUnknownError) as caught:
            session.observe_tree()
        assert caught.value.request_state == "response_unknown"
        assert "source_captured" in caught.value.completed_steps
        assert session.session_info().state == "uncertain"
        assert len(service.of_kind("settings:post")) == 2
        assert service.of_kind("quit") == []


def test_tree_restore_failure_preserves_primary_parse_error(
    service: ElementProtocolService,
) -> None:
    service.source = "<hierarchy><broken></hierarchy>"
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(status=500, payload=w3c_error("tree restore failed")),
    )
    with connected(service) as connection:
        session = session_for(service, connection, "tree-primary-cleanup")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert caught.value.code == "source_invalid"
        assert caught.value.cleanup_errors
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


def test_tree_cancel_after_source_restores_before_returning_error(
    service: ElementProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    cancellation = threading.Event()
    service.queue("source", ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "tree-cancel-after-source")

        def observe() -> None:
            try:
                session.observe_tree(
                    control=OperationControl(
                        timeout_seconds=2, cancellation=cancellation
                    )
                )
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=observe)
        worker.start()
        assert started.wait(timeout=1)
        cancellation.set()
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive() and len(failures) == 1
        error = failures[0]
        assert isinstance(error, OperationCancelledError)
        assert error.request_state == "response_received"
        assert "source_captured" in error.completed_steps
        assert "settings_restored" in error.completed_steps
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        session.quit()


def test_tree_source_timeout_is_unknown_and_holds_resources(
    service: ElementProtocolService,
) -> None:
    service.queue("source", ResponsePlan(delay_seconds=0.2))
    with connected(service) as connection:
        device = "tree-source-timeout"
        session = session_for(service, connection, device)
        with pytest.raises(OperationTimeoutError) as caught:
            session.observe_tree(control=OperationControl(timeout_seconds=0.05))
        assert_error(
            caught.value,
            OperationTimeoutError,
            "operation_timeout",
            "response_unknown",
        )
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []
        with pytest.raises(ResourceStateError):
            create_session(connection, device)


def test_tree_results_are_fresh_but_to_json_is_network_free(
    service: ElementProtocolService,
) -> None:
    service.source = basic_xml(node_xml(text="first"))
    with connected(service) as connection:
        session = session_for(service, connection, "tree-no-cache")
        first = session.observe_tree()
        service.source = basic_xml(node_xml(text="second"))
        second = session.observe_tree()
        assert first.roots[0].text.value == "first"
        assert second.roots[0].text.value == "second"
        before = len(service.snapshot())
        assert first.to_json() is first.to_json()
        assert len(service.snapshot()) == before
        assert len(service.of_kind("source")) == 2
        session.quit()


def test_tree_unknown_defect_after_source_restores_and_rethrows_identity(
    service: ElementProtocolService,
) -> None:
    failure = RuntimeError("projection checkpoint defect")
    cancellation = RaisingCancellation(failure)
    service.queue("source", ResponsePlan(after_send=cancellation.arm))
    service.source = basic_xml(node_xml(resource_id="com.example:id/target"))
    with connected(service) as connection:
        session = session_for(service, connection, "tree-unknown-defect")
        with pytest.raises(RuntimeError) as caught:
            session.observe_tree(
                control=OperationControl(timeout_seconds=2, cancellation=cancellation)
            )
        assert caught.value is failure
        assert service.settings["allowInvisibleElements"] is False
        assert [request.body for request in service.of_kind("settings:post")] == [
            {"settings": {"allowInvisibleElements": True}},
            {"settings": {"allowInvisibleElements": False}},
        ]
        assert session.session_info().state == "active"
        service.source = basic_xml()
        assert session.observe_tree().roots == ()
        session.quit()


def test_huge_numeric_bounds_is_source_invalid_and_restores_setting(
    service: ElementProtocolService,
) -> None:
    huge = "9" * 5_000
    service.source = basic_xml(
        node_xml(
            resource_id="com.example:id/huge",
            bounds=f"[{huge},0][{huge},1]",
        )
    )
    with connected(service) as connection:
        session = session_for(service, connection, "tree-huge-bounds")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert_error(
            caught.value,
            CommandError,
            "source_invalid",
            "response_received",
        )
        assert service.settings["allowInvisibleElements"] is False
        assert len(service.of_kind("settings:post")) == 2
        assert session.session_info().state == "active"
        service.source = basic_xml(
            node_xml(resource_id="com.example:id/valid", bounds="[0,0][1,1]")
        )
        result = session.observe_tree()
        assert result.roots[0].bounds.value is not None
        session.quit()


@pytest.mark.parametrize(
    ("resource_id", "package", "expected"),
    [
        ("com.example:id/save", "com.example", "save"),
        (
            "com.example-evil:id/save",
            "com.example-evil",
            "com.example-evil:id/save",
        ),
        ("com.example:id/foo-bar", "com.example", "com.example:id/foo-bar"),
        ("com.example:id/foo/bar", "com.example", "com.example:id/foo/bar"),
        ("com.other:id/save", "com.example", "com.other:id/save"),
    ],
)
def test_tree_resource_id_shortening_requires_complete_standard_grammar(
    service: ElementProtocolService,
    resource_id: str,
    package: str,
    expected: str,
) -> None:
    service.source = basic_xml(node_xml(resource_id=resource_id, package=package))
    with connected(service) as connection:
        session = session_for(service, connection, f"tree-id-{len(resource_id)}")
        result = session.observe_tree()
        assert result.roots[0].id.value == expected
        assert document(result)["payload"]["roots"][0]["id"] == expected
        session.quit()


def test_structure_target_and_declared_parent_exact_raw_schema(
    service: ElementProtocolService,
) -> None:
    sibling = node_xml(resource_id="com.example:id/sibling", text="first")
    target_xml = node_xml(
        resource_id="com.example:id/target",
        desc="Target",
        text="",
        extra='custom=""',
    )
    container = node_xml(
        tag="android.view.ViewGroup",
        resource_id="com.example:id/container",
        children=target_xml,
    )
    parent_xml = node_xml(
        tag="android.view.ViewGroup",
        resource_id="com.example:id/form",
        text="",
        children=sibling + container,
    )
    service.source = basic_xml(parent_xml)
    with connected(service) as connection:
        session = session_for(service, connection, "structure-schema")
        parent = session.element("id", "form")
        target = session.element("accessibility id", "Target", parent=parent)

        target_result = session.inspect_structure(target, scope="target")
        target_data = document(target_result)
        assert target_data["schema"] == 1 and target_data["kind"] == "structure"
        assert target_data["coverage"] == "requested_scope"
        assert target_data["complete_for_requested_scope"] is True
        assert target_data["upstream_completeness"] == "unknown"
        assert target_data["scope"]["kind"] == "element"
        assert target_data["scope"]["locator"] == target_data["scope"]["range_locator"]
        assert target_result.target_path == (0,)
        assert target_data["payload"]["target_path"] == [0]
        raw_target = target_data["payload"]["roots"][0]
        assert raw_target["tag"] == "android.widget.Button"
        assert raw_target["children"] == []
        assert raw_target["attributes"][:3] == [
            ["resource-id", "com.example:id/target"],
            ["content-desc", "Target"],
            ["text", ""],
        ]
        assert ["custom", ""] in raw_target["attributes"]

        parent_result = session.inspect_structure(target)
        parent_data = document(parent_result)
        assert parent_data["scope"]["kind"] == "declared_parent"
        assert parent_data["scope"]["locator"]["value"] == "Target"
        assert parent_data["scope"]["range_locator"]["value"] == ("com.example:id/form")
        assert parent_result.target_path == (0, 1, 0)
        assert parent_data["payload"]["target_path"] == [0, 1, 0]
        children = parent_data["payload"]["roots"][0]["children"]
        assert [child["attributes"][0][1] for child in children] == [
            "com.example:id/sibling",
            "com.example:id/container",
        ]
        with pytest.raises(FrozenInstanceError):
            parent_result.target_path = ()  # type: ignore[misc]
        session.quit()


def test_structure_declared_parent_without_parent_equals_target(
    service: ElementProtocolService,
) -> None:
    service.source = basic_xml(node_xml(resource_id="com.example:id/target"))
    with connected(service) as connection:
        session = session_for(service, connection, "structure-no-parent")
        target = session.element("id", "target")
        result = session.inspect_structure(target)
        data = document(result)
        assert result.target_path == (0,)
        assert data["scope"]["kind"] == "element"
        assert data["scope"]["locator"] == data["scope"]["range_locator"]
        assert data["payload"]["roots"][0]["attributes"][0][1] == (
            "com.example:id/target"
        )
        session.quit()


def test_structure_raw_id_and_second_window_are_exact_result_local_scope(
    service: ElementProtocolService,
) -> None:
    raw_value = "vendor/odd@id"
    first_window = node_xml(
        tag="android.view.FrameLayout",
        resource_id="com.first:id/root",
        package="com.first",
        extra='window-id="1"',
    )
    raw_target = node_xml(resource_id=raw_value, package="com.second")
    second_window = node_xml(
        tag="android.view.FrameLayout",
        resource_id="com.second:id/root",
        package="com.second",
        extra='window-id="2"',
        children=raw_target,
    )
    service.source = basic_xml(first_window + second_window)
    with connected(service) as connection:
        session = session_for(service, connection, "structure-raw-window")
        raw = session.element("id", raw_value, raw_id=True)
        result = session.inspect_structure(raw, scope="target")
        data = document(result)
        assert result.target_path == (0,)
        assert len(result.roots) == 1
        assert data["scope"]["locator"]["raw_id"] is True
        assert data["payload"]["roots"][0]["attributes"][0] == [
            "resource-id",
            raw_value,
        ]
        assert service.of_kind("find") == []
        session.quit()


def test_structure_invalid_scope_value_is_rejected_before_protocol_io(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "structure-invalid-scope")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.inspect_structure(
                session.element("id", "target"), scope=cast(Any, "root")
            )
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("locator", ["unresolved", "xpath", "foreign", "forged"])
def test_structure_invalid_scope_rejected_before_settings_and_source(
    service: ElementProtocolService, locator: str
) -> None:
    service.create_package = None
    with connected(service) as connection:
        first = session_for(service, connection, f"structure-invalid-a-{locator}")
        second = session_for(
            service, connection, f"structure-invalid-b-{locator}", app_id=None
        )
        if locator == "unresolved":
            element = second.element("id", "short")
            expected = "structure_scope_unavailable"
        elif locator == "xpath":
            element = second.element("xpath", "//*[@text='x']")
            expected = "structure_scope_unavailable"
        elif locator == "foreign":
            element = first.element("id", "target")
            expected = "element_session_mismatch"
        else:
            element = object.__new__(Element)
            expected = "invalid_argument"
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            second.inspect_structure(element)
        assert_error(caught.value, InvalidRequestError, expected, "not_sent")
        assert service.snapshot() == before
        first.quit()
        second.quit()


@pytest.mark.parametrize(
    ("stage", "count", "code"),
    [
        ("parent", 0, "target_not_found"),
        ("parent", 2, "target_ambiguous"),
        ("target", 0, "target_not_found"),
        ("target", 2, "target_ambiguous"),
    ],
)
def test_structure_requires_unique_match_at_every_local_layer(
    service: ElementProtocolService, stage: str, count: int, code: str
) -> None:
    target_nodes = "".join(
        node_xml(resource_id="com.example:id/target")
        for _ in range(count if stage == "target" else 1)
    )
    parent_nodes = "".join(
        node_xml(
            tag="android.view.ViewGroup",
            resource_id="com.example:id/form",
            children=target_nodes,
        )
        for _ in range(count if stage == "parent" else 1)
    )
    service.source = basic_xml(parent_nodes)
    with connected(service) as connection:
        session = session_for(service, connection, f"structure-unique-{stage}-{count}")
        parent = session.element("id", "form")
        target = session.element("id", "target", parent=parent)
        with pytest.raises(TargetError) as caught:
            session.inspect_structure(target)
        assert_error(caught.value, TargetError, code, "response_received")
        assert service.settings["allowInvisibleElements"] is False
        session.quit()


def test_structure_complete_document_65536_and_65537_boundaries(
    service: ElementProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "structure-json-edge")
        target = session.element("id", "target")

        def inspect(text: str) -> RawStructureObservation:
            service.source = basic_xml(
                node_xml(resource_id="com.example:id/target", text=text)
            )
            return session.inspect_structure(target, scope="target")

        baseline = inspect("")
        padding = 65_536 - len(baseline.to_json())
        assert padding > 0
        exact = inspect("x" * padding)
        assert len(exact.to_json()) == 65_536
        with pytest.raises(CommandError) as caught:
            inspect("x" * (padding + 1))
        assert caught.value.code == "observation_too_large"
        assert session.session_info().state == "active"
        session.quit()


def test_structure_fallback_keeps_invisible_target_path_and_recomputes_index(
    service: ElementProtocolService,
) -> None:
    visible = node_xml(resource_id="com.example:id/visible")
    removed = node_xml(
        resource_id="com.example:id/removed",
        text="x" * 66_000,
        displayed="false",
    )
    target_xml = node_xml(
        resource_id="com.example:id/target",
        displayed="false",
    )
    parent_xml = node_xml(
        tag="android.view.ViewGroup",
        resource_id="com.example:id/form",
        displayed="false",
        children=visible + removed + target_xml,
    )
    service.source = basic_xml(parent_xml)
    with connected(service) as connection:
        session = session_for(service, connection, "structure-target-fallback")
        parent = session.element("id", "form")
        target = session.element("id", "target", parent=parent)
        result = session.inspect_structure(target)
        data = document(result)
        assert data["coverage"] == "visible_with_ancestors_and_target"
        assert data["complete_for_requested_scope"] is False
        assert result.target_path == (0, 1)
        assert data["payload"]["target_path"] == [0, 1]
        children = data["payload"]["roots"][0]["children"]
        assert [child["attributes"][0][1] for child in children] == [
            "com.example:id/visible",
            "com.example:id/target",
        ]
        assert children[1]["attributes"][11] == ["displayed", "false"]
        session.quit()


def test_structure_forced_invisible_target_still_over_limit_fails(
    service: ElementProtocolService,
) -> None:
    target_xml = node_xml(
        resource_id="com.example:id/target",
        text="x" * 66_000,
        displayed="false",
    )
    service.source = basic_xml(target_xml)
    with connected(service) as connection:
        session = session_for(service, connection, "structure-target-too-large")
        with pytest.raises(CommandError) as caught:
            session.inspect_structure(session.element("id", "target"), scope="target")
        assert caught.value.code == "observation_too_large"
        assert session.session_info().state == "active"
        session.quit()


def test_structure_known_target_failure_restores_and_allows_reuse(
    service: ElementProtocolService,
) -> None:
    service.source = basic_xml()
    with connected(service) as connection:
        session = session_for(service, connection, "structure-known-error")
        target = session.element("id", "target")
        with pytest.raises(TargetError) as caught:
            session.inspect_structure(target)
        assert_error(
            caught.value,
            TargetError,
            "target_not_found",
            "response_received",
        )
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        service.source = basic_xml(node_xml(resource_id="com.example:id/target"))
        assert session.inspect_structure(target).target_path == (0,)
        session.quit()


def test_structure_source_unknown_closes_without_restore_or_delete(
    service: ElementProtocolService,
) -> None:
    service.queue("source", ResponsePlan(disconnect=True))
    with connected(service) as connection:
        device = "structure-source-unknown"
        session = session_for(service, connection, device)
        target = session.element("id", "target")
        with pytest.raises(ExecutionUnknownError) as caught:
            session.inspect_structure(target)
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
        )
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []
        assert not any(
            request.body == {"settings": {"allowInvisibleElements": False}}
            for request in service.of_kind("settings:post")
        )
        with pytest.raises(ResourceStateError):
            create_session(connection, device)


def test_structure_unknown_defect_restores_and_rethrows_same_object(
    service: ElementProtocolService,
) -> None:
    failure = RuntimeError("structure projection defect")
    cancellation = RaisingCancellation(failure)
    service.queue("source", ResponsePlan(after_send=cancellation.arm))
    service.source = basic_xml(node_xml(resource_id="com.example:id/target"))
    with connected(service) as connection:
        session = session_for(service, connection, "structure-unknown-defect")
        with pytest.raises(RuntimeError) as caught:
            session.inspect_structure(
                session.element("id", "target"),
                control=OperationControl(timeout_seconds=2, cancellation=cancellation),
            )
        assert caught.value is failure
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        service.source = basic_xml(node_xml(resource_id="com.example:id/target"))
        assert session.inspect_structure(
            session.element("id", "target")
        ).target_path == (0,)
        session.quit()


def test_structure_cancel_after_source_restores_before_error(
    service: ElementProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    cancellation = threading.Event()
    service.queue("source", ResponsePlan(started=started, release=release))

    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "structure-cancel")
        target = session.element("id", "target")

        def inspect() -> None:
            try:
                session.inspect_structure(
                    target,
                    control=OperationControl(
                        timeout_seconds=2, cancellation=cancellation
                    ),
                )
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=inspect)
        worker.start()
        assert started.wait(timeout=1)
        cancellation.set()
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive() and len(failures) == 1
        error = failures[0]
        assert isinstance(error, OperationCancelledError)
        assert error.request_state == "response_received"
        assert "source_captured" in error.completed_steps
        assert "settings_restored" in error.completed_steps
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        session.quit()


def test_structure_restore_unknown_preserves_source_and_target_ownership(
    service: ElementProtocolService,
) -> None:
    service.queue("settings:post", ResponsePlan(), ResponsePlan(disconnect=True))
    service.source = basic_xml(node_xml(resource_id="com.example:id/target"))
    with connected(service) as connection:
        session = session_for(service, connection, "structure-restore-unknown")
        with pytest.raises(ExecutionUnknownError) as caught:
            session.inspect_structure(session.element("id", "target"))
        assert caught.value.request_state == "response_unknown"
        assert "source_captured" in caught.value.completed_steps
        assert session.session_info().state == "uncertain"
        assert len(service.of_kind("settings:post")) == 2
        assert service.of_kind("quit") == []


def test_structure_source_deadline_is_unknown_and_retains_resources(
    service: ElementProtocolService,
) -> None:
    service.queue("source", ResponsePlan(delay_seconds=0.2))
    with connected(service) as connection:
        device = "structure-timeout"
        session = session_for(service, connection, device)
        with pytest.raises(OperationTimeoutError) as caught:
            session.inspect_structure(
                session.element("id", "target"),
                control=OperationControl(timeout_seconds=0.05),
            )
        assert_error(
            caught.value,
            OperationTimeoutError,
            "operation_timeout",
            "response_unknown",
        )
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []
        with pytest.raises(ResourceStateError):
            create_session(connection, device)


def test_structure_results_are_fresh_but_to_json_is_network_free(
    service: ElementProtocolService,
) -> None:
    target = "com.example:id/target"
    service.source = basic_xml(node_xml(resource_id=target, text="first"))
    with connected(service) as connection:
        session = session_for(service, connection, "structure-no-cache")
        element = session.element("id", "target")
        first = session.inspect_structure(element, scope="target")
        service.source = basic_xml(node_xml(resource_id=target, text="second"))
        second = session.inspect_structure(element, scope="target")
        assert first.roots[0].attributes[2] == ("text", "first")
        assert second.roots[0].attributes[2] == ("text", "second")
        before = len(service.snapshot())
        assert first.to_json() is first.to_json()
        assert len(service.snapshot()) == before
        assert len(service.of_kind("source")) == 2
        session.quit()


@pytest.mark.parametrize(
    ("bounds", "expected_relation", "expected_visibility"),
    [
        ("[10,20][110,120]", "inside", "visible"),
        ("[-10,20][50,120]", "intersects", "partially_visible"),
        ("[-110,20][-10,120]", "outside_left", "unknown"),
        ("[1090,20][1190,120]", "outside_right", "unknown"),
        ("[10,-120][110,-20]", "outside_above", "unknown"),
        ("[10,2410][110,2510]", "outside_below", "unknown"),
        ("[-110,-120][-10,-20]", "unknown", "unknown"),
    ],
)
def test_tree_viewport_relation_for_valid_single_viewport_geometry(
    service: ElementProtocolService,
    bounds: str,
    expected_relation: str,
    expected_visibility: str,
) -> None:
    service.source = basic_xml(
        node_xml(resource_id="com.example:id/geometry", bounds=bounds)
    )
    with connected(service) as connection:
        session = session_for(
            service, connection, f"spatial-{expected_relation}-{len(bounds)}"
        )
        result = session.observe_tree()
        node = result.roots[0]
        data = document(result)["payload"]["roots"][0]
        assert node.bounds.state == "value"
        assert node.viewport_relation == expected_relation
        assert node.visibility == expected_visibility
        assert data["viewport_relation"] == expected_relation
        assert data["visible"] == expected_visibility
        assert "requires_navigation" not in data
        assert "suggested_gesture" not in data
        assert "direct_action_allowed" not in data
        session.quit()


def test_reversed_edge_bounds_reports_outside_fact_without_fabricating_bounds(
    service: ElementProtocolService,
) -> None:
    reversed_bounds = "[1116,437][1080,688]"
    service.source = basic_xml(
        node_xml(
            resource_id="com.example:id/offscreen",
            bounds=reversed_bounds,
            displayed="false",
        )
    )

    with connected(service) as connection:
        session = session_for(service, connection, "spatial-reversed-edge")
        tree = session.observe_tree()
        node = tree.roots[0]
        data = document(tree)["payload"]["roots"][0]
        assert node.bounds.state == "unknown" and node.bounds.value is None
        assert node.viewport_relation == "outside_right"
        assert node.visibility == "not_visible"
        assert "bounds" in data["unknown"]
        assert data["viewport_relation"] == "outside_right"
        assert "bounds" not in data

        target = session.element("id", "offscreen")
        raw = session.inspect_structure(target, scope="target")
        assert ("bounds", reversed_bounds) in raw.roots[0].attributes
        assert ["bounds", reversed_bounds] in document(raw)["payload"]["roots"][0][
            "attributes"
        ]
        session.quit()


def test_invalid_displayed_value_keeps_visibility_unknown_but_geometry_fact(
    service: ElementProtocolService,
) -> None:
    service.source = basic_xml(
        node_xml(
            resource_id="com.example:id/invalid-displayed",
            bounds="[10,20][110,120]",
            displayed="invalid",
        )
    )
    with connected(service) as connection:
        session = session_for(service, connection, "spatial-invalid-displayed")
        node = session.observe_tree().roots[0]
        assert node.visibility == "unknown"
        assert node.viewport_relation == "inside"
        session.quit()


def test_multiple_window_roots_use_shared_positive_root_viewport(
    service: ElementProtocolService,
) -> None:
    first = node_xml(
        resource_id="com.first:id/one",
        package="com.first",
        bounds="[10,20][110,120]",
    )
    second = node_xml(
        resource_id="com.second:id/two",
        package="com.second",
        bounds="[1090,20][1190,120]",
        displayed="true",
    )
    service.source = basic_xml(first + second)
    with connected(service) as connection:
        session = session_for(service, connection, "spatial-multi-root")
        result = session.observe_tree()
        assert [node.viewport_relation for node in result.roots] == [
            "inside",
            "outside_right",
        ]
        assert [node.visibility for node in result.roots] == ["visible", "unknown"]
        data = document(result)["payload"]["roots"]
        assert [node["viewport_relation"] for node in data] == [
            "inside",
            "outside_right",
        ]
        session.quit()


@pytest.mark.parametrize(
    ("bounds", "displayed", "expected_visibility"),
    [
        ("[500,437][400,688]", "false", "not_visible"),
        ("[500,437][400,688]", "true", "unknown"),
        ("[1116,700][1080,600]", "true", "unknown"),
    ],
)
def test_ambiguous_reversed_bounds_remains_unknown_relation(
    service: ElementProtocolService,
    bounds: str,
    displayed: str,
    expected_visibility: str,
) -> None:
    service.source = basic_xml(
        node_xml(
            resource_id="com.example:id/reversed",
            bounds=bounds,
            displayed=displayed,
        )
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"spatial-ambiguous-{displayed}")
        result = session.observe_tree()
        node = result.roots[0]
        assert node.bounds.state == "unknown"
        assert node.viewport_relation == "unknown"
        assert node.visibility == expected_visibility
        data = document(result)["payload"]["roots"][0]
        assert data["viewport_relation"] == "unknown"
        assert "bounds" in data["unknown"]
        session.quit()


@pytest.mark.parametrize(
    "bounds",
    ["invalid", "[a,0][1,1]", "[0,0][1]", "[0,0][1.5,2]"],
)
def test_malformed_or_noninteger_source_bounds_still_source_invalid(
    service: ElementProtocolService, bounds: str
) -> None:
    service.source = basic_xml(
        node_xml(resource_id="com.example:id/malformed", bounds=bounds)
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"spatial-malformed-{len(bounds)}")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert_error(
            caught.value,
            CommandError,
            "source_invalid",
            "response_received",
        )
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        session.quit()


def test_inspect_element_invalid_rect_remains_source_invalid(
    service: ElementProtocolService,
) -> None:
    service.rects["target"] = {"x": 0, "y": 0, "width": -1, "height": 10}
    with connected(service) as connection:
        session = session_for(service, connection, "spatial-element-rect")
        with pytest.raises(CommandError) as caught:
            session.inspect_element(
                session.element("id", "target"), attributes=("bounds",)
            )
        assert_error(
            caught.value,
            CommandError,
            "source_invalid",
            "response_received",
        )
        assert session.session_info().state == "active"
        session.quit()


def test_tree_fallback_retains_offscreen_node_and_reports_offscreen_coverage(
    service: ElementProtocolService,
) -> None:
    hidden_large = node_xml(
        resource_id="com.example:id/hidden",
        text="x" * 66_000,
        displayed="false",
    )
    offscreen = node_xml(
        resource_id="com.example:id/offscreen",
        bounds="[1090,10][1190,110]",
        displayed="false",
    )
    ancestor = node_xml(
        tag="android.view.ViewGroup",
        resource_id="com.example:id/ancestor",
        displayed="false",
        children=hidden_large + offscreen,
    )
    service.source = basic_xml(ancestor)
    with connected(service) as connection:
        session = session_for(service, connection, "spatial-fallback")
        result = session.observe_tree()
        data = document(result)
        assert data["coverage"] == "visible_with_ancestors_and_offscreen"
        assert data["complete_for_requested_scope"] is False
        roots = data["payload"]["roots"]
        assert [root["id"] for root in roots] == ["ancestor"]
        children = roots[0]["children"]
        assert [child["id"] for child in children] == ["offscreen"]
        assert children[0]["viewport_relation"] == "outside_right"
        assert children[0]["visible"] == "not_visible"
        session.quit()


def test_offscreen_fallback_still_over_limit_fails_without_truncation(
    service: ElementProtocolService,
) -> None:
    offscreen_large = node_xml(
        resource_id="com.example:id/offscreen",
        text="x" * 66_000,
        bounds="[1090,10][1190,110]",
        displayed="false",
    )
    service.source = basic_xml(offscreen_large)
    with connected(service) as connection:
        session = session_for(service, connection, "spatial-offscreen-too-large")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert caught.value.code == "observation_too_large"
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    ("viewport_attributes", "bounds", "expected_bounds_state"),
    [
        ('rotation="0" height="2400"', "[1116,437][1080,688]", "unknown"),
        ('rotation="0" width="bad" height="2400"', "[10,20][110,120]", "value"),
        ('rotation="0" width="1080" height="bad"', "[1116,437][1080,688]", "unknown"),
        ('rotation="0" width="0" height="2400"', "[10,20][110,120]", "value"),
        ('rotation="0" width="1080" height="0"', "[1116,437][1080,688]", "unknown"),
        ('rotation="0" width="-1" height="2400"', "[10,20][110,120]", "value"),
        ('rotation="0" width="1080" height="-1"', "[1116,437][1080,688]", "unknown"),
    ],
)
def test_unreliable_viewport_preserves_bounds_state_but_not_relation(
    service: ElementProtocolService,
    viewport_attributes: str,
    bounds: str,
    expected_bounds_state: str,
) -> None:
    node = node_xml(
        resource_id="com.example:id/unreliable",
        bounds=bounds,
        displayed="false",
    )
    service.source = f"<hierarchy {viewport_attributes}>{node}</hierarchy>"
    with connected(service) as connection:
        session = session_for(service, connection, f"spatial-unreliable-{len(bounds)}")
        result = session.observe_tree()
        observed = result.roots[0]
        assert observed.bounds.state == expected_bounds_state
        assert observed.viewport_relation == "unknown"
        assert observed.visibility == "not_visible"
        data = document(result)["payload"]["roots"][0]
        assert data["viewport_relation"] == "unknown"
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    "viewport_attributes",
    [
        'rotation="0" width="bad" height="2400"',
        'rotation="0" width="0" height="2400"',
        'rotation="0" width="-1" height="2400"',
    ],
)
def test_multi_root_unreliable_viewport_keeps_relation_unknown(
    service: ElementProtocolService, viewport_attributes: str
) -> None:
    first = node_xml(resource_id="com.first:id/one", package="com.first")
    second = node_xml(
        resource_id="com.second:id/two",
        package="com.second",
        bounds="[1090,20][1190,120]",
    )
    service.source = f"<hierarchy {viewport_attributes}>{first}{second}</hierarchy>"
    with connected(service) as connection:
        session = session_for(service, connection, "spatial-multi-unreliable")
        result = session.observe_tree()
        assert [node.viewport_relation for node in result.roots] == [
            "unknown",
            "unknown",
        ]
        session.quit()


def test_multi_root_reversed_edge_uses_shared_viewport_and_raw_stays_exact(
    service: ElementProtocolService,
) -> None:
    reversed_bounds = "[1116,437][1080,688]"
    first = node_xml(
        resource_id="com.first:id/reversed",
        package="com.first",
        bounds=reversed_bounds,
        displayed="false",
    )
    second = node_xml(
        resource_id="com.second:id/root",
        package="com.second",
    )
    service.source = basic_xml(first + second)
    with connected(service) as connection:
        session = session_for(service, connection, "spatial-multi-reversed")
        result = session.observe_tree()
        observed = result.roots[0]
        assert observed.bounds.state == "unknown"
        assert observed.viewport_relation == "outside_right"
        assert observed.visibility == "not_visible"
        data = document(result)["payload"]["roots"][0]
        assert data["viewport_relation"] == "outside_right"
        assert "bounds" in data["unknown"]
        raw = session.inspect_structure(
            session.element("id", "com.first:id/reversed"), scope="target"
        )
        assert ("bounds", reversed_bounds) in raw.roots[0].attributes
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    "viewport_attributes",
    [
        'rotation="0" height="2400"',
        'rotation="0" width="bad" height="2400"',
        'rotation="0" width="0" height="2400"',
        'rotation="0" width="-1" height="2400"',
    ],
)
def test_unreliable_viewport_malformed_bounds_remains_source_invalid(
    service: ElementProtocolService, viewport_attributes: str
) -> None:
    node = node_xml(resource_id="com.example:id/bad", bounds="[a,0][1,1]")
    service.source = f"<hierarchy {viewport_attributes}>{node}</hierarchy>"
    with connected(service) as connection:
        session = session_for(service, connection, "spatial-unreliable-malformed")
        with pytest.raises(CommandError) as caught:
            session.observe_tree()
        assert_error(
            caught.value,
            CommandError,
            "source_invalid",
            "response_received",
        )
        assert service.settings["allowInvisibleElements"] is False
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ("[1116,437][1080,688]", "outside_right"),
        ("[0,437][-36,688]", "outside_left"),
        ("[100,2500][200,2400]", "outside_below"),
        ("[100,0][200,-100]", "outside_above"),
    ],
)
def test_reversed_exact_edge_positive_facts_cover_all_four_directions(
    service: ElementProtocolService, bounds: str, expected: str
) -> None:
    service.source = basic_xml(
        node_xml(
            resource_id="com.example:id/edge",
            bounds=bounds,
            displayed="false",
        )
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"spatial-edge-{expected}")
        node = session.observe_tree().roots[0]
        assert node.bounds.state == "unknown"
        assert node.viewport_relation == expected
        assert node.visibility == "not_visible"
        session.quit()


@pytest.mark.parametrize(
    "bounds",
    [
        "[1116,2500][1080,2600]",
        "[1116,-200][1080,-100]",
        "[0,2500][-36,2600]",
        "[0,-200][-36,-100]",
        "[1200,2500][1300,2400]",
        "[-200,2500][-100,2400]",
        "[1200,0][1300,-100]",
        "[-200,0][-100,-100]",
        "[1116,2500][1080,2400]",
    ],
)
def test_reversed_exact_edge_with_orthogonal_outside_conflict_is_unknown(
    service: ElementProtocolService, bounds: str
) -> None:
    service.source = basic_xml(
        node_xml(
            resource_id="com.example:id/conflict",
            bounds=bounds,
            displayed="true",
        )
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"spatial-conflict-{len(bounds)}")
        result = session.observe_tree()
        node = result.roots[0]
        assert node.bounds.state == "unknown"
        assert node.viewport_relation == "unknown"
        assert node.visibility == "unknown"
        data = document(result)["payload"]["roots"][0]
        assert data["viewport_relation"] == "unknown"
        assert "bounds" in data["unknown"]
        session.quit()
