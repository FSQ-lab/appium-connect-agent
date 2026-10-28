from __future__ import annotations

import math
import os
import sys
import threading
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
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

_METHODS = ("install_app", "remove_app")
_SCRIPTS = {"install_app": "installApp", "remove_app": "removeApp"}
_INVALID_RESULTS: tuple[tuple[str, object], ...] = (
    ("install_app", False),
    ("install_app", True),
    ("install_app", 0),
    ("install_app", ""),
    ("install_app", []),
    ("install_app", {}),
    ("remove_app", None),
    ("remove_app", 0),
    ("remove_app", 1),
    ("remove_app", 1.0),
    ("remove_app", "false"),
    ("remove_app", []),
    ("remove_app", {}),
)


@pytest.fixture
def service() -> Iterator[DeviceProtocolService]:
    current = DeviceProtocolService()
    with current:
        yield current


@pytest.fixture
def apk(tmp_path: Path) -> Path:
    path = tmp_path / "sample.apk"
    path.write_bytes(b"not parsed by Automation")
    return path


def invoke(
    device: Device,
    method: str,
    argument: Any,
    *,
    control: OperationControl | None = None,
    allow_test_packages: bool = False,
) -> object:
    operation = getattr(device, method)
    if method == "install_app":
        return cast(
            object,
            operation(
                argument,
                allow_test_packages=allow_test_packages,
                control=control,
            ),
        )
    return cast(object, operation(argument, control=control))


class OperationClock:
    """Instrument operation arithmetic without changing transport wait clocks."""

    def __init__(self, patch: pytest.MonkeyPatch, budget: float = 1) -> None:
        self.now = -budget
        clock = SimpleNamespace(monotonic=self.monotonic)
        patch.setattr(_session, "time", clock)
        patch.setattr(_system_actions, "time", clock)
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

    def delay_path_stat(
        self, patch: pytest.MonkeyPatch, path: Path, remaining: float
    ) -> None:
        original = Path.stat
        clock = self

        def timed_stat(
            current: Path, *, follow_symlinks: bool = True
        ) -> os.stat_result:
            if current == path:
                clock.now = -remaining
            return original(current, follow_symlinks=follow_symlinks)

        patch.setattr(Path, "stat", timed_stat)


def timed_argument(
    method: str,
    apk: Path,
    clock: OperationClock,
    patch: pytest.MonkeyPatch,
    remaining: float,
) -> object:
    if method == "remove_app":
        return clock.package(remaining)
    clock.delay_path_stat(patch, apk, remaining)
    return apk


@pytest.mark.parametrize("allow_test_packages", [False, True])
def test_exact_routes_payloads_defaults_and_single_requests(
    service: DeviceProtocolService,
    apk: Path,
    allow_test_packages: bool,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "management-exact")
        before = session.session_info()
        assert (
            invoke(
                session.device,
                "install_app",
                apk,
                allow_test_packages=allow_test_packages,
            )
            is None
        )
        assert session.device.remove_app("Com.Example_2.App") is False
        assert service.operation_kinds() == ["install_app", "remove_app"]
        install, remove = (
            service.of_kind("install_app")[0],
            service.of_kind("remove_app")[0],
        )
        assert install.method == remove.method == "POST"
        assert install.path == remove.path == "/wd/hub/session/appium-1/execute/sync"
        assert install.body == {
            "script": "mobile: installApp",
            "args": [
                {
                    "appPath": str(apk),
                    "replace": True,
                    "allowTestPackages": allow_test_packages,
                }
            ],
        }
        assert remove.body == {
            "script": "mobile: removeApp",
            "args": [{"appId": "Com.Example_2.App", "keepData": False}],
        }
        assert session.session_info() == before
        with pytest.raises(ResourceStateError):
            create_session(connection, before.device_id)
        session.quit()


@pytest.mark.parametrize("value", [None, "/tmp/sample.apk", True, 1, 1.0, object()])
def test_required_actual_path_precedes_busy_and_cancel(
    service: DeviceProtocolService, value: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "management-path-type")
        cancellation = threading.Event()
        cancellation.set()
        before = service.snapshot()
        session._operation_gate.acquire()
        try:
            with pytest.raises(InvalidRequestError) as caught:
                session.device.install_app(
                    cast(Any, value),
                    control=OperationControl(cancellation=cancellation),
                )
        finally:
            session._operation_gate.release()
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


