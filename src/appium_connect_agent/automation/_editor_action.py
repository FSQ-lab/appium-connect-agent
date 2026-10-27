"""Element-bound focus verification and one official Android editor action."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal, cast

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from ._actions import _ANDROID_ACTIONS, _InvalidActionResponse
from ._boolean_value import _parse_boolean_value
from ._element import Element
from ._element_target import (
    _READY_POLL_INTERVAL_SECONDS,
    _wait_for_ready_element,
    _with_raw_id_guard,
)
from ._models import InvalidRequestError, TargetError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_EditorAction = Literal[
    "normal", "unspecified", "none", "go", "search", "send", "next", "done", "previous"
]
_EDITOR_ACTIONS = frozenset(
    {
        "normal",
        "unspecified",
        "none",
        "go",
        "search",
        "send",
        "next",
        "done",
        "previous",
    }
)


def _validate_editor_action(value: object, operation_id: str) -> _EditorAction:
    if not isinstance(value, str) or value not in _EDITOR_ACTIONS:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return cast(_EditorAction, value)


def _read_focused(
    target: WebElement,
    gateway: _SessionOperationGateway,
    condition_deadline: float,
    *,
    pre_action: bool,
) -> bool:
    def checked() -> bool | None:
        value = target.get_attribute("focused")
        return None if value is None else _parse_boolean_value(value)

    focused = gateway.wait_request(checked, condition_deadline, pre_action=pre_action)
    if focused is None:
        raise TargetError(
            "precondition_not_met",
            gateway.operation_id,
            "response_received",
            completed_steps=gateway.completed_steps,
        )
    return focused


def _perform_editor_action(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    action: _EditorAction,
    condition_deadline: float,
) -> None:
    def guarded_action() -> None:
        focused = False

        def prepare(target: WebElement) -> None:
            nonlocal focused
            focused = _read_focused(
                target, gateway, condition_deadline, pre_action=True
            )

        target = _wait_for_ready_element(
            driver, element, gateway, condition_deadline, prepare=prepare
        )
        if not focused:
            gateway.final_action(
                lambda: _ANDROID_ACTIONS.perform(
                    driver, target, kind="single", duration_ms=None
                )
            )
            gateway.complete("focus_click_completed")
            while True:
                round_started = time.monotonic()
                if _read_focused(target, gateway, condition_deadline, pre_action=False):
                    break
                gateway.wait_until(
                    round_started + _READY_POLL_INTERVAL_SECONDS, condition_deadline
                )
        gateway.complete("target_focused")

        def perform() -> None:
            result = driver.execute_script(
                "mobile: performEditorAction", {"action": action}
            )
            if result is not None:
                raise _InvalidActionResponse

        gateway.final_action(perform)
        gateway.complete("action_completed")

    _with_raw_id_guard(driver, (element,), gateway, guarded_action)
