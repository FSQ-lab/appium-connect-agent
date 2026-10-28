from __future__ import annotations

import math
import sys
import threading
from collections.abc import Callable, Iterator
from functools import partial
from types import SimpleNamespace
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
    _session,
    _session_client,
    _system_actions,
    create_session,
)
from appium_connect_agent.runtime import OperationControl
from tests.automation._action_protocol import (
    ResponsePlan,
    assert_error,
    connected,
    session_for,
    w3c_error,
)
from tests.automation.test_device_actions import DeviceProtocolService

_METHODS = ("activate_app", "terminate_app", "query_app_state")
_SCRIPTS = {
    "activate_app": "activateApp",
    "terminate_app": "terminateApp",
    "query_app_state": "queryAppState",
}
_INVALID_RESULTS: tuple[tuple[str, object], ...] = (
    ("activate_app", False),
    ("activate_app", True),
    ("activate_app", 0),
    ("activate_app", ""),
    ("activate_app", []),
    ("activate_app", {}),
    ("terminate_app", None),
    ("terminate_app", 0),
    ("terminate_app", 1),
    ("terminate_app", 1.0),
    ("terminate_app", "false"),
    ("terminate_app", []),
    ("terminate_app", {}),
    ("query_app_state", None),
    ("query_app_state", False),
    ("query_app_state", True),
    ("query_app_state", 0.0),
    ("query_app_state", 4.0),
    ("query_app_state", "4"),
    ("query_app_state", 2),
    ("query_app_state", -1),
    ("query_app_state", 5),
    ("query_app_state", []),
    ("query_app_state", {}),
)


@pytest.fixture
def service() -> Iterator[DeviceProtocolService]:
    current = DeviceProtocolService()
    with current:
        yield current


def invoke(
    device: Device,
    method: str,
    app_id: Any = "com.example",
    *,
    control: OperationControl | None = None,
) -> object:
    return cast(object, getattr(device, method)(app_id, control=control))


class OperationClock:
    """Instrument operation arithmetic, never process-wide/socket wait clocks."""

    def __init__(self, patch: pytest.MonkeyPatch, budget: float = 1) -> None:
        self.now = -budget
        clock = SimpleNamespace(monotonic=self.monotonic)
        patch.setattr(_session, "time", clock)
        patch.setattr(_system_actions, "time", clock)
        # Arithmetic cases may leave only a microsecond to send. Give the real
        # SDK HTTP exchange a separate, stable ten-second transport allowance;
        # urllib3/socket/threading still use their untouched real clocks.
        patch.setattr(_session_client, "time", SimpleNamespace(monotonic=lambda: -10.0))

    def monotonic(self) -> float:
        return self.now

    def package(self, remaining: float) -> str:
        clock = self

        class TimedPackage(str):
            def __len__(self) -> int:
                clock.now = -remaining
                return super().__len__()

        return TimedPackage("com.example")


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize(
    "app_id", ["a", "_", "Com.Example_2.App", "a" * 254, "a" * 255]
)
def test_explicit_package_exact_single_request(
    service: DeviceProtocolService, method: str, app_id: str
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "app-package")
        expected = {"activate_app": None, "terminate_app": False, "query_app_state": 0}
        result = invoke(session.device, method, app_id)
        assert result == expected[method] and type(result) is type(expected[method])
        assert service.operation_kinds() == [method]
        request = service.of_kind(method)[0]
        assert request.method == "POST"
        assert request.path == "/wd/hub/session/appium-1/execute/sync"
        assert request.body == {
            "script": f"mobile: {_SCRIPTS[method]}",
            "args": [{"appId": app_id}],
        }
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize(
    "app_id",
    [
        None,
        True,
        12,
        [],
        {},
        "",
        "a" * 256,
        " com.example",
        "com.example\n",
        "com. example",
        "com\0example",
        "应用",
        "com.é",
        "\ud800",
        ".com",
        "com.",
        "com..example",
        "1com.app",
        "com.1app",
        "com-app",
        "a/b",
        "com.example/.Main",
        "https://example.app",
    ],
)
def test_invalid_package_precedes_busy_and_cancel(
    service: DeviceProtocolService, method: str, app_id: Any
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "app-invalid")
        cancel = threading.Event()
        cancel.set()
        before = service.snapshot()
        session._operation_gate.acquire()
        try:
            with pytest.raises(InvalidRequestError) as caught:
                invoke(
                    session.device,
                    method,
                    app_id,
                    control=OperationControl(cancellation=cancel),
                )
        finally:
            session._operation_gate.release()
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
def test_required_package_and_trusted_binding(
    service: DeviceProtocolService, method: str
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "app-binding")
        other = session_for(service, connection, "app-other-binding")
        before = service.snapshot()
        with pytest.raises(TypeError):
            getattr(session.device, method)()
        forged = object.__new__(Device)
        for receiver in (object(), session, forged):
            with pytest.raises(InvalidRequestError):
                getattr(Device, method)(receiver, "com.example")
        object.__setattr__(forged, "_owner", session)
        object.__setattr__(forged, "_marker", session.device._marker)
        with pytest.raises(InvalidRequestError):
            invoke(forged, method)
        for owner in (other, object.__new__(Session), object()):
            object.__setattr__(session.device, "_owner", owner)
            try:
                with pytest.raises(InvalidRequestError):
                    invoke(session.device, method)
            finally:
                object.__setattr__(session.device, "_owner", session)
        with pytest.raises(InvalidRequestError):
            invoke(session.device, method, control=cast(Any, object()))
        assert service.snapshot() == before
        session.quit()
        other.quit()


