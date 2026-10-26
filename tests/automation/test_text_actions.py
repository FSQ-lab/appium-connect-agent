from __future__ import annotations

import inspect
import threading
import time
from collections.abc import Callable, Iterator
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
    Session,
    SessionBusyError,
    TargetError,
    create_session,
)
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import OperationControl, Runtime, RuntimeConnection
from tests.automation._action_protocol import (
    _ELEMENT_KEY,
    ActionProtocolService,
    ResponsePlan,
    assert_error,
    connected,
    elements,
    stale_error,
    w3c_error,
)
from tests.automation._action_protocol import (
    session_for as protocol_session_for,
)

TextAction = Literal["send_keys", "clear", "replace"]


@pytest.fixture
def service() -> Iterator[ActionProtocolService]:
    with ActionProtocolService() as current:
        yield current


def session_for(
    service: ActionProtocolService,
    connection: RuntimeConnection,
    device: str,
) -> Session:
    return protocol_session_for(service, connection, f"text-{device}")


def invoke(
    session: Session,
    element: Element,
    action: TextAction,
    *,
    text: str = "value",
    wait_timeout_seconds: float = 2.0,
    control: OperationControl | None = None,
) -> None:
    if action == "send_keys":
        session.send_keys(
            element,
            text,
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )
    elif action == "clear":
        session.clear(
            element,
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )
    else:
        session.replace_element_value(
            element,
            text,
            wait_timeout_seconds=wait_timeout_seconds,
            control=control,
        )


def final_kind(action: TextAction) -> str:
    return {
        "send_keys": "send",
        "clear": "clear",
        "replace": "replace",
    }[action]


def assert_final_payload(
    service: ActionProtocolService,
    action: TextAction,
    text: str,
    *,
    element_id: str = "target",
) -> None:
    request = service.of_kind(final_kind(action))[0]
    if action == "send_keys":
        assert request.path.endswith(f"/element/{element_id}/value")
        assert request.body == {"text": text, "value": list(text)}
    elif action == "clear":
        assert request.path.endswith(f"/element/{element_id}/clear")
        assert request.body == {}
    else:
        assert request.path.endswith("/execute/sync")
        assert request.body == {
            "script": "mobile: replaceElementValue",
            "args": [{"elementId": element_id, "text": text}],
        }


