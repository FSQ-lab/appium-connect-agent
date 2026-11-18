from __future__ import annotations

import base64
import math
import os
import struct
import threading
import zlib
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from appium_connect_agent.automation import (
    MACOS_MODIFIER_CAPS_LOCK,
    MACOS_MODIFIER_COMMAND,
    MACOS_MODIFIER_CONTROL,
    MACOS_MODIFIER_FUNCTION,
    MACOS_MODIFIER_OPTION,
    MACOS_MODIFIER_SHIFT,
    CommandError,
    Device,
    Element,
    ExecutionUnknownError,
    InvalidRequestError,
    InvalidSessionStateError,
    MacKeyStroke,
    OperationCancelledError,
    OperationTimeoutError,
    SessionBusyError,
    _macos_actions,
    _session,
    _session_client,
)
from appium_connect_agent.runtime import OperationControl
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


def _chunk(kind: bytes, data: bytes = b"") -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def _png() -> bytes:
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)),
            _chunk(b"IDAT", b"x"),
            _chunk(b"IEND"),
        )
    )


class MacActionService(ActionProtocolService):
    @staticmethod
    def _kind(request: Request) -> str:
        if request.method == "GET" and request.path.endswith("/screenshot"):
            return "take_screenshot"
        if request.method == "POST" and request.path.endswith("/execute/sync"):
            script = None if request.body is None else request.body.get("script")
            if isinstance(script, str) and script.startswith("macos: "):
                return script.removeprefix("macos: ")
        return ActionProtocolService._kind(request)

    def _default_payload(self, request: Request, kind: str) -> object:
        if kind == "take_screenshot":
            return {"value": base64.b64encode(_png()).decode("ascii")}
        if kind == "getClipboard":
            return {"value": base64.b64encode("桌面".encode()).decode("ascii")}
        if kind == "terminateApp":
            return {"value": False}
        if kind == "queryAppState":
            return {"value": 2}
        if kind in {
            "click",
            "doubleClick",
            "rightClick",
            "hover",
            "press",
            "scroll",
            "swipe",
            "clickAndDrag",
            "keys",
            "setClipboard",
            "activateApp",
            "launchApp",
        }:
            return {"value": None}
        return super()._default_payload(request, kind)


@pytest.fixture
def service() -> Iterator[MacActionService]:
    current = MacActionService()
    with current:
        yield current


def _script_request(service: MacActionService, kind: str) -> Request:
    requests = service.of_kind(kind)
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.path.endswith("/execute/sync")
    return request


def _args(request: Request) -> dict[str, object]:
    assert request.body is not None
    args = request.body["args"]
    assert isinstance(args, list) and len(args) == 1 and isinstance(args[0], dict)
    return cast(dict[str, object], args[0])


def test_keyboard_exports_are_exact_immutable_values() -> None:
    assert (
        MACOS_MODIFIER_CAPS_LOCK,
        MACOS_MODIFIER_SHIFT,
        MACOS_MODIFIER_CONTROL,
        MACOS_MODIFIER_OPTION,
        MACOS_MODIFIER_COMMAND,
        MACOS_MODIFIER_FUNCTION,
    ) == (1, 2, 4, 8, 16, 32)
    stroke = MacKeyStroke("a", MACOS_MODIFIER_COMMAND)
    assert stroke.key == "a" and stroke.modifier_flags == 16
    with pytest.raises(FrozenInstanceError):
        stroke.key = "b"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("method", "kind", "kwargs", "payload"),
    [
        ("click", "click", {}, {"elementId": "target"}),
        (
            "double_click",
            "doubleClick",
            {"key_modifier_flags": 16},
            {"elementId": "target", "keyModifierFlags": 16},
        ),
        ("right_click", "rightClick", {}, {"elementId": "target"}),
        (
            "hover",
            "hover",
            {"key_modifier_flags": 0},
            {"elementId": "target", "keyModifierFlags": 0},
        ),
        (
            "long_click",
            "press",
            {"duration_ms": 750, "key_modifier_flags": 2},
            {"elementId": "target", "duration": 0.75, "keyModifierFlags": 2},
        ),
    ],
)
def test_element_pointer_actions_use_exact_mac2_scripts(
    service: MacActionService,
    method: str,
    kind: str,
    kwargs: dict[str, object],
    payload: dict[str, object],
) -> None:
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        element = session.element("name", "target")
        cast(Callable[..., None], getattr(element, method))(**kwargs)
        request = _script_request(service, kind)
        assert request.body == {"script": f"macos: {kind}", "args": [payload]}
        session.quit()


