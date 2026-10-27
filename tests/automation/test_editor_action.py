from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any, cast

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
    SessionBusyError,
    TargetError,
    create_session,
)
from appium_connect_agent.runtime import OperationControl
from tests.automation._action_protocol import (
    ActionProtocolService,
    Request,
    ResponsePlan,
    assert_error,
    connected,
    elements,
    session_for,
    stale_error,
    w3c_error,
)

_READY = ("target_resolved", "target_displayed", "target_enabled")
_CLICKED = (*_READY, "focus_click_completed")
_FOCUSED = (*_READY, "target_focused")


class EditorProtocolService(ActionProtocolService):
    @staticmethod
    def _kind(request: Request) -> str:
        if (
            request.method == "POST"
            and request.path.endswith("/execute/sync")
            and request.body is not None
            and request.body.get("script") == "mobile: performEditorAction"
        ):
            return "ime"
        return ActionProtocolService._kind(request)

    def _default_payload(self, request: Request, kind: str) -> object:
        if kind == "ime":
            return {"value": None}
        if kind == "attribute" and request.path.endswith("/attribute/focused"):
            element_id = request.path.split("/element/", 1)[1].split("/", 1)[0]
            return {"value": self.states.get((element_id, "focused"), True)}
        return super()._default_payload(request, kind)


@pytest.fixture
def service() -> Iterator[EditorProtocolService]:
    current = EditorProtocolService()
    with current:
        yield current


@pytest.mark.parametrize(
    "action",
    [
        "normal",
        "unspecified",
        "none",
        "go",
        "search",
        "send",
        "next",
        "done",
        "previous",
    ],
)
@pytest.mark.parametrize("focused", [True, "true", "TRUE", "TrUe"])
def test_already_focused_actions_skip_click_and_complete_once(
    service: EditorProtocolService, action: str, focused: object
) -> None:
    service.states[("target", "focused")] = focused
    with connected(service) as connection:
        session = session_for(service, connection, f"focused-{action}-{focused}")
        result = session.element("id", "target").perform_editor_action(  # type: ignore[func-returns-value]
            cast(Any, action)
        )
        assert result is None
        assert service.operation_kinds() == [
            "find",
            "displayed",
            "enabled",
            "attribute",
            "ime",
        ]
        assert service.of_kind("ime")[0].body == {
            "script": "mobile: performEditorAction",
            "args": [{"action": action}],
        }
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    "action", [None, True, 0, 7, 1.0, "DONE", " done", "done ", "submit", "", [], {}]
)
def test_invalid_action_is_rejected_without_device_requests(
    service: EditorProtocolService, action: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "invalid-action")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.element("id", "target").perform_editor_action(cast(Any, action))
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("wait", [None, True, 0, -1, float("nan"), float("inf"), "1"])
def test_invalid_wait_is_rejected_before_settings(
    service: EditorProtocolService, wait: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "invalid-wait")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.element("id", "vendor/odd@id", raw_id=True).perform_editor_action(
                "done", wait_timeout_seconds=cast(Any, wait)
            )
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("initial", [False, "false", "FALSE", "FaLsE"])
def test_click_once_then_delayed_focus_uses_same_handle_and_half_second_poll(
    service: EditorProtocolService, initial: object
) -> None:
    service.queue(
        "attribute",
        ResponsePlan(payload={"value": initial}),
        ResponsePlan(payload={"value": False}),
        ResponsePlan(payload={"value": "false"}),
        ResponsePlan(payload={"value": "TRUE"}),
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"delayed-{initial}")
        session.element("id", "target").perform_editor_action(
            "search", wait_timeout_seconds=3
        )
        assert service.operation_kinds() == [
            "find",
            "displayed",
            "enabled",
            "attribute",
            "action",
            "attribute",
            "attribute",
            "attribute",
            "ime",
        ]
        assert service.of_kind("action")[0].body == {
            "script": "mobile: clickGesture",
            "args": [{"elementId": "target"}],
        }
        reads = service.of_kind("attribute")
        assert all(
            item.path.endswith("/element/target/attribute/focused") for item in reads
        )
        assert reads[2].received_at - reads[1].received_at >= 0.4
        assert reads[3].received_at - reads[2].received_at >= 0.4
        session.quit()