def test_invalid_path_shapes_are_rejected_before_gate(
    service: DeviceProtocolService, tmp_path: Path
) -> None:
    relative = Path("relative.apk")
    apks = tmp_path / "bundle.apks"
    uppercase = tmp_path / "UPPER.APK"
    directory = tmp_path / "directory.apk"
    missing = tmp_path / "missing.apk"
    unreadable = tmp_path / "unreadable.apk"
    for path in (apks, uppercase, unreadable):
        path.write_bytes(b"content")
    directory.mkdir()
    unreadable.chmod(0)
    cancellation = threading.Event()
    cancellation.set()
    try:
        with connected(service) as connection:
            session = session_for(service, connection, "management-path-shape")
            before_requests, before_info = service.snapshot(), session.session_info()
            session._operation_gate.acquire()
            try:
                for path in (relative, apks, uppercase, directory, missing, unreadable):
                    with pytest.raises(InvalidRequestError) as caught:
                        session.device.install_app(
                            path, control=OperationControl(cancellation=cancellation)
                        )
                    assert_error(
                        caught.value,
                        InvalidRequestError,
                        "invalid_argument",
                        "not_sent",
                        steps=(),
                    )
            finally:
                session._operation_gate.release()
            assert service.snapshot() == before_requests
            assert session.session_info() == before_info
            session.quit()
    finally:
        unreadable.chmod(0o600)


@pytest.mark.parametrize("value", [None, 0, 1, 1.0, "false", [], {}])
def test_allow_test_packages_is_actual_bool_and_precedes_busy(
    service: DeviceProtocolService,
    apk: Path,
    value: object,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "management-bool")
        before = service.snapshot()
        session._operation_gate.acquire()
        try:
            with pytest.raises(InvalidRequestError) as caught:
                session.device.install_app(apk, allow_test_packages=cast(Any, value))
        finally:
            session._operation_gate.release()
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


def test_unknown_replace_keyword_is_rejected_without_send(
    service: DeviceProtocolService, apk: Path
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "management-unknown-keyword")
        before_requests, before_info = service.snapshot(), session.session_info()
        install_app = cast(Callable[..., None], session.device.install_app)
        with pytest.raises(TypeError):
            install_app(apk, replace=False)
        assert service.snapshot() == before_requests
        assert session.session_info() == before_info
        session.quit()


@pytest.mark.parametrize(
    "app_id", ["a", "_", "Com.Example_2.App", "a" * 254, "a" * 255]
)
def test_remove_reuses_exact_package_grammar(
    service: DeviceProtocolService, app_id: str
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "management-package")
        assert session.device.remove_app(app_id) is False
        assert service.of_kind("remove_app")[0].body == {
            "script": "mobile: removeApp",
            "args": [{"appId": app_id, "keepData": False}],
        }
        assert service.operation_kinds() == ["remove_app"]
        session.quit()


@pytest.mark.parametrize(
    "app_id",
    [
        None,
        True,
        12,
        "",
        "a" * 256,
        " com.example",
        "com.example\n",
        "com..example",
        "1com.app",
        "com.1app",
        "com-app",
        "com.example/.Main",
        "https://example.app",
        "应用",
        "\ud800",
    ],
)
def test_invalid_package_precedes_busy_and_cancel(
    service: DeviceProtocolService, app_id: Any
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "management-invalid-package")
        cancellation = threading.Event()
        cancellation.set()
        before = service.snapshot()
        session._operation_gate.acquire()
        try:
            with pytest.raises(InvalidRequestError) as caught:
                session.device.remove_app(
                    app_id, control=OperationControl(cancellation=cancellation)
                )
        finally:
            session._operation_gate.release()
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
def test_required_arguments_control_and_trusted_binding(
    service: DeviceProtocolService, apk: Path, method: str
) -> None:
    argument: object = apk if method == "install_app" else "com.example"
    with connected(service) as connection:
        session = session_for(service, connection, "management-binding")
        other = session_for(service, connection, "management-binding-other")
        before = service.snapshot()
        with pytest.raises(TypeError):
            getattr(session.device, method)()
        forged = object.__new__(Device)
        for receiver in (object(), session, forged):
            with pytest.raises(InvalidRequestError):
                getattr(Device, method)(receiver, argument)
        object.__setattr__(forged, "_owner", session)
        object.__setattr__(forged, "_marker", session.device._marker)
        with pytest.raises(InvalidRequestError):
            invoke(forged, method, argument)
        for owner in (other, object.__new__(Session), object()):
            object.__setattr__(session.device, "_owner", owner)
            try:
                with pytest.raises(InvalidRequestError):
                    invoke(session.device, method, argument)
            finally:
                object.__setattr__(session.device, "_owner", session)
        with pytest.raises(InvalidRequestError):
            invoke(
                session.device,
                method,
                argument,
                control=cast(Any, object()),
            )
        assert service.snapshot() == before
        session.quit()
        other.quit()