@pytest.mark.parametrize(
    ("method", "names"),
    [
        (
            Session.send_keys,
            ("self", "element", "text", "wait_timeout_seconds", "control"),
        ),
        (Session.clear, ("self", "element", "wait_timeout_seconds", "control")),
        (
            Session.replace_element_value,
            ("self", "element", "text", "wait_timeout_seconds", "control"),
        ),
    ],
)
def test_public_signatures_are_exact(
    method: Callable[..., object], names: tuple[str, ...]
) -> None:
    parameters = inspect.signature(method).parameters
    assert tuple(parameters) == names
    assert parameters["wait_timeout_seconds"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["wait_timeout_seconds"].default == 15.0
    assert parameters["control"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["control"].default is None


@pytest.mark.parametrize("action", ["send_keys", "clear", "replace"])
def test_exact_routes_payloads_order_none_and_one_final_request(
    service: ActionProtocolService,
    action: TextAction,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"exact-{action}")
        service.matches[(None, "id", "com.example:id/form")] = ["form"]
        service.matches[("form", "id", "com.example:id/target")] = ["target"]
        parent = session.element("id", "form")
        target = session.element("id", "target", parent=parent)

        if action == "send_keys":
            result = session.send_keys(  # type: ignore[func-returns-value]
                target, "A中🙂"
            )
        elif action == "clear":
            result = session.clear(target)  # type: ignore[func-returns-value]
        else:
            result = session.replace_element_value(  # type: ignore[func-returns-value]
                target, "A中🙂"
            )
        assert result is None

        assert service.operation_kinds() == [
            "find",
            "find",
            "displayed",
            "enabled",
            final_kind(action),
        ]
        root, child = service.of_kind("find")
        assert root.path.endswith("/elements")
        assert child.path.endswith("/element/form/elements")
        assert root.body == {"using": "id", "value": "com.example:id/form"}
        assert child.body == {
            "using": "id",
            "value": "com.example:id/target",
        }
        assert_final_payload(service, action, "A中🙂")
        session.quit()


@pytest.mark.parametrize("action", ["send_keys", "replace"])
@pytest.mark.parametrize(
    "text",
    [
        "ASCII",
        "中文",
        "🙂𐐷",
        "e\u0301",
        "👩\u200d💻",
        "עברית",
        r"inside\nvalue",
        "line1\nline2",
        "carriage\rreturn",
        "crlf\r\nvalue",
        "tab\tvalue",
        "control\x01value",
        "separators\u2028\u2029",
        "private\ue000value",
    ],
)
def test_valid_text_is_transparent_in_client_payload(
    service: ActionProtocolService,
    action: TextAction,
    text: str,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"transparent-{action}")
        invoke(session, session.element("id", "target"), action, text=text)
        assert_final_payload(service, action, text)
        session.quit()


@pytest.mark.parametrize(
    ("text", "allowed"),
    [
        ("a" * 65_535, True),
        ("a" * 65_536, True),
        ("a" * 65_537, False),
        ("🙂" * 16_384, True),
        ("🙂" * 16_384 + "a", False),
    ],
)
@pytest.mark.parametrize("action", ["send_keys", "replace"])
def test_text_limit_counts_strict_utf8_bytes_inclusively(
    service: ActionProtocolService,
    action: TextAction,
    text: str,
    allowed: bool,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"boundary-{action}-{len(text)}")
        target = session.element("id", "target")
        before = service.snapshot()
        if allowed:
            invoke(session, target, action, text=text)
            assert_final_payload(service, action, text)
        else:
            with pytest.raises(InvalidRequestError) as caught:
                invoke(session, target, action, text=text)
            assert_error(
                caught.value,
                InvalidRequestError,
                "invalid_argument",
                "not_sent",
                steps=(),
            )
            assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(
    ("action", "text"),
    [
        pytest.param("send_keys", "", id="send-empty"),
        pytest.param("send_keys", 1, id="send-integer"),
        pytest.param("replace", 1, id="replace-integer"),
        pytest.param("send_keys", b"bytes", id="send-bytes"),
        pytest.param("replace", b"bytes", id="replace-bytes"),
        pytest.param("send_keys", None, id="send-none"),
        pytest.param("replace", None, id="replace-none"),
        pytest.param("send_keys", "nul\x00value", id="send-nul"),
        pytest.param("replace", "nul\x00value", id="replace-nul"),
        pytest.param("send_keys", "lone\ud800", id="send-surrogate"),
        pytest.param("replace", "lone\udfff", id="replace-surrogate"),
        pytest.param("send_keys", r"trailing\n", id="send-backslash-n"),
        pytest.param("replace", r"trailing\n", id="replace-backslash-n"),
    ],
)
def test_invalid_text_is_zero_io(
    service: ActionProtocolService,
    action: Literal["send_keys", "replace"],
    text: object,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"invalid-{action}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            if action == "send_keys":
                session.send_keys(session.element("id", "target"), cast(Any, text))
            else:
                session.replace_element_value(
                    session.element("id", "target"), cast(Any, text)
                )
        assert_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        session.quit()


def test_replace_empty_is_one_replace_and_never_clear(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "replace-empty")
        session.replace_element_value(session.element("id", "target"), "")
        assert_final_payload(service, "replace", "")
        assert len(service.of_kind("replace")) == 1
        assert service.of_kind("send") == []
        assert service.of_kind("clear") == []
        session.quit()


@pytest.mark.parametrize("action", ["send_keys", "clear", "replace"])
@pytest.mark.parametrize("value", [True, 0, -1, float("inf"), float("nan"), "1"])
def test_invalid_wait_is_rejected_before_protocol_io(
    service: ActionProtocolService,
    action: TextAction,
    value: object,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"wait-{action}")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            invoke(
                session,
                session.element("id", "target"),
                action,
                wait_timeout_seconds=value,  # type: ignore[arg-type]
            )
        assert_error(caught.value, InvalidRequestError, "invalid_argument", "not_sent")
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("action", ["send_keys", "clear", "replace"])
@pytest.mark.parametrize(
    ("kind", "plans", "expected"),
    [
        (
            "find",
            [ResponsePlan(payload=elements()), ResponsePlan()],
            ["find", "find", "displayed", "enabled"],
        ),
        (
            "displayed",
            [ResponsePlan(payload={"value": False}), ResponsePlan()],
            ["find", "displayed", "find", "displayed", "enabled"],
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
            ],
        ),
    ],
)
def test_waits_for_missing_hidden_or_disabled_with_shared_half_second_pacing(
    service: ActionProtocolService,
    action: TextAction,
    kind: str,
    plans: list[ResponsePlan],
    expected: list[str],
) -> None:
    service.queue(kind, *plans)
    with connected(service) as connection:
        session = session_for(service, connection, f"wait-state-{action}-{kind}")
        invoke(session, session.element("id", "target"), action)
        assert service.operation_kinds() == [*expected, final_kind(action)]
        repeated = service.of_kind(kind)
        assert repeated[1].received_at - repeated[0].received_at >= 0.45
        session.quit()


@pytest.mark.parametrize("stage", [0, 1, 2])
def test_ambiguity_at_every_chain_level_is_immediate_and_action_free(
    service: ActionProtocolService,
    stage: int,
) -> None:
    values = ["com.example:id/root", "com.example:id/middle", "com.example:id/target"]
    parents: list[str | None] = [None, "root", "middle"]
    for index, (parent, value) in enumerate(zip(parents, values, strict=True)):
        service.matches[(parent, "id", value)] = (
            [f"node-{stage}-a", f"node-{stage}-b"]
            if index == stage
            else [["root", "middle", "target"][index]]
        )
    with connected(service) as connection:
        session = session_for(service, connection, f"ambiguous-{stage}")
        root = session.element("id", "root")
        middle = session.element("id", "middle", parent=root)
        target = session.element("id", "target", parent=middle)
        with pytest.raises(TargetError) as caught:
            session.send_keys(target, "value")
        assert_error(
            caught.value,
            TargetError,
            "target_ambiguous",
            "response_received",
            steps=(),
        )
        assert service.of_kind("send") == []
        session.quit()


@pytest.mark.parametrize("action", ["send_keys", "clear", "replace"])
@pytest.mark.parametrize("stage", ["root", "child", "displayed", "enabled"])
def test_each_pre_action_stale_restarts_the_complete_chain(
    service: ActionProtocolService,
    action: TextAction,
    stage: str,
) -> None:
    service.matches[(None, "id", "com.example:id/form")] = ["form"]
    service.matches[("form", "id", "com.example:id/target")] = ["target"]
    stale = ResponsePlan(status=404, payload=stale_error())
    if stage == "child":
        service.queue("find", ResponsePlan(), stale)
    else:
        service.queue("find" if stage == "root" else stage, stale)
    with connected(service) as connection:
        session = session_for(service, connection, f"stale-{action}-{stage}")
        parent = session.element("id", "form")
        target = session.element("id", "target", parent=parent)
        invoke(session, target, action)
        assert len(service.of_kind("find")) >= 3
        assert len(service.of_kind(final_kind(action))) == 1
        assert service.operation_kinds()[-1] == final_kind(action)
        session.quit()


@pytest.mark.parametrize(
    ("stage", "plan"),
    [
        ("find", ResponsePlan(status=500, payload=w3c_error("find"))),
        ("displayed", ResponsePlan(payload={"value": "true"})),
        ("enabled", ResponsePlan(payload={"value": 1})),
    ],
)
def test_non_stale_wait_errors_fail_immediately_without_final_action(
    service: ActionProtocolService,
    stage: str,
    plan: ResponsePlan,
) -> None:
    service.queue(stage, plan)
    with connected(service) as connection:
        session = session_for(service, connection, f"known-wait-{stage}")
        with pytest.raises(CommandError) as caught:
            session.replace_element_value(session.element("id", "target"), "value")
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=(),
        )
        assert service.of_kind("replace") == []
        session.quit()


@pytest.mark.parametrize("action", ["send_keys", "clear", "replace"])
@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (404, stale_error()),
        (500, w3c_error("final")),
    ],
)
def test_final_stale_and_valid_errors_are_never_replayed(
    service: ActionProtocolService,
    action: TextAction,
    status: int,
    payload: dict[str, object],
) -> None:
    service.queue(
        final_kind(action),
        ResponsePlan(status=status, payload=payload),
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"final-known-{action}-{status}")
        with pytest.raises(CommandError) as caught:
            invoke(session, session.element("id", "target"), action)
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=("target_resolved", "target_displayed", "target_enabled"),
        )
        assert len(service.of_kind(final_kind(action))) == 1
        assert len(service.of_kind("find")) == 1
        assert session.session_info().state == "active"
        session.quit()


