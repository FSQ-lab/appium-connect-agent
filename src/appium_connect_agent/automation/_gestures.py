"""Qualified Android Element gestures and restricted official scroll search."""

from __future__ import annotations

import math
import struct
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

from appium.webdriver.common.appiumby import AppiumBy
from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from ._element import Element, _standard_resource_id
from ._element_target import (
    _read_displayed_once,
    _resolve_unique_once,
    _wait_for_displayed_elements,
    _wait_for_displayed_locator,
    _with_raw_id_guard,
)
from ._models import CommandError, InvalidRequestError, TargetError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_Direction: TypeAlias = Literal["up", "down", "left", "right"]
_Number: TypeAlias = int | float
_DIRECTIONS = frozenset({"up", "down", "left", "right"})
_JAVA_INT_MIN = -(2**31)
_JAVA_INT_MAX = 2**31 - 1
_UIAUTOMATOR_STRATEGY = "-android uiautomator"


class _InvalidGestureResponse(Exception):
    pass


def _invalid_argument(operation_id: str) -> InvalidRequestError:
    return InvalidRequestError("invalid_argument", operation_id, "not_sent")


def _validate_direction(value: object, operation_id: str) -> _Direction:
    if not isinstance(value, str) or value not in _DIRECTIONS:
        raise _invalid_argument(operation_id)
    return cast(_Direction, value)


def _validate_percent(value: object, operation_id: str, *, maximum: float) -> _Number:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid_argument(operation_id)
    if (
        isinstance(value, float) and not math.isfinite(value)
    ) or not 0 < value <= maximum:
        raise _invalid_argument(operation_id)
    binary32 = struct.unpack("!f", struct.pack("!f", value))[0]
    if not math.isfinite(binary32) or binary32 <= 0:
        raise _invalid_argument(operation_id)
    return value


def _validate_max_swipes(value: object, operation_id: str) -> int:
    if type(value) is not int or not 1 <= value <= 30:
        raise _invalid_argument(operation_id)
    return value


def _validate_ratio(value: object, operation_id: str) -> _Number:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid_argument(operation_id)
    if (isinstance(value, float) and not math.isfinite(value)) or not 0 <= value <= 1:
        raise _invalid_argument(operation_id)
    return value


def _resource_selector(element: Element) -> str | None:
    if (
        element.by != "id"
        or element.raw_id
        or element.package is None
        or _standard_resource_id(element.value, element.package) is None
    ):
        return None
    return f'new UiSelector().resourceId("{element.value}")'


def _validate_scroll_mapping(
    container: Element, target: Element, operation_id: str
) -> tuple[str, str, str]:
    container_selector = _resource_selector(container)
    if container.parent is not None or container_selector is None:
        raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
    if target.parent is not container or container.parent is not None:
        raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
    if target.by == "id":
        target_selector = _resource_selector(target)
        if target_selector is None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        return container_selector, _UIAUTOMATOR_STRATEGY, target_selector
    if target.by == "accessibility id" and not target.raw_id:
        return container_selector, "accessibility id", target.value
    raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")


def _execute_none(driver: WebDriver, script: str, payload: dict[str, object]) -> None:
    if driver.execute_script(script, payload) is not None:
        raise _InvalidGestureResponse


def _execute_scroll_gesture(driver: WebDriver, payload: dict[str, object]) -> bool:
    result = driver.execute_script("mobile: scrollGesture", payload)
    if type(result) is not bool:
        raise _InvalidGestureResponse
    return result


def _gesture_payload(
    target: WebElement, direction: _Direction, percent: _Number
) -> dict[str, object]:
    return {
        "elementId": target.id,
        "direction": direction,
        "percent": percent,
    }


def _perform_swipe_gesture(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    direction: _Direction,
    percent: _Number,
    condition_deadline: float,
) -> None:
    def guarded_action() -> None:
        target = _wait_for_displayed_elements(
            driver,
            ((element, "source"),),
            gateway,
            condition_deadline,
            prepare=lambda resolved: resolved[0],
        )
        gateway.checkpoint()
        gateway.final_action(
            lambda: _execute_none(
                driver,
                "mobile: swipeGesture",
                _gesture_payload(target, direction, percent),
            )
        )
        gateway.complete("action_completed")

    _with_raw_id_guard(driver, (element,), gateway, guarded_action)


def _perform_scroll_gesture(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    direction: _Direction,
    percent: _Number,
    condition_deadline: float,
) -> bool:
    def guarded_action() -> bool:
        target = _wait_for_displayed_elements(
            driver,
            ((element, "source"),),
            gateway,
            condition_deadline,
            prepare=lambda resolved: resolved[0],
        )
        gateway.checkpoint()
        result = gateway.final_action(
            lambda: _execute_scroll_gesture(
                driver, _gesture_payload(target, direction, percent)
            )
        )
        gateway.complete("action_completed")
        return result

    return _with_raw_id_guard(driver, (element,), gateway, guarded_action)