@pytest.mark.parametrize(
    ("method", "value"),
    [("activate_app", None)]
    + [("terminate_app", value) for value in (True, False)]
    + [("query_app_state", value) for value in (0, 1, 3, 4)],
)
def test_strict_legal_scalar_results(
    service: DeviceProtocolService,
    method: str,
    value: object,
) -> None:
    service.queue(method, ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "app-results")
        result = invoke(session.device, method)
        assert type(result) is type(value) and result == value
        assert service.operation_kinds() == [method]
        session.quit()


@pytest.mark.parametrize(("method", "value"), _INVALID_RESULTS)
def test_bad_result_is_known_failure_and_session_stays_usable(
    service: DeviceProtocolService, method: str, value: object
) -> None:
    service.queue(method, ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "app-bad-result")
        with pytest.raises(CommandError) as caught:
            invoke(session.device, method)
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert caught.value.__cause__ is not None
        assert service.operation_kinds() == [method]
        assert session.session_info().state == "active"
        session.device.back()
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize(
    "message", ["not installed", "Permission denied", "still running after timeout"]
)
def test_official_errors_are_not_false_zero_or_operation_timeout(
    service: DeviceProtocolService, method: str, message: str
) -> None:
    service.queue(method, ResponsePlan(status=500, payload=w3c_error(message)))
    with connected(service) as connection:
        session = session_for(service, connection, "app-known-error")
        with pytest.raises(CommandError) as caught:
            invoke(session.device, method)
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert caught.value.__cause__ is not None
        assert service.operation_kinds() == [method]
        invoke(session.device, method)
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    "remaining",
    [
        math.nextafter(0.001, math.inf),
        0.0015,
        math.nextafter(0.099, -math.inf),
        0.099,
        math.nextafter(0.099, math.inf),
        math.nextafter(0.1, -math.inf),
        0.1,
        math.nextafter(0.1, math.inf),
        math.nextafter(0.5, -math.inf),
        0.5,
        math.nextafter(0.5, math.inf),
        1.0,
        sys.float_info.max,
    ],
)
def test_terminate_maximum_positive_integer_strictly_inside_sampled_budget(
    service: DeviceProtocolService, monkeypatch: pytest.MonkeyPatch, remaining: float
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "app-wait-boundary")
        with monkeypatch.context() as patch:
            budget = max(1.0, remaining)
            clock = OperationClock(patch, budget)
            assert (
                session.device.terminate_app(
                    clock.package(remaining),
                    control=OperationControl(timeout_seconds=budget),
                )
                is False
            )
        payload = service.of_kind("terminate_app")[0].body
        assert payload is not None
        assert payload["script"] == "mobile: terminateApp"
        options = payload["args"][0]
        assert set(options) == {"appId", "timeout"}
        timeout = options["timeout"]
        assert type(timeout) is int and 1 <= timeout <= 500
        assert timeout / 1000 < remaining
        assert timeout == 500 or (timeout + 1) / 1000 >= remaining
        assert service.operation_kinds() == ["terminate_app"]
        session.quit()


