from __future__ import annotations

import base64
import struct
import threading
import zlib
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.command import Command

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

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_COORDINATE = 2_147_483_647
_MAX_PNG_BYTES = 33_554_432
_MAX_BASE64_CHARS = 44_739_244


def _chunk(kind: bytes, data: bytes = b"") -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def _png(
    *idat_parts: bytes,
    width: int = 1,
    height: int = 1,
    before_iend: tuple[bytes, ...] = (),
) -> bytes:
    return b"".join(
        (
            _PNG_SIGNATURE,
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            *(_chunk(b"IDAT", part) for part in idat_parts),
            *before_iend,
            _chunk(b"IEND"),
        )
    )


_MINIMAL_PNG = _png(b"0123456789")
assert len(_MINIMAL_PNG) == 67


class DeviceProtocolService(ActionProtocolService):
    @staticmethod
    def _kind(request: Request) -> str:
        if request.method == "GET" and request.path.endswith("/screenshot"):
            return "take_screenshot"
        if request.method == "POST" and request.path.endswith("/actions"):
            return "swipe_between"
        if (
            request.method == "POST"
            and request.path.endswith("/execute/sync")
            and request.body is not None
            and request.body.get("script") == "mobile: clickGesture"
        ):
            return "tap_at"
        return ActionProtocolService._kind(request)

    def _default_payload(self, request: Request, kind: str) -> object:
        if kind == "take_screenshot":
            return {"value": base64.b64encode(_MINIMAL_PNG).decode("ascii")}
        if kind in {"tap_at", "swipe_between"}:
            return {"value": None}
        return super()._default_payload(request, kind)


@pytest.fixture
def service() -> Iterator[DeviceProtocolService]:
    current = DeviceProtocolService()
    with current:
        yield current


def _encoded(data: bytes, *, line_breaks: bool = False) -> str:
    value = base64.b64encode(data).decode("ascii")
    if line_breaks:
        value = "\r\n".join(
            value[index : index + 12] for index in range(0, len(value), 12)
        )
    return value


def _invoke(
    device: Device,
    action: str,
    *,
    control: OperationControl | None = None,
) -> object:
    if action == "take_screenshot":
        return device.take_screenshot(control=control)
    if action == "tap_at":
        device.tap_at(4, 5, control=control)
        return None
    if action == "swipe_between":
        duration_ms = 1 if control is not None else 200
        device.swipe_between(1, 2, 3, 4, duration_ms=duration_ms, control=control)
        return None
    raise AssertionError(action)


def _assert_command_failure(error: CommandError) -> None:
    assert_error(error, CommandError, "command_failed", "response_received", steps=())
    assert error.__cause__ is not None


@pytest.mark.parametrize("line_breaks", [False, True])
def test_screenshot_minimal_png_and_crlf_base64(
    service: DeviceProtocolService, line_breaks: bool
) -> None:
    service.queue(
        "take_screenshot",
        ResponsePlan(
            payload={"value": _encoded(_MINIMAL_PNG, line_breaks=line_breaks)}
        ),
    )
    with connected(service) as connection:
        session = session_for(service, connection, f"screenshot-valid-{line_breaks}")
        result = session.device.take_screenshot()
        assert type(result) is bytes and result == _MINIMAL_PNG
        requests = service.of_kind("take_screenshot")
        assert len(requests) == 1
        assert requests[0].method == "GET"
        assert requests[0].path.endswith("/screenshot")
        assert requests[0].body is None
        session.quit()


def _bounded_png(total_bytes: int) -> bytes:
    fixed_bytes = (
        len(_PNG_SIGNATURE)
        + len(_chunk(b"IHDR", b"\0" * 13))
        + 24
        + len(_chunk(b"IEND"))
    )
    idat_bytes = total_bytes - fixed_bytes
    assert idat_bytes >= 2
    result = _png(b"x", b"x" * (idat_bytes - 1))
    assert len(result) == total_bytes
    return result


