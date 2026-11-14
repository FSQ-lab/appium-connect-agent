"""Fixed Android system commands and strict value boundaries."""

from __future__ import annotations

import base64
import binascii
import math
import struct
import time
import zlib
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Literal

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.mouse_button import MouseButton
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.remote.command import Command

from ._models import InvalidRequestError, OperationTimeoutError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_TERMINATE_TIMEOUT_CAP_MS = 500
_REMOVE_TIMEOUT_CAP_MS = 100_000
_INSTALL_TIMEOUT_CAP_MS = 300_000


def _activate_app(
    driver: WebDriver, gateway: _SessionOperationGateway, app_id: str
) -> None:
    def action() -> None:
        _none(driver.execute_script("mobile: activateApp", {"appId": app_id}))

    gateway.final_action(action)
    gateway.complete("action_completed")


def _bounded_timeout(
    gateway: _SessionOperationGateway, deadline: float, cap_ms: int
) -> int:
    """Fit one positive integer timeout strictly inside the original budget."""
    gateway.checkpoint()
    remaining = deadline - time.monotonic()
    if remaining <= 0.001:
        # A sub-millisecond budget can be unexpired; cancellation still wins.
        gateway.checkpoint()
        raise gateway.failure(OperationTimeoutError, "operation_timeout", "not_sent")

    # Cap before multiplication: even a huge finite deadline stays bounded.
    milliseconds = math.floor(min(remaining, cap_ms / 1000) * 1000)
    # Multiplication can round across an integer boundary. Compare the actual
    # float division used by the contract, correcting in constant time.
    if milliseconds / 1000 >= remaining:
        milliseconds -= 1
    elif milliseconds < cap_ms and (milliseconds + 1) / 1000 < remaining:
        milliseconds += 1
    return milliseconds


def _terminate_app(
    driver: WebDriver, gateway: _SessionOperationGateway, app_id: str
) -> bool:
    def action() -> bool:
        payload: dict[str, str | int] = {"appId": app_id}
        deadline = gateway.operation_deadline
        if deadline is not None:
            # Sample only after the gateway has prepared this final request;
            # presend controlled failures therefore remain not_sent.
            payload["timeout"] = _bounded_timeout(
                gateway, deadline, _TERMINATE_TIMEOUT_CAP_MS
            )
        result: object = driver.execute_script("mobile: terminateApp", payload)
        if type(result) is not bool:
            raise ValueError("terminateApp must return bool")
        return result

    result = gateway.final_action(action)
    gateway.complete("action_completed")
    return result


def _query_app_state(
    driver: WebDriver, gateway: _SessionOperationGateway, app_id: str
) -> int:
    def action() -> int:
        result: object = driver.execute_script(
            "mobile: queryAppState", {"appId": app_id}
        )
        if type(result) is not int or result not in (0, 1, 3, 4):
            raise ValueError("queryAppState must return integer 0, 1, 3 or 4")
        return result

    result = gateway.final_action(action)
    gateway.complete("app_state_read")
    return result


def _install_app(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    app_path: str,
    allow_test_packages: bool,
) -> None:
    def action() -> None:
        payload: dict[str, str | bool | int] = {
            "appPath": app_path,
            "replace": True,
            "allowTestPackages": allow_test_packages,
        }
        deadline = gateway.operation_deadline
        if deadline is not None:
            payload["timeout"] = _bounded_timeout(
                gateway, deadline, _INSTALL_TIMEOUT_CAP_MS
            )
        _none(driver.execute_script("mobile: installApp", payload))

    gateway.final_action(action)
    gateway.complete("action_completed")


def _remove_app(
    driver: WebDriver, gateway: _SessionOperationGateway, *, app_id: str
) -> bool:
    def action() -> bool:
        payload: dict[str, str | bool | int] = {
            "appId": app_id,
            "keepData": False,
        }
        deadline = gateway.operation_deadline
        if deadline is not None:
            payload["timeout"] = _bounded_timeout(
                gateway, deadline, _REMOVE_TIMEOUT_CAP_MS
            )
        result: object = driver.execute_script("mobile: removeApp", payload)
        if type(result) is not bool:
            raise ValueError("removeApp must return bool")
        return result

    result = gateway.final_action(action)
    gateway.complete("action_completed")
    return result


def _status_bar_command(
    command: object, operation_id: str
) -> Literal["expandNotifications", "expandSettings", "collapse"]:
    if not isinstance(command, str):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if command == "expandNotifications":
        return "expandNotifications"
    if command == "expandSettings":
        return "expandSettings"
    if command == "collapse":
        return "collapse"
    raise InvalidRequestError("invalid_argument", operation_id, "not_sent")