def test_element_text_keys_scroll_swipe_and_drag_exact_payloads(
    service: MacActionService,
) -> None:
    service.matches[(None, "name", "source")] = ["source"]
    service.matches[(None, "name", "destination")] = ["destination"]
    service.states[("source", "rect")] = {"x": 10, "y": 20, "width": 30, "height": 40}
    service.states[("destination", "rect")] = {
        "x": 100,
        "y": 200,
        "width": 11,
        "height": 21,
    }
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        target = session.element("name", "target")
        target.send_keys("hello")
        target.clear()
        target.send_macos_keys(
            ["a", MacKeyStroke("XCUIKeyboardKeyReturn", MACOS_MODIFIER_COMMAND)]
        )
        target.scroll_by(delta_x=1, delta_y=-2.5, key_modifier_flags=8)
        target.macos_swipe(direction="left", velocity=3, key_modifier_flags=1)
        session.element("name", "source").drag_and_drop(
            session.element("name", "destination"),
            destination_x_ratio=1,
            destination_y_ratio=0,
            duration_ms=600,
            key_modifier_flags=4,
        )
        assert service.operation_kinds() == [
            "find",
            "displayed",
            "enabled",
            "send",
            "find",
            "displayed",
            "enabled",
            "clear",
            "find",
            "displayed",
            "enabled",
            "keys",
            "find",
            "displayed",
            "scroll",
            "find",
            "displayed",
            "swipe",
            "find",
            "displayed",
            "find",
            "displayed",
            "rect",
            "rect",
            "clickAndDrag",
        ]
        assert _args(_script_request(service, "keys")) == {
            "elementId": "target",
            "keys": [
                "a",
                {"key": "XCUIKeyboardKeyReturn", "modifierFlags": 16},
            ],
        }
        assert _args(_script_request(service, "scroll")) == {
            "elementId": "target",
            "deltaX": 1.0,
            "deltaY": -2.5,
            "keyModifierFlags": 8,
        }
        assert _args(_script_request(service, "swipe")) == {
            "elementId": "target",
            "direction": "left",
            "velocity": 3.0,
            "keyModifierFlags": 1,
        }
        assert _args(_script_request(service, "clickAndDrag")) == {
            "startX": 25,
            "startY": 40,
            "endX": 110,
            "endY": 200,
            "duration": 0.6,
            "keyModifierFlags": 4,
        }
        session.quit()


@pytest.mark.parametrize(
    "keys",
    [
        [],
        "a",
        ["ab"],
        ["\0"],
        ["XCUIKeyboardKeyF20"],
        ["\ud800"],
        [MacKeyStroke("a", True)],
        [MacKeyStroke("a", 64)],
        [object()],
    ],
)
def test_invalid_key_sequences_are_rejected_before_io(
    service: MacActionService, keys: Any
) -> None:
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.device.send_keys(keys)
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("value", [True, -1, 64, 1.0, "1"])
def test_invalid_modifier_flags_precede_gate_and_io(
    service: MacActionService, value: Any
) -> None:
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        before = service.snapshot()
        session._operation_gate.acquire()
        try:
            with pytest.raises(InvalidRequestError) as caught:
                session.element("name", "target").click(key_modifier_flags=value)
        finally:
            session._operation_gate.release()
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


