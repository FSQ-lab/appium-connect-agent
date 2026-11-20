from __future__ import annotations

import base64
import contextlib
import math
import threading
import time as time_module
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from appium_connect_agent.automation import (
    CommandError,
    DeviceTime,
    DisplaySize,
    ExecutionUnknownError,
    InvalidRequestError,
    OperationTimeoutError,
    ResourceStateError,
    Session,
    SessionBusyError,
    TargetError,
    _session_client,
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
            if script == "mobile: deviceScreenInfo":
                return {"value": {"screenSize": {"width": 390, "height": 844}}}
            if script == "mobile: getDeviceTime":
                return {"value": "2026-11-18T09:10:11+08:00"}
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


def _assert_no_canary(error: BaseException, *canaries: str) -> None:
    pending: list[object] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, str):
            assert all(canary not in current for canary in canaries)
            continue
        try:
            text = f"{current!s}\n{current!r}"
        except Exception:
            text = ""
        assert all(canary not in text for canary in canaries)
        if isinstance(current, BaseException):
            pending.extend(current.args)
            if current.__cause__ is not None:
                pending.append(current.__cause__)
            if current.__context__ is not None:
                pending.append(current.__context__)
            pending.extend(getattr(current, "cleanup_errors", ()))
            sensitive_object = getattr(current, "object", None)
            if sensitive_object is not None:
                pending.append(sensitive_object)
            with contextlib.suppress(TypeError):
                pending.extend(vars(current).values())
        elif isinstance(current, Mapping):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray)
        ):
            pending.extend(current)


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
        ("id", "SaveId", None, {"elementId": "container", "name": "SaveId"}),
        (
            "accessibility id",
            "SaveA11y",
            None,
            {"elementId": "container", "name": "SaveA11y"},
        ),
        ("name", "Save", None, {"elementId": "container", "name": "Save"}),
        (
            "class name",
            "XCUIElementTypeButton",
            None,
            {
                "elementId": "container",
                "predicateString": 'type == "XCUIElementTypeButton"',
            },
        ),
        (
            "-ios predicate string",
            'name == "Save"',
            "enabled == true",
            {
                "elementId": "container",
                "predicateString": '(name == "Save") AND (enabled == true)',
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


@pytest.mark.parametrize(
    ("outcome", "expected_code"),
    [
        ("not_found", "target_not_found"),
        ("ambiguous", "target_ambiguous"),
        ("not_displayed", "target_not_displayed"),
    ],
)
def test_container_scroll_all_postcheck_outcomes(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    expected_code: str,
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        container = session.element("id", "container")
        target = session.element("name", "postcheck", parent=container)
        if outcome == "not_found":
            service.matches[("container", "name", "postcheck")] = []
        elif outcome == "ambiguous":
            service.matches[("container", "name", "postcheck")] = ["one", "two"]
        else:
            service.matches[("container", "name", "postcheck")] = ["hidden"]
            service.states[("hidden", "displayed")] = False
        with pytest.raises(TargetError) as caught:
            container.scroll(target, max_swipes=1)
        assert_error(caught.value, TargetError, expected_code, "response_received")
        assert (
            len(
                [
                    request
                    for request in script_requests(service)
                    if script_and_payload(request)[0] == "mobile: scroll"
                ]
            )
            == 1
        )
        session.quit()


def test_container_scroll_rejects_non_xcui_class_without_request(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        container = session.element("id", "container")
        target = session.element("class name", "Button", parent=container)
        before = len(service.snapshot())
        with pytest.raises(InvalidRequestError) as caught:
            container.scroll(target, max_swipes=1)
        assert_error(
            caught.value, InvalidRequestError, "unsupported_operation", "not_sent"
        )
        assert len(service.snapshot()) == before
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
    ("direction", "expected"),
    [
        ("up", ((195, 675), (195, 169))),
        ("down", ((195, 169), (195, 675))),
        ("left", ((319, 422), (71, 422))),
        ("right", ((71, 422), (319, 422))),
    ],
)
def test_ios_display_size_directional_swipe_and_device_time(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
    expected: tuple[tuple[int, int], tuple[int, int]],
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        assert session.device.display_size() == DisplaySize(390, 844)
        assert session.device.device_time() == DeviceTime(
            iso_local="2026-11-18T09:10:11+08:00",
            date="2026-11-18",
            time="09:10:11",
            weekday="Wednesday",
            utc_offset="+08:00",
        )
        session.device.swipe(direction=cast(Any, direction))

        scripts = script_requests(service)
        assert [request.body for request in scripts] == [
            {"script": "mobile: deviceScreenInfo", "args": []},
            {"script": "mobile: getDeviceTime", "args": []},
            {"script": "mobile: deviceScreenInfo", "args": []},
        ]
        pointer = service.of_kind("pointer")[0]
        assert pointer.body is not None
        actions = cast(list[dict[str, Any]], pointer.body["actions"])[0]["actions"]
        assert (actions[0]["x"], actions[0]["y"]) == expected[0]
        assert (actions[2]["x"], actions[2]["y"]) == expected[1]
        session.quit()


@pytest.mark.parametrize(
    "screen_size",
    [
        None,
        {},
        {"width": True, "height": 844},
        {"width": 390, "height": 0},
        {"width": 2_147_483_648, "height": 844},
    ],
)
def test_ios_display_size_rejects_invalid_screen_info_without_leaking_response(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    screen_size: object,
) -> None:
    canary = "private-screen-canary"
    service.queue(
        "action",
        ResponsePlan(payload={"value": {"screenSize": screen_size, "secret": canary}}),
    )
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        with pytest.raises(CommandError) as caught:
            session.device.display_size()
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        _assert_no_canary(caught.value, canary)
        session.quit()


def test_ios_ensure_alive_reattaches_with_preserved_private_metadata(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        session_module,
        "_prepare_xcuitest_derived_data",
        lambda port, operation_id: f"/private/tmp/test-{port}",
    )
    dead = {
        "value": {
            "error": "invalid session id",
            "message": "session is either terminated or not started",
            "stacktrace": "",
        }
    }
    with connected(service) as connection:
        session = create_xcuitest_session(
            connection,
            "IOS-PRIVATE-UDID",
            bundle_id="com.example.front",
            app_path=None,
            arguments=("private-argument",),
            xcode_org_id="PRIVATE_ORG",
            xcode_signing_id="Private Signing",
            updated_wda_bundle_id="com.example.private.wda",
            show_xcode_log=True,
            wda_launch_timeout_ms=60_000,
            xcuitest_wait_for_idle_timeout_seconds=2.0,
            xcuitest_snapshot_max_depth=25,
            xcuitest_accessibility_deadline_seconds=10.0,
            xcuitest_animation_cool_off_timeout_seconds=3.5,
            xcuitest_page_source_excluded_attributes=("visible", "accessible"),
        )
        service.queue("action", ResponsePlan(status=404, payload=dead))
        assert session.ensure_alive() is True

        creates = service.of_kind("create")
        assert len(creates) == 2
        reattach = creates[1].body
        assert reattach is not None
        capabilities = cast(dict[str, Any], reattach["capabilities"])["alwaysMatch"]
        assert capabilities == {
            "platformName": "iOS",
            "appium:automationName": "XCUITest",
            "appium:udid": "IOS-PRIVATE-UDID",
            "appium:autoLaunch": False,
            "appium:forceAppLaunch": False,
            "appium:shouldTerminateApp": False,
            "appium:noReset": True,
            "appium:fullReset": False,
            "appium:showXcodeLog": True,
            "appium:newCommandTimeout": 900.0,
            "appium:wdaLocalPort": 8100,
            "appium:derivedDataPath": "/private/tmp/test-8100",
            "appium:xcodeOrgId": "PRIVATE_ORG",
            "appium:xcodeSigningId": "Private Signing",
            "appium:updatedWDABundleId": "com.example.private.wda",
            "appium:wdaLaunchTimeout": 60_000,
            "appium:waitForIdleTimeout": 2.0,
            "appium:settings[snapshotMaxDepth]": 25,
            "appium:settings[accessibilityDeadline]": 10.0,
            "appium:settings[animationCoolOffTimeout]": 3.5,
            "appium:settings[pageSourceExcludedAttributes]": "visible,accessible",
        }
        assert "appium:bundleId" not in capabilities
        assert "appium:app" not in capabilities
        assert "appium:processArguments" not in capabilities
        session.quit()


def test_ios_reattach_failure_redacts_sensitive_fields(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canaries = (
        "IOS-SENSITIVE-UDID",
        "SENSITIVE_ORG",
        "Sensitive Signing",
        "com.example.sensitive.wda",
        "upstream-sensitive-canary",
    )
    monkeypatch.setattr(
        session_module,
        "_prepare_xcuitest_derived_data",
        lambda port, operation_id: f"/private/tmp/test-{port}",
    )
    dead = {
        "value": {
            "error": "invalid session id",
            "message": "session is either terminated or not started",
            "stacktrace": "",
        }
    }
    with managed_connection(cast(Any, service)) as (connection, owner):
        session = create_xcuitest_session(
            connection,
            canaries[0],
            xcode_org_id=canaries[1],
            xcode_signing_id=canaries[2],
            updated_wda_bundle_id=canaries[3],
        )
        service.queue("action", ResponsePlan(status=404, payload=dead))
        service.queue(
            "create",
            ResponsePlan(status=500, payload=w3c_error(canaries[4])),
        )
        with pytest.raises(ResourceStateError) as caught:
            session.ensure_alive()
        assert_error(
            caught.value,
            ResourceStateError,
            "session_create_unknown",
            "response_unknown",
        )
        _assert_no_canary(caught.value, *canaries)
        assert session.session_info().state == "uncertain"
        session.dispose()
        assert owner.count == 0


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


@pytest.mark.parametrize(
    "invoke",
    [
        lambda session, value: session.element("id", "target").send_keys(value),
        lambda session, value: session.element("id", "target").replace_element_value(
            value
        ),
        lambda session, value: session.device.set_clipboard_text(value),
        lambda session, value: session.device.accept_alert(button_label=value),
        lambda session, value: session.device.dismiss_alert(button_label=value),
    ],
)
def test_ios_preflight_validation_redacts_surrogate_input(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    invoke: Any,
) -> None:
    canary = "IOS_PREFLIGHT_SECRET_CANARY"
    value = canary + chr(0xD800)
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        before = len(service.snapshot())
        with pytest.raises(InvalidRequestError) as caught:
            invoke(session, value)
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        _assert_no_canary(caught.value, canary, value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert len(service.snapshot()) == before
        session.quit()


@pytest.mark.parametrize(
    ("case", "queue_kind"),
    [
        ("install_path", "action"),
        ("activate_id", "action"),
        ("terminate_id", "action"),
        ("query_id", "action"),
        ("remove_id", "action"),
        ("launch_arguments", "action"),
        ("clipboard", "action"),
        ("element_keys", "action"),
        ("device_keys", "action"),
        ("button", "action"),
        ("tap_coordinates", "action"),
        ("swipe_coordinates", "pointer"),
        ("drag_coordinates", "action"),
    ],
)
def test_ios_remote_errors_redact_all_sensitive_action_inputs(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
    queue_kind: str,
) -> None:
    text_canary = (
        "密"
        if case in {"element_keys", "device_keys"}
        else "camera"
        if case == "button"
        else f"IOS_REMOTE_{case.upper()}_CANARY"
    )
    bundle_canary = "com.example.iosremotecanary"
    coordinate_canary = "2147483642" if case == "drag_coordinates" else "2147483647"
    app = tmp_path.resolve() / f"{text_canary}.ipa"
    app.write_bytes(b"ipa")
    service.queue(
        queue_kind,
        ResponsePlan(
            status=500,
            payload=w3c_error(
                "|".join((text_canary, bundle_canary, coordinate_canary, str(app)))
            ),
        ),
    )
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        element = session.element("id", "target")
        if case == "drag_coordinates":
            service.states[("source", "rect")] = {
                "x": 2_147_483_637,
                "y": 2_147_483_637,
                "width": 10,
                "height": 10,
            }

        def invoke() -> None:
            if case == "install_path":
                session.device.install_app(app)
                return
            if case == "activate_id":
                session.device.activate_app(bundle_canary)
                return
            if case == "terminate_id":
                session.device.terminate_app(bundle_canary)
                return
            if case == "query_id":
                session.device.query_app_state(bundle_canary)
                return
            if case == "remove_id":
                session.device.remove_app(bundle_canary)
                return
            if case == "launch_arguments":
                session.device.launch_app(
                    bundle_id=bundle_canary, arguments=(text_canary,)
                )
                return
            if case == "clipboard":
                session.device.set_clipboard_text(text_canary)
                return
            if case == "element_keys":
                element.send_macos_keys((text_canary[0],))
                return
            if case == "device_keys":
                session.device.send_keys((text_canary[0],))
                return
            if case == "button":
                assert text_canary == "camera"
                session.device.press_button("camera")
                return
            if case == "tap_coordinates":
                session.device.tap_at(2_147_483_647, 2_147_483_647)
                return
            if case == "swipe_coordinates":
                session.device.swipe_between(2_147_483_647, 2_147_483_647, 0, 0)
                return
            session.element("id", "source").drag_and_drop(
                session.element("id", "destination")
            )

        with pytest.raises(CommandError) as caught:
            invoke()
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        _assert_no_canary(
            caught.value,
            text_canary,
            bundle_canary,
            coordinate_canary,
            str(app),
        )
        session.quit()


def test_ios_disconnect_cleanup_failure_redacts_cleanup_chain(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleanup_canary = "IOS_ACTION_CLEANUP_CANARY"
    original_new_connection = cast(Any, session_module)._new_connection
    injected = False

    def add_cleanup_failure(server_url: str) -> Any:
        nonlocal injected
        client = original_new_connection(server_url)
        if not injected:
            injected = True
            original_clear = client._conn.clear
            remaining = 1

            def clear() -> None:
                nonlocal remaining
                if remaining:
                    remaining -= 1
                    raise OSError(cleanup_canary)
                original_clear()

            monkeypatch.setattr(client._conn, "clear", clear)
        return client

    monkeypatch.setattr(session_module, "_new_connection", add_cleanup_failure)
    service.queue("action", ResponsePlan(disconnect=True))
    with managed_connection(cast(Any, service)) as (connection, owner):
        session = ios_session_for(service, connection, monkeypatch)
        with pytest.raises(ExecutionUnknownError) as caught:
            session.device.press_button("camera")
        _assert_no_canary(caught.value, cleanup_canary, "camera")
        assert [str(item) for item in caught.value.cleanup_errors] == [
            "transport_cleanup_failed"
        ]
        session.dispose()
        assert owner.count == 0


def test_ios_scroll_distance_and_press_button_boundaries(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        target = session.element("id", "target")
        target.ios_scroll("up", distance=0.000_001)
        target.ios_scroll("down", distance=1.0)
        for distance in (0.0, -0.1, 1.000_001, math.nan, math.inf, True):
            before = len(service.snapshot())
            with pytest.raises(InvalidRequestError) as caught:
                target.ios_scroll("left", distance=cast(Any, distance))
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
            assert len(service.snapshot()) == before
        for name in ("home", "volumeUp", "volumeDown", "action", "camera"):
            session.device.press_button(cast(Any, name))
        for invalid_name in ("Home", "volumeup", "camera ", "", True, 1):
            before = len(service.snapshot())
            with pytest.raises(InvalidRequestError) as caught:
                session.device.press_button(cast(Any, invalid_name))
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
            assert len(service.snapshot()) == before
        scroll_payloads = [
            script_and_payload(request)[1]
            for request in script_requests(service)
            if script_and_payload(request)[0] == "mobile: scroll"
        ]
        assert scroll_payloads[-2:] == [
            {"elementId": "target", "direction": "up", "distance": 0.000_001},
            {"elementId": "target", "direction": "down", "distance": 1.0},
        ]
        session.quit()


def test_ios_drag_duration_and_rect_boundaries(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        source = session.element("id", "source")
        destination = session.element("id", "destination")
        source.drag_and_drop(
            destination,
            duration_ms=500,
            control=OperationControl(timeout_seconds=1.0),
        )
        source.drag_and_drop(
            destination,
            duration_ms=60_000,
            control=OperationControl(timeout_seconds=60.5),
        )
        for duration in (499, 60_001, 500.0, True):
            before = len(service.snapshot())
            with pytest.raises(InvalidRequestError) as caught:
                source.drag_and_drop(destination, duration_ms=cast(Any, duration))
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
            assert len(service.snapshot()) == before
        drag_payloads = [
            cast(dict[str, object], script_and_payload(request)[1])
            for request in script_requests(service)
            if script_and_payload(request)[0] == "mobile: dragFromToForDuration"
        ]
        assert [payload["duration"] for payload in drag_payloads] == [0.5, 60.0]
        for invalid_rect in (
            {"x": 0, "y": 0, "width": 0, "height": 10},
            {"x": 0, "y": 0, "width": -1, "height": 10},
            {"x": 0, "y": 0, "width": 10, "height": math.nan},
            {"x": 0, "y": 0, "width": 10, "height": math.inf},
            {"x": 0, "y": 0, "width": True, "height": 10},
        ):
            service.states[("source", "rect")] = invalid_rect
            script_count = len(script_requests(service))
            with pytest.raises(CommandError) as caught_command:
                source.drag_and_drop(destination)
            assert_error(
                caught_command.value,
                CommandError,
                "command_failed",
                "response_received",
            )
            assert len(script_requests(service)) == script_count
        session.quit()


def test_ios_install_app_bundle_ipa_symlink_and_timeout_boundaries(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = tmp_path.resolve() / "Boundary.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(b"plist")
    ipa = tmp_path.resolve() / "Boundary.ipa"
    ipa.write_bytes(b"ipa")
    link = tmp_path.resolve() / "Linked.ipa"
    link.symlink_to(ipa)
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        session.device.install_app(app, control=OperationControl(timeout_seconds=0.01))
        session.device.install_app(ipa)
        install_payloads = [
            cast(dict[str, object], script_and_payload(request)[1])
            for request in script_requests(service)
            if script_and_payload(request)[0] == "mobile: installApp"
        ]
        assert install_payloads[0]["app"] == str(app)
        assert isinstance(install_payloads[0]["timeoutMs"], int)
        assert 1 <= install_payloads[0]["timeoutMs"] <= 9
        assert install_payloads[1] == {"app": str(ipa)}
        before = len(service.snapshot())
        with pytest.raises(InvalidRequestError) as caught:
            session.device.install_app(link)
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert len(service.snapshot()) == before
        session.quit()


def test_ios_query_app_state_accepts_only_exact_domain(
    service: IosActionProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_id = "com.example.state"
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        for value in range(5):
            service.queue("action", ResponsePlan(payload={"value": value}))
            assert session.device.query_app_state(app_id) == value
        for invalid_state in (-1, 5, True, 2.0, "2", None):
            service.queue("action", ResponsePlan(payload={"value": invalid_state}))
            with pytest.raises(CommandError) as caught:
                session.device.query_app_state(app_id)
            assert_error(
                caught.value, CommandError, "command_failed", "response_received"
            )
        session.quit()


@pytest.mark.parametrize("action", ["long_click", "drag_and_drop", "swipe_between"])
@pytest.mark.parametrize(
    ("timeout_seconds", "succeeds"),
    [(0.499, False), (0.5, False), (0.501, True)],
)
def test_ios_duration_budget_strict_millisecond_boundaries(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    timeout_seconds: float,
    succeeds: bool,
) -> None:
    monkeypatch.setattr(time_module, "monotonic", lambda: 100.0)
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        control = OperationControl(timeout_seconds=timeout_seconds)
        source = session.element("id", "source")
        if succeeds:
            if action == "long_click":
                source.long_click(duration_ms=500, control=control)
            elif action == "drag_and_drop":
                source.drag_and_drop(
                    session.element("id", "destination"),
                    duration_ms=500,
                    control=control,
                )
            else:
                session.device.swipe_between(
                    0, 0, 10, 10, duration_ms=500, control=control
                )
        else:
            before_final = len(script_requests(service)) + len(
                [
                    request
                    for request in service.snapshot()
                    if request.path.endswith("/actions")
                ]
            )
            with pytest.raises(OperationTimeoutError) as caught:
                if action == "long_click":
                    source.long_click(duration_ms=500, control=control)
                elif action == "drag_and_drop":
                    source.drag_and_drop(
                        session.element("id", "destination"),
                        duration_ms=500,
                        control=control,
                    )
                else:
                    session.device.swipe_between(
                        0, 0, 10, 10, duration_ms=500, control=control
                    )
            assert_error(
                caught.value,
                OperationTimeoutError,
                "operation_timeout",
                "not_sent",
            )
            after_final = len(script_requests(service)) + len(
                [
                    request
                    for request in service.snapshot()
                    if request.path.endswith("/actions")
                ]
            )
            assert after_final == before_final
        session.quit()


@pytest.mark.parametrize(
    ("timeout_seconds", "succeeds"), [(0.001, False), (0.002, True)]
)
def test_ios_install_timeout_strict_millisecond_boundary(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    timeout_seconds: float,
    succeeds: bool,
) -> None:
    monkeypatch.setattr(time_module, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        _session_client,
        "time",
        type("Clock", (), {"monotonic": staticmethod(lambda: 90.0)})(),
    )
    ipa = tmp_path.resolve() / "Budget.ipa"
    ipa.write_bytes(b"ipa")
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        control = OperationControl(timeout_seconds=timeout_seconds)
        if succeeds:
            session.device.install_app(ipa, control=control)
            script, payload = script_and_payload(script_requests(service)[0])
            assert script == "mobile: installApp"
            assert payload == {"app": str(ipa), "timeoutMs": 1}
        else:
            with pytest.raises(OperationTimeoutError) as caught:
                session.device.install_app(ipa, control=control)
            assert_error(
                caught.value,
                OperationTimeoutError,
                "operation_timeout",
                "not_sent",
            )
            assert script_requests(service) == []
        session.quit()


def test_ios_invalid_values_precede_unsupported_operation_without_requests(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    valid_app_path = tmp_path.resolve() / "Unsupported.app"
    element_calls: list[Callable[[Any], object]] = [
        lambda element: element.right_click(key_modifier_flags=cast(Any, True)),
        lambda element: element.hover(key_modifier_flags=cast(Any, True)),
        lambda element: element.replace_element_value("\0"),
        lambda element: element.perform_editor_action(cast(Any, "invalid")),
        lambda element: element.swipe_gesture(
            direction=cast(Any, "diagonal"), percent=0.5
        ),
        lambda element: element.scroll_gesture(direction="up", percent=0.0),
        lambda element: element.scroll_by(delta_x=math.nan, delta_y=0.0),
    ]
    device_calls: list[Callable[[Any], object]] = [
        lambda device: device.press_keycode(cast(Any, True)),
        lambda device: device.long_press_keycode(cast(Any, True)),
        lambda device: device.status_bar(cast(Any, "invalid")),
        lambda device: device.click_at(-1, 0),
        lambda device: device.hover_at(-1, 0),
        lambda device: device.scroll_at(0, 0, delta_x=math.nan, delta_y=0.0),
        lambda device: device.launch_app(app_path=Path("relative.app")),
    ]
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        element = session.element("id", "target")
        for element_call in element_calls:
            before = len(service.snapshot())
            with pytest.raises(InvalidRequestError) as caught:
                element_call(element)
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
            assert len(service.snapshot()) == before
        for device_call in device_calls:
            before = len(service.snapshot())
            with pytest.raises(InvalidRequestError) as caught:
                device_call(session.device)
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
            assert len(service.snapshot()) == before

        legal_unsupported: list[Callable[[], object]] = [
            lambda: element.right_click(),
            lambda: element.hover(),
            lambda: element.replace_element_value("valid"),
            lambda: element.perform_editor_action("done"),
            lambda: element.swipe_gesture(direction="up", percent=0.5),
            lambda: element.scroll_gesture(direction="up", percent=0.5),
            lambda: element.scroll_by(delta_x=0.0, delta_y=1.0),
            lambda: session.device.back(),
            lambda: session.device.press_keycode(1),
            lambda: session.device.long_press_keycode(1),
            lambda: session.device.status_bar("collapse"),
            lambda: session.device.click_at(0, 0),
            lambda: session.device.hover_at(0, 0),
            lambda: session.device.scroll_at(0, 0, delta_x=0.0, delta_y=1.0),
            lambda: session.device.launch_app(app_path=valid_app_path),
        ]
        for unsupported_call in legal_unsupported:
            before = len(service.snapshot())
            with pytest.raises(InvalidRequestError) as caught:
                unsupported_call()
            assert_error(
                caught.value,
                InvalidRequestError,
                "unsupported_operation",
                "not_sent",
            )
            assert len(service.snapshot()) == before
        session.quit()


@pytest.mark.parametrize(
    ("action", "queue_kind", "script_name"),
    [
        ("double_click", "action", "mobile: doubleTap"),
        ("ios_scroll", "scroll", "mobile: scroll"),
        ("container_scroll", "scroll", "mobile: scroll"),
        ("install_app", "action", "mobile: installApp"),
    ],
)
def test_ios_representative_response_unknown_actions_are_isolated(
    service: IosActionProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    action: str,
    queue_kind: str,
    script_name: str,
) -> None:
    ipa = tmp_path.resolve() / "Unknown.ipa"
    ipa.write_bytes(b"ipa")
    service.queue(queue_kind, ResponsePlan(disconnect=True))
    with managed_connection(cast(Any, service)) as (connection, owner):
        session = ios_session_for(service, connection, monkeypatch)
        element = session.element("id", "target")
        with pytest.raises(ExecutionUnknownError) as caught:
            if action == "double_click":
                element.double_click()
            elif action == "ios_scroll":
                element.ios_scroll("down")
            elif action == "container_scroll":
                container = session.element("id", "container")
                container.scroll(
                    session.element("name", "target", parent=container), max_swipes=1
                )
            else:
                session.device.install_app(ipa)
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
        )
        assert session.session_info().state == "uncertain"
        matching = [
            request
            for request in script_requests(service)
            if script_and_payload(request)[0] == script_name
        ]
        assert len(matching) == 1
        session.dispose()
        assert owner.count == 0
