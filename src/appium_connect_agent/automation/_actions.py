"""Bounded Element click actions for the qualified Android platform."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, ClassVar, Literal

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from ._element import Element
from ._element_target import _wait_for_ready_element, _with_raw_id_guard
from ._models import InvalidRequestError, OperationTimeoutError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_ActionKind = Literal["single", "double", "long"]


class _InvalidActionResponse(Exception):
    pass


class _AndroidElementActions:
    _SCRIPTS: ClassVar[dict[_ActionKind, str]] = {
        "single": "mobile: clickGesture",
        "double": "mobile: doubleClickGesture",
        "long": "mobile: longClickGesture",
    }

    def perform(
        self,
        driver: WebDriver,
        target: WebElement,
        *,
        kind: _ActionKind,
        duration_ms: int | None,
    ) -> None:
        payload: dict[str, str | int] = {"elementId": target.id}
        if kind == "long":
            if duration_ms is None:
                raise RuntimeError("long click requires a normalized duration")
            payload["duration"] = duration_ms
        result = driver.execute_script(self._SCRIPTS[kind], payload)
        if result is not None:
            raise _InvalidActionResponse


_ANDROID_ACTIONS = _AndroidElementActions()


def _validate_duration(value: object, operation_id: str) -> int:
    if type(value) is not int or not 1 <= value <= 60_000:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _perform_action(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    kind: _ActionKind,
    duration_ms: int | None,
    condition_deadline: float,
) -> None:
    def guarded_action() -> None:
        target = _wait_for_ready_element(driver, element, gateway, condition_deadline)
        gateway.checkpoint()
        operation_deadline = gateway.operation_deadline
        if (
            duration_ms is not None
            and operation_deadline is not None
            and duration_ms / 1000.0 >= operation_deadline - time.monotonic()
        ):
            gateway.checkpoint()
            raise OperationTimeoutError(
                "operation_timeout",
                gateway.operation_id,
                "not_sent",
                completed_steps=gateway.completed_steps,
            )
        gateway.final_action(
            lambda: _ANDROID_ACTIONS.perform(
                driver,
                target,
                kind=kind,
                duration_ms=duration_ms,
            )
        )
        gateway.complete("action_completed")

    _with_raw_id_guard(driver, (element,), gateway, guarded_action)
