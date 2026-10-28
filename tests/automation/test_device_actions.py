from __future__ import annotations

import base64
import threading
import time
from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from appium_connect_agent.automation import (
    AutomationError,
    CommandError,
    Device,
    ExecutionUnknownError,
    InvalidRequestError,
    InvalidSessionStateError,
    OperationCancelledError,
    OperationTimeoutError,
    ResourceStateError,
    Session,
    SessionBusyError,
    create_session,
)
from appium_connect_agent.runtime import OperationControl
from tests.automation._action_protocol import (
    ActionProtocolService,
    Request,
    ResponsePlan,
    assert_error,
    connected,
    session_for,
    w3c_error,
)

_ACTIONS = (
    "back",
    "press_keycode",
    "long_press_keycode",
    "hide_keyboard",
    "get_clipboard_text",
    "set_clipboard_text",
    "accept_alert",
    "dismiss_alert",
)


class DeviceProtocolService(ActionProtocolService):
    @staticmethod
    def _kind(request: Request) -> str:
        if request.path.endswith("/back"):
            return "back"
        if request.path.endswith("/execute/sync") and request.body is not None:
            script = request.body.get("script")
            if script == "mobile: pressKey":
                args = request.body["args"][0]
                return (
                    "long_press_keycode" if args.get("isLongPress") else "press_keycode"
                )
            kinds = {
                "mobile: hideKeyboard": "hide_keyboard",
                "mobile: getClipboard": "get_clipboard_text",
                "mobile: setClipboard": "set_clipboard_text",
                "mobile: acceptAlert": "accept_alert",
                "mobile: dismissAlert": "dismiss_alert",
                "mobile: statusBar": "status_bar",
                "mobile: activateApp": "activate_app",
                "mobile: terminateApp": "terminate_app",
                "mobile: queryAppState": "query_app_state",
            }
            if isinstance(script, str) and script in kinds:
                return kinds[script]
        return ActionProtocolService._kind(request)

    def _default_payload(self, request: Request, kind: str) -> object:
        if kind == "hide_keyboard":
            return {"value": False}
        if kind in {"get_clipboard_text", "status_bar"}:
            return {"value": ""}
        if kind == "activate_app":
            return {"value": None}
        if kind == "terminate_app":
            return {"value": False}
        if kind == "query_app_state":
            return {"value": 0}
        if kind in _ACTIONS:
            return {"value": None}
        return super()._default_payload(request, kind)


@pytest.fixture
def service() -> Iterator[DeviceProtocolService]:
    current = DeviceProtocolService()
    with current:
        yield current


def invoke(
    device: Device, action: str, *, control: OperationControl | None = None
) -> object:
    method = getattr(device, action)
    if action in {"press_keycode", "long_press_keycode"}:
        return cast(object, method(4, control=control))
    if action == "set_clipboard_text":
        return cast(object, method("text", control=control))
    return cast(object, method(control=control))


@pytest.mark.parametrize("action", _ACTIONS)
def test_public_command_and_local_identity(
    service: DeviceProtocolService, action: str
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"device-basic-{action}")
        before = service.snapshot()
        device = session.device
        assert session.device is device
        assert service.snapshot() == before
        result = invoke(device, action)
        expected = {"hide_keyboard": False, "get_clipboard_text": ""}.get(action)
        assert result == expected and type(result) is type(expected)
        assert service.operation_kinds() == [action]
        if action == "back":
            request = service.of_kind(action)[0]
            assert request.method == "POST" and request.path.endswith("/back")
            assert request.body == {}
        session.quit()


@pytest.mark.parametrize("long", [False, True])
@pytest.mark.parametrize("keycode", [0, 1, 2_147_483_646, 2_147_483_647])
@pytest.mark.parametrize("optional", [None, 0, -2_147_483_648, 2_147_483_647])
def test_integer_boundaries_and_optional_presence(
    service: DeviceProtocolService, long: bool, keycode: int, optional: int | None
) -> None:
    action = "long_press_keycode" if long else "press_keycode"
    with connected(service) as connection:
        session = session_for(service, connection, "device-key-boundaries")
        method = getattr(session.device, action)
        assert method(keycode, metastate=optional, flags=optional) is None
        payload: dict[str, object] = {"keycode": keycode}
        if optional is not None:
            payload.update(metastate=optional, flags=optional)
        if long:
            payload["isLongPress"] = True
        assert service.of_kind(action)[0].body == {
            "script": "mobile: pressKey",
            "args": [payload],
        }
        assert service.operation_kinds() == [action]
        session.quit()


