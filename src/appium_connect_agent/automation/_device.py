"""Immutable system-action namespace owned by one Session."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from appium_connect_agent.runtime import OperationControl

from ._element import _PreparedOperation, _valid_package
from ._ios_actions import (
    _ios_alert,
    _ios_execute_bool,
    _ios_execute_none,
    _ios_hide_keyboard,
    _ios_install_app,
    _ios_query_app_state,
)
from ._macos_actions import (
    _macos_execute_bool,
    _macos_execute_none,
    _macos_pointer_action,
    _macos_query_app_state,
    _macos_send_keys,
    _modifier_payload,
    _validate_bundle_id,
    _validate_launch_arguments,
    _validate_mac_app_bundle,
    _validate_mac_app_path_syntax,
    _validate_macos_keys,
    _validate_modifier_flags,
    _validate_number,
)
from ._macos_keyboard import MacKeyStroke
from ._models import InvalidRequestError
from ._system_actions import (
    _activate_app,
    _alert,
    _back,
    _clipboard_content,
    _coordinate,
    _duration_ms,
    _get_clipboard_text,
    _hide_keyboard,
    _install_app,
    _key_arguments,
    _label,
    _press_keycode,
    _query_app_state,
    _remove_app,
    _set_clipboard_text,
    _status_bar,
    _status_bar_command,
    _swipe_between,
    _take_screenshot,
    _tap_at,
    _terminate_app,
)

if TYPE_CHECKING:
    from ._session import Session

_MARKER = object()


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Device:
    _owner: Session = field(repr=False)
    _marker: object = field(repr=False)

    def __init__(self) -> None:
        raise TypeError("Device objects are created by Session.device")

    def activate_app(
        self, app_id: str, *, control: OperationControl | None = None
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_app_id = (
            _validate_bundle_id(app_id, operation_id)
            if owner.platform in ("macos", "ios")
            else _checked_app_id(app_id, operation_id)
        )
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _macos_execute_none(
                    driver,
                    gateway,
                    "macos: activateApp",
                    {"bundleId": valid_app_id},
                )
                if owner.platform == "macos"
                else _ios_execute_none(
                    driver,
                    gateway,
                    "mobile: activateApp",
                    {"bundleId": valid_app_id},
                )
                if owner.platform == "ios"
                else _activate_app(driver, gateway, valid_app_id)
            ),
        )

    def terminate_app(
        self, app_id: str, *, control: OperationControl | None = None
    ) -> bool:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_app_id = (
            _validate_bundle_id(app_id, operation_id)
            if owner.platform in ("macos", "ios")
            else _checked_app_id(app_id, operation_id)
        )
        return owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _macos_execute_bool(
                    driver,
                    gateway,
                    "macos: terminateApp",
                    {"bundleId": valid_app_id},
                )
                if owner.platform == "macos"
                else _ios_execute_bool(
                    driver,
                    gateway,
                    "mobile: terminateApp",
                    {"bundleId": valid_app_id},
                )
                if owner.platform == "ios"
                else _terminate_app(driver, gateway, valid_app_id)
            ),
        )

    def query_app_state(
        self, app_id: str, *, control: OperationControl | None = None
    ) -> int:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_app_id = (
            _validate_bundle_id(app_id, operation_id)
            if owner.platform in ("macos", "ios")
            else _checked_app_id(app_id, operation_id)
        )
        return owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _macos_query_app_state(driver, gateway, valid_app_id)
                if owner.platform == "macos"
                else _ios_query_app_state(driver, gateway, valid_app_id)
                if owner.platform == "ios"
                else _query_app_state(driver, gateway, valid_app_id)
            ),
        )

    def launch_app(
        self,
        *,
        bundle_id: str | None = None,
        app_path: Path | None = None,
        arguments: Sequence[str] | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_bundle_id = (
            None if bundle_id is None else _validate_bundle_id(bundle_id, operation_id)
        )
        valid_arguments = _validate_launch_arguments(arguments, operation_id)
        valid_path_value = (
            None
            if app_path is None
            else _validate_ios_app_path_lexical(app_path, operation_id)
            if owner.platform == "ios"
            else _validate_mac_app_path_syntax(app_path, operation_id)
        )
        if valid_bundle_id is None and valid_path_value is None:
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        if owner.platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        if owner.platform == "ios" and valid_path_value is not None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        valid_path = (
            None
            if valid_path_value is None or owner.platform == "ios"
            else _validate_mac_app_bundle(valid_path_value, operation_id)
        )
        payload: dict[str, object] = {}
        if valid_bundle_id is not None:
            payload["bundleId"] = valid_bundle_id
        if valid_path is not None:
            payload["path"] = valid_path
        if valid_arguments is not None:
            payload["arguments"] = valid_arguments
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _ios_execute_none(driver, gateway, "mobile: launchApp", payload)
                if owner.platform == "ios"
                else _macos_execute_none(driver, gateway, "macos: launchApp", payload)
            ),
        )

    def install_app(
        self,
        app_path: Path,
        *,
        allow_test_packages: bool = False,
        control: OperationControl | None = None,
    ) -> None:
        """Install one bounded local application package."""
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        allow_test_packages = _check_bool(allow_test_packages, operation_id)
        if owner.platform == "macos":
            _validate_apk_path_lexical(app_path, operation_id)
            owner._reject_macos(operation_id)
        if owner.platform == "ios":
            _validate_ios_app_path_lexical(app_path, operation_id)
            if allow_test_packages:
                raise InvalidRequestError(
                    "unsupported_operation", operation_id, "not_sent"
                )
            app_path = _check_ios_app_path(app_path, operation_id)
        else:
            app_path = _check_app_path(app_path, operation_id)
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _ios_install_app(
                    driver,
                    gateway,
                    app_path=str(app_path),
                    timeout_deadline=deadline if control is not None else None,
                )
                if owner.platform == "ios"
                else _install_app(
                    driver,
                    gateway,
                    app_path=str(app_path),
                    allow_test_packages=allow_test_packages,
                )
            ),
        )

    def remove_app(
        self, app_id: str, *, control: OperationControl | None = None
    ) -> bool:
        """Remove one explicit package and preserve the official boolean."""
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        app_id = (
            _validate_bundle_id(app_id, operation_id)
            if owner.platform == "ios"
            else _checked_app_id(app_id, operation_id)
        )
        owner._reject_macos(operation_id)
        return owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _ios_execute_bool(
                    driver,
                    gateway,
                    "mobile: removeApp",
                    {"bundleId": app_id},
                )
                if owner.platform == "ios"
                else _remove_app(driver, gateway, app_id=app_id)
            ),
        )

    def status_bar(
        self,
        command: Literal["expandNotifications", "expandSettings", "collapse"],
        *,
        control: OperationControl | None = None,
    ) -> str:
        """Send one panel command; output does not prove panel visibility."""
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        command = _status_bar_command(command, operation_id)
        owner._reject_macos(operation_id)
        owner._reject_ios(operation_id)
        return owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _status_bar(driver, gateway, command),
        )

    def back(self, *, control: OperationControl | None = None) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        owner._reject_macos(operation_id)
        owner._reject_ios(operation_id)
        owner._run_operation(operation_id, control, deadline, _back)

    def press_button(
        self,
        name: Literal["home", "volumeUp", "volumeDown", "action", "camera"],
        *,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_name = _check_press_button(name, operation_id)
        if owner.platform != "ios":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _ios_execute_none(
                driver,
                gateway,
                "mobile: pressButton",
                {"name": valid_name},
            ),
        )

    def press_keycode(
        self,
        keycode: int,
        *,
        metastate: int | None = None,
        flags: int | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        keycode, metastate, flags = _key_arguments(
            keycode, metastate, flags, operation_id
        )
        owner._reject_macos(operation_id)
        owner._reject_ios(operation_id)
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _press_keycode(
                driver,
                gateway,
                keycode=keycode,
                metastate=metastate,
                flags=flags,
                long=False,
            ),
        )

    def long_press_keycode(
        self,
        keycode: int,
        *,
        metastate: int | None = None,
        flags: int | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        keycode, metastate, flags = _key_arguments(
            keycode, metastate, flags, operation_id
        )
        owner._reject_macos(operation_id)
        owner._reject_ios(operation_id)
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _press_keycode(
                driver,
                gateway,
                keycode=keycode,
                metastate=metastate,
                flags=flags,
                long=True,
            ),
        )

    def hide_keyboard(self, *, control: OperationControl | None = None) -> bool:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        owner._reject_macos(operation_id)
        return owner._run_operation(
            operation_id,
            control,
            deadline,
            _ios_hide_keyboard if owner.platform == "ios" else _hide_keyboard,
        )

    def get_clipboard_text(self, *, control: OperationControl | None = None) -> str:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        return owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _get_clipboard_text(
                driver,
                gateway,
                script="macos: getClipboard"
                if owner.platform == "macos"
                else "mobile: getClipboard",
            ),
        )

    def set_clipboard_text(
        self,
        text: str,
        *,
        label: str | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        content = _clipboard_content(text, operation_id)
        label = _label(label, operation_id)
        if owner.platform in ("macos", "ios") and label is not None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _set_clipboard_text(
                driver,
                gateway,
                content=content,
                label=label,
                script="macos: setClipboard"
                if owner.platform == "macos"
                else "mobile: setClipboard",
            ),
        )

    def accept_alert(
        self,
        *,
        button_label: str | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        button_label = _label(button_label, operation_id)
        owner._reject_macos(operation_id)
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _ios_alert(
                    driver,
                    gateway,
                    accept=True,
                    button_label=button_label,
                )
                if owner.platform == "ios"
                else _alert(driver, gateway, accept=True, button_label=button_label)
            ),
        )

    def dismiss_alert(
        self,
        *,
        button_label: str | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        button_label = _label(button_label, operation_id)
        owner._reject_macos(operation_id)
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _ios_alert(
                    driver,
                    gateway,
                    accept=False,
                    button_label=button_label,
                )
                if owner.platform == "ios"
                else _alert(driver, gateway, accept=False, button_label=button_label)
            ),
        )

    def take_screenshot(self, *, control: OperationControl | None = None) -> bytes:
        """Capture one bounded validated PNG screenshot in memory."""
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        return owner._run_operation(operation_id, control, deadline, _take_screenshot)

    def tap_at(
        self, x: int, y: int, *, control: OperationControl | None = None
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_x = _coordinate(x, operation_id)
        valid_y = _coordinate(y, operation_id)
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _macos_pointer_action(
                    driver,
                    gateway,
                    script="macos: click",
                    payload={"x": valid_x, "y": valid_y},
                )
                if owner.platform == "macos"
                else _ios_execute_none(
                    driver,
                    gateway,
                    "mobile: tap",
                    {"x": valid_x, "y": valid_y},
                )
                if owner.platform == "ios"
                else _tap_at(driver, gateway, x=valid_x, y=valid_y)
            ),
        )

    def click_at(
        self,
        x: int,
        y: int,
        *,
        button: Literal["left", "right"] = "left",
        double: bool = False,
        key_modifier_flags: int | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_x = _coordinate(x, operation_id)
        valid_y = _coordinate(y, operation_id)
        valid_button = _check_button(button, operation_id)
        valid_double = _check_bool(double, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        if valid_button == "right" and valid_double:
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        if owner.platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        owner._reject_ios(operation_id)
        script = (
            "macos: rightClick"
            if valid_button == "right"
            else "macos: doubleClick"
            if valid_double
            else "macos: click"
        )
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _macos_pointer_action(
                driver,
                gateway,
                script=script,
                payload={
                    "x": valid_x,
                    "y": valid_y,
                    **_modifier_payload(modifier_flags),
                },
            ),
        )

    def hover_at(
        self,
        x: int,
        y: int,
        *,
        key_modifier_flags: int | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_x = _coordinate(x, operation_id)
        valid_y = _coordinate(y, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        if owner.platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        owner._reject_ios(operation_id)
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _macos_pointer_action(
                driver,
                gateway,
                script="macos: hover",
                payload={
                    "x": valid_x,
                    "y": valid_y,
                    **_modifier_payload(modifier_flags),
                },
            ),
        )

    def scroll_at(
        self,
        x: int,
        y: int,
        *,
        delta_x: float,
        delta_y: float,
        key_modifier_flags: int | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_x = _coordinate(x, operation_id)
        valid_y = _coordinate(y, operation_id)
        valid_delta_x = _validate_number(delta_x, operation_id)
        valid_delta_y = _validate_number(delta_y, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        if owner.platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        owner._reject_ios(operation_id)
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _macos_pointer_action(
                driver,
                gateway,
                script="macos: scroll",
                payload={
                    "x": valid_x,
                    "y": valid_y,
                    "deltaX": valid_delta_x,
                    "deltaY": valid_delta_y,
                    **_modifier_payload(modifier_flags),
                },
            ),
        )

    def swipe_between(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        duration_ms: int = 200,
        key_modifier_flags: int | None = None,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_sx = _coordinate(start_x, operation_id)
        valid_sy = _coordinate(start_y, operation_id)
        valid_ex = _coordinate(end_x, operation_id)
        valid_ey = _coordinate(end_y, operation_id)
        valid_duration = _duration_ms(duration_ms, operation_id)
        modifier_flags = _validate_modifier_flags(key_modifier_flags, operation_id)
        if owner.platform in ("android", "ios") and modifier_flags is not None:
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _swipe_between(
                    driver,
                    gateway,
                    start_x=valid_sx,
                    start_y=valid_sy,
                    end_x=valid_ex,
                    end_y=valid_ey,
                    duration_ms=valid_duration,
                )
                if owner.platform in ("android", "ios")
                else _macos_pointer_action(
                    driver,
                    gateway,
                    script="macos: clickAndDrag",
                    payload={
                        "startX": valid_sx,
                        "startY": valid_sy,
                        "endX": valid_ex,
                        "endY": valid_ey,
                        **_modifier_payload(modifier_flags),
                    },
                    duration_seconds=valid_duration / 1000.0,
                )
            ),
        )

    def send_keys(
        self,
        keys: Sequence[str | MacKeyStroke],
        *,
        control: OperationControl | None = None,
    ) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        valid_keys = _validate_macos_keys(keys, operation_id)
        if owner.platform == "android":
            raise InvalidRequestError("unsupported_operation", operation_id, "not_sent")
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: (
                _ios_execute_none(driver, gateway, "mobile: keys", {"keys": valid_keys})
                if owner.platform == "ios"
                else _macos_send_keys(driver, gateway, valid_keys)
            ),
        )


def _validate_ios_app_path_lexical(app_path: object, operation_id: str) -> Path:
    if not isinstance(app_path, Path):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        encoded = str(app_path).encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if (
        not app_path.is_absolute()
        or app_path.suffix.casefold() not in {".app", ".ipa"}
        or len(encoded) > 4_096
        or any(unicodedata.category(character) == "Cc" for character in str(app_path))
        or ".." in app_path.parts
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return app_path


def _validate_apk_path_lexical(app_path: object, operation_id: str) -> Path:
    if not isinstance(app_path, Path):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        text = str(app_path)
        text.encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError):
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if (
        not app_path.is_absolute()
        or app_path.suffix != ".apk"
        or any(unicodedata.category(character) == "Cc" for character in text)
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return app_path


def _check_ios_app_path(app_path: object, operation_id: str) -> Path:
    from ._session import _validate_ios_app_path

    valid_path = _validate_ios_app_path(app_path, operation_id)
    if valid_path is None:
        raise RuntimeError("required iOS app path validation returned no path")
    return valid_path


def _check_app_path(app_path: object, operation_id: str) -> Path:
    if not isinstance(app_path, Path):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")

    # Import lazily because Session owns the single file-rule implementation
    # and creates Device while its own module is still being imported.
    from ._session import _validate_app_path

    valid_path = _validate_app_path(app_path, operation_id)
    if valid_path is None:
        raise RuntimeError("required app path validation returned no path")
    return valid_path


def _check_bool(value: object, operation_id: str) -> bool:
    if type(value) is not bool:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _checked_app_id(app_id: str, operation_id: str) -> str:
    if not _valid_package(app_id):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return app_id


def _check_press_button(
    value: object, operation_id: str
) -> Literal["home", "volumeUp", "volumeDown", "action", "camera"]:
    if not isinstance(value, str) or value not in {
        "home",
        "volumeUp",
        "volumeDown",
        "action",
        "camera",
    }:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return cast(Literal["home", "volumeUp", "volumeDown", "action", "camera"], value)


def _check_button(value: object, operation_id: str) -> Literal["left", "right"]:
    if value not in ("left", "right") or not isinstance(value, str):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    return value


def _bind_operation(
    device: Device, control: OperationControl | None
) -> tuple[Session, _PreparedOperation]:
    from ._session import Session, _new_operation

    operation = _new_operation(control)
    owner = getattr(device, "_owner", None)
    if (
        not isinstance(device, Device)
        or not all(hasattr(device, name) for name in Device.__slots__)
        or getattr(device, "_marker", None) is not _MARKER
        or not isinstance(owner, Session)
        or not all(hasattr(owner, name) for name in Session.__slots__)
        or getattr(owner, "_device", None) is not device
    ):
        raise InvalidRequestError("invalid_argument", operation[0], "not_sent")
    return owner, operation


def _create_device(owner: Session) -> Device:
    device = object.__new__(Device)
    object.__setattr__(device, "_owner", owner)
    object.__setattr__(device, "_marker", _MARKER)
    return device