def test_device_clipboard_screenshot_and_application_actions(
    service: MacActionService,
) -> None:
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        device = session.device
        assert device.get_clipboard_text() == "桌面"
        device.set_clipboard_text("text")
        assert device.take_screenshot() == _png()
        device.activate_app("com.apple.Calculator")
        assert device.terminate_app("com.apple.Calculator") is False
        assert device.query_app_state("com.apple.Calculator") == 2
        assert _args(_script_request(service, "getClipboard")) == {
            "contentType": "plaintext"
        }
        assert _args(_script_request(service, "setClipboard")) == {
            "content": base64.b64encode(b"text").decode("ascii"),
            "contentType": "plaintext",
        }
        assert _args(_script_request(service, "activateApp")) == {
            "bundleId": "com.apple.Calculator"
        }
        session.quit()


def test_device_pointer_and_keyboard_actions_exact_payloads(
    service: MacActionService,
) -> None:
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        device = session.device
        device.tap_at(1, 2)
        device.click_at(3, 4, double=True, key_modifier_flags=16)
        device.click_at(5, 6, button="right")
        device.hover_at(7, 8, key_modifier_flags=0)
        device.scroll_at(9, 10, delta_x=-1, delta_y=2.5)
        device.swipe_between(11, 12, 13, 14, duration_ms=250, key_modifier_flags=2)
        device.send_keys(["x", MacKeyStroke("XCUIKeyboardKeyF19", 32)])
        assert _args(service.of_kind("click")[0]) == {"x": 1, "y": 2}
        assert _args(_script_request(service, "doubleClick")) == {
            "x": 3,
            "y": 4,
            "keyModifierFlags": 16,
        }
        assert _args(_script_request(service, "rightClick")) == {"x": 5, "y": 6}
        assert _args(_script_request(service, "hover")) == {
            "x": 7,
            "y": 8,
            "keyModifierFlags": 0,
        }
        assert _args(_script_request(service, "scroll")) == {
            "x": 9,
            "y": 10,
            "deltaX": -1.0,
            "deltaY": 2.5,
        }
        assert _args(_script_request(service, "clickAndDrag")) == {
            "startX": 11,
            "startY": 12,
            "endX": 13,
            "endY": 14,
            "duration": 0.25,
            "keyModifierFlags": 2,
        }
        assert _args(_script_request(service, "keys")) == {
            "keys": ["x", {"key": "XCUIKeyboardKeyF19", "modifierFlags": 32}]
        }
        session.quit()


def test_launch_app_validates_bundle_and_path_and_sends_only_present_keys(
    service: MacActionService, tmp_path: Path
) -> None:
    app = tmp_path.resolve() / "Example.app"
    contents = app / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_text("plist")
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        session.device.launch_app(
            bundle_id="com.example.App",
            app_path=app,
            arguments=["--safe", ""],
        )
        assert _args(_script_request(service, "launchApp")) == {
            "bundleId": "com.example.App",
            "path": str(app),
            "arguments": ["--safe", ""],
        }
        session.quit()


@pytest.mark.parametrize(
    "invoke",
    [
        lambda device: device.click_at(1, 2),
        lambda device: device.hover_at(1, 2),
        lambda device: device.scroll_at(1, 2, delta_x=0, delta_y=1),
        lambda device: device.send_keys(["a"]),
        lambda device: device.launch_app(bundle_id="com.example.App"),
    ],
)
def test_macos_only_device_actions_reject_android_without_io(
    service: MacActionService, invoke: Callable[[Device], None]
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "android-cross-platform")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            invoke(session.device)
        assert_error(
            caught.value, InvalidRequestError, "unsupported_operation", "not_sent"
        )
        assert service.snapshot() == before
        session.quit()