def test_screenshot_exact_32_mib_multi_idat_is_accepted(
    service: DeviceProtocolService,
) -> None:
    png = _bounded_png(_MAX_PNG_BYTES)
    encoded = _encoded(png)
    assert len(encoded) == _MAX_BASE64_CHARS
    service.queue("take_screenshot", ResponsePlan(payload={"value": encoded}))
    with connected(service) as connection:
        session = session_for(service, connection, "screenshot-max")
        assert session.device.take_screenshot() == png
        assert service.operation_kinds() == ["take_screenshot"]
        session.quit()


def test_screenshot_32_mib_plus_one_with_same_base64_length_is_rejected(
    service: DeviceProtocolService,
) -> None:
    png = _bounded_png(_MAX_PNG_BYTES + 1)
    encoded = _encoded(png)
    assert len(encoded) == _MAX_BASE64_CHARS
    service.queue("take_screenshot", ResponsePlan(payload={"value": encoded}))
    with connected(service) as connection:
        session = session_for(service, connection, "screenshot-max-plus-one")
        with pytest.raises(CommandError) as caught:
            session.device.take_screenshot()
        _assert_command_failure(caught.value)
        assert service.operation_kinds() == ["take_screenshot"]
        assert session.session_info().state == "active"
        session.quit()


def _invalid_png_cases() -> list[tuple[str, bytes]]:
    empty_idat = _png(b"")
    assert len(empty_idat) == 57
    no_idat = (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + _chunk(b"tEXt", b"x")
        + _chunk(b"IEND")
    )
    bad_crc = bytearray(_MINIMAL_PNG)
    bad_crc[-13] ^= 1
    bad_type = bytearray(_MINIMAL_PNG)
    bad_type[37:41] = b"ID1T"
    duplicate_ihdr = _png(
        b"x",
        before_iend=(_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)),),
    )
    zero_width = _png(b"x", width=0)
    zero_height = _png(b"x", height=0)
    missing_iend = _MINIMAL_PNG[: -len(_chunk(b"IEND"))]
    trailing = _MINIMAL_PNG + b"tail"
    huge_chunk_length = (
        _PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + struct.pack(">I", 2_147_483_648)
        + b"IDAT"
        + b"padding-to-minimum-length"
    )
    return [
        ("empty-idat-57-bytes", empty_idat),
        ("no-idat", no_idat),
        ("bad-crc", bytes(bad_crc)),
        ("illegal-chunk-type", bytes(bad_type)),
        ("duplicate-ihdr", duplicate_ihdr),
        ("zero-width", zero_width),
        ("zero-height", zero_height),
        ("missing-iend", missing_iend),
        ("iend-trailing-bytes", trailing),
        ("oversized-chunk-length", huge_chunk_length),
    ]


@pytest.mark.parametrize(
    ("case", "png"),
    _invalid_png_cases(),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_screenshot_rejects_malformed_png_container(
    service: DeviceProtocolService, case: str, png: bytes
) -> None:
    service.queue("take_screenshot", ResponsePlan(payload={"value": _encoded(png)}))
    with connected(service) as connection:
        session = session_for(service, connection, f"screenshot-invalid-{case}")
        with pytest.raises(CommandError) as caught:
            session.device.take_screenshot()
        _assert_command_failure(caught.value)
        assert service.operation_kinds() == ["take_screenshot"]
        session.quit()


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        [],
        1,
        True,
        "",
        "!!!!",
        "abc=",
        "AAAAA===",
        "é===",
    ],
)
def test_screenshot_rejects_missing_or_invalid_base64_value(
    service: DeviceProtocolService, value: object
) -> None:
    payload = {"value": value}
    service.queue("take_screenshot", ResponsePlan(payload=payload))
    with connected(service) as connection:
        session = session_for(service, connection, "screenshot-invalid-base64")
        with pytest.raises(CommandError) as caught:
            session.device.take_screenshot()
        _assert_command_failure(caught.value)
        session.quit()