def _status_bar(
    driver: WebDriver, gateway: _SessionOperationGateway, command: str
) -> str:
    def action() -> str:
        result: object = driver.execute_script(
            "mobile: statusBar", {"command": command}
        )
        # This is response validation, not an invalid-argument input boundary.
        # Bound character count before allocating the strict UTF-8 encoding.
        if not isinstance(result, str) or len(result) > 65_536:
            raise ValueError("invalid statusBar response shape or size")
        if len(result.encode("utf-8", errors="strict")) > 65_536:
            raise ValueError("statusBar response exceeds UTF-8 size limit")
        return result

    result = gateway.final_action(action)
    gateway.complete("action_completed")
    return result


def _integer(value: object, minimum: int, operation_id: str) -> int:
    if type(value) is not int or not (minimum <= value <= 2_147_483_647):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _coordinate(value: object, operation_id: str) -> int:
    return _integer(value, 0, operation_id)


def _duration_ms(value: object, operation_id: str) -> int:
    if type(value) is not int or not (1 <= value <= 60_000):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _key_arguments(
    keycode: object, metastate: object, flags: object, operation_id: str
) -> tuple[int, int | None, int | None]:
    return (
        _integer(keycode, 0, operation_id),
        None
        if metastate is None
        else _integer(metastate, -2_147_483_648, operation_id),
        None if flags is None else _integer(flags, -2_147_483_648, operation_id),
    )


def _utf8(value: object, limit: int, operation_id: str) -> bytes:
    if not isinstance(value, str):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as cause:
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from cause
    if len(encoded) > limit:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return encoded


def _label(value: str | None, operation_id: str) -> str | None:
    if value is not None:
        _utf8(value, 1_024, operation_id)
    return value


def _clipboard_content(text: str, operation_id: str) -> str:
    return base64.b64encode(_utf8(text, 65_536, operation_id)).decode("ascii")


def _none(value: object) -> None:
    if value is not None:
        raise ValueError("system command must return null")


def _back(driver: WebDriver, gateway: _SessionOperationGateway) -> None:
    back: Callable[[], object] = driver.back

    def action() -> None:
        _none(back())

    gateway.final_action(action)
    gateway.complete("action_completed")


def _press_keycode(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    keycode: int,
    metastate: int | None,
    flags: int | None,
    long: bool,
) -> None:
    def action() -> None:
        helper = driver.long_press_keycode if long else driver.press_keycode
        if helper(keycode, metastate=metastate, flags=flags) is not driver:
            raise ValueError("key helper must return its driver")

    gateway.final_action(action)
    gateway.complete("action_completed")


def _hide_keyboard(driver: WebDriver, gateway: _SessionOperationGateway) -> bool:
    def action() -> bool:
        result: object = driver.execute_script("mobile: hideKeyboard", {})
        if type(result) is not bool:
            raise ValueError("hideKeyboard must return bool")
        return result

    result = gateway.final_action(action)
    gateway.complete("action_completed")
    return result


def _get_clipboard_text(driver: WebDriver, gateway: _SessionOperationGateway) -> str:
    def action() -> str:
        result: object = driver.execute_script(
            "mobile: getClipboard", {"contentType": "plaintext"}
        )
        if not isinstance(result, str) or len(result) > 87_384:
            raise ValueError("invalid clipboard response shape or encoded size")
        encoded = result.encode("ascii", errors="strict")
        decoded = base64.b64decode(encoded, validate=True)
        if len(decoded) > 65_536:
            raise ValueError("clipboard response exceeds decoded size limit")
        return decoded.decode("utf-8", errors="strict")

    result = gateway.final_action(action)
    gateway.complete("clipboard_read")
    return result


def _set_clipboard_text(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    content: str,
    label: str | None,
) -> None:
    payload = {"content": content, "contentType": "plaintext"}
    if label is not None:
        payload["label"] = label
    gateway.final_action(
        lambda: _none(driver.execute_script("mobile: setClipboard", payload))
    )
    gateway.complete("action_completed")


def _alert(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    accept: bool,
    button_label: str | None,
) -> None:
    payload = {} if button_label is None else {"buttonLabel": button_label}
    script = "mobile: acceptAlert" if accept else "mobile: dismissAlert"
    gateway.final_action(lambda: _none(driver.execute_script(script, payload)))
    gateway.complete("action_completed")


_SCREENSHOT_RAW_CHAR_LIMIT = 45_900_000
_SCREENSHOT_COMPACT_B64_LIMIT = 44_739_244
_SCREENSHOT_DECODED_MIN_BYTES = 58
_SCREENSHOT_DECODED_MAX_BYTES = 33_554_432
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_CHUNK_MAX_LEN = 2_147_483_647


def _is_png_chunk_type(chunk_type: bytes) -> bool:
    return len(chunk_type) == 4 and all(
        (65 <= byte <= 90) or (97 <= byte <= 122) for byte in chunk_type
    )


