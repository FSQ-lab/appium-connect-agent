"""Bounded Element click actions for the qualified Android platform."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar, Literal

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from ._element import Element
from ._element_target import (
    _PreActionStale,
    _resolve_unique_once,
    _with_raw_id_guard,
)
from ._models import InvalidRequestError, OperationTimeoutError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_ActionKind = Literal["single", "double", "long"]
_ACTION_POLL_INTERVAL_SECONDS = 0.5


class _InvalidActionResponse(Exception):
    pass


class _InvalidTargetState(Exception):
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


def _validate_wait_timeout(value: object, operation_id: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return float(value)


def _validate_duration(value: object, operation_id: str) -> int:
    if type(value) is not int or not 1 <= value <= 60_000:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _wait_bool(
    action: Callable[[], object],
    gateway: _SessionOperationGateway,
    condition_deadline: float,
) -> bool:
    def checked() -> bool:
        result = action()
        if type(result) is not bool:
            raise _InvalidTargetState
        return result

    return gateway.wait_request(checked, condition_deadline)


def _wait_for_action_target(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    condition_deadline: float,
) -> WebElement:
    while True:
        round_started = time.monotonic()
        gateway.wait_checkpoint(condition_deadline)
        try:
            target = _resolve_unique_once(
                driver,
                element,
                gateway,
                condition_deadline=condition_deadline,
            )
            if (
                target is not None
                and _wait_bool(target.is_displayed, gateway, condition_deadline)
                and _wait_bool(target.is_enabled, gateway, condition_deadline)
            ):
                gateway.complete("target_resolved")
                gateway.complete("target_displayed")
                gateway.complete("target_enabled")
                return target
        except _PreActionStale:
            pass
        gateway.wait_until(
            round_started + _ACTION_POLL_INTERVAL_SECONDS, condition_deadline
        )


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
        target = _wait_for_action_target(driver, element, gateway, condition_deadline)
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

    _with_raw_id_guard(driver, element, gateway, guarded_action)
