from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from selenium.webdriver.remote import utils

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
    TargetError,
    create_session,
)
from appium_connect_agent.runtime import OperationControl
from tests.automation._action_protocol import (
    ResponsePlan,
    assert_error,
    connected,
    elements,
    session_for,
    stale_error,
    w3c_error,
)
from tests.automation.test_device_actions import DeviceProtocolService


@pytest.fixture
def service() -> Iterator[DeviceProtocolService]:
    current = DeviceProtocolService()
    with current:
        yield current


@pytest.mark.parametrize(
    "command", ["expandNotifications", "expandSettings", "collapse"]
)
def test_exact_route_and_empty_output(
    service: DeviceProtocolService, command: Any
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "panel-route")
        assert session.device.status_bar(command) == ""
        assert service.operation_kinds() == ["status_bar"]
        request = service.of_kind("status_bar")[0]
        assert request.method == "POST"
        assert request.path == "/wd/hub/session/appium-1/execute/sync"
        assert request.body == {
            "script": "mobile: statusBar",
            "args": [{"command": command}],
        }
        session.quit()


@pytest.mark.parametrize(
    "command",
    [
        "",
        "ExpandSettings",
        "expandsettings",
        " collapse",
        "collapse\n",
        "addTile",
        "removeTile",
        "clickTile",
        "getStatusIcons",
        "collapse; id",
        None,
        True,
        0,
        [],
        {},
    ],
)
def test_invalid_command_precedes_busy_and_cancel(
    service: DeviceProtocolService, command: Any
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "panel-invalid")
        cancel = threading.Event()
        cancel.set()
        before = service.snapshot()
        session._operation_gate.acquire()
        try:
            with pytest.raises(InvalidRequestError) as caught:
                session.device.status_bar(
                    command, control=OperationControl(cancellation=cancel)
                )
        finally:
            session._operation_gate.release()
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


def test_untrusted_receivers_are_rejected(service: DeviceProtocolService) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "panel-binding")
        other = session_for(service, connection, "panel-other")
        forged = object.__new__(Device)
        before = service.snapshot()
        for receiver in (forged, object(), session):
            with pytest.raises(InvalidRequestError):
                Device.status_bar(cast(Device, receiver), "collapse")
        object.__setattr__(forged, "_owner", session)
        object.__setattr__(forged, "_marker", session.device._marker)
        with pytest.raises(InvalidRequestError):
            forged.status_bar("collapse")
        for owner in (other, object.__new__(Session), object()):
            object.__setattr__(session.device, "_owner", owner)
            try:
                with pytest.raises(InvalidRequestError):
                    session.device.status_bar("collapse")
            finally:
                object.__setattr__(session.device, "_owner", session)
        with pytest.raises(InvalidRequestError):
            session.device.status_bar("collapse", control=cast(Any, object()))
        assert service.snapshot() == before
        session.quit()
        other.quit()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "中文😀e\u0301",
        " \t\r\n\0 output \n",
        "Permission denied",
        "a" * 65_535,
        "a" * 65_536,
        "😀" * 16_383 + "abc",
        "😀" * 16_384,
    ],
)
def test_output_preserves_client_string(
    service: DeviceProtocolService, value: str
) -> None:
    service.queue("status_bar", ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "panel-output")
        assert session.device.status_bar("expandSettings") == value
        assert service.operation_kinds() == ["status_bar"]
        session.quit()


@pytest.mark.parametrize(
    "value", [None, False, 0, [], {}, "\ud800", "a" * 65_537, "😀" * 16_384 + "x"]
)
def test_invalid_response_is_known_failure_without_completion(
    service: DeviceProtocolService, value: object
) -> None:
    service.queue("status_bar", ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "panel-bad-output")
        with pytest.raises(CommandError) as caught:
            session.device.status_bar("expandNotifications")
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert caught.value.__cause__ is not None
        assert service.operation_kinds() == ["status_bar"]
        assert session.session_info().state == "active"
        assert session.device.status_bar("collapse") == ""
        session.quit()


