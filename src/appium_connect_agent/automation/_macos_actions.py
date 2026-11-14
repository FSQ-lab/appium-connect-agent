"""Mac2 desktop action values, validation, and fixed protocol mappings."""

from __future__ import annotations

import math
import os
import re
import stat
import time
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from ._element import Element
from ._element_target import _wait_for_displayed_elements, _wait_for_ready_element
from ._macos_keyboard import MacKeyStroke
from ._models import CommandError, InvalidRequestError, OperationTimeoutError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway


_Number: TypeAlias = int | float
_Direction: TypeAlias = Literal["up", "down", "left", "right"]
_DIRECTIONS = frozenset({"up", "down", "left", "right"})
_JAVA_INT_MIN = -(2**31)
_JAVA_INT_MAX = 2**31 - 1
_MAC_BUNDLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,254}")
_NAMED_KEYS = frozenset(
    {
        "XCUIKeyboardKeyDelete",
        "XCUIKeyboardKeyReturn",
        "XCUIKeyboardKeyEnter",
        "XCUIKeyboardKeyTab",
        "XCUIKeyboardKeySpace",
        "XCUIKeyboardKeyEscape",
        "XCUIKeyboardKeyUpArrow",
        "XCUIKeyboardKeyDownArrow",
        "XCUIKeyboardKeyLeftArrow",
        "XCUIKeyboardKeyRightArrow",
        *(f"XCUIKeyboardKeyF{index}" for index in range(1, 20)),
        "XCUIKeyboardKeyForwardDelete",
        "XCUIKeyboardKeyHome",
        "XCUIKeyboardKeyEnd",
        "XCUIKeyboardKeyPageUp",
        "XCUIKeyboardKeyPageDown",
        "XCUIKeyboardKeyClear",
        "XCUIKeyboardKeyHelp",
        "XCUIKeyboardKeyCapsLock",
        "XCUIKeyboardKeyShift",
        "XCUIKeyboardKeyControl",
        "XCUIKeyboardKeyOption",
        "XCUIKeyboardKeyCommand",
        "XCUIKeyboardKeyRightShift",
        "XCUIKeyboardKeyRightControl",
        "XCUIKeyboardKeyRightOption",
        "XCUIKeyboardKeyRightCommand",
        "XCUIKeyboardKeySecondaryFn",
    }
)


def _invalid(operation_id: str) -> InvalidRequestError:
    return InvalidRequestError("invalid_argument", operation_id, "not_sent")