@pytest.mark.parametrize(
    ("method", "cap"), [("install_app", 300_000), ("remove_app", 100_000)]
)
@pytest.mark.parametrize(
    "position", ["one_ms", "fractional", "below_cap", "at_cap", "above_cap", "huge"]
)
def test_maximum_timeout_is_strictly_inside_sampled_budget(
    service: DeviceProtocolService,
    apk: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    cap: int,
    position: str,
) -> None:
    cap_seconds = cap / 1000
    remaining = {
        "one_ms": math.nextafter(0.001, math.inf),
        "fractional": 0.0015,
        "below_cap": math.nextafter(cap_seconds, -math.inf),
        "at_cap": cap_seconds,
        "above_cap": math.nextafter(cap_seconds, math.inf),
        "huge": sys.float_info.max,
    }[position]
    with connected(service) as connection:
        session = session_for(service, connection, "management-timeout-boundary")
        with monkeypatch.context() as patch:
            budget = max(1.0, remaining)
            clock = OperationClock(patch, budget)
            argument = timed_argument(method, apk, clock, patch, remaining)
            result = invoke(
                session.device,
                method,
                argument,
                control=OperationControl(timeout_seconds=budget),
            )
        expected: object = None if method == "install_app" else False
        assert type(result) is type(expected) and result == expected
        payload = service.of_kind(method)[0].body
        assert payload is not None
        assert payload["script"] == f"mobile: {_SCRIPTS[method]}"
        options = payload["args"][0]
        timeout = options["timeout"]
        assert type(timeout) is int and 1 <= timeout <= cap
        assert timeout / 1000 < remaining
        assert timeout == cap or (timeout + 1) / 1000 >= remaining
        assert service.operation_kinds() == [method]
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize(
    "remaining", [math.nextafter(0.001, -math.inf), 0.001, 0.0005, 5e-324]
)
@pytest.mark.parametrize("cancelled", [False, True])
def test_insufficient_timeout_rejects_without_send_and_cancel_wins(
    service: DeviceProtocolService,
    apk: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    remaining: float,
    cancelled: bool,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "management-insufficient")
        cancellation = threading.Event()
        if cancelled:
            cancellation.set()
        before = service.snapshot()
        error_type = OperationCancelledError if cancelled else OperationTimeoutError
        code = "operation_cancelled" if cancelled else "operation_timeout"
        with monkeypatch.context() as patch:
            clock = OperationClock(patch)
            argument = timed_argument(method, apk, clock, patch, remaining)
            with pytest.raises(error_type) as caught:
                invoke(
                    session.device,
                    method,
                    argument,
                    control=OperationControl(
                        timeout_seconds=1, cancellation=cancellation
                    ),
                )
        assert_error(caught.value, error_type, code, "not_sent", steps=())
        assert service.snapshot() == before
        assert session.session_info().state == "active"
        session.device.back()
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
def test_cancellation_arriving_at_timeout_sample_has_priority(
    service: DeviceProtocolService,
    apk: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "management-sample-cancel")
        cancellation = threading.Event()
        before = service.snapshot()
        with monkeypatch.context() as patch:
            clock = OperationClock(patch)
            argument = timed_argument(method, apk, clock, patch, 0.001)

            def sample() -> float:
                cancellation.set()
                return clock.now

            patch.setattr(_system_actions, "time", SimpleNamespace(monotonic=sample))
            with pytest.raises(OperationCancelledError) as caught:
                invoke(
                    session.device,
                    method,
                    argument,
                    control=OperationControl(
                        timeout_seconds=1, cancellation=cancellation
                    ),
                )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize(("method", "value"), _INVALID_RESULTS)
