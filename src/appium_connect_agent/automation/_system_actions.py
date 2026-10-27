"""Fixed Android system commands and strict value boundaries."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from appium.webdriver.webdriver import WebDriver

from ._models import InvalidRequestError

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway


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
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not (minimum <= value <= 2_147_483_647)
    ):
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