def test_screenshot_rejects_wire_response_missing_value(
    service: DeviceProtocolService,
) -> None:
    service.queue("take_screenshot", ResponsePlan(payload={}))
    with connected(service) as connection:
        session = session_for(service, connection, "screenshot-missing-value")
        with pytest.raises(CommandError) as caught:
            session.device.take_screenshot()
        _assert_command_failure(caught.value)
        session.quit()


@pytest.mark.parametrize("length", [_MAX_BASE64_CHARS + 4, 45_900_001])
def test_screenshot_rejects_encoded_length_before_decode(
    service: DeviceProtocolService, length: int
) -> None:
    service.queue("take_screenshot", ResponsePlan(payload={"value": "A" * length}))
    with connected(service) as connection:
        session = session_for(service, connection, f"screenshot-encoded-size-{length}")
        with pytest.raises(CommandError) as caught:
            session.device.take_screenshot()
        _assert_command_failure(caught.value)
        session.quit()


def test_screenshot_error_never_echoes_base64_or_decoded_canary(
    service: DeviceProtocolService,
) -> None:
    decoded_canary = b"SCREENSHOT-CANARY-PRIVATE"
    encoded_canary = _encoded(decoded_canary)
    service.queue("take_screenshot", ResponsePlan(payload={"value": encoded_canary}))
    with connected(service) as connection:
        session = session_for(service, connection, "screenshot-canary")
        with pytest.raises(CommandError) as caught:
            session.device.take_screenshot()
        rendered = str(caught.value)
        assert encoded_canary not in rendered
        assert decoded_canary.decode() not in rendered
        assert repr(decoded_canary) not in rendered
        session.quit()


@pytest.mark.parametrize("coordinate", [0, _MAX_COORDINATE])
def test_tap_at_exact_protocol_and_coordinate_boundaries(
    service: DeviceProtocolService, coordinate: int
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"tap-{coordinate}")
        session.device.tap_at(coordinate, coordinate)
        requests = service.of_kind("tap_at")
        assert len(requests) == 1
        assert requests[0].method == "POST"
        assert requests[0].path.endswith("/execute/sync")
        assert requests[0].body == {
            "script": "mobile: clickGesture",
            "args": [{"x": coordinate, "y": coordinate}],
        }
        session.quit()


@pytest.mark.parametrize("field", ["x", "y"])
@pytest.mark.parametrize("value", [-1, _MAX_COORDINATE + 1, True, False, 1.0, "1"])
def test_tap_invalid_coordinates_are_not_sent(
    service: DeviceProtocolService, field: str, value: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "tap-invalid")
        before = service.snapshot()
        arguments: dict[str, object] = {"x": 1, "y": 2, field: value}
        with pytest.raises(InvalidRequestError) as caught:
            session.device.tap_at(**arguments)  # type: ignore[arg-type]
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("value", [False, 0, 1, "unexpected", {}, []])
def test_tap_rejects_non_none_client_result(
    service: DeviceProtocolService, value: object
) -> None:
    service.queue("tap_at", ResponsePlan(payload={"value": value}))
    with connected(service) as connection:
        session = session_for(service, connection, "tap-result")
        with pytest.raises(CommandError) as caught:
            session.device.tap_at(0, 0)
        _assert_command_failure(caught.value)
        assert service.operation_kinds() == ["tap_at"]
        session.quit()


