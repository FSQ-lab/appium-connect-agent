from __future__ import annotations

import hashlib
import math
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, Literal, cast

import pytest

from appium_connect_agent.automation import (
    AutomationError,
    CommandError,
    Element,
    ElementValidationError,
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
from tests.automation._action_protocol import (
    ActionProtocolService,
    ResponsePlan,
    assert_error,
    connected,
    elements,
    no_such_error,
    stale_error,
    w3c_error,
)
from tests.automation._action_protocol import (
    session_for as protocol_session_for,
)

SingleGesture = Literal["swipe", "scroll_gesture"]
FinalKind = Literal["swipe", "scroll_gesture", "scroll", "drag"]

_CONTAINER_ID = "com.example:id/container"
_TARGET_ID = "com.example:id/target"
_CONTAINER_SELECTOR = f'new UiSelector().resourceId("{_CONTAINER_ID}")'
_TARGET_SELECTOR = f'new UiSelector().resourceId("{_TARGET_ID}")'
_SINGLE_STEPS = ("source_resolved", "source_displayed")
_SCROLL_STEPS = (
    "settings_read",
    "container_resolved",
    "container_displayed",
)
_DRAG_STEPS = (
    "source_resolved",
    "source_displayed",
    "destination_resolved",
    "destination_displayed",
    "destination_geometry_read",
)


@pytest.fixture
def service() -> Iterator[ActionProtocolService]:
    with ActionProtocolService() as current:
        yield current


def session_for(
    service: ActionProtocolService,
    connection: RuntimeConnection,
    device: str,
) -> Session:
    digest = hashlib.sha256(device.encode("utf-8")).hexdigest()
    return protocol_session_for(service, connection, f"gesture-{digest}")


def assert_clean_error(
    error: AutomationError,
    error_type: type[AutomationError],
    code: str,
    request_state: str,
    *,
    steps: tuple[str, ...] = (),
) -> None:
    assert_error(
        error,
        error_type,
        code,
        request_state,
        steps=steps,
    )
    assert error.cleanup_errors == ()


def invoke_single(
    element: Element,
    kind: SingleGesture,
    *,
    direction: str = "up",
    percent: float = 0.5,
    wait_timeout_seconds: float = 2.0,
    control: OperationControl | None = None,
) -> bool | None:
    if kind == "swipe":
        return cast(
            bool | None,
            cast(Callable[..., object], element.swipe_gesture)(
                direction=cast(Any, direction),
                percent=percent,
                wait_timeout_seconds=wait_timeout_seconds,
                control=control,
            ),
        )
    return element.scroll_gesture(
        direction=cast(Any, direction),
        percent=percent,
        wait_timeout_seconds=wait_timeout_seconds,
        control=control,
    )


def drag_elements(session: Session) -> tuple[Element, Element]:
    return session.element("id", "source"), session.element("id", "destination")


def configure_drag(service: ActionProtocolService) -> None:
    service.matches[(None, "id", "com.example:id/source")] = ["source"]
    service.matches[(None, "id", "com.example:id/destination")] = ["destination"]


def scroll_elements(
    service: ActionProtocolService,
    session: Session,
    *,
    target_by: Literal["id", "accessibility id"] = "id",
    target_value: str = "target",
) -> tuple[Element, Element]:
    container = session.element("id", "container")
    target = session.element(target_by, target_value, parent=container)
    service.matches[(None, "-android uiautomator", _CONTAINER_SELECTOR)] = [
        "legacy-container"
    ]
    service.matches[(None, "id", _CONTAINER_ID)] = ["project-container"]
    resolved_target = _TARGET_ID if target_by == "id" else target_value
    service.matches[("project-container", target_by, resolved_target)] = ["target"]
    return container, target


def invoke_final(
    service: ActionProtocolService,
    session: Session,
    kind: FinalKind,
    *,
    control: OperationControl | None = None,
) -> bool | None:
    if kind == "swipe":
        return cast(
            bool | None,
            cast(Callable[..., object], session.element("id", "target").swipe_gesture)(
                direction="up",
                percent=0.5,
                control=control,
            ),
        )
    if kind == "scroll_gesture":
        return session.element("id", "target").scroll_gesture(
            direction="down",
            percent=1.5,
            control=control,
        )
    if kind == "scroll":
        container, target = scroll_elements(service, session)
        return cast(
            bool | None,
            cast(Callable[..., object], container.scroll)(
                target,
                max_swipes=3,
                control=control,
            ),
        )
    configure_drag(service)
    source, destination = drag_elements(session)
    return cast(
        bool | None,
        cast(Callable[..., object], source.drag_and_drop)(
            destination,
            destination_x_ratio=0.5,
            destination_y_ratio=0.5,
            control=control,
        ),
    )


def final_steps(kind: FinalKind) -> tuple[str, ...]:
    return {
        "swipe": _SINGLE_STEPS,
        "scroll_gesture": _SINGLE_STEPS,
        "scroll": _SCROLL_STEPS,
        "drag": _DRAG_STEPS,
    }[kind]


@pytest.mark.parametrize(
    ("kind", "script", "direction", "percent", "result"),
    [
        ("swipe", "mobile: swipeGesture", "up", 0.25, None),
        ("swipe", "mobile: swipeGesture", "down", 1.0, None),
        ("swipe", "mobile: swipeGesture", "left", 1, None),
        ("swipe", "mobile: swipeGesture", "right", 0.5, None),
        ("scroll_gesture", "mobile: scrollGesture", "up", 0.25, False),
        ("scroll_gesture", "mobile: scrollGesture", "down", 1.0, True),
        ("scroll_gesture", "mobile: scrollGesture", "left", 2.0, False),
        ("scroll_gesture", "mobile: scrollGesture", "right", 3.0, True),
    ],
)
def test_single_gestures_use_exact_wire_and_displayed_only_precondition(
    service: ActionProtocolService,
    kind: SingleGesture,
    script: str,
    direction: str,
    percent: float,
    result: bool | None,
) -> None:
    service.queue(kind, ResponsePlan(payload={"value": result}))
    with connected(service) as connection:
        session = session_for(service, connection, f"wire-{kind}-{direction}")
        actual = invoke_single(
            session.element("id", "target"),
            kind,
            direction=direction,
            percent=percent,
        )
        assert actual is result
        assert service.operation_kinds() == ["find", "displayed", kind]
        request = service.of_kind(kind)[0]
        assert request.path.endswith("/execute/sync")
        assert request.body == {
            "script": script,
            "args": [
                {
                    "elementId": "target",
                    "direction": direction,
                    "percent": percent,
                }
            ],
        }
        assert service.of_kind("enabled") == []
        assert service.of_kind("attribute") == []
        assert service.of_kind("rect") == []
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("kind", ["swipe", "scroll_gesture"])
@pytest.mark.parametrize("direction", ["", "UP", "Down", " up", "right ", 1, None])
def test_invalid_directions_are_zero_request(
    service: ActionProtocolService,
    kind: SingleGesture,
    direction: object,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"direction-{kind}-{direction!r}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            invoke_single(
                session.element("id", "target"),
                kind,
                direction=cast(Any, direction),
            )
        assert_clean_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("swipe", True),
        ("swipe", False),
        ("swipe", 0),
        ("swipe", -1e-12),
        ("swipe", math.nextafter(1.0, math.inf)),
        ("swipe", float("nan")),
        ("swipe", float("inf")),
        ("swipe", "0.5"),
        ("scroll_gesture", True),
        ("scroll_gesture", 0),
        ("scroll_gesture", -1e-12),
        ("scroll_gesture", math.nextafter(3.0, math.inf)),
        ("scroll_gesture", float("nan")),
        ("scroll_gesture", float("-inf")),
        ("scroll_gesture", None),
    ],
)
def test_invalid_percent_values_are_zero_request(
    service: ActionProtocolService,
    kind: SingleGesture,
    value: object,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"percent-{kind}-{value!r}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            invoke_single(
                session.element("id", "target"),
                kind,
                percent=cast(Any, value),
            )
        assert_clean_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("kind", ["swipe", "scroll_gesture"])