@pytest.mark.parametrize(
    "remaining", [math.nextafter(0.001, -math.inf), 0.001, 0.0005, 5e-324]
)
@pytest.mark.parametrize("cancelled", [False, True])
def test_insufficient_positive_wait_rejects_without_send_and_cancel_wins(
    service: DeviceProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    remaining: float,
    cancelled: bool,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "app-no-positive-wait")
        cancel = threading.Event()
        if cancelled:
            cancel.set()
        before = service.snapshot()
        error_type = OperationCancelledError if cancelled else OperationTimeoutError
        code = "operation_cancelled" if cancelled else "operation_timeout"
        with monkeypatch.context() as patch:
            clock = OperationClock(patch)
            with pytest.raises(error_type) as caught:
                session.device.terminate_app(
                    clock.package(remaining),
                    control=OperationControl(timeout_seconds=1, cancellation=cancel),
                )
        assert_error(caught.value, error_type, code, "not_sent", steps=())
        assert service.snapshot() == before
        assert session.session_info().state == "active"
        session.device.back()
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize("cancelled", [False, True])
def test_expired_original_budget_never_restarts(
    service: DeviceProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    cancelled: bool,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "app-original-deadline")
        cancel = threading.Event()
        if cancelled:
            cancel.set()
        before = service.snapshot()
        error_type = OperationCancelledError if cancelled else OperationTimeoutError
        code = "operation_cancelled" if cancelled else "operation_timeout"
        with monkeypatch.context() as patch:
            clock = OperationClock(patch)
            with pytest.raises(error_type) as caught:
                invoke(
                    session.device,
                    method,
                    clock.package(-0.25),
                    control=OperationControl(timeout_seconds=1, cancellation=cancel),
                )
        assert_error(caught.value, error_type, code, "not_sent", steps=())
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize("late", ["cancel", "deadline"])
@pytest.mark.parametrize("result_kind", ["valid", "invalid", "official"])
def test_validation_is_inside_final_gate_and_late_control_cannot_replace_result(
    service: DeviceProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    late: str,
    result_kind: str,
) -> None:
    cancel = threading.Event()
    original = _session._SessionOperationGateway.final_action
    outcomes: list[str] = []
    with connected(service) as connection:
        session = session_for(service, connection, "app-final-gate")
        with monkeypatch.context() as patch:
            clock = OperationClock(patch)

            def observed(
                gateway: _session._SessionOperationGateway, action: Callable[[], Any]
            ) -> Any:
                def finish() -> Any:
                    try:
                        result = action()
                    except Exception:
                        outcomes.append("invalid")
                        raise
                    else:
                        outcomes.append("valid")
                        return result
                    finally:
                        assert session.session_info().busy
                        with pytest.raises(SessionBusyError):
                            session.device.back()
                        if late == "cancel":
                            cancel.set()
                        else:
                            clock.now = 1.0

                return original(gateway, finish)

            patch.setattr(_session._SessionOperationGateway, "final_action", observed)
            if result_kind != "valid":
                plan = (
                    ResponsePlan(payload={"value": "invalid"})
                    if result_kind == "invalid"
                    else ResponsePlan(status=500, payload=w3c_error())
                )
                service.queue(method, plan)
                with pytest.raises(CommandError) as caught:
                    invoke(
                        session.device,
                        method,
                        control=OperationControl(
                            timeout_seconds=1, cancellation=cancel
                        ),
                    )
                assert_error(
                    caught.value,
                    CommandError,
                    "command_failed",
                    "response_received",
                    steps=(),
                )
            else:
                result = invoke(
                    session.device,
                    method,
                    control=OperationControl(timeout_seconds=1, cancellation=cancel),
                )
                expected = {
                    "activate_app": None,
                    "terminate_app": False,
                    "query_app_state": 0,
                }
                assert type(result) is type(expected[method])
                assert result == expected[method]
        assert outcomes == ["valid" if result_kind == "valid" else "invalid"]
        assert session.session_info().state == "active"
        assert service.operation_kinds() == [method]
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize("phase", ["disconnect", "header", "body", "cancel"])
def test_unknown_closes_client_retains_device_port_and_never_replays(
    service: DeviceProtocolService, method: str, phase: str
) -> None:
    started, release, cancel = threading.Event(), threading.Event(), threading.Event()
    service.queue(
        method,
        ResponsePlan(
            disconnect=phase in {"disconnect", "cancel"},
            started=started,
            release=release if phase == "cancel" else None,
            header_delay_seconds=0.2 if phase == "header" else 0,
            body_delay_seconds=0.2 if phase == "body" else 0,
        ),
    )
    control = None
    if phase == "cancel":
        control = OperationControl(timeout_seconds=2, cancellation=cancel)
    elif phase != "disconnect":
        control = OperationControl(timeout_seconds=0.05)
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "app-unknown")

        def run() -> None:
            try:
                invoke(session.device, method, control=control)
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
        assert not worker.is_alive() and len(failures) == 1
        error_type: type[AutomationError]
        if phase == "disconnect":
            error_type, code = ExecutionUnknownError, "execution_unknown"
        elif phase == "cancel":
            error_type, code = OperationCancelledError, "operation_cancelled"
        else:
            error_type, code = OperationTimeoutError, "operation_timeout"
        assert isinstance(failures[0], AutomationError)
        assert_error(failures[0], error_type, code, "response_unknown", steps=())
        assert session.session_info().state == "uncertain"
        assert session._client._closed
        with pytest.raises(ResourceStateError) as occupied:
            create_session(connection, "app-unknown")
        assert occupied.value.code == "device_busy"
        other = session_for(service, connection, "app-unknown-other")
        creates = service.of_kind("create")
        ports = [
            request.body["capabilities"]["alwaysMatch"]["appium:systemPort"]
            for request in creates
            if request.body is not None
        ]
        assert ports == [8200, 8201]
        before = service.snapshot()
        attempts: list[Callable[[], object]] = [
            partial(invoke, session.device, name) for name in _METHODS
        ]
        attempts.append(session.quit)
        for attempt in attempts:
            with pytest.raises(InvalidSessionStateError):
                attempt()
        assert service.snapshot() == before
        assert service.operation_kinds() == [method]
        assert service.of_kind("quit") == []
        other.quit()