def _require_scroll_settings(
    driver: WebDriver, gateway: _SessionOperationGateway
) -> None:
    settings = gateway.request(driver.get_settings, "settings_read")
    if (
        not isinstance(settings, dict)
        or type(settings.get("mapTestTagToResourceId")) is not bool
    ):
        raise CommandError(
            "source_settings_invalid",
            gateway.operation_id,
            "response_received",
            completed_steps=gateway.completed_steps,
        )
    if settings["mapTestTagToResourceId"]:
        raise InvalidRequestError(
            "unsupported_operation",
            gateway.operation_id,
            "response_received",
            completed_steps=gateway.completed_steps,
        )


def _postcheck_scroll_target(
    driver: WebDriver,
    target: Element,
    gateway: _SessionOperationGateway,
) -> None:
    resolved = _resolve_unique_once(driver, target, gateway)
    if resolved is None:
        raise TargetError(
            "target_not_found",
            gateway.operation_id,
            "response_received",
            completed_steps=gateway.completed_steps,
        )
    gateway.complete("target_resolved")
    if not _read_displayed_once(resolved, gateway):
        raise TargetError(
            "precondition_not_met",
            gateway.operation_id,
            "response_received",
            completed_steps=gateway.completed_steps,
        )
    gateway.complete("target_displayed")


def _perform_official_scroll(
    driver: WebDriver,
    target: Element,
    gateway: _SessionOperationGateway,
    *,
    mapping: tuple[str, str, str],
    max_swipes: int,
    condition_deadline: float,
) -> None:
    container_selector, target_strategy, target_selector = mapping
    _require_scroll_settings(driver, gateway)
    temporary = _wait_for_displayed_locator(
        driver,
        AppiumBy.ANDROID_UIAUTOMATOR,
        container_selector,
        "container",
        gateway,
        condition_deadline,
    )
    payload: dict[str, object] = {
        "elementId": temporary.id,
        "strategy": target_strategy,
        "selector": target_selector,
        "maxSwipes": max_swipes,
    }
    gateway.checkpoint()
    gateway.final_action(lambda: _execute_none(driver, "mobile: scroll", payload))
    gateway.complete("action_completed")
    _postcheck_scroll_target(driver, target, gateway)


def _command_failed(gateway: _SessionOperationGateway) -> CommandError:
    return CommandError(
        "command_failed",
        gateway.operation_id,
        "response_received",
        completed_steps=gateway.completed_steps,
    )


def _coordinate(origin: int, size: int, ratio: _Number) -> int | None:
    if ratio == 0:
        return origin
    if ratio == 1:
        return origin + size - 1
    try:
        return origin + math.floor(ratio * (size - 1))
    except OverflowError:
        return None


def _read_drag_endpoint(
    destination: WebElement,
    x_ratio: _Number,
    y_ratio: _Number,
    gateway: _SessionOperationGateway,
    condition_deadline: float,
) -> tuple[int, int]:
    raw = gateway.wait_request(lambda: destination.rect, condition_deadline)
    if not isinstance(raw, Mapping):
        raise _command_failed(gateway)
    parts = tuple(raw.get(name) for name in ("x", "y", "width", "height"))
    if not all(type(part) is int for part in parts):
        raise _command_failed(gateway)
    x, y, width, height = cast(tuple[int, int, int, int], parts)
    if width <= 0 or height <= 0:
        raise _command_failed(gateway)
    end_x = _coordinate(x, width, x_ratio)
    end_y = _coordinate(y, height, y_ratio)
    if (
        end_x is None
        or end_y is None
        or not _JAVA_INT_MIN <= end_x <= _JAVA_INT_MAX
        or not _JAVA_INT_MIN <= end_y <= _JAVA_INT_MAX
    ):
        raise _command_failed(gateway)
    gateway.wait_checkpoint(condition_deadline, response_received=True)
    return end_x, end_y


def _perform_drag_and_drop(
    driver: WebDriver,
    source: Element,
    destination: Element,
    gateway: _SessionOperationGateway,
    *,
    x_ratio: _Number,
    y_ratio: _Number,
    condition_deadline: float,
) -> None:
    def guarded_action() -> None:
        def prepare(
            resolved: tuple[WebElement, ...],
        ) -> tuple[WebElement, int, int]:
            end_x, end_y = _read_drag_endpoint(
                resolved[1],
                x_ratio,
                y_ratio,
                gateway,
                condition_deadline,
            )
            return resolved[0], end_x, end_y

        resolved_source, end_x, end_y = _wait_for_displayed_elements(
            driver,
            ((source, "source"), (destination, "destination")),
            gateway,
            condition_deadline,
            prepare=prepare,
        )
        gateway.complete("destination_geometry_read")
        gateway.checkpoint()
        gateway.final_action(
            lambda: _execute_none(
                driver,
                "mobile: dragGesture",
                {
                    "elementId": resolved_source.id,
                    "endX": end_x,
                    "endY": end_y,
                },
            )
        )
        gateway.complete("action_completed")

    _with_raw_id_guard(driver, (source, destination), gateway, guarded_action)