def test_binary32_positive_boundary_is_checked_without_rewriting_wire_value(
    service: ActionProtocolService,
    kind: SingleGesture,
) -> None:
    minimum_binary32 = float.fromhex("0x1p-149")
    rounds_to_zero = float.fromhex("0x1p-150")
    with connected(service) as connection:
        accepted = session_for(service, connection, f"binary32-ok-{kind}")
        invoke_single(
            accepted.element("id", "target"),
            kind,
            percent=minimum_binary32,
        )
        payload = service.of_kind(kind)[0].body
        assert payload is not None
        assert payload["args"] == [
            {
                "elementId": "target",
                "direction": "up",
                "percent": minimum_binary32,
            }
        ]
        accepted.quit()

        rejected = session_for(service, connection, f"binary32-zero-{kind}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            invoke_single(
                rejected.element("id", "target"),
                kind,
                percent=rounds_to_zero,
            )
        assert_clean_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "not_sent",
        )
        assert service.snapshot() == before
        rejected.quit()


@pytest.mark.parametrize("kind", ["swipe", "scroll_gesture"])
@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), float("inf"), "1"])
def test_invalid_wait_timeout_is_zero_request(
    service: ActionProtocolService,
    kind: SingleGesture,
    value: object,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"wait-{kind}-{value!r}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            invoke_single(
                session.element("id", "target"),
                kind,
                wait_timeout_seconds=cast(Any, value),
            )
        assert_clean_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    ("kind", "plans", "expected"),
    [
        (
            "find",
            [ResponsePlan(payload=elements()), ResponsePlan()],
            ["find", "find", "displayed"],
        ),
        (
            "displayed",
            [ResponsePlan(payload={"value": False}), ResponsePlan()],
            ["find", "displayed", "find", "displayed"],
        ),
    ],
)
def test_single_gesture_waits_for_missing_or_hidden_without_enabled_reads(
    service: ActionProtocolService,
    kind: str,
    plans: list[ResponsePlan],
    expected: list[str],
) -> None:
    service.queue(kind, *plans)
    with connected(service) as connection:
        session = session_for(service, connection, f"wait-visible-{kind}")
        session.element("id", "target").swipe_gesture(
            direction="up",
            percent=0.5,
            wait_timeout_seconds=2,
        )
        assert service.operation_kinds() == [*expected, "swipe"]
        repeated = service.of_kind(kind)
        assert repeated[1].received_at - repeated[0].received_at >= 0.45
        assert service.of_kind("enabled") == []
        assert len(service.of_kind("swipe")) == 1
        session.quit()


def test_single_gesture_ambiguity_is_immediate_and_action_free(
    service: ActionProtocolService,
) -> None:
    service.matches[(None, "id", "com.example:id/target")] = ["one", "two"]
    with connected(service) as connection:
        session = session_for(service, connection, "ambiguous")
        with pytest.raises(TargetError) as caught:
            session.element("id", "target").scroll_gesture(
                direction="down",
                percent=1,
            )
        assert_clean_error(
            caught.value,
            TargetError,
            "target_ambiguous",
            "response_received",
        )
        assert service.of_kind("scroll_gesture") == []
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("stage", ["root", "child", "displayed"])
def test_each_single_gesture_pre_action_stale_restarts_the_complete_chain(
    service: ActionProtocolService,
    stage: str,
) -> None:
    service.matches[(None, "id", "com.example:id/root")] = ["root"]
    service.matches[("root", "id", "com.example:id/target")] = ["target"]
    stale = ResponsePlan(status=404, payload=stale_error())
    if stage == "child":
        service.queue("find", ResponsePlan(), stale)
    else:
        service.queue("find" if stage == "root" else "displayed", stale)
    with connected(service) as connection:
        session = session_for(service, connection, f"stale-single-{stage}")
        root = session.element("id", "root")
        target = session.element("id", "target", parent=root)
        target.swipe_gesture(direction="left", percent=0.5)
        assert len(service.of_kind("find")) >= 3
        assert len(service.of_kind("swipe")) == 1
        assert service.operation_kinds()[-1] == "swipe"
        session.quit()