@pytest.mark.parametrize(
    ("start", "end", "duration"),
    [
        ((0, 0), (0, 0), 1),
        ((_MAX_COORDINATE, _MAX_COORDINATE), (0, _MAX_COORDINATE), 200),
        ((1, 2), (3, 4), 60_000),
    ],
)
def test_swipe_exact_single_touch_pointer_protocol(
    service: DeviceProtocolService,
    start: tuple[int, int],
    end: tuple[int, int],
    duration: int,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"swipe-{duration}")
        session.device.swipe_between(*start, *end, duration_ms=duration)
        requests = service.of_kind("swipe_between")
        assert len(requests) == 1
        assert requests[0].method == "POST" and requests[0].path.endswith("/actions")
        assert requests[0].body == {
            "actions": [
                {
                    "type": "pointer",
                    "parameters": {"pointerType": "touch"},
                    "id": "touch",
                    "actions": [
                        {
                            "type": "pointerMove",
                            "duration": 0,
                            "x": start[0],
                            "y": start[1],
                            "origin": "viewport",
                        },
                        {"type": "pointerDown", "duration": 0, "button": 0},
                        {
                            "type": "pointerMove",
                            "duration": duration,
                            "x": end[0],
                            "y": end[1],
                            "origin": "viewport",
                        },
                        {"type": "pointerUp", "duration": 0, "button": 0},
                    ],
                }
            ]
        }
        session.quit()


@pytest.mark.parametrize("field", ["start_x", "start_y", "end_x", "end_y"])
@pytest.mark.parametrize("value", [-1, _MAX_COORDINATE + 1, True, 1.0, "1"])
def test_swipe_invalid_coordinates_are_not_sent(
    service: DeviceProtocolService, field: str, value: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "swipe-invalid-coordinate")
        before = service.snapshot()
        arguments: dict[str, object] = {
            "start_x": 1,
            "start_y": 2,
            "end_x": 3,
            "end_y": 4,
            field: value,
        }
        with pytest.raises(InvalidRequestError) as caught:
            session.device.swipe_between(**arguments)  # type: ignore[arg-type]
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("duration", [0, -1, 60_001, True, False, 1.0, "200"])
def test_swipe_invalid_duration_is_not_sent(
    service: DeviceProtocolService, duration: object
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "swipe-invalid-duration")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.device.swipe_between(1, 2, 3, 4, duration_ms=duration)  # type: ignore[arg-type]
        assert_error(
            caught.value, InvalidRequestError, "invalid_argument", "not_sent", steps=()
        )
        assert service.snapshot() == before
        session.quit()


@pytest.mark.parametrize("payload", [{"value": False}, {"value": 0}, {"value": "null"}])
def test_swipe_requires_explicit_none_value(
    service: DeviceProtocolService, payload: object
) -> None:
    service.queue("swipe_between", ResponsePlan(payload=payload))
    with connected(service) as connection:
        session = session_for(service, connection, "swipe-result")
        with pytest.raises(CommandError) as caught:
            session.device.swipe_between(1, 2, 3, 4)
        _assert_command_failure(caught.value)
        assert service.operation_kinds() == ["swipe_between"]
        session.quit()