def test_android_display_size_and_device_time_reject_macos_without_io(
    service: MacActionService,
) -> None:
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        before = service.snapshot()
        for invoke in (
            lambda: session.device.display_size(),
            lambda: session.device.device_time(),
        ):
            with pytest.raises(InvalidRequestError) as caught:
                invoke()
            assert_error(
                caught.value, InvalidRequestError, "unsupported_operation", "not_sent"
            )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    "invoke",
    [
        lambda element: element.right_click(),
        lambda element: element.hover(),
        lambda element: element.send_macos_keys(["a"]),
        lambda element: element.scroll_by(delta_x=0, delta_y=1),
        lambda element: element.macos_swipe(direction="up"),
    ],
)
def test_macos_only_element_actions_reject_android_without_io(
    service: MacActionService, invoke: Callable[[Element], None]
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "android-element-cross-platform")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            invoke(session.element("id", "target"))
        assert_error(
            caught.value, InvalidRequestError, "unsupported_operation", "not_sent"
        )
        assert service.snapshot() == before
        session.quit()


def test_unsupported_install_and_launch_paths_are_lexical_and_zero_filesystem_io(
    service: MacActionService, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("filesystem metadata must not be read")

    with connected(service) as connection:
        mac = mac_session_for(service, connection)
        android = session_for(service, connection, "android-path-gates")
        monkeypatch.setattr(Path, "stat", forbidden)
        monkeypatch.setattr(os, "lstat", forbidden)
        monkeypatch.setattr(os, "access", forbidden)

        before = service.snapshot()
        for invalid_apk in (
            Path("relative.apk"),
            Path("/tmp/upper.APK"),
            Path("/tmp/control\n.apk"),
        ):
            with pytest.raises(InvalidRequestError) as caught:
                mac.device.install_app(invalid_apk)
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
        with pytest.raises(InvalidRequestError) as unsupported_install:
            mac.device.install_app(Path("/tmp/not-present.apk"))
        assert_error(
            unsupported_install.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )

        for invalid_app in (
            Path("relative.app"),
            Path("/Applications/not-an-app.txt"),
            Path("/Applications/control\n.app"),
        ):
            with pytest.raises(InvalidRequestError) as caught:
                android.device.launch_app(app_path=invalid_app)
            assert_error(
                caught.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
        with pytest.raises(InvalidRequestError) as unsupported_launch:
            android.device.launch_app(app_path=Path("/Applications/Missing.app"))
        assert_error(
            unsupported_launch.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )
        assert service.snapshot() == before
        mac.quit()
        android.quit()


def test_mac_drag_rejects_out_of_range_geometry_before_action(
    service: MacActionService,
) -> None:
    service.matches[(None, "name", "source")] = ["source"]
    service.matches[(None, "name", "destination")] = ["destination"]
    service.states[("source", "rect")] = {
        "x": 2_147_483_647,
        "y": 0,
        "width": 2,
        "height": 1,
    }
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        with pytest.raises(CommandError) as caught:
            session.element("name", "source").drag_and_drop(
                session.element("name", "destination")
            )
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        assert service.of_kind("clickAndDrag") == []
        session.quit()


def test_invalid_mac_results_are_command_failures_without_replay(
    service: MacActionService,
) -> None:
    service.queue("queryAppState", ResponsePlan(payload={"value": 5}))
    service.queue("click", ResponsePlan(payload={"value": False}))
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        with pytest.raises(CommandError) as query_error:
            session.device.query_app_state("com.example.App")
        assert_error(
            query_error.value, CommandError, "command_failed", "response_received"
        )
        with pytest.raises(CommandError) as click_error:
            session.element("name", "target").click()
        assert_error(
            click_error.value, CommandError, "command_failed", "response_received"
        )
        assert len(service.of_kind("queryAppState")) == 1
        assert len(service.of_kind("click")) == 1
        session.quit()


def _duration_action(
    session: Any,
    action: str,
    duration_ms: int,
    control: OperationControl | None,
) -> None:
    if action == "press":
        session.element("name", "target").long_click(
            duration_ms=duration_ms, control=control
        )
    elif action == "drag":
        session.element("name", "source").drag_and_drop(
            session.element("name", "destination"),
            duration_ms=duration_ms,
            control=control,
        )
    else:
        session.device.swipe_between(
            1, 2, 3, 4, duration_ms=duration_ms, control=control
        )


@pytest.mark.parametrize(
    ("action", "kind"),
    [("press", "press"), ("drag", "clickAndDrag"), ("swipe", "clickAndDrag")],
)
def test_duration_budget_allows_strictly_less_and_rejects_equal_or_greater(
    service: MacActionService, action: str, kind: str
) -> None:
    with connected(service) as connection:
        allowed = mac_session_for(service, connection)
        _duration_action(allowed, action, 1, OperationControl(timeout_seconds=1))
        assert len(service.of_kind(kind)) == 1
        allowed.quit()

        for boundary, duration_ms, timeout_seconds in (
            ("equal", 100, 0.1),
            ("greater", 60_000, 1),
        ):
            rejected = mac_session_for(service, connection)
            before = len(service.of_kind(kind))
            with pytest.raises(OperationTimeoutError) as caught:
                _duration_action(
                    rejected,
                    action,
                    duration_ms,
                    OperationControl(timeout_seconds=timeout_seconds),
                )
            assert_error(
                caught.value,
                OperationTimeoutError,
                "operation_timeout",
                "not_sent",
            )
            assert len(service.of_kind(kind)) == before, boundary
            assert rejected.session_info().state == "active"
            rejected.quit()

        cancelled = mac_session_for(service, connection)
        cancellation = threading.Event()
        cancellation.set()
        before = len(service.of_kind(kind))
        with pytest.raises(OperationCancelledError) as cancelled_error:
            _duration_action(
                cancelled,
                action,
                60_000,
                OperationControl(timeout_seconds=5e-324, cancellation=cancellation),
            )
        assert_error(
            cancelled_error.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
        )
        assert len(service.of_kind(kind)) == before
        cancelled.quit()


@pytest.mark.parametrize(
    ("action", "kind"),
    [("press", "press"), ("drag", "clickAndDrag"), ("swipe", "clickAndDrag")],
)
def test_frozen_clock_proves_equal_duration_is_rejected_but_99ms_is_allowed(
    service: MacActionService,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    kind: str,
) -> None:
    frozen = SimpleNamespace(monotonic=lambda: 0.0)
    monkeypatch.setattr(_session, "time", frozen)
    monkeypatch.setattr(_macos_actions, "time", frozen)
    monkeypatch.setattr(
        _session_client, "time", SimpleNamespace(monotonic=lambda: -10.0)
    )
    assert 0.1 - frozen.monotonic() == 100 / 1000.0

    with connected(service) as connection:
        allowed = mac_session_for(service, connection)
        before = len(service.of_kind(kind))
        _duration_action(allowed, action, 99, OperationControl(timeout_seconds=0.1))
        assert len(service.of_kind(kind)) == before + 1
        allowed.quit()

        equal = mac_session_for(service, connection)
        before = len(service.of_kind(kind))
        with pytest.raises(OperationTimeoutError) as caught:
            _duration_action(equal, action, 100, OperationControl(timeout_seconds=0.1))
        assert_error(
            caught.value,
            OperationTimeoutError,
            "operation_timeout",
            "not_sent",
        )
        assert len(service.of_kind(kind)) == before
        assert equal.session_info().state == "active"
        equal.quit()


def test_mac_action_presend_cancel_known_error_and_busy_are_isolated(
    service: MacActionService,
) -> None:
    cancellation = threading.Event()
    cancellation.set()
    with connected(service) as connection:
        cancelled = mac_session_for(service, connection)
        before = service.snapshot()
        with pytest.raises(OperationCancelledError) as caught:
            cancelled.device.click_at(
                1, 2, control=OperationControl(cancellation=cancellation)
            )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
        )
        assert service.snapshot() == before
        cancelled.quit()

        service.queue("click", ResponsePlan(status=500, payload=w3c_error()))
        known = mac_session_for(service, connection)
        with pytest.raises(CommandError) as command:
            known.device.click_at(1, 2)
        assert_error(command.value, CommandError, "command_failed", "response_received")
        assert known.session_info().state == "active"
        assert len(service.of_kind("click")) == 1
        known.quit()

        started, release = threading.Event(), threading.Event()
        service.queue("click", ResponsePlan(started=started, release=release))
        busy = mac_session_for(service, connection)
        failures: list[BaseException] = []

        def run() -> None:
            try:
                busy.device.click_at(1, 2)
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        assert started.wait(timeout=2)
        before = service.snapshot()
        try:
            with pytest.raises(SessionBusyError) as busy_error:
                busy.device.hover_at(3, 4)
            assert_error(busy_error.value, SessionBusyError, "session_busy", "not_sent")
            assert service.snapshot() == before
        finally:
            release.set()
            worker.join(timeout=2)
        assert not worker.is_alive() and failures == []
        busy.quit()


@pytest.mark.parametrize("phase", ["disconnect", "timeout"])
def test_mac_response_unknown_quarantines_session_and_rejects_followup(
    service: MacActionService, phase: str
) -> None:
    plan = (
        ResponsePlan(disconnect=True)
        if phase == "disconnect"
        else ResponsePlan(header_delay_seconds=0.2)
    )
    service.queue("click", plan)
    control = None if phase == "disconnect" else OperationControl(timeout_seconds=0.05)
    error_type = (
        ExecutionUnknownError if phase == "disconnect" else OperationTimeoutError
    )
    code = "execution_unknown" if phase == "disconnect" else "operation_timeout"
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        with pytest.raises(error_type) as caught:
            session.device.click_at(1, 2, control=control)
        assert_error(caught.value, error_type, code, "response_unknown")
        assert len(service.of_kind("click")) == 1
        assert session.session_info().state == "uncertain"
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as followup:
            session.device.hover_at(3, 4)
        assert_error(
            followup.value,
            InvalidSessionStateError,
            "session_invalid",
            "not_sent",
        )
        assert service.snapshot() == before


def test_android_rejects_complete_mac_extension_matrix_without_io(
    service: MacActionService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "android-full-matrix")
        source = session.element("id", "source")
        destination = session.element("id", "destination")
        attempts: tuple[Callable[[], object], ...] = (
            lambda: source.click(key_modifier_flags=0),
            lambda: source.double_click(key_modifier_flags=0),
            lambda: source.long_click(key_modifier_flags=0),
            lambda: source.drag_and_drop(destination, duration_ms=1),
            lambda: source.drag_and_drop(destination, key_modifier_flags=0),
            lambda: session.device.swipe_between(1, 2, 3, 4, key_modifier_flags=0),
            lambda: source.right_click(),
            lambda: source.hover(),
            lambda: source.send_macos_keys(["a"]),
            lambda: source.scroll_by(delta_x=0, delta_y=1),
            lambda: source.macos_swipe(direction="up"),
            lambda: session.device.launch_app(bundle_id="com.example.App"),
            lambda: session.device.click_at(1, 2),
            lambda: session.device.hover_at(1, 2),
            lambda: session.device.scroll_at(1, 2, delta_x=0, delta_y=1),
            lambda: session.device.send_keys(["a"]),
        )
        before = service.snapshot()
        for attempt in attempts:
            with pytest.raises(InvalidRequestError) as caught:
                attempt()
            assert_error(
                caught.value,
                InvalidRequestError,
                "unsupported_operation",
                "not_sent",
            )
            assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    "attempt",
    [
        lambda session: session.element("id", "x").click(key_modifier_flags=True),
        lambda session: session.element("id", "x").drag_and_drop(
            session.element("id", "y"), duration_ms=0
        ),
        lambda session: session.device.swipe_between(
            1, 2, 3, 4, key_modifier_flags=True
        ),
        lambda session: session.element("id", "x").scroll_by(
            delta_x=math.nan, delta_y=0
        ),
        lambda session: session.element("id", "x").macos_swipe(
            direction="up", velocity=0
        ),
        lambda session: session.device.launch_app(app_path=Path("relative.app")),
        lambda session: session.device.click_at(1, 2, button="right", double=True),
        lambda session: session.device.hover_at(-1, 2),
        lambda session: session.device.scroll_at(1, 2, delta_x=True, delta_y=0),
        lambda session: session.device.send_keys([]),
    ],
)
def test_android_mac_extension_invalid_arguments_precede_unsupported(
    service: MacActionService, attempt: Callable[[Any], object]
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "android-invalid-precedence")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            attempt(session)
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