@pytest.mark.parametrize("kind", ["swipe", "scroll_gesture", "scroll", "drag"])
@pytest.mark.parametrize("status", [404, 500])
def test_final_stale_or_valid_error_is_never_replayed(
    service: ActionProtocolService,
    kind: FinalKind,
    status: int,
) -> None:
    payload = stale_error() if status == 404 else w3c_error("final failed")
    service.queue(kind, ResponsePlan(status=status, payload=payload))
    with connected(service) as connection:
        session = session_for(service, connection, f"known-final-{kind}-{status}")
        with pytest.raises(CommandError) as caught:
            invoke_final(service, session, kind)
        assert_clean_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=final_steps(kind),
        )
        assert len(service.of_kind(kind)) == 1
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    ("kind", "invalid"),
    [
        ("swipe", False),
        ("scroll", False),
        ("drag", False),
        ("scroll_gesture", None),
        ("scroll_gesture", 0),
        ("scroll_gesture", 1),
        ("scroll_gesture", "true"),
    ],
)
def test_final_return_shapes_are_strict_and_never_replayed(
    service: ActionProtocolService,
    kind: FinalKind,
    invalid: object,
) -> None:
    service.queue(kind, ResponsePlan(payload={"value": invalid}))
    with connected(service) as connection:
        session = session_for(service, connection, f"return-shape-{kind}")
        with pytest.raises(CommandError) as caught:
            invoke_final(service, session, kind)
        assert_clean_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=final_steps(kind),
        )
        assert len(service.of_kind(kind)) == 1
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("result", [False, True])
def test_scroll_gesture_returns_exact_bool_without_automatic_continuation(
    service: ActionProtocolService,
    result: bool,
) -> None:
    service.queue("scroll_gesture", ResponsePlan(payload={"value": result}))
    with connected(service) as connection:
        session = session_for(service, connection, f"scroll-bool-{result}")
        actual = session.element("id", "target").scroll_gesture(
            direction="up",
            percent=3,
        )
        assert actual is result
        assert len(service.of_kind("scroll_gesture")) == 1
        assert service.operation_kinds() == ["find", "displayed", "scroll_gesture"]
        session.quit()


@pytest.mark.parametrize("kind", ["swipe", "scroll_gesture", "scroll", "drag"])
@pytest.mark.parametrize("phase", ["disconnect", "header", "body"])
def test_final_response_unknown_is_never_replayed_and_makes_session_uncertain(
    service: ActionProtocolService,
    kind: FinalKind,
    phase: str,
) -> None:
    if phase == "disconnect":
        plan = ResponsePlan(disconnect=True)
        control = None
        error_type: type[AutomationError] = ExecutionUnknownError
        code = "execution_unknown"
    else:
        plan = ResponsePlan(
            header_delay_seconds=0.2 if phase == "header" else 0,
            body_delay_seconds=0.2 if phase == "body" else 0,
        )
        control = OperationControl(timeout_seconds=0.05)
        error_type = OperationTimeoutError
        code = "operation_timeout"
    service.queue(kind, plan)
    with connected(service) as connection:
        session = session_for(service, connection, f"unknown-{kind}-{phase}")
        with pytest.raises(error_type) as caught:
            invoke_final(service, session, kind, control=control)
        assert_clean_error(
            caught.value,
            error_type,
            code,
            "response_unknown",
            steps=final_steps(kind),
        )
        assert len(service.of_kind(kind)) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


def test_final_inflight_cancellation_is_unknown_and_not_replayed(
    service: ActionProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    cancellation = threading.Event()
    service.queue(
        "drag",
        ResponsePlan(started=started, release=release, disconnect=True),
    )
    result: list[BaseException | None] = []
    with connected(service) as connection:
        session = session_for(service, connection, "drag-cancel")
        configure_drag(service)
        source, destination = drag_elements(session)

        def run() -> None:
            try:
                source.drag_and_drop(
                    destination,
                    destination_x_ratio=0.5,
                    destination_y_ratio=0.5,
                    control=OperationControl(
                        timeout_seconds=2,
                        cancellation=cancellation,
                    ),
                )
            except BaseException as error:
                result.append(error)
            else:
                result.append(None)

        worker = threading.Thread(target=run)
        worker.start()
        assert started.wait(timeout=2)
        cancellation.set()
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert len(result) == 1
        error = result[0]
        assert isinstance(error, OperationCancelledError)
        assert_clean_error(
            error,
            OperationCancelledError,
            "operation_cancelled",
            "response_unknown",
            steps=_DRAG_STEPS,
        )
        assert len(service.of_kind("drag")) == 1
        assert session.session_info().state == "uncertain"


def test_combined_raw_guard_rejects_raw_and_unresolved_across_drag_targets(
    service: ActionProtocolService,
) -> None:
    service.create_package = None
    with connected(service) as connection:
        session = create_session(connection, "gesture-raw-mixed")
        source = session.element("id", "vendor/raw@source", raw_id=True)
        destination = session.element("id", "short")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            source.drag_and_drop(
                destination,
                destination_x_ratio=0.5,
                destination_y_ratio=0.5,
            )
        assert_clean_error(
            caught.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("initial", [False, True])
def test_combined_raw_guard_wraps_both_drag_targets_once(
    service: ActionProtocolService,
    initial: bool,
) -> None:
    service.settings["disableIdLocatorAutocompletion"] = initial
    source_value = "vendor/raw@source"
    destination_value = "vendor/raw@destination"
    service.matches[(None, "id", source_value)] = ["source"]
    service.matches[(None, "id", destination_value)] = ["destination"]
    with connected(service) as connection:
        session = session_for(service, connection, f"raw-drag-{initial}")
        source = session.element("id", source_value, raw_id=True)
        destination = session.element("id", destination_value, raw_id=True)
        result = cast(Callable[..., object], source.drag_and_drop)(
            destination,
            destination_x_ratio=0.5,
            destination_y_ratio=0.5,
        )
        assert result is None
        assert len(service.of_kind("settings:get")) == 1
        assert len(service.of_kind("settings:post")) == (0 if initial else 2)
        assert len(service.of_kind("drag")) == 1
        assert service.settings["disableIdLocatorAutocompletion"] is initial
        session.quit()


def test_raw_primary_error_survives_restore_error_and_preserves_steps(
    service: ActionProtocolService,
) -> None:
    service.queue("swipe", ResponsePlan(status=500, payload=w3c_error("swipe")))
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(status=500, payload=w3c_error("restore")),
    )
    with connected(service) as connection:
        session = session_for(service, connection, "raw-double-error")
        target = session.element("id", "vendor/raw@target", raw_id=True)
        with pytest.raises(CommandError) as caught:
            target.swipe_gesture(direction="up", percent=0.5)
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=(
                "settings_read",
                "settings_changed",
                *_SINGLE_STEPS,
            ),
        )
        assert len(caught.value.cleanup_errors) == 1
        cleanup = caught.value.cleanup_errors[0]
        assert isinstance(cleanup, CommandError)
        assert cleanup.code == "command_failed"
        assert len(service.of_kind("swipe")) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