@pytest.mark.parametrize("phase", ["find", "displayed", "enabled", "attribute"])
def test_pre_click_stale_retries_entire_round_without_committing_failed_round(
    service: EditorProtocolService, phase: str
) -> None:
    service.queue(phase, ResponsePlan(status=404, payload=stale_error()))
    # Neither the stale round nor the later missing-focus round commits readiness.
    service.queue("attribute", ResponsePlan(payload={"value": None}))
    with connected(service) as connection:
        session = session_for(service, connection, f"pre-stale-{phase}")
        with pytest.raises(TargetError) as caught:
            session.element("id", "target").perform_editor_action(
                "done", wait_timeout_seconds=2
            )
        assert_error(
            caught.value,
            TargetError,
            "precondition_not_met",
            "response_received",
            steps=(),
        )
        assert len(service.of_kind("find")) == 2
        assert service.of_kind("action") == service.of_kind("ime") == []
        session.quit()


def test_pre_click_stale_can_relocate_to_new_handle_then_succeed(
    service: EditorProtocolService,
) -> None:
    service.queue(
        "find",
        ResponsePlan(payload=elements("old")),
        ResponsePlan(payload=elements("new")),
    )
    service.queue("attribute", ResponsePlan(status=404, payload=stale_error()))
    with connected(service) as connection:
        session = session_for(service, connection, "fresh-handle")
        session.element("xpath", "//*[@text='query']").perform_editor_action(
            "done", wait_timeout_seconds=2
        )
        paths = [
            item.path.rsplit("/element/", 1)[1] for item in service.of_kind("attribute")
        ]
        assert paths == ["old/attribute/focused", "new/attribute/focused"]
        assert service.of_kind("action") == []
        assert len(service.of_kind("ime")) == 1
        session.quit()


@pytest.mark.parametrize("kind", ["find", "displayed", "enabled"])
def test_ready_waits_for_missing_hidden_and_disabled(
    service: EditorProtocolService, kind: str
) -> None:
    service.queue(
        kind, ResponsePlan(payload=elements() if kind == "find" else {"value": False})
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"ready-{kind}")
        session.element("id", "target").perform_editor_action(
            "done", wait_timeout_seconds=2
        )
        assert len(service.of_kind("find")) == 2
        assert len(service.of_kind("attribute")) == len(service.of_kind("ime")) == 1
        assert service.of_kind("action") == []
        session.quit()


@pytest.mark.parametrize("stage", [0, 1, 2])
def test_each_locator_level_must_be_unique(
    service: EditorProtocolService, stage: int
) -> None:
    names = ["root", "middle", "target"]
    parents: list[str | None] = [None, "root", "middle"]
    for index, name in enumerate(names):
        service.matches[(parents[index], "id", f"com.example:id/{name}")] = (
            [name, "duplicate"] if index == stage else [name]
        )
    with connected(service) as connection:
        session = session_for(service, connection, f"ambiguous-{stage}")
        root = session.element("id", "root")
        middle = session.element("id", "middle", parent=root)
        target = session.element("id", "target", parent=middle)
        with pytest.raises(TargetError) as caught:
            target.perform_editor_action("done")
        assert_error(
            caught.value, TargetError, "target_ambiguous", "response_received", steps=()
        )
        assert len(service.of_kind("find")) == stage + 1
        assert service.of_kind("attribute") == service.of_kind("ime") == []
        session.quit()


