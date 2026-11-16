from __future__ import annotations

import base64
import threading
import time as time_module
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from appium_connect_agent.automation import (
    CommandError,
    ExecutionUnknownError,
    InvalidRequestError,
    OperationTimeoutError,
    Session,
    SessionBusyError,
    TargetError,
    create_xcuitest_session,
)
from appium_connect_agent.automation import _session as session_module
from appium_connect_agent.runtime import OperationControl, RuntimeConnection
from tests.automation._action_protocol import (
    ActionProtocolService,
    Request,
    ResponsePlan,
    assert_error,
    connected,
    mac_session_for,
    session_for,
    w3c_error,
)
from tests.automation.test_screenshot_pointer import _MINIMAL_PNG
from tests.automation.test_session_lifecycle import managed_connection


class IosActionProtocolService(ActionProtocolService):
    @staticmethod
    def _kind(request: Request) -> str:
        if request.method == "GET" and request.path.endswith("/screenshot"):
            return "screenshot"
        if request.method == "POST" and request.path.endswith("/actions"):
            return "pointer"
        return ActionProtocolService._kind(request)

    def _default_payload(self, request: Request, kind: str) -> object:
        if kind == "screenshot":
            return {"value": base64.b64encode(_MINIMAL_PNG).decode("ascii")}
        if kind == "pointer":
            return {"value": None}
        if request.path.endswith("/execute/sync") and request.body is not None:
            script = request.body.get("script")
            if script in {"mobile: terminateApp", "mobile: removeApp"}:
                return {"value": True}
            if script == "mobile: queryAppState":
                return {"value": 2}
            if script == "mobile: getClipboard":
                return {"value": base64.b64encode("剪贴板".encode()).decode()}
        return super()._default_payload(request, kind)


@pytest.fixture
def service() -> Iterator[IosActionProtocolService]:
    current = IosActionProtocolService()
    with current:
        yield current


