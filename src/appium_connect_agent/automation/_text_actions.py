"""Bounded Element text actions for the qualified Android platform."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from appium.webdriver.webdriver import WebDriver
from appium.webdriver.webelement import WebElement

from ._element import Element
from ._element_target import _wait_for_ready_element, _with_raw_id_guard
from ._models import InvalidRequestError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_TextAction = Literal["send_keys", "clear", "replace"]
_MAX_TEXT_UTF8_BYTES = 65_536


class _InvalidTextActionResponse(Exception):
    pass


class _AndroidElementTextActions:
    def perform(
        self,
        driver: WebDriver,
        target: WebElement,
        *,
        action: _TextAction,
        text: str | None,
    ) -> None:
        if action == "clear":
            if text is not None:
                raise RuntimeError("clear requires no text")
            if target.clear() is not target:
                raise _InvalidTextActionResponse
            return

        if text is None:
            raise RuntimeError(f"{action} requires validated text")
        if action == "send_keys":
            if target.send_keys(text) is not target:
                raise _InvalidTextActionResponse
            return

        result = driver.execute_script(
            "mobile: replaceElementValue",
            {"elementId": target.id, "text": text},
        )
        if result is not None:
            raise _InvalidTextActionResponse


_ANDROID_TEXT_ACTIONS = _AndroidElementTextActions()


def _validate_text(
    value: object,
    operation_id: str,
    *,
    allow_empty: bool,
) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    if "\x00" in value or value.endswith("\\n"):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as cause:
        error = InvalidRequestError("invalid_argument", operation_id, "not_sent")
        raise error from cause
    if len(encoded) > _MAX_TEXT_UTF8_BYTES:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _perform_text_action(
    driver: WebDriver,
    element: Element,
    gateway: _SessionOperationGateway,
    *,
    action: _TextAction,
    text: str | None,
    condition_deadline: float,
) -> None:
    def guarded_action() -> None:
        target = cast(
            WebElement,
            _wait_for_ready_element(driver, element, gateway, condition_deadline),
        )
        gateway.checkpoint()
        gateway.final_action(
            lambda: _ANDROID_TEXT_ACTIONS.perform(
                driver,
                target,
                action=action,
                text=text,
            )
        )
        gateway.complete("action_completed")

    _with_raw_id_guard(driver, element, gateway, guarded_action)