@pytest.mark.parametrize("after_click", [False, True])
@pytest.mark.parametrize("value", [None, "yes", " true ", 1, 0, {}, [], ""])
def test_focus_none_and_malformed_values_do_not_authorize_ime(
    service: EditorProtocolService, after_click: bool, value: object
) -> None:
    if after_click:
        service.queue("attribute", ResponsePlan(payload={"value": False}))
    service.queue("attribute", ResponsePlan(payload={"value": value}))
    expected_type: type[AutomationError] = (
        TargetError if value is None else CommandError
    )
    code = "precondition_not_met" if value is None else "command_failed"
    with connected(service) as connection:
        session = session_for(service, connection, f"bad-focused-{after_click}")
        with pytest.raises(expected_type) as caught:
            session.element("id", "target").perform_editor_action("done")
        assert_error(
            caught.value,
            expected_type,
            code,
            "response_received",
            steps=_CLICKED if after_click else (),
        )
        assert len(service.of_kind("action")) == int(after_click)
        assert len(service.of_kind("find")) == 1
        assert service.of_kind("ime") == []
        if value is not None:
            assert caught.value.__cause__ is not None
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("failure", ["stale", "known", "shape", "none"])
def test_changed_text_locator_never_replaces_clicked_handle_on_focus_failure(
    service: EditorProtocolService, failure: str
) -> None:
    locator = "//*[@text='before']"
    service.matches[(None, "xpath", locator)] = ["original"]
    service.queue("attribute", ResponsePlan(payload={"value": False}))

    def change_locator() -> None:
        service.matches[(None, "xpath", locator)] = ["replacement"]

    service.queue("action", ResponsePlan(after_send=change_locator))
    plan = {
        "stale": ResponsePlan(status=404, payload=stale_error()),
        "known": ResponsePlan(status=500, payload=w3c_error()),
        "shape": ResponsePlan(payload={"value": {"unexpected": True}}),
        "none": ResponsePlan(payload={"value": None}),
    }[failure]
    service.queue("attribute", plan)
    expected_type: type[AutomationError] = (
        TargetError if failure == "none" else CommandError
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"identity-{failure}")
        with pytest.raises(expected_type) as caught:
            session.element("xpath", locator).perform_editor_action("done")
        assert_error(
            caught.value,
            expected_type,
            "precondition_not_met" if failure == "none" else "command_failed",
            "response_received",
            steps=_CLICKED,
        )
        assert len(service.of_kind("find")) == len(service.of_kind("action")) == 1
        assert all(
            "/element/original/" in item.path for item in service.of_kind("attribute")
        )
        assert service.of_kind("ime") == []
        session.quit()


@pytest.mark.parametrize("phase", ["click", "ime"])
@pytest.mark.parametrize("result", [True, False, 0, "", {}, []])
def test_action_responses_must_be_strict_none(
    service: EditorProtocolService, phase: str, result: object
) -> None:
    if phase == "click":
        service.queue("attribute", ResponsePlan(payload={"value": False}))
    service.queue(
        "action" if phase == "click" else "ime",
        ResponsePlan(payload={"value": result}),
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"strict-{phase}")
        with pytest.raises(CommandError) as caught:
            session.element("id", "target").perform_editor_action("done")
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=_READY if phase == "click" else _FOCUSED,
        )
        assert len(service.of_kind("action")) == int(phase == "click")
        assert len(service.of_kind("ime")) == int(phase == "ime")
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("phase", ["action", "ime"])
def test_stale_action_response_is_never_replayed(
    service: EditorProtocolService, phase: str
) -> None:
    if phase == "action":
        service.queue("attribute", ResponsePlan(payload={"value": False}))
    service.queue(phase, ResponsePlan(status=404, payload=stale_error()))
    with connected(service) as connection:
        session = session_for(service, connection, f"final-stale-{phase}")
        with pytest.raises(CommandError) as caught:
            session.element("id", "target").perform_editor_action("done")
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=_READY if phase == "action" else _FOCUSED,
        )
        assert len(service.of_kind("find")) == len(service.of_kind(phase)) == 1
        session.quit()