def test_bad_result_is_known_failure_without_completion_or_replay(
    service: DeviceProtocolService,
    apk: Path,
    method: str,
    value: object,
) -> None:
    service.queue(method, ResponsePlan(payload={"value": value}))
    argument: object = apk if method == "install_app" else "com.example"
    with connected(service) as connection:
        session = session_for(service, connection, "management-bad-result")
        with pytest.raises(CommandError) as caught:
            invoke(session.device, method, argument)
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert caught.value.__cause__ is not None
        assert service.operation_kinds() == [method]
        assert session.session_info().state == "active"
        session.device.back()
        assert service.operation_kinds() == [method, "back"]
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize("message", ["not installed", "Permission denied", "failed"])
def test_official_error_is_known_and_not_message_classified_or_replayed(
    service: DeviceProtocolService, apk: Path, method: str, message: str
) -> None:
    service.queue(method, ResponsePlan(status=500, payload=w3c_error(message)))
    argument: object = apk if method == "install_app" else "com.example"
    with connected(service) as connection:
        session = session_for(service, connection, "management-known-error")
        with pytest.raises(CommandError) as caught:
            invoke(session.device, method, argument)
        assert_error(
            caught.value, CommandError, "command_failed", "response_received", steps=()
        )
        assert caught.value.__cause__ is not None
        assert service.operation_kinds() == [method]
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize("late", ["cancel", "deadline"])
def test_result_validation_holds_gate_and_valid_final_success_wins(
    service: DeviceProtocolService,
    apk: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    late: str,
) -> None:
    cancellation = threading.Event()
    original = _session._SessionOperationGateway.final_action
    outcomes: list[str] = []
    argument: object = apk if method == "install_app" else "com.example"
    with connected(service) as connection:
        session = session_for(service, connection, "management-final-success")
        with monkeypatch.context() as patch:
            clock = OperationClock(patch)

            def observed(
                gateway: _session._SessionOperationGateway, action: Callable[[], Any]
            ) -> Any:
                def finish() -> Any:
                    result = action()
                    outcomes.append("valid")
                    assert session.session_info().busy
                    with pytest.raises(SessionBusyError):
                        session.device.back()
                    if late == "cancel":
                        cancellation.set()
                    else:
                        clock.now = 1.0
                    return result

                return original(gateway, finish)

            patch.setattr(_session._SessionOperationGateway, "final_action", observed)
            result = invoke(
                session.device,
                method,
                argument,
                control=OperationControl(timeout_seconds=1, cancellation=cancellation),
            )
        expected: object = None if method == "install_app" else False
        assert type(result) is type(expected) and result == expected
        assert outcomes == ["valid"]
        assert session.session_info().state == "active"
        assert service.operation_kinds() == [method]
        session.quit()


@pytest.mark.parametrize("method", _METHODS)
@pytest.mark.parametrize("phase", ["disconnect", "header", "body", "cancel"])
def test_unknown_closes_client_retains_resources_and_never_replays_or_restores(
    service: DeviceProtocolService,
    apk: Path,
    method: str,
    phase: str,
) -> None:
    started, release, cancellation = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
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
        control = OperationControl(timeout_seconds=2, cancellation=cancellation)
    elif phase != "disconnect":
        control = OperationControl(timeout_seconds=0.05)
    argument: object = apk if method == "install_app" else "com.example"
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "management-unknown")

        def run() -> None:
            try:
                invoke(session.device, method, argument, control=control)
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            if phase == "cancel":
                cancellation.set()
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
            create_session(connection, "management-unknown")
        assert occupied.value.code == "device_busy"
        other = session_for(service, connection, "management-unknown-other")
        creates = service.of_kind("create")
        ports = [
            request.body["capabilities"]["alwaysMatch"]["appium:systemPort"]
            for request in creates
            if request.body is not None
        ]
        assert ports == [8200, 8201]
        before = service.snapshot()
        attempts: tuple[Callable[[], object], ...] = (
            partial(invoke, session.device, "install_app", apk),
            partial(invoke, session.device, "remove_app", "com.example"),
            session.quit,
        )
        for attempt in attempts:
            with pytest.raises(InvalidSessionStateError):
                attempt()
        assert service.snapshot() == before
        assert service.operation_kinds() == [method]
        assert service.of_kind("settings:get") == []
        assert service.of_kind("settings:post") == []
        assert service.of_kind("quit") == []
        other.quit()