@pytest.mark.parametrize("action", ["press_keycode", "long_press_keycode"])
@pytest.mark.parametrize("field", ["keycode", "metastate", "flags"])
@pytest.mark.parametrize(
    "value", [True, False, 1.0, "4", -2_147_483_649, 2_147_483_648]
)
def test_invalid_integer_precedes_busy_and_cancel(
    service: DeviceProtocolService, action: str, field: str, value: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "device-invalid-key")
        args: dict[str, Any] = {"keycode": 4, field: value}
        cancel = threading.Event()
        cancel.set()
        args["control"] = OperationControl(cancellation=cancel)
        before = service.snapshot()
        session._operation_gate.acquire()
        try:
            with pytest.raises(InvalidRequestError) as caught:
                getattr(session.device, action)(**args)
        finally:
            session._operation_gate.release()
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("value", [-1, None])
def test_negative_or_missing_keycode(
    service: DeviceProtocolService, value: Any
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "device-negative-key")
        with pytest.raises(InvalidRequestError):
            session.device.press_keycode(value)
        assert service.operation_kinds() == []
        session.quit()


@pytest.mark.parametrize("value", [True, False])
def test_hide_preserves_boolean(service: DeviceProtocolService, value: bool) -> None:
    service.queue("hide_keyboard", ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "device-hide")
        assert session.device.hide_keyboard() is value
        assert service.of_kind("hide_keyboard")[0].body == {
            "script": "mobile: hideKeyboard",
            "args": [{}],
        }
        assert service.operation_kinds() == ["hide_keyboard"]
        session.quit()


@pytest.mark.parametrize(
    "text",
    ["", "中文😀e\u0301", "\0\n\r\x01", "literal\\n", "a" * 65_535, "a" * 65_536],
)
@pytest.mark.parametrize("label", [None, "", "精确标签", "a" * 1_023, "a" * 1_024])
def test_clipboard_values_and_boundaries(
    service: DeviceProtocolService, text: str, label: str | None
) -> None:
    encoded = base64.b64encode(text.encode()).decode("ascii")
    service.queue("get_clipboard_text", ResponsePlan(payload={"value": encoded}))
    with connected(service) as connection:
        session = session_for(service, connection, "device-clipboard")
        session.device.set_clipboard_text(text, label=label)
        assert session.device.get_clipboard_text() == text
        payload = {"content": encoded, "contentType": "plaintext"}
        if label is not None:
            payload["label"] = label
        assert service.of_kind("set_clipboard_text")[0].body == {
            "script": "mobile: setClipboard",
            "args": [payload],
        }
        assert service.of_kind("get_clipboard_text")[0].body == {
            "script": "mobile: getClipboard",
            "args": [{"contentType": "plaintext"}],
        }
        assert service.operation_kinds() == ["set_clipboard_text", "get_clipboard_text"]
        session.quit()


@pytest.mark.parametrize(
    "text", [None, True, 12, "\ud800", "a" * 65_537, "😀" * 16_385]
)
def test_invalid_clipboard_text(service: DeviceProtocolService, text: Any) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "device-invalid-text")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.device.set_clipboard_text(text)
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    "action", ["set_clipboard_text", "accept_alert", "dismiss_alert"]
)
@pytest.mark.parametrize("label", [False, 1, "\udfff", "a" * 1_025, "😀" * 257])
def test_invalid_labels(
    service: DeviceProtocolService, action: str, label: Any
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "device-invalid-label")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            if action == "set_clipboard_text":
                session.device.set_clipboard_text("text", label=label)
            else:
                getattr(session.device, action)(button_label=label)
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("action", ["accept_alert", "dismiss_alert"])
@pytest.mark.parametrize(
    "label", [None, "", "  精确😀  ", "a" * 1_023, "a" * 1_024, "😀" * 256]
)
def test_alert_exact_labels(
    service: DeviceProtocolService, action: str, label: str | None
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "device-alert")
        assert getattr(session.device, action)(button_label=label) is None
        script = (
            "mobile: acceptAlert"
            if action == "accept_alert"
            else "mobile: dismissAlert"
        )
        assert service.of_kind(action)[0].body == {
            "script": script,
            "args": [{} if label is None else {"buttonLabel": label}],
        }
        assert service.operation_kinds() == [action]
        session.quit()