@pytest.mark.parametrize("total_budget", [False, True])
def test_post_click_focus_wait_shares_original_condition_and_operation_budget(
    service: EditorProtocolService, total_budget: bool
) -> None:
    service.states[("target", "focused")] = False
    service.queue(
        "attribute", ResponsePlan(payload={"value": False}, header_delay_seconds=0.1)
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"shared-budget-{total_budget}")
        expected_type: type[AutomationError] = (
            OperationTimeoutError if total_budget else TargetError
        )
        started = time.monotonic()
        with pytest.raises(expected_type) as caught:
            session.element("id", "target").perform_editor_action(
                "done",
                wait_timeout_seconds=1 if total_budget else 0.25,
                control=OperationControl(timeout_seconds=0.25)
                if total_budget
                else None,
            )
        assert time.monotonic() - started < 0.45
        assert_error(
            caught.value,
            expected_type,
            "operation_timeout" if total_budget else "condition_timeout",
            "not_sent",
            steps=_CLICKED,
        )
        assert len(service.of_kind("find")) == len(service.of_kind("action")) == 1
        assert service.of_kind("ime") == []
        assert session.session_info().state == "active"
        session.quit()


def test_cancellation_after_successful_focus_click_preserves_click_and_stops(
    service: EditorProtocolService,
) -> None:
    cancellation = threading.Event()
    service.queue("attribute", ResponsePlan(payload={"value": False}))
    service.queue("action", ResponsePlan(after_send=cancellation.set))
    with connected(service) as connection:
        session = session_for(service, connection, "cancel-after-click")
        with pytest.raises(OperationCancelledError) as caught:
            session.element("id", "target").perform_editor_action(
                "done", control=OperationControl(cancellation=cancellation)
            )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
            steps=_CLICKED,
        )
        assert len(service.of_kind("attribute")) == len(service.of_kind("action")) == 1
        assert service.of_kind("ime") == []
        session.quit()


def test_cancellation_wakes_false_focus_poll_without_reclick(
    service: EditorProtocolService,
) -> None:
    cancellation = threading.Event()
    service.states[("target", "focused")] = False
    service.queue("attribute", ResponsePlan(payload={"value": False}))
    service.queue(
        "attribute",
        ResponsePlan(payload={"value": False}, after_send=cancellation.set),
    )
    with connected(service) as connection:
        session = session_for(service, connection, "cancel-focus-poll")
        with pytest.raises(OperationCancelledError) as caught:
            session.element("id", "target").perform_editor_action(
                "done", control=OperationControl(cancellation=cancellation)
            )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "response_received",
            steps=_CLICKED,
        )
        assert len(service.of_kind("action")) == len(service.of_kind("find")) == 1
        assert service.of_kind("ime") == []
        session.quit()