def _validate_png_container(data: bytes) -> None:
    total = len(data)
    if not (
        _SCREENSHOT_DECODED_MIN_BYTES <= total <= _SCREENSHOT_DECODED_MAX_BYTES
    ) or not data.startswith(_PNG_SIGNATURE):
        raise ValueError("invalid PNG container header or size")
    offset = len(_PNG_SIGNATURE)
    chunk_index = 0
    idat_bytes = 0
    saw_iend = False
    while offset < total:
        if offset + 8 > total:
            raise ValueError("truncated PNG chunk header")
        (chunk_len,) = struct.unpack_from(">I", data, offset)
        if chunk_len > _PNG_CHUNK_MAX_LEN:
            raise ValueError("PNG chunk length exceeds int32 bound")
        chunk_type = data[offset + 4 : offset + 8]
        if not _is_png_chunk_type(chunk_type):
            raise ValueError("invalid PNG chunk type")
        data_start = offset + 8
        data_end = data_start + chunk_len
        crc_end = data_end + 4
        if crc_end > total:
            raise ValueError("truncated PNG chunk body")
        (expected_crc,) = struct.unpack_from(">I", data, data_end)
        actual_crc = zlib.crc32(memoryview(data)[offset + 4 : data_end]) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError("PNG chunk CRC mismatch")
        if chunk_index == 0:
            if chunk_type != b"IHDR" or chunk_len != 13:
                raise ValueError("PNG must start with 13-byte IHDR")
            width, height = struct.unpack_from(">II", data, data_start)
            if not (1 <= width <= _PNG_CHUNK_MAX_LEN) or not (
                1 <= height <= _PNG_CHUNK_MAX_LEN
            ):
                raise ValueError("invalid PNG dimensions")
        elif chunk_type == b"IHDR":
            raise ValueError("duplicate PNG IHDR chunk")
        elif chunk_type == b"IDAT":
            idat_bytes += chunk_len
        elif chunk_type == b"IEND":
            if chunk_len != 0 or crc_end != total or idat_bytes < 1:
                raise ValueError("invalid PNG IEND or empty IDAT payload")
            saw_iend = True
            break
        offset = crc_end
        chunk_index += 1
    if not saw_iend:
        raise ValueError("missing PNG IEND chunk")


def _decode_screenshot_response(response: object) -> bytes:
    if not isinstance(response, Mapping) or "value" not in response:
        raise ValueError("screenshot response missing value")
    raw = response["value"]
    if type(raw) is not str or not (1 <= len(raw) <= _SCREENSHOT_RAW_CHAR_LIMIT):
        raise ValueError("invalid screenshot value shape or length")
    try:
        raw_ascii = raw.encode("ascii", errors="strict")
    except UnicodeEncodeError as cause:
        raise ValueError("screenshot payload is not ASCII") from cause
    compact = raw_ascii.translate(None, b"\r\n")
    if (
        not compact
        or len(compact) % 4 != 0
        or len(compact) > _SCREENSHOT_COMPACT_B64_LIMIT
    ):
        raise ValueError("invalid screenshot base64 length")
    try:
        decoded = base64.b64decode(compact, validate=True)
    except binascii.Error as cause:
        raise ValueError("invalid screenshot base64 content") from cause
    _validate_png_container(decoded)
    return decoded


def _take_screenshot(driver: WebDriver, gateway: _SessionOperationGateway) -> bytes:
    def action() -> bytes:
        response: object = driver.execute(Command.SCREENSHOT)
        return _decode_screenshot_response(response)

    result = gateway.final_action(action)
    gateway.complete("screenshot_captured")
    return result


def _tap_at(
    driver: WebDriver, gateway: _SessionOperationGateway, *, x: int, y: int
) -> None:
    gateway.final_action(
        lambda: _none(driver.execute_script("mobile: clickGesture", {"x": x, "y": y}))
    )
    gateway.complete("action_completed")


def _swipe_between(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int,
) -> None:
    gateway.checkpoint()
    deadline = gateway.operation_deadline
    if deadline is not None and duration_ms / 1000.0 >= deadline - time.monotonic():
        gateway.checkpoint()
        raise gateway.failure(OperationTimeoutError, "operation_timeout", "not_sent")

    touch = PointerInput(  # type: ignore[no-untyped-call]
        interaction.POINTER_TOUCH, "touch"
    )
    touch.create_pointer_move(duration=0, x=start_x, y=start_y, origin="viewport")
    touch.create_pointer_down(button=MouseButton.LEFT)  # type: ignore[no-untyped-call]
    touch.create_pointer_move(duration=duration_ms, x=end_x, y=end_y, origin="viewport")
    touch.create_pointer_up(button=MouseButton.LEFT)  # type: ignore[no-untyped-call]
    payload: dict[str, object] = {
        "actions": [touch.encode()]  # type: ignore[no-untyped-call]
    }

    def action() -> None:
        response: object = driver.execute(Command.W3C_ACTIONS, payload)
        if not isinstance(response, Mapping) or "value" not in response:
            raise ValueError("W3C actions response missing value")
        _none(response["value"])

    gateway.final_action(action)
    gateway.complete("action_completed")