@pytest.mark.parametrize(
    "value",
    [
        None,
        False,
        0,
        [],
        {},
        "!",
        "@@",
        "YQ",
        "Y===",
        "YQ==\n",
        "é",
        "😀",
        "/w==",
        "AA==!",
        "a" * 87_385,
        base64.b64encode(b"a" * 65_537).decode("ascii"),
        base64.b64encode(b"a" * 65_538).decode("ascii"),
    ],
)
def test_bad_clipboard_response_is_not_empty_success(
    service: DeviceProtocolService, value: object
) -> None:
    service.queue("get_clipboard_text", ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "device-bad-clipboard")
        with pytest.raises(CommandError) as caught:
            session.device.get_clipboard_text()
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert caught.value.__cause__ is not None
        assert session.session_info().state == "active"
        assert service.operation_kinds() == ["get_clipboard_text"]
        session.quit()


@pytest.mark.parametrize(
    "action", ["hide_keyboard", "set_clipboard_text", "accept_alert", "dismiss_alert"]
)
@pytest.mark.parametrize("value", [0, 1, "false", [], {}])
def test_invalid_shape_has_no_completion(
    service: DeviceProtocolService, action: str, value: object
) -> None:
    service.queue(action, ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "device-shape")
        with pytest.raises(CommandError) as caught:
            invoke(session.device, action)
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert service.operation_kinds() == [action]
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("action", _ACTIONS)
@pytest.mark.parametrize(
    "message", ["no alert open", "button label does not match", "failed"]
)
def test_official_errors_are_not_replayed_or_message_classified(
    service: DeviceProtocolService, action: str, message: str
) -> None:
    service.queue(action, ResponsePlan(status=500, payload=w3c_error(message)))
    with connected(service) as connection:
        session = session_for(service, connection, "device-known-error")
        with pytest.raises(CommandError) as caught:
            invoke(session.device, action)
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert caught.value.__cause__ is not None
        assert service.operation_kinds() == [action]
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("action", _ACTIONS)
@pytest.mark.parametrize("phase", ["disconnect", "header", "body"])
def test_unknown_retains_ownership_without_replay(
    service: DeviceProtocolService, action: str, phase: str
) -> None:
    service.queue(
        action,
        ResponsePlan(
            disconnect=phase == "disconnect",
            header_delay_seconds=0.2 if phase == "header" else 0,
            body_delay_seconds=0.2 if phase == "body" else 0,
        ),
    )
    control = None if phase == "disconnect" else OperationControl(timeout_seconds=0.05)
    error_type = (
        ExecutionUnknownError if phase == "disconnect" else OperationTimeoutError
    )
    code = "execution_unknown" if phase == "disconnect" else "operation_timeout"
    with connected(service) as connection:
        device_id = f"device-unknown-{action}-{phase}"
        session = session_for(service, connection, device_id)
        with pytest.raises(error_type) as caught:
            invoke(session.device, action, control=control)
        assert_error(caught.value, error_type, code, "response_unknown", steps=())
        assert service.operation_kinds() == [action]
        assert session.session_info().state == "uncertain"
        with pytest.raises(ResourceStateError):
            create_session(connection, device_id)
        with pytest.raises(InvalidSessionStateError):
            session.device.back()
        assert service.of_kind("quit") == []