def test_macos_rejects_complete_android_only_matrix_without_io(
    service: MacActionService,
) -> None:
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        source = session.element("id", "source")
        destination = session.element("id", "destination")
        attempts: tuple[Callable[[], object], ...] = (
            lambda: source.replace_element_value("x"),
            lambda: source.swipe_gesture(direction="up", percent=0.5),
            lambda: source.scroll_gesture(direction="up", percent=0.5),
            lambda: source.scroll(destination, max_swipes=1),
            lambda: source.perform_editor_action("done"),
            lambda: session.device.set_clipboard_text("x", label="x"),
            lambda: session.device.back(),
            lambda: session.device.press_keycode(1),
            lambda: session.device.long_press_keycode(1),
            lambda: session.device.hide_keyboard(),
            lambda: session.device.accept_alert(),
            lambda: session.device.dismiss_alert(),
            lambda: session.device.status_bar("collapse"),
            lambda: session.device.install_app(Path("/tmp/example.apk")),
            lambda: session.device.remove_app("com.example"),
        )
        before = service.snapshot()
        for attempt in attempts:
            with pytest.raises(InvalidRequestError) as caught:
                attempt()
            assert_error(
                caught.value,
                InvalidRequestError,
                "unsupported_operation",
                "not_sent",
            )
            assert service.snapshot() == before
        session.quit()