def _validate_modifier_flags(value: object, operation_id: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= 63:
        raise _invalid(operation_id)
    return value


def _validate_number(value: object, operation_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(operation_id)
    result = float(value)
    if not math.isfinite(result):
        raise _invalid(operation_id)
    return result


def _validate_velocity(value: object, operation_id: str) -> float | None:
    if value is None:
        return None
    result = _validate_number(value, operation_id)
    if result <= 0:
        raise _invalid(operation_id)
    return result


def _validate_macos_direction(value: object, operation_id: str) -> _Direction:
    if not isinstance(value, str) or value not in _DIRECTIONS:
        raise _invalid(operation_id)
    return cast(_Direction, value)


def _validate_key(value: object, operation_id: str) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise _invalid(operation_id)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise _invalid(operation_id) from None
    if len(value) != 1 and value not in _NAMED_KEYS:
        raise _invalid(operation_id)
    return value


def _validate_macos_keys(
    value: object, operation_id: str
) -> list[str | dict[str, str | int]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _invalid(operation_id)
    try:
        items = list(value)
    except Exception:
        raise _invalid(operation_id) from None
    if not 1 <= len(items) <= 1_024:
        raise _invalid(operation_id)
    result: list[str | dict[str, str | int]] = []
    for item in items:
        if isinstance(item, str):
            result.append(_validate_key(item, operation_id))
            continue
        if not isinstance(item, MacKeyStroke):
            raise _invalid(operation_id)
        key = _validate_key(item.key, operation_id)
        modifier_flags = _validate_modifier_flags(item.modifier_flags, operation_id)
        assert modifier_flags is not None
        result.append(
            key
            if modifier_flags == 0
            else {"key": key, "modifierFlags": modifier_flags}
        )
    return result


def _validate_bundle_id(value: object, operation_id: str) -> str:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or _MAC_BUNDLE_ID.fullmatch(value) is None
    ):
        raise _invalid(operation_id)
    return value


def _validate_launch_arguments(value: object, operation_id: str) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _invalid(operation_id)
    try:
        result = list(value)
    except Exception:
        raise _invalid(operation_id) from None
    if len(result) > 64:
        raise _invalid(operation_id)
    for item in result:
        if not isinstance(item, str) or len(item) > 4_096 or "\0" in item:
            raise _invalid(operation_id)
        try:
            item.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise _invalid(operation_id) from None
    return result


def _validate_mac_app_path_syntax(app_path: object, operation_id: str) -> Path:
    if not isinstance(app_path, Path):
        raise _invalid(operation_id)
    try:
        text = str(app_path)
        encoded = text.encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError):
        raise _invalid(operation_id) from None
    if (
        not app_path.is_absolute()
        or "." in app_path.parts
        or ".." in app_path.parts
        or app_path.suffix.casefold() != ".app"
        or not 1 <= len(encoded) <= 4_096
        or any(unicodedata.category(character) == "Cc" for character in text)
    ):
        raise _invalid(operation_id)
    return app_path


def _validate_mac_app_bundle(app_path: object, operation_id: str) -> str:
    valid_path = _validate_mac_app_path_syntax(app_path, operation_id)
    prefixes = [Path(valid_path.anchor)]
    current = prefixes[0]
    for part in valid_path.parts[1:]:
        current /= part
        prefixes.append(current)
    contents = valid_path / "Contents"
    plist = contents / "Info.plist"
    metadata: list[tuple[Path, os.stat_result]] = []
    try:
        for path in (*prefixes, contents, plist):
            item = os.lstat(path)
            if stat.S_ISLNK(item.st_mode):
                raise _invalid(operation_id)
            metadata.append((path, item))
        readable = os.access(plist, os.R_OK)
    except InvalidRequestError:
        raise
    except (OSError, ValueError):
        raise _invalid(operation_id) from None
    modes = {path: item.st_mode for path, item in metadata}
    if (
        not stat.S_ISDIR(modes[valid_path])
        or not stat.S_ISDIR(modes[contents])
        or not stat.S_ISREG(modes[plist])
        or not readable
    ):
        raise _invalid(operation_id)
    return str(valid_path)


def _none(value: object) -> None:
    if value is not None:
        raise ValueError("Mac2 action must return null")


def _modifier_payload(value: int | None) -> dict[str, object]:
    return {} if value is None else {"keyModifierFlags": value}


def _budget_gate(gateway: _SessionOperationGateway, duration_seconds: float) -> None:
    gateway.checkpoint()
    deadline = gateway.operation_deadline
    if deadline is not None and duration_seconds >= deadline - time.monotonic():
        gateway.checkpoint()
        raise gateway.failure(OperationTimeoutError, "operation_timeout", "not_sent")


def _perform_macos_element_action(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    script: Literal["click", "doubleClick", "rightClick", "hover", "press"],
    modifier_flags: int | None,
    condition_deadline: float,
    duration_seconds: float | None = None,
) -> None:
    target = (
        _wait_for_displayed_elements(
            driver,
            ((element, "target"),),
            gateway,
            condition_deadline,
            prepare=lambda resolved: resolved[0],
        )
        if script == "hover"
        else _wait_for_ready_element(driver, element, gateway, condition_deadline)
    )
    payload: dict[str, object] = {
        "elementId": target.id,
        **_modifier_payload(modifier_flags),
    }
    if duration_seconds is not None:
        _budget_gate(gateway, duration_seconds)
        payload["duration"] = duration_seconds
    gateway.final_action(
        lambda: _none(driver.execute_script(f"macos: {script}", payload))
    )
    gateway.complete("action_completed")


def _perform_macos_element_keys(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    keys: list[str | dict[str, str | int]],
    condition_deadline: float,
) -> None:
    target = _wait_for_ready_element(driver, element, gateway, condition_deadline)
    gateway.final_action(
        lambda: _none(
            driver.execute_script("macos: keys", {"elementId": target.id, "keys": keys})
        )
    )
    gateway.complete("action_completed")


def _perform_macos_element_scroll(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    delta_x: float,
    delta_y: float,
    modifier_flags: int | None,
    condition_deadline: float,
) -> None:
    target = _wait_for_displayed_elements(
        driver,
        ((element, "target"),),
        gateway,
        condition_deadline,
        prepare=lambda resolved: resolved[0],
    )
    payload = {
        "elementId": target.id,
        "deltaX": delta_x,
        "deltaY": delta_y,
        **_modifier_payload(modifier_flags),
    }
    gateway.final_action(lambda: _none(driver.execute_script("macos: scroll", payload)))
    gateway.complete("action_completed")


def _perform_macos_element_swipe(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    direction: _Direction,
    velocity: float | None,
    modifier_flags: int | None,
    condition_deadline: float,
) -> None:
    target = _wait_for_displayed_elements(
        driver,
        ((element, "target"),),
        gateway,
        condition_deadline,
        prepare=lambda resolved: resolved[0],
    )
    payload: dict[str, object] = {
        "elementId": target.id,
        "direction": direction,
        **_modifier_payload(modifier_flags),
    }
    if velocity is not None:
        payload["velocity"] = velocity
    gateway.final_action(lambda: _none(driver.execute_script("macos: swipe", payload)))
    gateway.complete("action_completed")


def _rect(
    element: WebElement,
    gateway: _SessionOperationGateway,
    condition_deadline: float,
) -> tuple[int, int, int, int]:
    value = gateway.wait_request(lambda: element.rect, condition_deadline)
    if not isinstance(value, Mapping):
        raise gateway.failure(CommandError, "command_failed", "response_received")
    parts = tuple(value.get(name) for name in ("x", "y", "width", "height"))
    if not all(type(part) is int for part in parts):
        raise gateway.failure(CommandError, "command_failed", "response_received")
    x, y, width, height = cast(tuple[int, int, int, int], parts)
    if width <= 0 or height <= 0:
        raise gateway.failure(CommandError, "command_failed", "response_received")
    return x, y, width, height


def _interior_coordinate(origin: int, size: int, ratio: _Number) -> int:
    if ratio == 0:
        return origin
    if ratio == 1:
        return origin + size - 1
    return origin + math.floor(ratio * (size - 1))


def _perform_macos_drag(
    driver: WebDriver,
    source: Element,
    destination: Element,
    gateway: _SessionOperationGateway,
    *,
    x_ratio: _Number,
    y_ratio: _Number,
    duration_seconds: float,
    modifier_flags: int | None,
    condition_deadline: float,
) -> None:
    def prepare(resolved: tuple[WebElement, ...]) -> tuple[int, int, int, int]:
        source_x, source_y, source_width, source_height = _rect(
            resolved[0], gateway, condition_deadline
        )
        dest_x, dest_y, dest_width, dest_height = _rect(
            resolved[1], gateway, condition_deadline
        )
        coordinates = (
            source_x + source_width // 2,
            source_y + source_height // 2,
            _interior_coordinate(dest_x, dest_width, x_ratio),
            _interior_coordinate(dest_y, dest_height, y_ratio),
        )
        if not all(_JAVA_INT_MIN <= value <= _JAVA_INT_MAX for value in coordinates):
            raise gateway.failure(CommandError, "command_failed", "response_received")
        return coordinates

    start_x, start_y, end_x, end_y = _wait_for_displayed_elements(
        driver,
        ((source, "source"), (destination, "destination")),
        gateway,
        condition_deadline,
        prepare=prepare,
    )
    gateway.complete("source_geometry_read")
    gateway.complete("destination_geometry_read")
    _budget_gate(gateway, duration_seconds)
    payload = {
        "startX": start_x,
        "startY": start_y,
        "endX": end_x,
        "endY": end_y,
        "duration": duration_seconds,
        **_modifier_payload(modifier_flags),
    }
    gateway.final_action(
        lambda: _none(driver.execute_script("macos: clickAndDrag", payload))
    )
    gateway.complete("action_completed")


def _macos_execute_none(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    script: str,
    payload: dict[str, object],
) -> None:
    gateway.final_action(lambda: _none(driver.execute_script(script, payload)))
    gateway.complete("action_completed")


def _macos_execute_bool(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    script: str,
    payload: dict[str, object],
) -> bool:
    def action() -> bool:
        value: object = driver.execute_script(script, payload)
        if type(value) is not bool:
            raise ValueError("Mac2 action must return bool")
        return value

    result = gateway.final_action(action)
    gateway.complete("action_completed")
    return result


def _macos_query_app_state(
    driver: WebDriver, gateway: _SessionOperationGateway, bundle_id: str
) -> int:
    def action() -> int:
        value: object = driver.execute_script(
            "macos: queryAppState", {"bundleId": bundle_id}
        )
        if type(value) is not int or value not in (0, 1, 2, 3, 4):
            raise ValueError("Mac2 app state must be an integer from 0 through 4")
        return value

    result = gateway.final_action(action)
    gateway.complete("app_state_read")
    return result


def _macos_send_keys(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    keys: list[str | dict[str, str | int]],
) -> None:
    _macos_execute_none(driver, gateway, "macos: keys", {"keys": keys})


def _macos_pointer_action(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    script: str,
    payload: dict[str, object],
    duration_seconds: float | None = None,
) -> None:
    if duration_seconds is not None:
        _budget_gate(gateway, duration_seconds)
        payload["duration"] = duration_seconds
    _macos_execute_none(driver, gateway, script, payload)