@pytest.mark.parametrize(
    "holder", [*_METHODS, "element", "device", "observation", "quit"]
)
def test_bidirectional_gate_across_all_operation_channels(
    service: DeviceProtocolService, holder: str
) -> None:
    started, release = threading.Event(), threading.Event()
    kind = {
        "element": "action",
        "device": "back",
        "observation": "attribute",
        "quit": "quit",
    }.get(holder, holder)
    service.queue(kind, ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "app-shared-gate")
        other = session_for(service, connection, "app-independent-gate")
        calls: dict[str, Callable[[], object]] = {
            name: partial(invoke, session.device, name) for name in _METHODS
        }
        calls.update(
            element=session.element("id", "target").click,
            device=session.device.back,
            observation=lambda: session.element("id", "target").inspect(
                attributes=("text",)
            ),
            quit=session.quit,
        )

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
            attempts = (
                list(calls.values())
                if holder in _METHODS
                else [calls[n] for n in _METHODS]
            )
            if holder in _METHODS:
                attempts.append(session.observe_tree)
            for attempt in attempts:
                with pytest.raises(SessionBusyError) as caught:
                    attempt()
                assert_error(
                    caught.value, SessionBusyError, "session_busy", "not_sent", steps=()
                )
            assert service.snapshot() == before
            assert other.device.query_app_state("missing.app") == 0
        finally:
            release.set()
            worker.join(timeout=3)
        assert not worker.is_alive() and failures == []
        other.quit()
        if holder != "quit":
            session.quit()