@pytest.mark.parametrize("unknown", [False, True])
def test_raw_success_restore_failure_retains_action_completed(
    service: ActionProtocolService,
    unknown: bool,
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
        target = session.element("id", "vendor/raw@target", raw_id=True)
        with pytest.raises(expected_type) as caught:
            target.swipe_gesture(direction="up", percent=0.5)
        assert_error(
            caught.value,
            expected_type,
            expected_code,
            expected_state,
            steps=(
                "settings_read",
                "settings_changed",
                *_SINGLE_STEPS,
                "action_completed",
            ),
        )
        assert len(caught.value.cleanup_errors) == (0 if unknown else 1)
        assert len(service.of_kind("swipe")) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


@pytest.mark.parametrize("value", [True, False, 0, 31, -1, 1.0, "1", None])
def test_invalid_max_swipes_is_zero_request(
    service: ActionProtocolService,
    value: object,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"max-{value!r}")
        container, target = scroll_elements(service, session)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            container.scroll(target, max_swipes=cast(Any, value))
        assert_clean_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("max_swipes", [1, 30])
@pytest.mark.parametrize(
    ("target_by", "target_value", "strategy", "selector"),
    [
        ("id", "target", "-android uiautomator", _TARGET_SELECTOR),
        ("accessibility id", "Target label", "accessibility id", "Target label"),
    ],
)
def test_official_scroll_exact_settings_uiautomator_wire_and_postcheck(
    service: ActionProtocolService,
    max_swipes: int,
    target_by: Literal["id", "accessibility id"],
    target_value: str,
    strategy: str,
    selector: str,
) -> None:
    with connected(service) as connection:
        session = session_for(
            service,
            connection,
            f"scroll-wire-{max_swipes}-{target_by}",
        )
        container, target = scroll_elements(
            service,
            session,
            target_by=target_by,
            target_value=target_value,
        )
        result = cast(Callable[..., object], container.scroll)(
            target,
            max_swipes=max_swipes,
        )
        assert result is None
        assert service.operation_kinds() == [
            "settings:get",
            "find",
            "displayed",
            "scroll",
            "find",
            "find",
            "displayed",
        ]
        legacy_find, project_container_find, target_find = service.of_kind("find")
        assert legacy_find.body == {
            "using": "-android uiautomator",
            "value": _CONTAINER_SELECTOR,
        }
        assert project_container_find.body == {
            "using": "id",
            "value": _CONTAINER_ID,
        }
        assert target_find.path.endswith("/element/project-container/elements")
        expected_target_value = _TARGET_ID if target_by == "id" else target_value
        assert target_find.body == {
            "using": target_by,
            "value": expected_target_value,
        }
        request = service.of_kind("scroll")[0]
        assert request.path.endswith("/execute/sync")
        assert request.body == {
            "script": "mobile: scroll",
            "args": [
                {
                    "elementId": "legacy-container",
                    "strategy": strategy,
                    "selector": selector,
                    "maxSwipes": max_swipes,
                }
            ],
        }
        assert len(request.body["args"]) == 1
        payload = cast(list[dict[str, object]], request.body["args"])[0]
        assert set(payload) == {"elementId", "strategy", "selector", "maxSwipes"}
        assert service.of_kind("scroll") == [request]
        assert service.of_kind("enabled") == []
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    ("stage", "plans", "expected_prefix"),
    [
        (
            "find",
            [ResponsePlan(payload=elements()), ResponsePlan()],
            ["settings:get", "find", "find", "displayed", "scroll"],
        ),
        (
            "displayed",
            [ResponsePlan(payload={"value": False}), ResponsePlan()],
            [
                "settings:get",
                "find",
                "displayed",
                "find",
                "displayed",
                "scroll",
            ],
        ),
    ],
)
def test_official_scroll_waits_for_missing_or_hidden_container_only(
    service: ActionProtocolService,
    stage: str,
    plans: list[ResponsePlan],
    expected_prefix: list[str],
) -> None:
    service.queue(stage, *plans)
    with connected(service) as connection:
        session = session_for(service, connection, f"scroll-container-wait-{stage}")
        container, target = scroll_elements(service, session)
        container.scroll(target, max_swipes=1)
        kinds = service.operation_kinds()
        assert kinds[: len(expected_prefix)] == expected_prefix
        repeated = service.of_kind(stage)
        assert repeated[1].received_at - repeated[0].received_at >= 0.45
        assert len(service.of_kind("scroll")) == 1
        assert service.of_kind("enabled") == []
        session.quit()