@pytest.mark.parametrize("phase", ["attribute", "action", "ime"])
@pytest.mark.parametrize("failure", ["disconnect", "timeout", "cancel"])
def test_post_click_or_final_unknown_never_replays_or_restores_raw_settings(
    service: EditorProtocolService, phase: str, failure: str
) -> None:
    cancellation = threading.Event()
    started = threading.Event()
    release = threading.Event()
    worker: threading.Thread | None = None
    if phase != "ime":
        service.queue("attribute", ResponsePlan(payload={"value": False}))
    if failure == "disconnect":
        plan = ResponsePlan(disconnect=True)
        expected_type: type[AutomationError] = ExecutionUnknownError
        code = "execution_unknown"
        control = None
    elif failure == "timeout":
        plan = ResponsePlan(header_delay_seconds=0.4)
        expected_type = OperationTimeoutError
        code = "operation_timeout"
        control = OperationControl(timeout_seconds=0.2)
    else:
        plan = ResponsePlan(started=started, release=release, disconnect=True)
        expected_type = OperationCancelledError
        code = "operation_cancelled"
        control = OperationControl(cancellation=cancellation)

        def cancel_inflight() -> None:
            assert started.wait(timeout=2)
            cancellation.set()
            release.set()

        worker = threading.Thread(target=cancel_inflight)
        worker.start()
    service.queue(phase, plan)
    steps = (
        _CLICKED if phase == "attribute" else _READY if phase == "action" else _FOCUSED
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"unknown-{phase}-{failure}")
        with pytest.raises(expected_type) as caught:
            session.element("id", "vendor/odd@id", raw_id=True).perform_editor_action(
                "done", control=control
            )
        if worker is not None:
            worker.join(timeout=2)
            assert not worker.is_alive()
        assert_error(
            caught.value,
            expected_type,
            code,
            "response_unknown",
            steps=("settings_read", "settings_changed", *steps),
        )
        assert session.session_info().state == "uncertain"
        assert len(service.of_kind("settings:post")) == 1
        assert len(service.of_kind("find")) == 1
        assert len(service.of_kind("action")) == int(phase != "ime")
        assert len(service.of_kind("ime")) == int(phase == "ime")
        assert service.of_kind("quit") == []
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError):
            session.element("id", "target").perform_editor_action("done")
        assert service.snapshot() == before
        with pytest.raises(ResourceStateError) as busy:
            create_session(connection, f"unknown-{phase}-{failure}")
        assert busy.value.code == "device_busy"


@pytest.mark.parametrize("initial", [False, True])
def test_one_raw_guard_spans_stale_preparation_click_poll_and_ime(
    service: EditorProtocolService, initial: bool
) -> None:
    service.settings["disableIdLocatorAutocompletion"] = initial
    service.queue(
        "attribute",
        ResponsePlan(status=404, payload=stale_error()),
        ResponsePlan(payload={"value": False}),
        ResponsePlan(payload={"value": False}),
        ResponsePlan(payload={"value": True}),
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"guard-{initial}")
        session.element("id", "vendor/odd@id", raw_id=True).perform_editor_action(
            "done", wait_timeout_seconds=3
        )
        assert len(service.of_kind("settings:get")) == 1
        assert len(service.of_kind("settings:post")) == (0 if initial else 2)
        assert service.settings["disableIdLocatorAutocompletion"] is initial
        assert service.operation_kinds()[0] == "settings:get"
        assert service.operation_kinds()[-1] == ("ime" if initial else "settings:post")
        assert len(service.of_kind("find")) == 2
        assert len(service.of_kind("action")) == len(service.of_kind("ime")) == 1
        session.quit()


@pytest.mark.parametrize("after_click", [False, True])
def test_raw_known_focus_error_restores_and_preserves_only_actual_steps(
    service: EditorProtocolService, after_click: bool
) -> None:
    if after_click:
        service.queue("attribute", ResponsePlan(payload={"value": False}))
    service.queue("attribute", ResponsePlan(payload={"value": None}))
    with connected(service) as connection:
        session = session_for(service, connection, f"raw-focus-error-{after_click}")
        with pytest.raises(TargetError) as caught:
            session.element("id", "vendor/odd@id", raw_id=True).perform_editor_action(
                "done"
            )
        assert_error(
            caught.value,
            TargetError,
            "precondition_not_met",
            "response_received",
            steps=(
                "settings_read",
                "settings_changed",
                *(_CLICKED if after_click else ()),
                "settings_restored",
            ),
        )
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert service.of_kind("ime") == []
        session.quit()