def test_target_and_short_ids_stay_bound_after_explicit_other_app_activation(
    service: DeviceProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "app-target-stability")
        old = session.element("id", "button")
        before = session.session_info()
        old.click()
        session.device.activate_app("org.other")
        service.matches[(None, "id", "com.example:id/button")] = ["a-new"]
        old.click()
        session.element("id", "button").click()
        service.matches[(None, "id", "org.other:id/button")] = ["b"]
        session.element("id", "button", package="org.other").click()
        raw = session.element("id", "vendor/raw@button", raw_id=True)
        raw.click()
        service.matches[(None, "id", "vendor/raw@button")] = ["raw-new"]
        raw.click()
        after = session.session_info()
        assert after.target_app_id == before.target_app_id == "com.example"
        assert after.appium_session_id == before.appium_session_id
        finds = service.of_kind("find")
        assert [r.body["value"] for r in finds if r.body is not None] == [
            "com.example:id/button",
            "com.example:id/button",
            "com.example:id/button",
            "org.other:id/button",
            "vendor/raw@button",
            "vendor/raw@button",
        ]
        actions = [r.body for r in service.of_kind("action")]
        assert actions == [
            {"script": "mobile: clickGesture", "args": [{"elementId": eid}]}
            for eid in ("target", "a-new", "a-new", "b", "target", "raw-new")
        ]
        assert [r.body for r in service.of_kind("settings:post")] == [
            {"settings": {"disableIdLocatorAutocompletion": value}}
            for value in (True, False, True, False)
        ]
        assert service.settings["disableIdLocatorAutocompletion"] is False
        assert len(service.of_kind("activate_app")) == 1
        session.quit()


def test_sessions_route_independently_and_only_quit_releases_resources(
    service: DeviceProtocolService,
) -> None:
    with connected(service) as connection:
        first = session_for(service, connection, "app-first")
        second = session_for(service, connection, "app-second")
        first_info, second_info = first.session_info(), second.session_info()
        assert first.device.query_app_state("missing.app") == 0
        assert second.device.terminate_app("com.example") is False
        first.device.activate_app("org.other")
        assert first.device.terminate_app("com.example") is False
        assert second.device.query_app_state("missing.app") == 0
        for session, original in ((first, first_info), (second, second_info)):
            assert session.session_info() == original
            with pytest.raises(ResourceStateError):
                create_session(connection, original.device_id)
        routes = [
            r.path for r in service.snapshot() if r.path.endswith("/execute/sync")
        ]
        assert routes == [
            f"/wd/hub/session/appium-{sid}/execute/sync" for sid in (1, 2, 1, 1, 2)
        ]
        first.quit()
        replacement = session_for(service, connection, "app-first")
        create = service.of_kind("create")[-1]
        assert create.body is not None
        assert create.body["capabilities"]["alwaysMatch"]["appium:systemPort"] == 8200
        replacement.quit()
        second.quit()


def test_terminate_true_then_explicit_query_running_does_not_repeat_termination(
    service: DeviceProtocolService,
) -> None:
    service.queue("terminate_app", ResponsePlan(payload={"value": True}))
    service.queue("query_app_state", ResponsePlan(payload={"value": 4}))
    with connected(service) as connection:
        session = session_for(service, connection, "app-relaunched")
        assert session.device.terminate_app("com.example") is True
        assert service.operation_kinds() == ["terminate_app"]
        assert session.device.query_app_state("com.example") == 4
        assert service.operation_kinds() == ["terminate_app", "query_app_state"]
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
def test_closed_and_exited_connection_reject_before_send(
    service: DeviceProtocolService, method: str
) -> None:
    with connected(service) as connection:
        closed = session_for(service, connection, "app-closed")
        closed.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as caught:
            invoke(closed.device, method)
        assert_error(
            caught.value,
            InvalidSessionStateError,
            "session_closed",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        active = session_for(service, connection, "app-exited")
    before = service.snapshot()
    with pytest.raises(InvalidSessionStateError) as exited:
        invoke(active.device, method)
    assert_error(
        exited.value, InvalidSessionStateError, "session_invalid", "not_sent", steps=()
    )
    assert active.session_info().state == "uncertain"
    assert service.snapshot() == before


def test_cancellation_arriving_at_insufficient_wait_sample_has_priority(
    service: DeviceProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "app-sample-cancel")
        cancel = threading.Event()
        before = service.snapshot()
        with monkeypatch.context() as patch:
            clock = OperationClock(patch)

            def sample() -> float:
                cancel.set()
                return clock.now

            patch.setattr(_system_actions, "time", SimpleNamespace(monotonic=sample))
            with pytest.raises(OperationCancelledError) as caught:
                session.device.terminate_app(
                    clock.package(0.001),
                    control=OperationControl(timeout_seconds=1, cancellation=cancel),
                )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        assert session.session_info().state == "active"
        session.quit()