def test_official_scroll_ambiguous_container_is_immediate_and_action_free(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "scroll-container-ambiguous")
        container, target = scroll_elements(service, session)
        service.matches[(None, "-android uiautomator", _CONTAINER_SELECTOR)] = [
            "container-one",
            "container-two",
        ]
        with pytest.raises(TargetError) as caught:
            container.scroll(target, max_swipes=1)
        assert_clean_error(
            caught.value,
            TargetError,
            "target_ambiguous",
            "response_received",
            steps=("settings_read",),
        )
        assert service.of_kind("scroll") == []
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("stage", ["find", "displayed"])
def test_official_scroll_pre_action_stale_restarts_container_preparation(
    service: ActionProtocolService,
    stage: str,
) -> None:
    service.queue(stage, ResponsePlan(status=404, payload=stale_error()))
    with connected(service) as connection:
        session = session_for(service, connection, f"scroll-container-stale-{stage}")
        container, target = scroll_elements(service, session)
        container.scroll(target, max_swipes=1)
        assert len(service.of_kind("find")) >= 3
        assert len(service.of_kind("scroll")) == 1
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("setting", [True, "false", 0, None])
def test_official_scroll_requires_actual_false_map_test_tag_setting(
    service: ActionProtocolService,
    setting: object,
) -> None:
    if setting is None:
        service.settings.pop("mapTestTagToResourceId")
    else:
        service.settings["mapTestTagToResourceId"] = setting
    with connected(service) as connection:
        session = session_for(service, connection, f"scroll-setting-{setting!r}")
        container, target = scroll_elements(service, session)
        expected_type: type[AutomationError] = (
            InvalidRequestError if setting is True else CommandError
        )
        expected_code = (
            "unsupported_operation" if setting is True else "source_settings_invalid"
        )
        with pytest.raises(expected_type) as caught:
            container.scroll(target, max_swipes=1)
        assert_clean_error(
            caught.value,
            expected_type,
            expected_code,
            "response_received",
            steps=("settings_read",),
        )
        assert len(service.of_kind("settings:get")) == 1
        assert service.of_kind("find") == []
        assert service.of_kind("scroll") == []
        assert session.session_info().state == "active"
        session.quit()


def test_official_scroll_target_is_not_polled_before_the_one_final_command(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "scroll-target-absent")
        container, target = scroll_elements(service, session)
        service.matches[("project-container", "id", _TARGET_ID)] = []
        with pytest.raises(TargetError) as caught:
            container.scroll(target, max_swipes=2)
        assert_clean_error(
            caught.value,
            TargetError,
            "target_not_found",
            "response_received",
            steps=(*_SCROLL_STEPS, "action_completed"),
        )
        kinds = service.operation_kinds()
        assert kinds.index("scroll") < kinds.index("find", kinds.index("scroll") + 1)
        assert len(service.of_kind("scroll")) == 1
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    ("payload", "message"),
    [(no_such_error(), "no such"), (w3c_error("valid error"), "other")],
)
def test_official_scroll_final_valid_errors_remain_command_errors(
    service: ActionProtocolService,
    payload: dict[str, object],
    message: str,
) -> None:
    service.queue(
        "scroll",
        ResponsePlan(
            status=404 if message == "no such" else 500,
            payload=payload,
        ),
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"scroll-final-{message}")
        container, target = scroll_elements(service, session)
        with pytest.raises(CommandError) as caught:
            container.scroll(target, max_swipes=3)
        assert_clean_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=_SCROLL_STEPS,
        )
        assert len(service.of_kind("scroll")) == 1
        assert len(service.of_kind("find")) == 1
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    ("mode", "code", "steps"),
    [
        ("missing", "target_not_found", (*_SCROLL_STEPS, "action_completed")),
        ("ambiguous", "target_ambiguous", (*_SCROLL_STEPS, "action_completed")),
        (
            "hidden",
            "precondition_not_met",
            (*_SCROLL_STEPS, "action_completed", "target_resolved"),
        ),
    ],
)
def test_official_scroll_postcheck_target_outcomes_preserve_action_fact(
    service: ActionProtocolService,
    mode: str,
    code: str,
    steps: tuple[str, ...],
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"scroll-post-{mode}")
        container, target = scroll_elements(service, session)
        if mode == "missing":
            service.matches[("project-container", "id", _TARGET_ID)] = []
        elif mode == "ambiguous":
            service.matches[("project-container", "id", _TARGET_ID)] = ["one", "two"]
        else:
            service.states[("target", "displayed")] = False
        with pytest.raises(TargetError) as caught:
            container.scroll(target, max_swipes=2)
        assert_clean_error(
            caught.value,
            TargetError,
            code,
            "response_received",
            steps=steps,
        )
        assert len(service.of_kind("scroll")) == 1
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    "stage",
    ["root", "root_error", "child", "displayed", "displayed_invalid"],
)
def test_official_scroll_postcheck_known_read_failures_do_not_retry_or_replay(
    service: ActionProtocolService,
    stage: str,
) -> None:
    stale = ResponsePlan(status=404, payload=stale_error())
    expected_steps: tuple[str, ...]
    if stage == "root":
        service.queue("find", ResponsePlan(), stale)
        expected_steps = (*_SCROLL_STEPS, "action_completed")
    elif stage == "root_error":
        service.queue(
            "find",
            ResponsePlan(),
            ResponsePlan(status=500, payload=w3c_error("postcheck")),
        )
        expected_steps = (*_SCROLL_STEPS, "action_completed")
    elif stage == "child":
        service.queue("find", ResponsePlan(), ResponsePlan(), stale)
        expected_steps = (*_SCROLL_STEPS, "action_completed")
    elif stage == "displayed":
        service.queue("displayed", ResponsePlan(), stale)
        expected_steps = (*_SCROLL_STEPS, "action_completed", "target_resolved")
    else:
        service.queue(
            "displayed",
            ResponsePlan(),
            ResponsePlan(payload={"value": "true"}),
        )
        expected_steps = (*_SCROLL_STEPS, "action_completed", "target_resolved")
    with connected(service) as connection:
        session = session_for(service, connection, f"scroll-post-known-{stage}")
        container, target = scroll_elements(service, session)
        with pytest.raises(CommandError) as caught:
            container.scroll(target, max_swipes=2)
        assert_clean_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=expected_steps,
        )
        assert len(service.of_kind("scroll")) == 1
        assert len(service.of_kind("find")) <= 3
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("stage", ["resolution", "displayed"])
def test_official_scroll_postcheck_unknown_preserves_prior_steps_and_uncertain_state(
    service: ActionProtocolService,
    stage: str,
) -> None:
    expected_steps: tuple[str, ...]
    if stage == "resolution":
        service.queue("find", ResponsePlan(), ResponsePlan(disconnect=True))
        expected_steps = (*_SCROLL_STEPS, "action_completed")
    else:
        service.queue("displayed", ResponsePlan(), ResponsePlan(disconnect=True))
        expected_steps = (*_SCROLL_STEPS, "action_completed", "target_resolved")
    with connected(service) as connection:
        session = session_for(service, connection, f"scroll-post-unknown-{stage}")
        container, target = scroll_elements(service, session)
        with pytest.raises(ExecutionUnknownError) as caught:
            container.scroll(target, max_swipes=2)
        assert_clean_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
            steps=expected_steps,
        )
        assert len(service.of_kind("scroll")) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