@pytest.mark.parametrize("action", _ACTIONS)
def test_presend_cancel_and_deadline(
    service: DeviceProtocolService, action: str
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "device-presend")
        cancel = threading.Event()
        cancel.set()
        before = service.snapshot()
        with pytest.raises(OperationCancelledError) as caught:
            invoke(
                session.device,
                action,
                control=OperationControl(timeout_seconds=5e-324, cancellation=cancel),
            )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
            steps=(),
        )
        with pytest.raises(OperationTimeoutError) as expired:
            invoke(
                session.device,
                action,
                control=OperationControl(timeout_seconds=5e-324),
            )
        assert_error(
            expired.value,
            OperationTimeoutError,
            "operation_timeout",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("action", _ACTIONS)
def test_inflight_cancel_unknown(service: DeviceProtocolService, action: str) -> None:
    started, release, cancel = threading.Event(), threading.Event(), threading.Event()
    service.queue(
        action, ResponsePlan(started=started, release=release, disconnect=True)
    )
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, f"device-inflight-{action}")

        def run() -> None:
            try:
                invoke(
                    session.device,
                    action,
                    control=OperationControl(timeout_seconds=2, cancellation=cancel),
                )
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            cancel.set()
        finally:
            release.set()
            worker.join(timeout=3)
        assert not worker.is_alive()
        assert len(failures) == 1 and isinstance(failures[0], AutomationError)
        assert_error(
            failures[0],
            OperationCancelledError,
            "operation_cancelled",
            "response_unknown",
            steps=(),
        )
        assert service.operation_kinds() == [action]
        assert session.session_info().state == "uncertain"


@pytest.mark.parametrize("action", _ACTIONS)
def test_gate_blocks_all_other_session_channels(
    service: DeviceProtocolService, action: str
) -> None:
    started, release = threading.Event(), threading.Event()
    service.queue(action, ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, f"device-gate-{action}")

        def run() -> None:
            try:
                invoke(session.device, action)
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            assert session.session_info().busy
            before = service.snapshot()
            attempts = (
                session.device.back,
                session.element("id", "target").click,
                session.element("id", "other").clear,
                session.observe_tree,
                session.quit,
            )
            for attempt in attempts:
                with pytest.raises(SessionBusyError) as caught:
                    attempt()
                assert_error(
                    caught.value, SessionBusyError, "session_busy", "not_sent", steps=()
                )
            assert service.snapshot() == before
        finally:
            release.set()
            worker.join(timeout=3)
        assert not worker.is_alive() and failures == []
        assert not session.session_info().busy
        session.quit()