_ALL_MAC_KEY_NAMES = (
    "XCUIKeyboardKeyDelete",
    "XCUIKeyboardKeyReturn",
    "XCUIKeyboardKeyEnter",
    "XCUIKeyboardKeyTab",
    "XCUIKeyboardKeySpace",
    "XCUIKeyboardKeyEscape",
    "XCUIKeyboardKeyUpArrow",
    "XCUIKeyboardKeyDownArrow",
    "XCUIKeyboardKeyLeftArrow",
    "XCUIKeyboardKeyRightArrow",
    *(f"XCUIKeyboardKeyF{index}" for index in range(1, 20)),
    "XCUIKeyboardKeyForwardDelete",
    "XCUIKeyboardKeyHome",
    "XCUIKeyboardKeyEnd",
    "XCUIKeyboardKeyPageUp",
    "XCUIKeyboardKeyPageDown",
    "XCUIKeyboardKeyClear",
    "XCUIKeyboardKeyHelp",
    "XCUIKeyboardKeyCapsLock",
    "XCUIKeyboardKeyShift",
    "XCUIKeyboardKeyControl",
    "XCUIKeyboardKeyOption",
    "XCUIKeyboardKeyCommand",
    "XCUIKeyboardKeyRightShift",
    "XCUIKeyboardKeyRightControl",
    "XCUIKeyboardKeyRightOption",
    "XCUIKeyboardKeyRightCommand",
    "XCUIKeyboardKeySecondaryFn",
)