def test_official_scroll_rejects_foreign_target_before_any_request(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        owner = session_for(service, connection, "scroll-owner")
        other = session_for(service, connection, "scroll-other")
        container = owner.element("id", "container")
        foreign_container = other.element("id", "container")
        target = other.element("id", "target", parent=foreign_container)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            container.scroll(target, max_swipes=1)
        assert_clean_error(
            caught.value, InvalidRequestError, "element_session_mismatch", "not_sent"
        )
        assert service.snapshot() == before
        owner.quit()
        other.quit()


def test_official_scroll_whitelist_rejects_unsupported_shapes_before_settings(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "scroll-whitelist")
        canonical = session.element("id", "container")
        other = session.element("id", "other")
        cases = [
            (
                session.element("accessibility id", "container"),
                session.element("id", "target", parent=canonical),
            ),
            (
                session.element("xpath", "//android.view.ViewGroup"),
                session.element("id", "target", parent=canonical),
            ),
            (
                session.element("id", "vendor/raw@container", raw_id=True),
                session.element("id", "target", parent=canonical),
            ),
            (canonical, session.element("id", "target")),
            (canonical, session.element("id", "target", parent=other)),
            (
                canonical,
                session.element(
                    "id", "target", parent=session.element("id", "container")
                ),
            ),
            (
                canonical,
                session.element(
                    "id",
                    "leaf",
                    parent=session.element("id", "middle", parent=canonical),
                ),
            ),
            (
                canonical,
                session.element(
                    "id",
                    'bad");evil();("',
                    raw_id=True,
                    parent=canonical,
                ),
            ),
        ]
        for index, (container, target) in enumerate(cases):
            before = service.snapshot()
            with pytest.raises(InvalidRequestError) as caught:
                container.scroll(target, max_swipes=1)
            assert_clean_error(
                caught.value,
                InvalidRequestError,
                "unsupported_operation",
                "not_sent",
            )
            assert service.snapshot() == before, index
        before_xpath = service.snapshot()
        with pytest.raises(ElementValidationError):
            session.element("xpath", ".//target", parent=canonical)
        assert service.snapshot() == before_xpath
        session.quit()


def test_official_scroll_rejects_unresolved_ids_and_element_factory_rejects_class(
    service: ActionProtocolService,
) -> None:
    service.create_package = None
    with connected(service) as connection:
        session = create_session(connection, "gesture-scroll-unresolved")
        unresolved_container = session.element("id", "container")
        target = session.element("id", "target", parent=unresolved_container)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            unresolved_container.scroll(target, max_swipes=1)
        assert_clean_error(
            caught.value,
            InvalidRequestError,
            "unsupported_operation",
            "not_sent",
        )
        assert service.snapshot() == before
        with pytest.raises(ElementValidationError):
            session.element("class name", "android.widget.ScrollView")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    ("x_ratio", "y_ratio", "expected_x", "expected_y"),
    [
        (0, 0, -10, -20),
        (0.5, 0.5, -6, -15),
        (1, 1, -2, -10),
    ],
)
def test_drag_uses_floor_inside_destination_and_exact_minimal_payload(
    service: ActionProtocolService,
    x_ratio: int | float,
    y_ratio: int | float,
    expected_x: int,
    expected_y: int,
) -> None:
    configure_drag(service)
    service.states[("destination", "rect")] = {
        "x": -10,
        "y": -20,
        "width": 9,
        "height": 11,
        "ignored": "extra upstream field",
    }
    with connected(service) as connection:
        session = session_for(service, connection, f"drag-floor-{x_ratio}-{y_ratio}")
        source, destination = drag_elements(session)
        result = cast(Callable[..., object], source.drag_and_drop)(
            destination,
            destination_x_ratio=x_ratio,
            destination_y_ratio=y_ratio,
        )
        assert result is None
        assert service.operation_kinds() == [
            "find",
            "displayed",
            "find",
            "displayed",
            "rect",
            "drag",
        ]
        request = service.of_kind("drag")[0]
        assert request.body == {
            "script": "mobile: dragGesture",
            "args": [
                {
                    "elementId": "source",
                    "endX": expected_x,
                    "endY": expected_y,
                }
            ],
        }
        payload = cast(list[dict[str, object]], request.body["args"])[0]
        assert set(payload) == {"elementId", "endX", "endY"}
        assert service.of_kind("enabled") == []
        assert service.of_kind("attribute") == []
        assert len(service.of_kind("drag")) == 1
        session.quit()