@pytest.mark.parametrize("action", _ACTIONS)
def test_closed_reference_is_readable_commands_rejected(
    service: DeviceProtocolService, action: str
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "device-closed")
        device = session.device
        session.quit()
        before = service.snapshot()
        assert session.device is device
        with pytest.raises(InvalidSessionStateError) as caught:
            invoke(device, action)
        assert_error(
            caught.value,
            InvalidSessionStateError,
            "session_closed",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before


def test_binding_construction_mutation_and_forged_slots(
    service: DeviceProtocolService,
) -> None:
    with pytest.raises(TypeError):
        Device()
    with connected(service) as connection:
        session = session_for(service, connection, "device-binding")
        other = session_for(service, connection, "device-binding-other")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            cast(Any, session.device)._owner = other
        with pytest.raises(AttributeError):
            cast(Any, session).device = other.device
        before = service.snapshot()
        forged = object.__new__(Device)
        with pytest.raises(InvalidRequestError):
            forged.back()
        object.__setattr__(forged, "_owner", session)
        with pytest.raises(InvalidRequestError):
            forged.back()
        object.__setattr__(forged, "_marker", object())
        with pytest.raises(InvalidRequestError):
            forged.back()
        original_owner = session.device._owner
        object.__setattr__(session.device, "_owner", object.__new__(Session))
        try:
            with pytest.raises(InvalidRequestError):
                session.device.back()
        finally:
            object.__setattr__(session.device, "_owner", original_owner)
        assert service.snapshot() == before
        session.quit()
        other.quit()


@pytest.mark.parametrize("cancel_after_decode", [False, True])
def test_valid_clipboard_final_success_wins_after_codec_work(
    service: DeviceProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    cancel_after_decode: bool,
) -> None:
    # Keep the real HTTP client and codec: only control when local decoding ends.
    cancellation = threading.Event()
    original = base64.b64decode

    def decode(value: bytes, *, validate: bool = False) -> bytes:
        result = original(value, validate=validate)
        if cancel_after_decode:
            cancellation.set()
        else:
            time.sleep(0.25)
        return result

    service.queue("get_clipboard_text", ResponsePlan(payload={"value": "eA=="}))
    with connected(service) as connection:
        session = session_for(service, connection, "device-final-priority")
        monkeypatch.setattr(base64, "b64decode", decode)
        assert (
            session.device.get_clipboard_text(
                control=OperationControl(timeout_seconds=0.2, cancellation=cancellation)
            )
            == "x"
        )
        assert service.operation_kinds() == ["get_clipboard_text"]
        assert session.session_info().state == "active"
        session.quit()


def test_input_codec_time_counts_against_original_budget(
    service: DeviceProtocolService,
) -> None:
    class SlowText(str):
        def encode(self, encoding: str = "utf-8", errors: str = "strict") -> bytes:
            time.sleep(0.06)
            return super().encode(encoding, errors)

    with connected(service) as connection:
        session = session_for(service, connection, "device-codec-budget")
        before = service.snapshot()
        with pytest.raises(OperationTimeoutError) as caught:
            session.device.set_clipboard_text(
                SlowText("text"), control=OperationControl(timeout_seconds=0.02)
            )
        assert_error(
            caught.value,
            OperationTimeoutError,
            "operation_timeout",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("action", _ACTIONS)
def test_element_inflight_blocks_device(
    service: DeviceProtocolService, action: str
) -> None:
    started, release = threading.Event(), threading.Event()
    service.queue("action", ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "device-reverse-gate")

        def click() -> None:
            try:
                session.element("id", "target").click()
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=click)
        worker.start()
        try:
            assert started.wait(timeout=2)
            before = service.snapshot()
            with pytest.raises(SessionBusyError) as caught:
                invoke(session.device, action)
            assert_error(
                caught.value, SessionBusyError, "session_busy", "not_sent", steps=()
            )
            assert service.snapshot() == before
        finally:
            release.set()
            worker.join(timeout=3)
        assert not worker.is_alive() and failures == []
        session.quit()


def test_invalid_control_precedes_receiver_and_codec(
    service: DeviceProtocolService,
) -> None:
    class UnencodableText(str):
        def encode(self, encoding: str = "utf-8", errors: str = "strict") -> bytes:
            raise AssertionError("invalid control must be rejected before encoding")

    with connected(service) as connection:
        session = session_for(service, connection, "device-control-first")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.device.set_clipboard_text(
                UnencodableText("text"), control=cast(Any, object())
            )
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        forged = object.__new__(Device)
        with pytest.raises(InvalidRequestError):
            forged.back(control=cast(Any, object()))
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("action", _ACTIONS)
def test_exited_connection_rejects_all_device_commands(
    service: DeviceProtocolService, action: str
) -> None:
    with connected(service) as connection:
        session = session_for(
            service, connection, f"device-inactive-connection-{action}"
        )
    before = service.snapshot()
    with pytest.raises(InvalidSessionStateError) as caught:
        invoke(session.device, action)
    assert_error(
        caught.value, InvalidSessionStateError, "session_invalid", "not_sent", steps=()
    )
    assert service.snapshot() == before
    assert session.session_info().state == "uncertain"
    assert service.of_kind("quit") == []


@pytest.mark.parametrize(
    ("action", "value"),
    [
        ("hide_keyboard", None),
        ("hide_keyboard", "true"),
        ("set_clipboard_text", True),
        ("set_clipboard_text", False),
        ("accept_alert", True),
        ("dismiss_alert", False),
    ],
)
def test_null_bool_and_string_are_not_interchangeable(
    service: DeviceProtocolService, action: str, value: object
) -> None:
    service.queue(action, ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "device-null-bool")
        with pytest.raises(CommandError) as caught:
            invoke(session.device, action)
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert service.operation_kinds() == [action]
        session.quit()