@pytest.mark.parametrize("unknown", [False, True])
def test_raw_restore_failure_keeps_successful_focus_and_ime_facts(
    service: EditorProtocolService, unknown: bool
) -> None:
    service.queue("attribute", ResponsePlan(payload={"value": False}))
    restore = (
        ResponsePlan(disconnect=True)
        if unknown
        else ResponsePlan(status=500, payload=w3c_error("restore"))
    )
    service.queue("settings:post", ResponsePlan(), restore)
    expected_type: type[AutomationError] = (
        ExecutionUnknownError if unknown else ResourceStateError
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"restore-error-{unknown}")
        with pytest.raises(expected_type) as caught:
            session.element("id", "vendor/odd@id", raw_id=True).perform_editor_action(
                "done"
            )
        assert_error(
            caught.value,
            expected_type,
            "execution_unknown" if unknown else "cleanup_failed",
            "response_unknown" if unknown else "response_received",
            steps=(
                "settings_read",
                "settings_changed",
                *_CLICKED,
                "target_focused",
                "action_completed",
            ),
        )
        assert len(caught.value.cleanup_errors) == (0 if unknown else 1)
        assert len(service.of_kind("action")) == len(service.of_kind("ime")) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


def test_primary_ime_error_precedes_restore_failure(
    service: EditorProtocolService,
) -> None:
    service.queue("ime", ResponsePlan(status=500, payload=w3c_error("ime")))
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(status=500, payload=w3c_error("restore")),
    )
    with connected(service) as connection:
        session = session_for(service, connection, "primary-cleanup")
        with pytest.raises(CommandError) as caught:
            session.element("id", "vendor/odd@id", raw_id=True).perform_editor_action(
                "done"
            )
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=("settings_read", "settings_changed", *_FOCUSED),
        )
        assert len(caught.value.cleanup_errors) == 1
        assert caught.value.__cause__ is not None
        assert "ime" in str(caught.value.__cause__)
        assert session.session_info().state == "uncertain"


@pytest.mark.parametrize("known_error", [False, True])
def test_final_success_or_known_error_wins_later_cancellation(
    service: EditorProtocolService, known_error: bool
) -> None:
    cancellation = threading.Event()
    plan = (
        ResponsePlan(
            status=500, payload=w3c_error("known"), after_send=cancellation.set
        )
        if known_error
        else ResponsePlan(after_send=cancellation.set)
    )
    service.queue("ime", plan)
    with connected(service) as connection:
        session = session_for(service, connection, f"final-priority-{known_error}")
        target = session.element("id", "vendor/odd@id", raw_id=True)
        control = OperationControl(cancellation=cancellation)
        if known_error:
            with pytest.raises(CommandError) as caught:
                target.perform_editor_action("done", control=control)
            assert_error(
                caught.value,
                CommandError,
                "command_failed",
                "response_received",
                steps=(
                    "settings_read",
                    "settings_changed",
                    *_FOCUSED,
                    "settings_restored",
                ),
            )
        else:
            target.perform_editor_action("done", control=control)
        assert cancellation.is_set()
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert len(service.of_kind("ime")) == 1
        session.quit()


def test_condition_budget_does_not_limit_final_ime_response(
    service: EditorProtocolService,
) -> None:
    service.queue("ime", ResponsePlan(header_delay_seconds=0.35))
    with connected(service) as connection:
        session = session_for(service, connection, "final-condition")
        session.element("id", "target").perform_editor_action(
            "done", wait_timeout_seconds=0.2
        )
        assert len(service.of_kind("ime")) == 1
        assert session.session_info().state == "active"
        session.quit()


def test_raw_unresolved_chain_rejected_before_any_request(
    service: EditorProtocolService,
) -> None:
    service.create_package = None
    with connected(service) as connection:
        session = create_session(connection, "raw-unresolved")
        parent = session.element("id", "vendor/odd@id", raw_id=True)
        target = session.element("id", "short", parent=parent)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            target.perform_editor_action("done")
        assert_error(
            caught.value, InvalidRequestError, "unsupported_operation", "not_sent"
        )
        assert service.snapshot() == before
        session.quit()