@pytest.mark.parametrize(
    "mode",
    [
        "source_missing",
        "source_hidden",
        "destination_missing",
        "destination_hidden",
    ],
)
def test_drag_waits_for_each_missing_or_hidden_target_as_a_complete_round(
    service: ActionProtocolService,
    mode: str,
) -> None:
    configure_drag(service)
    if mode == "source_missing":
        service.queue("find", ResponsePlan(payload=elements()), ResponsePlan())
    elif mode == "source_hidden":
        service.queue(
            "displayed",
            ResponsePlan(payload={"value": False}),
            ResponsePlan(),
        )
    elif mode == "destination_missing":
        service.queue(
            "find",
            ResponsePlan(),
            ResponsePlan(payload=elements()),
            ResponsePlan(),
            ResponsePlan(),
        )
    else:
        service.queue(
            "displayed",
            ResponsePlan(),
            ResponsePlan(payload={"value": False}),
            ResponsePlan(),
            ResponsePlan(),
        )
    with connected(service) as connection:
        session = session_for(service, connection, f"drag-wait-{mode}")
        source, destination = drag_elements(session)
        source.drag_and_drop(
            destination,
            destination_x_ratio=0.5,
            destination_y_ratio=0.5,
        )
        source_finds = [
            request
            for request in service.of_kind("find")
            if request.body == {"using": "id", "value": "com.example:id/source"}
        ]
        assert len(source_finds) == 2
        assert len(service.of_kind("drag")) == 1
        assert service.of_kind("enabled") == []
        session.quit()


@pytest.mark.parametrize("role", ["source", "destination"])
def test_drag_ambiguity_for_either_target_is_immediate_and_action_free(
    service: ActionProtocolService,
    role: str,
) -> None:
    configure_drag(service)
    service.matches[(None, "id", f"com.example:id/{role}")] = ["one", "two"]
    with connected(service) as connection:
        session = session_for(service, connection, f"drag-ambiguous-{role}")
        source, destination = drag_elements(session)
        with pytest.raises(TargetError) as caught:
            source.drag_and_drop(
                destination,
                destination_x_ratio=0.5,
                destination_y_ratio=0.5,
            )
        assert_clean_error(
            caught.value,
            TargetError,
            "target_ambiguous",
            "response_received",
        )
        assert service.of_kind("rect") == []
        assert service.of_kind("drag") == []
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    "rect",
    [
        {},
        {"x": 0, "y": 0, "width": 1},
        {"x": True, "y": 0, "width": 1, "height": 1},
        {"x": 0.0, "y": 0, "width": 1, "height": 1},
        {"x": 0, "y": 0, "width": 0, "height": 1},
        {"x": 0, "y": 0, "width": 1, "height": -1},
        [0, 0, 1, 1],
        None,
    ],
)
def test_invalid_destination_rect_fails_before_drag(
    service: ActionProtocolService,
    rect: object,
) -> None:
    configure_drag(service)
    service.queue("rect", ResponsePlan(payload={"value": rect}))
    with connected(service) as connection:
        session = session_for(service, connection, f"drag-rect-{rect!r}")
        source, destination = drag_elements(session)
        with pytest.raises(CommandError) as caught:
            source.drag_and_drop(
                destination,
                destination_x_ratio=0.5,
                destination_y_ratio=0.5,
            )
        assert_clean_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
        )
        assert service.of_kind("drag") == []
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    ("rect", "ratio", "allowed", "expected"),
    [
        (
            {"x": 2_147_483_647, "y": -2_147_483_648, "width": 1, "height": 1},
            1.0,
            True,
            (2_147_483_647, -2_147_483_648),
        ),
        (
            {"x": 2_147_483_647, "y": 0, "width": 2, "height": 1},
            1.0,
            False,
            None,
        ),
        (
            {"x": 0, "y": 2_147_483_647, "width": 1, "height": 2},
            1.0,
            False,
            None,
        ),
    ],
)
def test_drag_computed_coordinates_enforce_java_int_range(
    service: ActionProtocolService,
    rect: dict[str, int],
    ratio: float,
    allowed: bool,
    expected: tuple[int, int] | None,
) -> None:
    configure_drag(service)
    service.states[("destination", "rect")] = rect
    with connected(service) as connection:
        session = session_for(service, connection, f"drag-java-{allowed}-{rect['x']}")
        source, destination = drag_elements(session)
        if allowed:
            source.drag_and_drop(
                destination,
                destination_x_ratio=ratio,
                destination_y_ratio=ratio,
            )
            request = service.of_kind("drag")[0]
            assert request.body is not None
            args = cast(list[dict[str, object]], request.body["args"])[0]
            assert (args["endX"], args["endY"]) == expected
        else:
            with pytest.raises(CommandError) as caught:
                source.drag_and_drop(
                    destination,
                    destination_x_ratio=ratio,
                    destination_y_ratio=ratio,
                )
            assert_clean_error(
                caught.value,
                CommandError,
                "command_failed",
                "response_received",
            )
            assert service.of_kind("drag") == []
        session.quit()


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        -math.ulp(0.0),
        math.nextafter(1.0, math.inf),
        float("nan"),
        float("inf"),
        "0.5",
        None,
    ],
)
@pytest.mark.parametrize("coordinate", ["x", "y"])
def test_invalid_drag_ratios_are_zero_request(
    service: ActionProtocolService,
    value: object,
    coordinate: str,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"drag-ratio-{coordinate}-{value!r}")
        source, destination = drag_elements(session)
        before = service.snapshot()
        x_value: object = value if coordinate == "x" else 0.5
        y_value: object = value if coordinate == "y" else 0.5
        with pytest.raises(InvalidRequestError) as caught:
            source.drag_and_drop(
                destination,
                destination_x_ratio=cast(Any, x_value),
                destination_y_ratio=cast(Any, y_value),
            )
        assert_clean_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "not_sent",
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    "stage",
    [
        "source_find",
        "source_displayed",
        "destination_find",
        "destination_displayed",
        "rect",
    ],
)
def test_each_drag_pre_action_stale_restarts_the_entire_two_target_round(
    service: ActionProtocolService,
    stage: str,
) -> None:
    configure_drag(service)
    stale = ResponsePlan(status=404, payload=stale_error())
    if stage == "source_find":
        service.queue("find", stale)
    elif stage == "destination_find":
        service.queue("find", ResponsePlan(), stale)
    elif stage == "source_displayed":
        service.queue("displayed", stale)
    elif stage == "destination_displayed":
        service.queue("displayed", ResponsePlan(), stale)
    else:
        service.queue("rect", stale)
    service.queue("drag", ResponsePlan(status=500, payload=w3c_error("final")))
    with connected(service) as connection:
        session = session_for(service, connection, f"drag-stale-{stage}")
        source, destination = drag_elements(session)
        with pytest.raises(CommandError) as caught:
            source.drag_and_drop(
                destination,
                destination_x_ratio=0.5,
                destination_y_ratio=0.5,
            )
        assert_clean_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=_DRAG_STEPS,
        )
        assert len(service.of_kind("find")) >= 3
        assert len(service.of_kind("drag")) == 1
        assert session.session_info().state == "active"
        session.quit()


