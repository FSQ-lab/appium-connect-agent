"""Shared trusted-element resolution and Settings transactions."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from functools import partial
from typing import TYPE_CHECKING, TypeVar, cast

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from ._element import Element, _locator_chain, _trusted_chain_error
from ._models import (
    AutomationError,
    CommandError,
    InvalidRequestError,
    ResourceStateError,
    TargetError,
)

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_Result = TypeVar("_Result")
_MISSING = object()


class _PreActionStale(Exception):
    """A terminal stale response permits a fresh pre-action resolution round."""


class _InvalidTargetState(Exception):
    pass


_READY_POLL_INTERVAL_SECONDS = 0.5


def _validate_owner(element: object, owner: object, operation_id: str) -> Element:
    if not isinstance(element, Element):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    error_code = _trusted_chain_error(element, owner)
    if error_code is not None:
        raise InvalidRequestError(error_code, operation_id, "not_sent")
    return element


def _validate_raw_chain(element: Element, operation_id: str) -> None:
    chain = _locator_chain(element)
    if any(item.raw_id for item in chain) and any(
        item.by == "id" and not item.raw_id and item.package is None for item in chain
    ):
        raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")


def _validate_wait_timeout(value: object, operation_id: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return float(value)


def _find_elements(
    context: WebDriver | WebElement, element: Element
) -> Sequence[WebElement]:
    return context.find_elements(element.by, element.value)


def _resolve_unique_once(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    condition_deadline: float | None = None,
) -> WebElement | None:
    """Resolve a complete locator chain once without waiting or choosing a match."""
    parent: WebDriver | WebElement = driver
    target: WebElement | None = None
    for locator in _locator_chain(element):
        action = partial(_find_elements, parent, locator)
        matches = (
            gateway.request(action)
            if condition_deadline is None
            else gateway.wait_request(action, condition_deadline)
        )
        if not matches:
            return None
        if len(matches) != 1:
            raise TargetError(
                "target_ambiguous",
                gateway.operation_id,
                "response_received",
                completed_steps=gateway.completed_steps,
            )
        target = matches[0]
        parent = target
    return target


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


def _wait_for_ready_element(
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
            round_started + _READY_POLL_INTERVAL_SECONDS, condition_deadline
        )


def _resolve_required_once(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
) -> WebElement:
    target = _resolve_unique_once(driver, element, gateway)
    if target is None:
        raise TargetError(
            "target_not_found",
            gateway.operation_id,
            "response_received",
            completed_steps=gateway.completed_steps,
        )
    gateway.complete("target_resolved")
    return target


def _restore_setting(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    setting: str,
    value: bool,
    primary: BaseException | None,
) -> None:
    if not gateway.can_send:
        if primary is not None:
            raise primary
        return
    try:
        gateway.cleanup_request(
            lambda: driver.update_settings({setting: value}), "settings_restored"
        )
    except AutomationError as restoration:
        close_errors = () if not gateway.can_send else gateway.abandon()
        if primary is not None:
            if isinstance(primary, AutomationError):
                primary.completed_steps = gateway.completed_steps
                primary.cleanup_errors += (restoration, *close_errors)
            else:
                primary.__dict__["automation_cleanup_errors"] = (
                    restoration,
                    *close_errors,
                )
            raise primary from primary.__cause__
        if restoration.request_state == "response_unknown":
            raise restoration
        error = ResourceStateError(
            "cleanup_failed",
            gateway.operation_id,
            restoration.request_state,
            completed_steps=gateway.completed_steps,
            cleanup_errors=(restoration, *close_errors),
        )
        raise error from restoration
    if primary is not None:
        if isinstance(primary, AutomationError):
            primary.completed_steps = gateway.completed_steps
        raise primary from primary.__cause__


def _with_raw_id_guard(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    action: Callable[[], _Result],
) -> _Result:
    """Hold raw-ID autocompletion semantics across one complete Session operation."""
    if not any(locator.raw_id for locator in _locator_chain(element)):
        return action()

    changed = False
    primary: BaseException | None = None
    result: object = _MISSING
    try:
        settings = gateway.request(driver.get_settings, "settings_read")
        if (
            not isinstance(settings, dict)
            or type(settings.get("disableIdLocatorAutocompletion")) is not bool
        ):
            raise CommandError(
                "source_settings_invalid",
                gateway.operation_id,
                "response_received",
                completed_steps=gateway.completed_steps,
            )
        changed = not settings["disableIdLocatorAutocompletion"]
        if changed:
            gateway.request(
                lambda: driver.update_settings(
                    {"disableIdLocatorAutocompletion": True}
                ),
                "settings_changed",
            )
        result = action()
    except BaseException as error:
        primary = error

    if changed and "settings_changed" in gateway.completed_steps:
        _restore_setting(
            driver,
            gateway,
            "disableIdLocatorAutocompletion",
            False,
            primary,
        )
    if primary is not None:
        raise primary
    if result is _MISSING:
        raise RuntimeError("raw-ID operation produced no result")
    return cast(_Result, result)