def test_all_46_wda_named_keys_and_modifier_boundaries(
    service: MacActionService,
) -> None:
    assert len(_ALL_MAC_KEY_NAMES) == 46
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        session.device.send_keys(list(_ALL_MAC_KEY_NAMES))
        session.device.send_keys([MacKeyStroke("a", 0), MacKeyStroke("b", 63)])
        for invalid_name in ("XCUIKeyboardKeyF20", "Enter"):
            with pytest.raises(InvalidRequestError):
                session.device.send_keys([invalid_name])
        for invalid_flags in (-1, 64, True):
            with pytest.raises(InvalidRequestError):
                session.device.send_keys([MacKeyStroke("a", invalid_flags)])
        assert len(service.of_kind("keys")) == 2
        session.quit()


def test_coordinate_number_velocity_and_duration_boundaries(
    service: MacActionService,
) -> None:
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        session.device.click_at(0, 0)
        session.device.click_at(2_147_483_647, 2_147_483_647)
        session.device.swipe_between(0, 0, 1, 1, duration_ms=1)
        session.device.swipe_between(0, 0, 1, 1, duration_ms=60_000)
        for coordinate in (-1, 2_147_483_648, True):
            with pytest.raises(InvalidRequestError):
                session.device.click_at(coordinate, 0)
        for value in (True, math.nan, math.inf, -math.inf):
            with pytest.raises(InvalidRequestError):
                session.device.scroll_at(0, 0, delta_x=value, delta_y=0)
            with pytest.raises(InvalidRequestError):
                session.device.scroll_at(0, 0, delta_x=0, delta_y=value)
            with pytest.raises(InvalidRequestError):
                session.element("name", "x").macos_swipe(direction="up", velocity=value)
        for velocity in (0, -1):
            with pytest.raises(InvalidRequestError):
                session.element("name", "x").macos_swipe(
                    direction="up", velocity=velocity
                )
        for duration in (0, 60_001, True):
            with pytest.raises(InvalidRequestError):
                session.device.swipe_between(0, 0, 1, 1, duration_ms=duration)
        session.quit()