def test_ime_holds_session_gate_against_element_device_observation_and_quit(
    service: EditorProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.queue("ime", ResponsePlan(started=started, release=release))
    results: list[BaseException | None] = []
    with connected(service) as connection:
        session = session_for(service, connection, "ime-gate")
        target = session.element("id", "target")

        def run() -> None:
            try:
                target.perform_editor_action("done")
            except BaseException as error:
                results.append(error)
            else:
                results.append(None)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            before = service.snapshot()
            for call in (
                target.click,
                session.device.back,
                session.observe_tree,
                session.quit,
            ):
                with pytest.raises(SessionBusyError) as caught:
                    call()
                assert_error(caught.value, SessionBusyError, "session_busy", "not_sent")
            with pytest.raises(InvalidRequestError) as invalid:
                target.perform_editor_action(cast(Any, "DONE"))
            assert_error(
                invalid.value, InvalidRequestError, "invalid_argument", "not_sent"
            )
            assert service.snapshot() == before
            assert session.session_info().busy is True
        finally:
            release.set()
            worker.join(timeout=2)
        assert not worker.is_alive()
        assert results == [None]
        assert session.session_info().busy is False
        session.quit()


def test_invalid_receiver_and_closed_owner_do_not_send_requests(
    service: EditorProtocolService,
) -> None:
    forged = object.__new__(Element)
    with pytest.raises(InvalidRequestError) as invalid:
        forged.perform_editor_action("done")
    assert_error(invalid.value, InvalidRequestError, "invalid_argument", "not_sent")
    with connected(service) as connection:
        session = session_for(service, connection, "closed-ime")
        target = session.element("id", "target")
        session.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as closed:
            target.perform_editor_action("done")
        assert_error(
            closed.value, InvalidSessionStateError, "session_closed", "not_sent"
        )
        assert service.snapshot() == before


@pytest.mark.parametrize("focused", [True, False, "TRUE", "false", "junk", 1])
def test_shared_boolean_helper_preserves_observation_source_invalid_behavior(
    service: EditorProtocolService, focused: object
) -> None:
    service.states[("target", "focused")] = focused
    with connected(service) as connection:
        session = session_for(service, connection, "boolean-observation")
        target = session.element("id", "target")
        if focused in ("junk", 1) and not isinstance(focused, bool):
            with pytest.raises(CommandError) as caught:
                target.inspect(attributes=("focused",))
            assert_error(
                caught.value, CommandError, "source_invalid", "response_received"
            )
        else:
            result = target.inspect(attributes=("focused",))
            assert result.attributes[0].value is (str(focused).lower() == "true")
        session.quit()


def test_changed_locator_does_not_replace_handle_during_successful_focus_poll(
    service: EditorProtocolService,
) -> None:
    locator = "//*[@text='before']"
    service.matches[(None, "xpath", locator)] = ["original"]
    service.queue(
        "attribute",
        ResponsePlan(payload={"value": False}),
        ResponsePlan(payload={"value": False}),
        ResponsePlan(payload={"value": True}),
    )

    def replace_match() -> None:
        service.matches[(None, "xpath", locator)] = ["replacement", "duplicate"]

    service.queue("action", ResponsePlan(after_send=replace_match))
    with connected(service) as connection:
        session = session_for(service, connection, "successful-identity")
        session.element("xpath", locator).perform_editor_action("done")
        assert len(service.of_kind("find")) == 1
        assert all(
            "/element/original/" in item.path for item in service.of_kind("attribute")
        )
        assert len(service.of_kind("action")) == len(service.of_kind("ime")) == 1
        session.quit()


def test_already_cancelled_wins_expired_budget_without_any_requests(
    service: EditorProtocolService,
) -> None:
    cancellation = threading.Event()
    cancellation.set()
    with connected(service) as connection:
        session = session_for(service, connection, "initial-control-priority")
        before = service.snapshot()
        with pytest.raises(OperationCancelledError) as caught:
            session.element("id", "vendor/odd@id", raw_id=True).perform_editor_action(
                "done",
                control=OperationControl(
                    timeout_seconds=5e-324, cancellation=cancellation
                ),
            )
        assert_error(
            caught.value, OperationCancelledError, "operation_cancelled", "not_sent"
        )
        assert service.snapshot() == before
        session.quit()