def test_foreign_forged_closed_and_connection_invalid_are_request_free(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        owner = session_for(service, connection, "owner")
        other = session_for(service, connection, "other")
        source = owner.element("id", "target")
        destination = other.element("id", "target")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as mismatch:
            source.drag_and_drop(
                destination,
                destination_x_ratio=0.5,
                destination_y_ratio=0.5,
            )
        assert_clean_error(
            mismatch.value,
            InvalidRequestError,
            "element_session_mismatch",
            "not_sent",
        )
        with pytest.raises(InvalidRequestError) as forged:
            object.__new__(Element).swipe_gesture(direction="up", percent=0.5)
        assert_clean_error(
            forged.value, InvalidRequestError, "invalid_argument", "not_sent"
        )
        assert service.snapshot() == before
        owner.quit()
        other.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as closed:
            other.element("id", "target").swipe_gesture(
                direction="up",
                percent=0.5,
            )
        assert_clean_error(
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
        target.scroll_gesture(direction="down", percent=1)
    assert_clean_error(
        invalid_error.value,
        InvalidSessionStateError,
        "session_invalid",
        "not_sent",
    )
    assert invalid.session_info().state == "uncertain"
    assert service.snapshot() == before


def test_overlapping_gesture_is_immediately_busy_and_sends_no_second_final(
    service: ActionProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.queue("swipe", ResponsePlan(started=started, release=release))
    result: list[BaseException | None] = []
    with connected(service) as connection:
        session = session_for(service, connection, "busy")
        target = session.element("id", "target")

        def run() -> None:
            try:
                target.swipe_gesture(direction="up", percent=0.5)
            except BaseException as error:
                result.append(error)
            else:
                result.append(None)

        worker = threading.Thread(target=run)
        worker.start()
        assert started.wait(timeout=2)
        before = len(service.of_kind("scroll_gesture"))
        with pytest.raises(SessionBusyError) as caught:
            target.scroll_gesture(direction="down", percent=1)
        assert_clean_error(
            caught.value,
            SessionBusyError,
            "session_busy",
            "not_sent",
        )
        assert len(service.of_kind("scroll_gesture")) == before
        assert session.session_info().busy is True
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert result == [None]
        assert len(service.of_kind("swipe")) == 1
        assert session.session_info().busy is False
        session.quit()


def test_cancellation_wakes_pre_action_wait_and_is_request_state_not_sent(
    service: ActionProtocolService,
) -> None:
    service.matches[(None, "id", "com.example:id/missing")] = []
    cancellation = threading.Event()
    timer = threading.Timer(0.05, cancellation.set)
    with connected(service) as connection:
        session = session_for(service, connection, "cancel-wait")
        timer.start()
        started = time.monotonic()
        with pytest.raises(OperationCancelledError) as caught:
            session.element("id", "missing").swipe_gesture(
                direction="up",
                percent=0.5,
                wait_timeout_seconds=1,
                control=OperationControl(
                    timeout_seconds=2,
                    cancellation=cancellation,
                ),
            )
        elapsed = time.monotonic() - started
        timer.join(timeout=1)
        assert not timer.is_alive()
        assert elapsed < 0.4
        assert_clean_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
        )
        assert service.of_kind("swipe") == []
        assert session.session_info().state == "active"
        session.quit()


def test_condition_timeout_reports_no_completed_target_steps(
    service: ActionProtocolService,
) -> None:
    service.matches[(None, "id", "com.example:id/missing")] = []
    with connected(service) as connection:
        session = session_for(service, connection, "condition-timeout")
        with pytest.raises(TargetError) as caught:
            session.element("id", "missing").scroll_gesture(
                direction="down",
                percent=1,
                wait_timeout_seconds=0.03,
            )
        assert_clean_error(
            caught.value,
            TargetError,
            "condition_timeout",
            "not_sent",
        )
        assert service.of_kind("scroll_gesture") == []
        assert session.session_info().state == "active"
        session.quit()


def test_gestures_preserve_aif02_aif03_aif04_and_aif05_behavior(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "regression")
        target = session.element("id", "target")
        target.swipe_gesture(direction="up", percent=0.5)
        target.click()
        target.send_keys("value")
        inspection = target.inspect(attributes=("text",))
        assert inspection.attributes[0].state == "missing"
        assert service.operation_kinds() == [
            "find",
            "displayed",
            "swipe",
            "find",
            "displayed",
            "enabled",
            "action",
            "find",
            "displayed",
            "enabled",
            "send",
            "find",
            "attribute",
        ]
        assert len(service.of_kind("swipe")) == 1
        assert len(service.of_kind("action")) == 1
        assert len(service.of_kind("send")) == 1
        assert session.session_info().state == "active"
        session.quit()
        assert session.session_info().state == "closed"
        assert len(service.of_kind("quit")) == 1