@pytest.mark.parametrize(
    "message", ["Permission denied", "unsupported", "device offline"]
)
def test_official_error_is_not_message_classified_or_replayed(
    service: DeviceProtocolService, message: str
) -> None:
    service.queue("status_bar", ResponsePlan(status=500, payload=w3c_error(message)))
    with connected(service) as connection:
        session = session_for(service, connection, "panel-error")
        with pytest.raises(CommandError) as caught:
            session.device.status_bar("expandSettings")
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert caught.value.__cause__ is not None
        assert service.operation_kinds() == ["status_bar"]
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("phase", ["disconnect", "header", "body", "cancel"])
def test_unknown_retains_resources_and_never_restores_panel(
    service: DeviceProtocolService, phase: str
) -> None:
    started, release, cancel = threading.Event(), threading.Event(), threading.Event()
    service.queue(
        "status_bar",
        ResponsePlan(
            disconnect=phase in {"disconnect", "cancel"},
            header_delay_seconds=0.2 if phase == "header" else 0,
            body_delay_seconds=0.2 if phase == "body" else 0,
            started=started,
            release=release if phase == "cancel" else None,
        ),
    )
    failures: list[BaseException] = []
    control = None
    if phase == "cancel":
        control = OperationControl(timeout_seconds=2, cancellation=cancel)
    elif phase != "disconnect":
        control = OperationControl(timeout_seconds=0.05)
    with connected(service) as connection:
        session = session_for(service, connection, "panel-unknown")

        def run() -> None:
            try:
                session.device.status_bar("expandSettings", control=control)
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            if phase == "cancel":
                cancel.set()
        finally:
            release.set()
            worker.join(timeout=3)
        assert not worker.is_alive()
        assert len(failures) == 1 and isinstance(failures[0], AutomationError)
        error_type: type[AutomationError]
        if phase == "cancel":
            error_type, code = OperationCancelledError, "operation_cancelled"
        elif phase == "disconnect":
            error_type, code = ExecutionUnknownError, "execution_unknown"
        else:
            error_type, code = OperationTimeoutError, "operation_timeout"
        assert_error(failures[0], error_type, code, "response_unknown", steps=())
        assert session.session_info().state == "uncertain"
        with pytest.raises(ResourceStateError):
            create_session(connection, "panel-unknown")
        before = service.snapshot()
        for attempt in (lambda: session.device.status_bar("collapse"), session.quit):
            with pytest.raises(InvalidSessionStateError):
                attempt()
        assert service.snapshot() == before
        assert service.operation_kinds() == ["status_bar"]
        assert service.of_kind("quit") == []


def test_presend_cancel_deadline_and_lifecycle(service: DeviceProtocolService) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "panel-priority")
        cancellation = threading.Event()
        cancellation.set()
        before = service.snapshot()
        for cancel, error_type, code in (
            (cancellation, OperationCancelledError, "operation_cancelled"),
            (None, OperationTimeoutError, "operation_timeout"),
        ):
            with pytest.raises(error_type) as caught:
                session.device.status_bar(
                    "collapse",
                    control=OperationControl(
                        timeout_seconds=5e-324, cancellation=cancel
                    ),
                )
            assert_error(caught.value, error_type, code, "not_sent", steps=())
        assert service.snapshot() == before
        session.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as closed:
            session.device.status_bar("collapse")
        assert closed.value.code == "session_closed"
        assert service.snapshot() == before
        active = session_for(service, connection, "panel-exited-connection")
    before = service.snapshot()
    with pytest.raises(InvalidSessionStateError) as exited:
        active.device.status_bar("collapse")
    assert exited.value.code == "session_invalid"
    assert service.snapshot() == before


@pytest.mark.parametrize(
    "holder", ["panel", "element", "device", "observation", "quit"]
)
def test_bidirectional_shared_gate(service: DeviceProtocolService, holder: str) -> None:
    started, release = threading.Event(), threading.Event()
    kind = {
        "panel": "status_bar",
        "element": "action",
        "device": "back",
        "observation": "attribute",
        "quit": "quit",
    }[holder]
    service.queue(kind, ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "panel-gate")
        # Hold a real attribute response, without needing unrelated XML fixtures.
        calls: dict[str, Callable[[], object]] = {
            "panel": lambda: session.device.status_bar("expandSettings"),
            "element": session.element("id", "target").click,
            "device": session.device.back,
            "observation": lambda: session.element("id", "target").inspect(
                attributes=("text",)
            ),
            "quit": session.quit,
        }

        def run() -> None:
            try:
                calls[holder]()
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            before = service.snapshot()
            attempts = list(calls.values()) if holder == "panel" else [calls["panel"]]
            if holder == "panel":
                attempts.append(session.observe_tree)
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
        if holder != "quit":
            session.quit()