@pytest.mark.parametrize(
    "holder", ["install_app", "remove_app", "element", "device", "observation", "quit"]
)
def test_bidirectional_shared_gate_and_other_session_independence(
    service: DeviceProtocolService, apk: Path, holder: str
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
        session = session_for(service, connection, "management-shared-gate")
        other = session_for(service, connection, "management-independent-gate")
        calls: dict[str, Callable[[], object]] = {
            "install_app": partial(invoke, session.device, "install_app", apk),
            "remove_app": partial(invoke, session.device, "remove_app", "com.example"),
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
            attempts = (
                list(calls.values())
                if holder in _METHODS
                else [calls[name] for name in _METHODS]
            )
            if holder in _METHODS:
                attempts.append(session.observe_tree)
            for attempt in attempts:
                with pytest.raises(SessionBusyError) as caught:
                    attempt()
                assert_error(
                    caught.value,
                    SessionBusyError,
                    "session_busy",
                    "not_sent",
                    steps=(),
                )
            assert service.snapshot() == before
            assert other.device.remove_app("missing.app") is False
        finally:
            release.set()
            worker.join(timeout=3)
        assert not worker.is_alive() and failures == []
        other.quit()
        if holder != "quit":
            session.quit()


def test_remove_target_known_followup_keeps_identity_ownership_and_no_recovery(
    service: DeviceProtocolService,
) -> None:
    service.queue("remove_app", ResponsePlan(payload={"value": True}))
    service.queue("action", ResponsePlan(status=500, payload=w3c_error()))
    with connected(service) as connection:
        session = session_for(service, connection, "management-target")
        before = session.session_info()
        assert before.target_app_id == "com.example"
        assert session.device.remove_app("com.example") is True
        with pytest.raises(CommandError) as caught:
            session.element("id", "target").click()
        assert_error(caught.value, CommandError, "command_failed", "response_received")
        assert session.session_info() == before
        with pytest.raises(ResourceStateError):
            create_session(connection, before.device_id)
        assert service.operation_kinds() == [
            "remove_app",
            "find",
            "displayed",
            "enabled",
            "action",
        ]
        routes = [
            request.path
            for request in service.snapshot()
            if request.path.endswith("/execute/sync")
        ]
        assert routes == [
            f"/wd/hub/session/appium-{session_id}/execute/sync" for session_id in (1, 1)
        ]
        assert len(service.of_kind("create")) == 1
        assert service.of_kind("settings:get") == []
        assert service.of_kind("settings:post") == []
        assert service.of_kind("quit") == []
        session.quit()


def test_two_sessions_route_independently_and_management_never_releases_resources(
    service: DeviceProtocolService, apk: Path
) -> None:
    with connected(service) as connection:
        first = session_for(service, connection, "management-first")
        second = session_for(service, connection, "management-second")
        first_info, second_info = first.session_info(), second.session_info()
        first.device.install_app(apk)
        assert second.device.remove_app("com.example") is False
        assert first.device.remove_app("missing.app") is False
        second.device.install_app(apk, allow_test_packages=True)
        assert first.session_info() == first_info
        assert second.session_info() == second_info
        for original in (first_info, second_info):
            with pytest.raises(ResourceStateError):
                create_session(connection, original.device_id)
        routes = [
            request.path
            for request in service.snapshot()
            if request.path.endswith("/execute/sync")
        ]
        assert routes == [
            f"/wd/hub/session/appium-{session_id}/execute/sync"
            for session_id in (1, 2, 1, 2)
        ]
        assert service.operation_kinds() == [
            "install_app",
            "remove_app",
            "remove_app",
            "install_app",
        ]
        first.quit()
        replacement = session_for(service, connection, "management-first")
        create = service.of_kind("create")[-1]
        assert create.body is not None
        assert create.body["capabilities"]["alwaysMatch"]["appium:systemPort"] == 8200
        replacement.quit()
        second.quit()


@pytest.mark.parametrize("method", _METHODS)
def test_closed_and_exited_connection_reject_before_send(
    service: DeviceProtocolService, apk: Path, method: str
) -> None:
    argument: object = apk if method == "install_app" else "com.example"
    with connected(service) as connection:
        closed = session_for(service, connection, "management-closed")
        closed.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as caught:
            invoke(closed.device, method, argument)
        assert_error(
            caught.value,
            InvalidSessionStateError,
            "session_closed",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        active = session_for(service, connection, "management-exited")
    before = service.snapshot()
    with pytest.raises(InvalidSessionStateError) as exited:
        invoke(active.device, method, argument)
    assert_error(
        exited.value,
        InvalidSessionStateError,
        "session_invalid",
        "not_sent",
        steps=(),
    )
    assert active.session_info().state == "uncertain"
    assert service.snapshot() == before