def ios_session_for(
    service: IosActionProtocolService,
    connection: RuntimeConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> Session:
    service.matches.update(
        {
            (None, "id", name): [name]
            for name in ("container", "source", "destination", "target")
        }
    )
    monkeypatch.setattr(
        session_module,
        "_prepare_xcuitest_derived_data",
        lambda port, operation_id: f"/private/tmp/test-{port}",
    )
    return create_xcuitest_session(connection, f"IOS-ACTION-{id(service)}")


def script_requests(service: IosActionProtocolService) -> list[Request]:
    return [
        request
        for request in service.snapshot()
        if request.path.endswith("/execute/sync")
    ]


def script_and_payload(request: Request) -> tuple[object, object]:
    assert request.body is not None
    args = request.body.get("args")
    assert isinstance(args, list) and len(args) == 1
    return request.body.get("script"), args[0]


def test_element_exact_routes_and_payloads(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        element = session.element("id", "target")

        element.click()
        element.double_click()
        element.long_click(duration_ms=750)
        element.send_keys("text")
        element.clear()
        element.send_macos_keys(("a",))
        element.macos_swipe(direction="left", velocity=2.5)
        element.ios_scroll("down", distance=0.75)

        requests = service.snapshot()
        click = [request for request in requests if request.path.endswith("/click")]
        send = [request for request in requests if request.path.endswith("/value")]
        clear = [request for request in requests if request.path.endswith("/clear")]
        assert len(click) == len(send) == len(clear) == 1
        assert send[0].body == {"text": "text", "value": ["t", "e", "x", "t"]}
        assert [
            script_and_payload(request) for request in script_requests(service)
        ] == [
            ("mobile: doubleTap", {"elementId": "target"}),
            (
                "mobile: touchAndHold",
                {"elementId": "target", "duration": 0.75},
            ),
            ("mobile: keys", {"elementId": "target", "keys": ["a"]}),
            (
                "mobile: swipe",
                {"elementId": "target", "direction": "left", "velocity": 2.5},
            ),
            (
                "mobile: scroll",
                {"elementId": "target", "direction": "down", "distance": 0.75},
            ),
        ]
        session.quit()


@pytest.mark.parametrize(
    ("by", "value", "predicate", "payload"),
    [
        ("name", "Save", None, {"elementId": "container", "name": "Save"}),
        (
            "class name",
            "XCUIElementTypeButton",
            "enabled == true",
            {
                "elementId": "container",
                "predicateString": 'type == "XCUIElementTypeButton" AND (enabled == true)',
            },
        ),
    ],
)
def test_container_scroll_payload_and_postcheck(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    by: str,
    value: str,
    predicate: str | None,
    payload: dict[str, object],
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        container = session.element("id", "container")
        target = session.element(by, value, parent=container, predicate=predicate)
        container.scroll(target, max_swipes=30)
        scroll = script_requests(service)[0]
        assert script_and_payload(scroll) == ("mobile: scroll", payload)
        postcheck = [
            request
            for request in service.snapshot()
            if "/element/container/elements" in request.path
        ]
        assert len(postcheck) == 1
        session.quit()


def test_container_scroll_postcheck_failures(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        container = session.element("id", "container")
        target = session.element("name", "missing", parent=container)
        service.matches[("container", "name", "missing")] = []
        with pytest.raises(TargetError) as caught:
            container.scroll(target, max_swipes=1)
        assert_error(
            caught.value,
            TargetError,
            "target_not_found",
            "response_received",
            steps=("container_resolved", "container_displayed", "action_completed"),
        )
        session.quit()


def test_drag_payload_and_ios_duration_floor(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        source = session.element("id", "source")
        destination = session.element("id", "destination")
        source.drag_and_drop(
            destination,
            destination_x_ratio=1.0,
            destination_y_ratio=0.0,
            duration_ms=500,
        )
        assert script_and_payload(script_requests(service)[0]) == (
            "mobile: dragFromToForDuration",
            {
                "duration": 0.5,
                "fromX": 25,
                "fromY": 40,
                "toX": 39,
                "toY": 20,
            },
        )
        before = len(service.snapshot())
        with pytest.raises(InvalidRequestError) as caught:
            source.drag_and_drop(destination, duration_ms=499)
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert len(service.snapshot()) == before
        session.quit()


@pytest.mark.parametrize("action", ["long_click", "drag_and_drop"])
def test_duration_equal_to_remaining_budget_is_not_sent(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    monkeypatch.setattr(time_module, "monotonic", lambda: 100.0)
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        source = session.element("id", "source")
        before_scripts = len(script_requests(service))
        with pytest.raises(OperationTimeoutError) as caught:
            if action == "long_click":
                source.long_click(
                    duration_ms=500,
                    control=OperationControl(timeout_seconds=0.5),
                )
            else:
                source.drag_and_drop(
                    session.element("id", "destination"),
                    duration_ms=500,
                    control=OperationControl(timeout_seconds=0.5),
                )
        assert_error(
            caught.value, OperationTimeoutError, "operation_timeout", "not_sent"
        )
        assert len(script_requests(service)) == before_scripts
        session.quit()


def test_device_exact_commands_and_application_management(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = tmp_path.resolve() / "Sample.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(b"plist")
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        device = session.device
        device.press_button("home")
        device.tap_at(1, 2)
        device.swipe_between(1, 2, 3, 4, duration_ms=500)
        device.send_keys(("a",))
        assert device.hide_keyboard() is True
        assert device.get_clipboard_text() == "剪贴板"
        device.set_clipboard_text("秘密")
        device.accept_alert(button_label="Allow")
        device.dismiss_alert()
        assert device.take_screenshot() == _MINIMAL_PNG
        device.activate_app("com.example.app")
        assert device.terminate_app("com.example.app") is True
        assert device.query_app_state("com.example.app") == 2
        device.launch_app(bundle_id="com.example.app", arguments=("--safe",))
        device.install_app(
            app,
            control=OperationControl(timeout_seconds=5.0),
        )
        assert device.remove_app("com.example.app") is True

        scripts = [script_and_payload(request) for request in script_requests(service)]
        assert scripts[:12] == [
            ("mobile: pressButton", {"name": "home"}),
            ("mobile: tap", {"x": 1, "y": 2}),
            ("mobile: keys", {"keys": ["a"]}),
            ("mobile: hideKeyboard", {}),
            ("mobile: getClipboard", {"contentType": "plaintext"}),
            (
                "mobile: setClipboard",
                {
                    "content": base64.b64encode("秘密".encode()).decode(),
                    "contentType": "plaintext",
                },
            ),
            ("mobile: alert", {"action": "accept", "buttonLabel": "Allow"}),
            ("mobile: alert", {"action": "dismiss"}),
            ("mobile: activateApp", {"bundleId": "com.example.app"}),
            ("mobile: terminateApp", {"bundleId": "com.example.app"}),
            ("mobile: queryAppState", {"bundleId": "com.example.app"}),
            (
                "mobile: launchApp",
                {"bundleId": "com.example.app", "arguments": ["--safe"]},
            ),
        ]
        assert scripts[13] == (
            "mobile: removeApp",
            {"bundleId": "com.example.app"},
        )
        install_payload = cast(dict[str, object], scripts[12][1])
        assert install_payload["app"] == str(app)
        timeout_ms = install_payload["timeoutMs"]
        assert type(timeout_ms) is int
        assert 1 <= timeout_ms <= 5_000
        session.quit()


@pytest.mark.parametrize(
    "call",
    [
        lambda session: session.element("id", "x").ios_scroll("up"),
        lambda session: session.device.press_button("home"),
    ],
)
def test_new_ios_only_methods_reject_android_and_macos_without_send(
    service: IosActionProtocolService,
    call: Any,
) -> None:
    with connected(service) as connection:
        sessions = (
            session_for(service, connection, "android"),
            mac_session_for(service, connection),
        )
        for session in sessions:
            before = len(service.snapshot())
            with pytest.raises(InvalidRequestError) as caught:
                call(session)
            assert_error(
                caught.value,
                InvalidRequestError,
                "unsupported_operation",
                "not_sent",
            )
            assert len(service.snapshot()) == before
            session.quit()


@pytest.mark.parametrize(
    ("queue_kind", "result", "invoke"),
    [
        ("action", False, lambda session: session.device.press_button("home")),
        ("action", True, lambda session: session.device.hide_keyboard()),
        ("action", 1, lambda session: session.device.terminate_app("com.example")),
        ("action", True, lambda session: session.device.query_app_state("com.example")),
        (
            "action",
            False,
            lambda session: session.element("id", "target").double_click(),
        ),
        (
            "scroll",
            False,
            lambda session: session.element("id", "target").ios_scroll("up"),
        ),
        (
            "action",
            False,
            lambda session: session.element("id", "source").drag_and_drop(
                session.element("id", "destination")
            ),
        ),
    ],
)
def test_ios_strict_action_results_are_known_failures(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    queue_kind: str,
    result: object,
    invoke: Any,
) -> None:
    service.queue(queue_kind, ResponsePlan(payload={"value": result}))
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        with pytest.raises(CommandError) as caught:
            invoke(session)
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        assert session.session_info().state == "active"
        session.quit()


def test_ios_value_and_platform_gates_precede_io(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        element = session.element("id", "target")
        destination = session.element("id", "destination")
        cases: list[tuple[str, Any]] = [
            ("invalid_argument", lambda: element.ios_scroll("up", distance=True)),
            (
                "invalid_argument",
                lambda: session.device.press_button("HOME"),  # type: ignore[arg-type]
            ),
            (
                "unsupported_operation",
                lambda: element.click(key_modifier_flags=1),
            ),
            (
                "unsupported_operation",
                lambda: element.macos_swipe(direction="up", key_modifier_flags=1),
            ),
            (
                "unsupported_operation",
                lambda: element.drag_and_drop(destination, key_modifier_flags=1),
            ),
            (
                "unsupported_operation",
                lambda: session.device.swipe_between(1, 2, 3, 4, key_modifier_flags=1),
            ),
            (
                "unsupported_operation",
                lambda: session.device.set_clipboard_text("secret", label="label"),
            ),
            (
                "unsupported_operation",
                lambda: session.device.launch_app(
                    bundle_id="com.example", app_path=Path("/tmp/Missing.app")
                ),
            ),
            (
                "unsupported_operation",
                lambda: session.device.install_app(
                    Path("/tmp/Missing.ipa"), allow_test_packages=True
                ),
            ),
        ]
        before = len(service.snapshot())
        for code, invoke in cases:
            with pytest.raises(InvalidRequestError) as caught:
                invoke()
            assert_error(caught.value, InvalidRequestError, code, "not_sent")
            assert len(service.snapshot()) == before
        session.quit()


def test_ios_action_errors_redact_sensitive_chain(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    canary = "IOS_ACTION_SECRET_CANARY"
    service.queue(
        "action", ResponsePlan(status=500, payload=w3c_error(f"failed {canary}"))
    )
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        with pytest.raises(CommandError) as caught:
            session.device.launch_app(
                bundle_id="com.example.secret", arguments=(canary,)
            )
        error = caught.value
        assert_error(error, CommandError, "command_failed", "response_received")
        assert error.__cause__ is None
        assert error.__context__ is None
        assert error.cleanup_errors == ()
        assert canary not in str(error)
        assert canary not in repr(error)
        session.quit()


def test_ios_response_unknown_is_uncertain_and_never_replayed(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.queue("action", ResponsePlan(disconnect=True))
    with managed_connection(cast(Any, service)) as (connection, owner):
        session = ios_session_for(service, connection, monkeypatch)
        with pytest.raises(ExecutionUnknownError) as caught:
            session.device.press_button("home")
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
        )
        assert session.session_info().state == "uncertain"
        assert len(script_requests(service)) == 1
        session.dispose()
        assert owner.count == 0


def test_ios_actions_share_the_session_gate(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.queue("action", ResponsePlan(started=started, release=release))
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        failure: list[BaseException] = []

        def run() -> None:
            try:
                session.device.press_button("home")
            except BaseException as error:
                failure.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        assert started.wait(timeout=2)
        with pytest.raises(SessionBusyError) as caught:
            session.device.tap_at(1, 2)
        assert_error(caught.value, SessionBusyError, "session_busy", "not_sent")
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive() and failure == []
        session.quit()
