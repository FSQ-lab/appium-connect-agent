from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any, Literal, cast

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
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import OperationControl, Runtime
from tests.automation._action_protocol import (
    _ELEMENT_KEY,
    ActionProtocolService,
    ResponsePlan,
    assert_error,
    connected,
    elements,
    session_for,
    stale_error,
    w3c_error,
)

ActionKind = Literal["single", "double", "long"]


@pytest.fixture
def service() -> Iterator[ActionProtocolService]:
    with ActionProtocolService() as current:
        yield current


def invoke(
    element: Element,
    kind: ActionKind,
    *,
    duration_ms: int = 500,
    wait_timeout_seconds: float = 2.0,
    control: OperationControl | None = None,
) -> None:
    if kind == "single":
        element.click(
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )
    elif kind == "double":
        element.double_click(
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )
    else:
        element.long_click(
            duration_ms=duration_ms,
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )


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
        assert invoke(target, kind) is None  # type: ignore[func-returns-value]
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
        session.element("id", "target").click(wait_timeout_seconds=2)
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
            target.click()
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
        target.click()
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
            session.element("id", "target").click()
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
            session.element("id", "target").double_click()
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
            session.element("id", "target").click(
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
            session.element("id", "target").long_click(duration_ms=cast(Any, value))
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("duration", [1, 500, 60_000])
def test_long_duration_boundaries_are_sent_as_exact_integers(
    service: ActionProtocolService, duration: int
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"duration-{duration}")
        session.element("id", "target").long_click(duration_ms=duration)
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
        succeeds.element("id", "target").long_click(
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
                session.element("id", "target").long_click(
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
            session.element("id", "missing").click(
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
            session.element("id", "target").click(wait_timeout_seconds=0.04)
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
            target.click(wait_timeout_seconds=0.05)
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
            target.click()
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
            session.element("id", "missing").click(
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
            precedence.element("id", "missing").click(
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
            known.element("id", "target").click(
                control=OperationControl(timeout_seconds=1, cancellation=cancellation),
            )
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        known.quit()

        cancellation.clear()
        service.queue("action", ResponsePlan(after_send=cancellation.set))
        success = session_for(service, connection, "success-priority")
        assert (
            success.element("id", "target").click(  # type: ignore[func-returns-value]
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
            session.element("id", "target").click(  # type: ignore[func-returns-value]
                wait_timeout_seconds=0.3
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
            session.element("id", "target").click(control=control)
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
        session.element("id", raw_value, raw_id=True).click(
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
            unresolved.click()
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
            session.element("id", raw_value, raw_id=True).click(
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
            target.long_click()
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
            session.element("id", "vendor/odd@id", raw_id=True).click()
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
            session.element("id", "vendor/odd@id", raw_id=True).click()
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


def test_own_session_routing_and_invalid_bindings_respect_lifecycle(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        owner = session_for(service, connection, "owner")
        other = session_for(service, connection, "other")
        foreign = owner.element("id", "target")
        twin = other.element("id", "target")
        foreign.click()
        twin.click()
        assert [request.path for request in service.of_kind("action")] == [
            f"/wd/hub/session/{owner.session_info().appium_session_id}/execute/sync",
            f"/wd/hub/session/{other.session_info().appium_session_id}/execute/sync",
        ]
        forged = object.__new__(Element)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            forged.click()
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        owner.quit()
        other.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as closed:
            other.element("id", "target").click()
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
        target.click()
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
                target.click()
            except BaseException as error:
                result.append(error)
            else:
                result.append(None)

        worker = threading.Thread(target=run)
        worker.start()
        assert started.wait(timeout=2)
        before = len(service.of_kind("action"))
        with pytest.raises(SessionBusyError) as caught:
            target.double_click()
        assert_error(caught.value, SessionBusyError, "session_busy", "not_sent")
        assert len(service.of_kind("action")) == before
        before_requests = service.snapshot()
        with pytest.raises(SessionBusyError) as observation:
            session.observe_tree()
        assert_error(observation.value, SessionBusyError, "session_busy", "not_sent")
        with pytest.raises(SessionBusyError) as closing:
            session.quit()
        assert_error(closing.value, SessionBusyError, "session_busy", "not_sent")
        assert service.snapshot() == before_requests
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
        target.click()
        inspection = target.inspect(attributes=("text",))
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
