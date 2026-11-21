"""XCUITest touch, keyboard, button, and application action mappings."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

from appium.webdriver.webdriver import WebDriver
from selenium.common.exceptions import InvalidElementStateException, WebDriverException
from selenium.webdriver.remote.webelement import WebElement

from ._element import Element
from ._element_target import (
    _combined_predicate_query,
    _predicate_string_literal,
    _read_displayed_once,
    _resolve_unique_locator_once,
    _wait_for_displayed_elements,
    _wait_for_ready_element,
)
from ._macos_actions import _budget_gate
from ._models import CommandError, InvalidRequestError, TargetError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_Number: TypeAlias = int | float
_Direction: TypeAlias = Literal["up", "down", "left", "right"]
_IOS_SCROLL_BY = frozenset(
    {"id", "accessibility id", "name", "class name", "-ios predicate string"}
)
_JAVA_INT_MIN = -(2**31)
_JAVA_INT_MAX = 2**31 - 1

_HIDE_KEYBOARD_KEYS = (
    "done",
    "Done",
    "return",
    "Return",
    "go",
    "Go",
    "search",
    "Search",
    "send",
    "Send",
    "next",
    "Next",
    "hide",
    "Hide keyboard",
)
_KEYBOARD_NOT_DISMISSED = "did not know how to dismiss the keyboard"


def _none(value: object) -> None:
    if value is not None:
        raise ValueError("XCUITest action must return null")


def _ios_execute_none(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    script: str,
    payload: dict[str, object],
) -> None:
    gateway.final_action(lambda: _none(driver.execute_script(script, payload)))
    gateway.complete("action_completed")


def _ios_execute_bool(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    script: str,
    payload: dict[str, object],
) -> bool:
    def action() -> bool:
        value: object = driver.execute_script(script, payload)
        if type(value) is not bool:
            raise ValueError("XCUITest action must return bool")
        return value

    result = gateway.final_action(action)
    gateway.complete("action_completed")
    return result


def _ios_query_app_state(
    driver: WebDriver, gateway: _SessionOperationGateway, bundle_id: str
) -> int:
    def action() -> int:
        value: object = driver.execute_script(
            "mobile: queryAppState", {"bundleId": bundle_id}
        )
        if type(value) is not int or value not in (0, 1, 2, 3, 4):
            raise ValueError("XCUITest app state must be an integer from 0 through 4")
        return value

    result = gateway.final_action(action)
    gateway.complete("app_state_read")
    return result


def _perform_ios_element_click(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    script: Literal["click", "doubleTap", "touchAndHold"],
    condition_deadline: float,
    duration_seconds: float | None = None,
) -> None:
    target = _wait_for_ready_element(driver, element, gateway, condition_deadline)
    if duration_seconds is not None:
        _budget_gate(gateway, duration_seconds)
    if script == "click":
        click: Callable[[], object] = target.click
        gateway.final_action(lambda: _none(click()))
    else:
        payload: dict[str, object] = {"elementId": target.id}
        if duration_seconds is not None:
            payload["duration"] = duration_seconds
        gateway.final_action(
            lambda: _none(driver.execute_script(f"mobile: {script}", payload))
        )
    gateway.complete("action_completed")


def _perform_ios_element_keys(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    keys: list[str | dict[str, str | int]],
    condition_deadline: float,
) -> None:
    target = _wait_for_ready_element(driver, element, gateway, condition_deadline)
    _ios_execute_none(
        driver,
        gateway,
        "mobile: keys",
        {"elementId": target.id, "keys": keys},
    )


def _perform_ios_element_swipe(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    direction: _Direction,
    velocity: float | None,
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
    }
    if velocity is not None:
        payload["velocity"] = velocity
    _ios_execute_none(driver, gateway, "mobile: swipe", payload)


def _perform_ios_element_scroll(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    direction: _Direction,
    distance: float,
    condition_deadline: float,
) -> None:
    target = _wait_for_displayed_elements(
        driver,
        ((element, "target"),),
        gateway,
        condition_deadline,
        prepare=lambda resolved: resolved[0],
    )
    _ios_execute_none(
        driver,
        gateway,
        "mobile: scroll",
        {"elementId": target.id, "direction": direction, "distance": distance},
    )


def _validate_ios_scroll_mapping(
    container: Element, target: Element, operation_id: str
) -> None:
    if (
        container.parent is not None
        or target.parent is not container
        or target.package is not None
        or target.raw_id
        or target.by not in _IOS_SCROLL_BY
        or (
            target.by == "class name" and not target.value.startswith("XCUIElementType")
        )
    ):
        raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")


def _ios_scroll_payload(target: Element, container_id: str) -> dict[str, object]:
    if target.by in ("id", "accessibility id", "name") and target.predicate is None:
        return {"elementId": container_id, "name": target.value}
    if target.predicate is not None:
        combined = _combined_predicate_query(
            target.by,
            target.value,
            target.predicate,
            platform="ios",
        )
        assert combined is not None
        predicate = combined[1]
    elif target.by == "class name":
        predicate = f"type == {_predicate_string_literal(target.value)}"
    else:
        assert target.by == "-ios predicate string"
        predicate = target.value
    return {"elementId": container_id, "predicateString": predicate}


def _postcheck_ios_scroll_target(
    container: WebElement,
    target: Element,
    gateway: _SessionOperationGateway,
) -> None:
    resolved = _resolve_unique_locator_once(
        container,
        target.by,
        target.value,
        gateway,
        predicate=target.predicate,
    )
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
            "target_not_displayed",
            gateway.operation_id,
            "response_received",
            completed_steps=gateway.completed_steps,
        )
    gateway.complete("target_displayed")


def _perform_ios_container_scroll(
    driver: WebDriver,
    container: Element,
    target: Element,
    gateway: _SessionOperationGateway,
    *,
    condition_deadline: float,
) -> None:
    container_element = _wait_for_displayed_elements(
        driver,
        ((container, "container"),),
        gateway,
        condition_deadline,
        prepare=lambda resolved: resolved[0],
    )
    gateway.final_action(
        lambda: _none(
            driver.execute_script(
                "mobile: scroll", _ios_scroll_payload(target, container_element.id)
            )
        )
    )
    gateway.complete("action_completed")
    _postcheck_ios_scroll_target(container_element, target, gateway)


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


def _perform_ios_drag(
    driver: WebDriver,
    source: Element,
    destination: Element,
    gateway: _SessionOperationGateway,
    *,
    x_ratio: _Number,
    y_ratio: _Number,
    duration_seconds: float,
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
    _ios_execute_none(
        driver,
        gateway,
        "mobile: dragFromToForDuration",
        {
            "duration": duration_seconds,
            "fromX": start_x,
            "fromY": start_y,
            "toX": end_x,
            "toY": end_y,
        },
    )


def _ios_install_app(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    app_path: str,
    timeout_deadline: float | None,
) -> None:
    def action() -> None:
        from ._system_actions import _INSTALL_TIMEOUT_CAP_MS, _bounded_timeout

        payload: dict[str, object] = {"app": app_path}
        if timeout_deadline is not None:
            payload["timeoutMs"] = _bounded_timeout(
                gateway, timeout_deadline, _INSTALL_TIMEOUT_CAP_MS
            )
        _none(driver.execute_script("mobile: installApp", payload))

    gateway.final_action(action)
    gateway.complete("action_completed")


def _keyboard_cannot_be_dismissed(error: CommandError) -> bool:
    cause = error.__cause__
    if type(cause) is InvalidElementStateException:
        return True
    if not isinstance(cause, WebDriverException):
        return False
    message = getattr(cause, "msg", None)
    return isinstance(message, str) and _KEYBOARD_NOT_DISMISSED in message.casefold()


def _ios_hide_keyboard(driver: WebDriver, gateway: _SessionOperationGateway) -> bool:
    try:
        _ios_execute_none(
            driver,
            gateway,
            "mobile: hideKeyboard",
            {"keys": _HIDE_KEYBOARD_KEYS},
        )
    except CommandError as error:
        if (
            error.code == "command_failed"
            and error.request_state == "response_received"
            and _keyboard_cannot_be_dismissed(error)
        ):
            return False
        raise
    return True


def _ios_alert(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    accept: bool,
    button_label: str | None,
) -> None:
    payload: dict[str, object] = {"action": "accept" if accept else "dismiss"}
    if button_label is not None:
        payload["buttonLabel"] = button_label
    _ios_execute_none(driver, gateway, "mobile: alert", payload)