def test_swipe_rejects_client_mapping_without_value(
    service: DeviceProtocolService, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_execute = WebDriver.execute

    def execute(
        driver: WebDriver, command: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        response = cast(dict[str, object], original_execute(driver, command, params))
        if command == Command.W3C_ACTIONS:
            return {}
        return response

    with connected(service) as connection:
        session = session_for(service, connection, "swipe-missing-client-value")
        monkeypatch.setattr(WebDriver, "execute", execute)
        with pytest.raises(CommandError) as caught:
            session.device.swipe_between(1, 2, 3, 4)
        _assert_command_failure(caught.value)
        assert len(service.of_kind("swipe_between")) == 1
        session.quit()


def test_swipe_explicit_budget_must_strictly_exceed_duration(
    service: DeviceProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "swipe-budget")
        before = service.snapshot()
        with pytest.raises(OperationTimeoutError) as caught:
            session.device.swipe_between(
                1,
                2,
                3,
                4,
                duration_ms=1_000,
                control=OperationControl(timeout_seconds=1),
            )
        assert_error(
            caught.value,
            OperationTimeoutError,
            "operation_timeout",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        assert session.session_info().state == "active"
        session.device.swipe_between(
            1,
            2,
            3,
            4,
            duration_ms=1,
            control=OperationControl(timeout_seconds=1),
        )
        session.quit()


def test_swipe_budget_gate_preserves_cancellation_priority(
    service: DeviceProtocolService,
) -> None:
    cancellation = threading.Event()
    cancellation.set()
    with connected(service) as connection:
        session = session_for(service, connection, "swipe-cancel-priority")
        before = service.snapshot()
        with pytest.raises(OperationCancelledError) as caught:
            session.device.swipe_between(
                1,
                2,
                3,
                4,
                duration_ms=60_000,
                control=OperationControl(timeout_seconds=1, cancellation=cancellation),
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


@pytest.mark.parametrize("action", ["take_screenshot", "tap_at", "swipe_between"])
@pytest.mark.parametrize("phase", ["disconnect", "header", "body"])
def test_response_unknown_is_not_replayed_and_quarantines_session(
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
        device_id = f"pointer-unknown-{action}-{phase}"
        session = session_for(service, connection, device_id)
        with pytest.raises(error_type) as caught:
            _invoke(session.device, action, control=control)
        assert_error(caught.value, error_type, code, "response_unknown", steps=())
        assert service.operation_kinds() == [action]
        assert session.session_info().state == "uncertain"
        with pytest.raises(ResourceStateError):
            create_session(connection, device_id)
        with pytest.raises(InvalidSessionStateError):
            session.device.back()
        assert service.of_kind("quit") == []


@pytest.mark.parametrize("action", ["take_screenshot", "tap_at", "swipe_between"])
def test_inflight_cancellation_is_unknown_and_not_replayed(
    service: DeviceProtocolService, action: str
) -> None:
    started, release, cancellation = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    service.queue(
        action, ResponsePlan(started=started, release=release, disconnect=True)
    )
    failures: list[BaseException] = []
    with connected(service) as connection:
        device_id = f"pointer-inflight-cancel-{action}"
        session = session_for(service, connection, device_id)

        def run() -> None:
            try:
                _invoke(
                    session.device,
                    action,
                    control=OperationControl(
                        timeout_seconds=2, cancellation=cancellation
                    ),
                )
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            cancellation.set()
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
        with pytest.raises(ResourceStateError):
            create_session(connection, device_id)
        with pytest.raises(InvalidSessionStateError):
            session.device.back()
        assert service.of_kind("quit") == []


@pytest.mark.parametrize("action", ["take_screenshot", "tap_at", "swipe_between"])
def test_official_errors_are_known_and_never_replayed(
    service: DeviceProtocolService, action: str
) -> None:
    service.queue(action, ResponsePlan(status=500, payload=w3c_error("private-canary")))
    with connected(service) as connection:
        session = session_for(service, connection, f"pointer-known-{action}")
        with pytest.raises(CommandError) as caught:
            _invoke(session.device, action)
        _assert_command_failure(caught.value)
        assert "private-canary" not in str(caught.value)
        assert service.operation_kinds() == [action]
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("action", ["take_screenshot", "tap_at", "swipe_between"])
def test_presend_cancel_and_expired_budget_make_no_request(
    service: DeviceProtocolService, action: str
) -> None:
    cancellation = threading.Event()
    cancellation.set()
    with connected(service) as connection:
        session = session_for(service, connection, f"pointer-presend-{action}")
        before = service.snapshot()
        with pytest.raises(OperationCancelledError) as cancelled:
            _invoke(
                session.device,
                action,
                control=OperationControl(
                    timeout_seconds=5e-324, cancellation=cancellation
                ),
            )
        assert_error(
            cancelled.value,
            OperationCancelledError,
            "operation_cancelled",
            "not_sent",
            steps=(),
        )
        with pytest.raises(OperationTimeoutError) as expired:
            _invoke(
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


@pytest.mark.parametrize("action", ["take_screenshot", "tap_at", "swipe_between"])
def test_closed_session_rejects_new_device_actions(
    service: DeviceProtocolService, action: str
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"pointer-closed-{action}")
        device = session.device
        session.quit()
        before = service.snapshot()
        with pytest.raises(InvalidSessionStateError) as caught:
            _invoke(device, action)
        assert_error(
            caught.value,
            InvalidSessionStateError,
            "session_closed",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before


@pytest.mark.parametrize("action", ["take_screenshot", "tap_at", "swipe_between"])
def test_exited_runtime_connection_rejects_new_device_actions(
    service: DeviceProtocolService, action: str
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, f"pointer-exited-{action}")
    before = service.snapshot()
    with pytest.raises(InvalidSessionStateError) as caught:
        _invoke(session.device, action)
    assert_error(
        caught.value,
        InvalidSessionStateError,
        "session_invalid",
        "not_sent",
        steps=(),
    )
    assert service.snapshot() == before


def test_new_device_actions_share_the_session_gate(
    service: DeviceProtocolService,
) -> None:
    started, release = threading.Event(), threading.Event()
    service.queue("take_screenshot", ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "pointer-gate")

        def run() -> None:
            try:
                session.device.take_screenshot()
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            before = service.snapshot()
            attempts = (
                lambda: session.device.tap_at(1, 2),
                lambda: session.device.swipe_between(1, 2, 3, 4),
                session.element("id", "target").click,
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
        session.quit()


def test_invalid_pointer_arguments_precede_session_busy(
    service: DeviceProtocolService,
) -> None:
    started, release = threading.Event(), threading.Event()
    service.queue("take_screenshot", ResponsePlan(started=started, release=release))
    failures: list[BaseException] = []
    with connected(service) as connection:
        session = session_for(service, connection, "pointer-invalid-before-busy")

        def run() -> None:
            try:
                session.device.take_screenshot()
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=run)
        worker.start()
        try:
            assert started.wait(timeout=2)
            before = service.snapshot()
            attempts: tuple[Callable[[], None], ...] = (
                lambda: session.device.tap_at(-1, 0),
                lambda: session.device.swipe_between(0, 0, 1, 1, duration_ms=0),
            )
            for attempt in attempts:
                with pytest.raises(InvalidRequestError) as caught:
                    attempt()
                assert_error(
                    caught.value,
                    InvalidRequestError,
                    "invalid_argument",
                    "not_sent",
                    steps=(),
                )
            assert service.snapshot() == before
        finally:
            release.set()
            worker.join(timeout=3)
        assert not worker.is_alive() and failures == []
        session.quit()


def test_device_binding_is_trusted_for_new_methods(
    service: DeviceProtocolService,
) -> None:
    with pytest.raises(TypeError):
        Device()
    with connected(service) as connection:
        session = session_for(service, connection, "pointer-binding")
        other = session_for(service, connection, "pointer-binding-other")
        with pytest.raises((AttributeError, FrozenInstanceError)):
            cast(Any, session.device)._owner = other
        before = service.snapshot()
        forged = object.__new__(Device)
        for action in ("take_screenshot", "tap_at", "swipe_between"):
            with pytest.raises(InvalidRequestError) as caught:
                _invoke(forged, action)
            assert_error(
                caught.value,
                InvalidRequestError,
                "invalid_argument",
                "not_sent",
                steps=(),
            )
        object.__setattr__(forged, "_owner", session)
        object.__setattr__(forged, "_marker", object())
        with pytest.raises(InvalidRequestError):
            forged.take_screenshot()
        original_owner = session.device._owner
        object.__setattr__(session.device, "_owner", object.__new__(Session))
        try:
            with pytest.raises(InvalidRequestError):
                session.device.tap_at(0, 0)
        finally:
            object.__setattr__(session.device, "_owner", original_owner)
        assert service.snapshot() == before
        session.quit()
        other.quit()