@pytest.mark.parametrize("late", ["cancel", "deadline"])
def test_codec_holds_gate_and_valid_final_wins(
    service: DeviceProtocolService, monkeypatch: pytest.MonkeyPatch, late: str
) -> None:
    # Keep real HTTP/JSON and UTF-8. Instrument only the delivered string's codec.
    original = utils.load_json
    cancellation = threading.Event()
    with connected(service) as connection:
        session = session_for(service, connection, "panel-codec")

        class DeliveredText(str):
            def encode(self, encoding: str = "utf-8", errors: str = "strict") -> bytes:
                assert session.session_info().busy
                with pytest.raises(SessionBusyError):
                    session.device.back()
                result = super().encode(encoding, errors)
                if late == "cancel":
                    cancellation.set()
                else:
                    time.sleep(0.25)
                return result

        def decode(value: str) -> Any:
            parsed = original(value)
            if isinstance(parsed, dict) and parsed.get("value") == "codec-output":
                parsed["value"] = DeliveredText(parsed["value"])
            return parsed

        service.queue("status_bar", ResponsePlan(payload={"value": "codec-output"}))
        with monkeypatch.context() as patch:
            patch.setattr(utils, "load_json", decode)
            assert (
                session.device.status_bar(
                    "collapse",
                    control=OperationControl(
                        timeout_seconds=0.2, cancellation=cancellation
                    ),
                )
                == "codec-output"
            )
        assert service.operation_kinds() == ["status_bar"]
        assert session.session_info().state == "active"
        session.quit()


def test_explicit_panel_then_scoped_tile_relocates(
    service: DeviceProtocolService,
) -> None:
    service.matches[(None, "id", "com.android.systemui:id/panel")] = ["panel"]
    service.matches[("panel", "id", "com.android.systemui:id/tile")] = ["tile-one"]
    with connected(service) as connection:
        session = session_for(service, connection, "panel-tile")
        panel = session.element("id", "panel", package="com.android.systemui")
        tile = session.element(
            "id", "tile", package="com.android.systemui", parent=panel
        )
        assert service.operation_kinds() == []
        session.device.status_bar("expandSettings")
        tile.click()
        service.matches[("panel", "id", "com.android.systemui:id/tile")] = ["tile-two"]
        tile.click()
        assert (
            service.operation_kinds()
            == ["status_bar"]
            + [
                "find",
                "find",
                "displayed",
                "enabled",
                "action",
            ]
            * 2
        )
        assert "/element/panel/elements" in service.of_kind("find")[1].path
        assert [request.body for request in service.of_kind("action")] == [
            {"script": "mobile: clickGesture", "args": [{"elementId": element_id}]}
            for element_id in ("tile-one", "tile-two")
        ]
        session.quit()


@pytest.mark.parametrize("failure", ["ambiguous", "missing", "hidden", "disabled"])
def test_tile_rejects_without_automatic_panel_commands(
    service: DeviceProtocolService, failure: str
) -> None:
    matches = ["tile"]
    if failure == "ambiguous":
        matches = ["one", "two"]
    elif failure == "missing":
        matches = []
    service.matches[(None, "id", "com.android.systemui:id/tile")] = matches
    if failure in {"hidden", "disabled"}:
        service.states[("tile", "displayed" if failure == "hidden" else "enabled")] = (
            False
        )
    with connected(service) as connection:
        session = session_for(service, connection, "panel-tile-reject")
        session.device.status_bar("expandSettings")
        with pytest.raises(TargetError):
            session.element("id", "tile", package="com.android.systemui").click(
                wait_timeout_seconds=0.05
            )
        assert service.of_kind("action") == []
        assert len(service.of_kind("status_bar")) == 1
        session.quit()


@pytest.mark.parametrize("stage", ["pre", "final", "raw"])
def test_tile_stale_and_raw_guard_keep_existing_semantics(
    service: DeviceProtocolService, stage: str
) -> None:
    if stage == "pre":
        service.queue("displayed", ResponsePlan(status=404, payload=stale_error()))
    elif stage == "final":
        service.queue("action", ResponsePlan(status=404, payload=stale_error()))
    else:
        service.queue("find", ResponsePlan(payload=elements()), ResponsePlan())
    with connected(service) as connection:
        session = session_for(service, connection, "panel-tile-stale")
        session.device.status_bar("expandSettings")
        tile = session.element(
            "id",
            "vendor/odd@id" if stage == "raw" else "com.android.systemui:id/tile",
            raw_id=stage == "raw",
        )
        if stage == "final":
            with pytest.raises(CommandError) as caught:
                tile.click()
            assert caught.value.request_state == "response_received"
        else:
            tile.click(wait_timeout_seconds=2)
        assert len(service.of_kind("action")) == 1
        assert len(service.of_kind("status_bar")) == 1
        assert len(service.of_kind("find")) == (1 if stage == "final" else 2)
        if stage == "raw":
            assert service.settings["disableIdLocatorAutocompletion"] is False
            assert len(service.of_kind("settings:post")) == 2
        session.quit()