@pytest.mark.parametrize("state", [0, 1, 2, 3, 4])
def test_all_mac_app_states_are_preserved(
    service: MacActionService, state: int
) -> None:
    service.queue("queryAppState", ResponsePlan(payload={"value": state}))
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        result = session.device.query_app_state("com.example.App")
        assert result == state and type(result) is int
        session.quit()


@pytest.mark.parametrize("state", [-1, 5, True])
def test_invalid_mac_app_states_are_command_failures(
    service: MacActionService, state: object
) -> None:
    service.queue("queryAppState", ResponsePlan(payload={"value": state}))
    with connected(service) as connection:
        session = mac_session_for(service, connection)
        with pytest.raises(CommandError) as caught:
            session.device.query_app_state("com.example.App")
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        session.quit()


def test_launch_symlinks_clipboard_boundaries_and_controlled_errors_hide_secrets(
    service: MacActionService, tmp_path: Path
) -> None:
    root = tmp_path.resolve()
    real_parent = root / "real"
    real_bundle = real_parent / "SecretBundle.app"
    contents = real_bundle / "Contents"
    contents.mkdir(parents=True)
    (contents / "Info.plist").write_text("plist")
    parent_link = root / "secret-parent-link"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    bundle_link = root / "secret-bundle-link.app"
    bundle_link.symlink_to(real_bundle, target_is_directory=True)
    path_secrets = (parent_link / real_bundle.name, bundle_link)
    key_secret = "secret-key-value"
    clipboard_secret = "s" * 65_537
    argument_secret = "secret-argument\0"

    with connected(service) as connection:
        session = mac_session_for(service, connection)
        session.device.set_clipboard_text("c" * 65_536)
        failures: list[tuple[InvalidRequestError, str]] = []
        for secret_path in path_secrets:
            with pytest.raises(InvalidRequestError) as caught:
                session.device.launch_app(app_path=secret_path)
            failures.append((caught.value, str(secret_path)))
        with pytest.raises(InvalidRequestError) as key_error:
            session.device.send_keys([key_secret])
        failures.append((key_error.value, key_secret))
        with pytest.raises(InvalidRequestError) as clipboard_error:
            session.device.set_clipboard_text(clipboard_secret)
        failures.append((clipboard_error.value, clipboard_secret))
        with pytest.raises(InvalidRequestError) as argument_error:
            session.device.launch_app(
                bundle_id="com.example.App", arguments=[argument_secret]
            )
        failures.append((argument_error.value, argument_secret))

        for error, secret in failures:
            assert secret not in str(error)
            assert secret not in repr(error)
            assert_error(error, InvalidRequestError, "invalid_argument", "not_sent")
        assert len(service.of_kind("setClipboard")) == 1
        session.quit()