def test_replace_non_null_response_is_invalid_and_never_replayed(
    service: ActionProtocolService,
) -> None:
    service.queue("replace", ResponsePlan(payload={"value": "unexpected"}))
    with connected(service) as connection:
        session = session_for(service, connection, "replace-invalid-return")
        with pytest.raises(CommandError) as caught:
            session.replace_element_value(session.element("id", "target"), "value")
        assert_error(
            caught.value,
            CommandError,
            "command_failed",
            "response_received",
            steps=("target_resolved", "target_displayed", "target_enabled"),
        )
        assert len(service.of_kind("replace")) == 1
        session.quit()


@pytest.mark.parametrize(
    ("control", "wait", "error_type", "code"),
    [
        (None, 0.03, TargetError, "condition_timeout"),
        (
            OperationControl(timeout_seconds=0.03),
            1.0,
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
            session.send_keys(
                session.element("id", "missing"),
                "value",
                wait_timeout_seconds=wait,
                control=control,
            )
        assert_error(caught.value, error_type, code, "not_sent", steps=())
        assert len(service.of_kind("find")) == 1
        assert service.of_kind("send") == []
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
            session.clear(
                session.element("id", "target"),
                wait_timeout_seconds=0.04,
            )
        assert_error(
            caught.value,
            TargetError,
            "condition_timeout",
            "response_received",
            steps=(),
        )
        assert service.of_kind("clear") == []
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("phase", ["header", "body"])
def test_condition_deadline_in_flight_is_unknown_and_closes_local_client(
    service: ActionProtocolService,
    phase: str,
) -> None:
    plan = (
        ResponsePlan(header_delay_seconds=0.2)
        if phase == "header"
        else ResponsePlan(body_delay_seconds=0.2)
    )
    service.queue("find", plan)
    with connected(service) as connection:
        session = session_for(service, connection, f"condition-unknown-{phase}")
        with pytest.raises(TargetError) as caught:
            session.replace_element_value(
                session.element("id", "target"),
                "value",
                wait_timeout_seconds=0.05,
            )
        assert_error(
            caught.value,
            TargetError,
            "condition_timeout",
            "response_unknown",
            steps=(),
        )
        assert session.session_info().state == "uncertain"
        assert service.of_kind("replace") == []
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError):
            session.clear(session.element("id", "target"))
        assert service.snapshot() == before


def test_cancellation_wakes_poll_and_wins_at_shared_deadline(
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
            session.clear(
                session.element("id", "missing"),
                control=OperationControl(
                    timeout_seconds=2,
                    cancellation=cancellation,
                ),
            )
        elapsed = time.monotonic() - started
        timer.join(timeout=1)
        assert not timer.is_alive()
        assert elapsed < 0.4
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
            steps=(),
        )
        assert service.of_kind("clear") == []
        session.quit()

        already_cancelled = threading.Event()
        already_cancelled.set()
        precedence = session_for(service, connection, "cancel-precedence")
        before = service.snapshot()
        with pytest.raises(OperationCancelledError) as simultaneous:
            precedence.send_keys(
                precedence.element("id", "target"),
                "value",
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
            steps=(),
        )
        assert service.snapshot() == before
        precedence.quit()


def test_condition_deadline_no_longer_limits_started_final_action(
    service: ActionProtocolService,
) -> None:
    service.queue("send", ResponsePlan(header_delay_seconds=0.35))
    with connected(service) as connection:
        session = session_for(service, connection, "condition-final-separation")
        session.send_keys(
            session.element("id", "target"),
            "value",
            wait_timeout_seconds=0.3,
        )
        assert len(service.of_kind("send")) == 1
        session.quit()


@pytest.mark.parametrize("action", ["send_keys", "clear", "replace"])
@pytest.mark.parametrize("phase", ["disconnect", "header", "body"])
def test_final_unknown_is_never_replayed_and_retains_session_ownership(
    service: ActionProtocolService,
    action: TextAction,
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
    service.queue(final_kind(action), plan)
    with connected(service) as connection:
        session = session_for(service, connection, f"final-unknown-{action}-{phase}")
        with pytest.raises(error_type) as caught:
            invoke(
                session,
                session.element("id", "target"),
                action,
                control=control,
            )
        assert_error(
            caught.value,
            error_type,
            code,
            "response_unknown",
            steps=("target_resolved", "target_displayed", "target_enabled"),
        )
        assert len(service.of_kind(final_kind(action))) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


def test_final_in_flight_cancellation_is_unknown_and_not_replayed(
    service: ActionProtocolService,
) -> None:
    request_started = threading.Event()
    release = threading.Event()
    cancellation = threading.Event()
    service.queue(
        "replace",
        ResponsePlan(
            started=request_started,
            release=release,
            disconnect=True,
        ),
    )
    result: list[BaseException | None] = []
    with connected(service) as connection:
        session = session_for(service, connection, "final-cancel")

        def run() -> None:
            try:
                session.replace_element_value(
                    session.element("id", "target"),
                    "value",
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
        assert request_started.wait(timeout=2)
        cancellation.set()
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert len(result) == 1
        error = result[0]
        assert isinstance(error, OperationCancelledError)
        assert_error(
            error,
            OperationCancelledError,
            "operation_cancelled",
            "response_unknown",
            steps=("target_resolved", "target_displayed", "target_enabled"),
        )
        assert len(service.of_kind("replace")) == 1
        assert session.session_info().state == "uncertain"


@pytest.mark.parametrize("action", ["send_keys", "clear", "replace"])
@pytest.mark.parametrize("initial", [False, True])
def test_raw_guard_wraps_all_waits_and_restores_exact_initial_value(
    service: ActionProtocolService,
    action: TextAction,
    initial: bool,
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
        session = session_for(service, connection, f"raw-{action}-{initial}")
        invoke(
            session,
            session.element("id", raw_value, raw_id=True),
            action,
        )
        expected = ["settings:get"]
        if not initial:
            expected.append("settings:post")
        expected.extend(
            ["find", "find", "find", "displayed", "enabled", final_kind(action)]
        )
        if not initial:
            expected.append("settings:post")
        assert service.operation_kinds() == expected
        assert service.settings["disableIdLocatorAutocompletion"] is initial
        assert len(service.of_kind(final_kind(action))) == 1
        session.quit()


def test_raw_mixed_unresolved_chain_is_rejected_before_any_request(
    service: ActionProtocolService,
) -> None:
    service.create_package = None
    with connected(service) as connection:
        session = create_session(connection, "text-raw-mixed")
        raw = session.element("id", "vendor/odd@id", raw_id=True)
        unresolved = session.element("id", "short", parent=raw)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.send_keys(unresolved, "value")
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
            session.clear(
                session.element("id", raw_value, raw_id=True),
                wait_timeout_seconds=0.03,
            )
        assert_error(
            caught.value,
            TargetError,
            "condition_timeout",
            "not_sent",
            steps=("settings_read", "settings_changed", "settings_restored"),
        )
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert service.of_kind("clear") == []
        assert session.session_info().state == "active"
        session.quit()


def test_raw_primary_final_error_survives_restore_error_without_replay(
    service: ActionProtocolService,
) -> None:
    service.queue("send", ResponsePlan(status=500, payload=w3c_error("send")))
    service.queue(
        "settings:post",
        ResponsePlan(),
        ResponsePlan(status=500, payload=w3c_error("restore")),
    )
    with connected(service) as connection:
        session = session_for(service, connection, "raw-double-error")
        target = session.element("id", "vendor/odd@id", raw_id=True)
        with pytest.raises(CommandError) as caught:
            session.send_keys(target, "value")
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
        assert len(caught.value.cleanup_errors) >= 1
        cleanup = caught.value.cleanup_errors[0]
        assert isinstance(cleanup, CommandError)
        assert cleanup.code == "command_failed"
        assert len(service.of_kind("send")) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


@pytest.mark.parametrize("unknown", [False, True])
def test_raw_success_restore_failure_preserves_action_completed(
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
        with pytest.raises(expected_type) as caught:
            session.replace_element_value(
                session.element("id", "vendor/odd@id", raw_id=True),
                "value",
            )
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
        assert len(service.of_kind("replace")) == 1
        assert session.session_info().state == "uncertain"
        assert service.of_kind("quit") == []


def test_raw_final_unknown_never_attempts_overlapping_restore(
    service: ActionProtocolService,
) -> None:
    service.queue("clear", ResponsePlan(disconnect=True))
    with connected(service) as connection:
        session = session_for(service, connection, "raw-final-unknown")
        with pytest.raises(ExecutionUnknownError) as caught:
            session.clear(session.element("id", "vendor/odd@id", raw_id=True))
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
            steps=(
                "settings_read",
                "settings_changed",
                "target_resolved",
                "target_displayed",
                "target_enabled",
            ),
        )
        assert len(service.of_kind("settings:post")) == 1
        assert len(service.of_kind("clear")) == 1
        assert session.session_info().state == "uncertain"


def test_raw_setting_unknown_never_finds_or_restores(
    service: ActionProtocolService,
) -> None:
    service.queue("settings:get", ResponsePlan(disconnect=True))
    with connected(service) as connection:
        session = session_for(service, connection, "raw-setting-unknown")
        with pytest.raises(ExecutionUnknownError) as caught:
            session.send_keys(
                session.element("id", "vendor/odd@id", raw_id=True),
                "value",
            )
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
            steps=(),
        )
        assert service.of_kind("find") == []
        assert service.of_kind("settings:post") == []
        assert service.of_kind("send") == []
        assert session.session_info().state == "uncertain"


def test_foreign_forged_closed_and_connection_invalid_are_request_free(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        owner = session_for(service, connection, "owner")
        other = session_for(service, connection, "other")
        foreign = owner.element("id", "target")
        for element, code in (
            (foreign, "element_session_mismatch"),
            (object.__new__(Element), "invalid_argument"),
        ):
            before = service.snapshot()
            with pytest.raises(InvalidRequestError) as caught:
                other.replace_element_value(element, "value")
            assert_error(caught.value, InvalidRequestError, code, "not_sent")
            assert service.snapshot() == before
        owner.quit()
        other.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as closed:
            other.clear(other.element("id", "target"))
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
        invalid.send_keys(target, "value")
    assert_error(
        invalid_error.value,
        InvalidSessionStateError,
        "session_invalid",
        "not_sent",
    )
    assert invalid.session_info().state == "uncertain"
    assert service.snapshot() == before


def test_overlapping_text_action_is_immediately_busy_and_sends_no_second_final(
    service: ActionProtocolService,
) -> None:
    started = threading.Event()
    release = threading.Event()
    service.queue("replace", ResponsePlan(started=started, release=release))
    result: list[BaseException | None] = []
    with connected(service) as connection:
        session = session_for(service, connection, "text-busy")
        target = session.element("id", "target")

        def run() -> None:
            try:
                session.replace_element_value(target, "value")
            except BaseException as error:
                result.append(error)
            else:
                result.append(None)

        worker = threading.Thread(target=run)
        worker.start()
        assert started.wait(timeout=2)
        before = len(service.of_kind("replace"))
        with pytest.raises(SessionBusyError) as caught:
            session.clear(target)
        assert_error(caught.value, SessionBusyError, "session_busy", "not_sent")
        assert len(service.of_kind("replace")) == before
        assert service.of_kind("clear") == []
        assert session.session_info().busy is True
        release.set()
        worker.join(timeout=2)
        assert not worker.is_alive()
        assert result == [None]
        assert len(service.of_kind("replace")) == 1
        session.quit()


def test_text_actions_preserve_aif02_aif03_and_aif04_behavior(
    service: ActionProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "regression")
        target = session.element("id", "target")
        session.click(target)
        session.send_keys(target, "value")
        inspection = session.inspect_element(target, attributes=("text",))
        assert inspection.attributes[0].state == "missing"
        assert service.operation_kinds() == [
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
        assert len(service.of_kind("action")) == 1
        assert len(service.of_kind("send")) == 1
        assert session.session_info().state == "active"
        session.quit()
        assert session.session_info().state == "closed"
        assert len(service.of_kind("quit")) == 1
