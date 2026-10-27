"""Immutable system-action namespace owned by one Session."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from appium_connect_agent.runtime import OperationControl

from ._element import _PreparedOperation
from ._models import InvalidRequestError
from ._system_actions import (
    _alert,
    _back,
    _clipboard_content,
    _get_clipboard_text,
    _hide_keyboard,
    _key_arguments,
    _label,
    _press_keycode,
    _set_clipboard_text,
    _status_bar,
    _status_bar_command,
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

    def status_bar(
        self,
        command: Literal["expandNotifications", "expandSettings", "collapse"],
        *,
        control: OperationControl | None = None,
    ) -> str:
        """Send one panel command; output does not prove panel visibility."""
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        command = _status_bar_command(command, operation_id)
        return owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _status_bar(driver, gateway, command),
        )

    def back(self, *, control: OperationControl | None = None) -> None:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        owner._run_operation(operation_id, control, deadline, _back)

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
        return owner._run_operation(operation_id, control, deadline, _hide_keyboard)

    def get_clipboard_text(self, *, control: OperationControl | None = None) -> str:
        owner, (operation_id, control, _, deadline) = _bind_operation(self, control)
        return owner._run_operation(
            operation_id, control, deadline, _get_clipboard_text
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
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _set_clipboard_text(
                driver, gateway, content=content, label=label
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
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _alert(
                driver, gateway, accept=True, button_label=button_label
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
        owner._run_operation(
            operation_id,
            control,
            deadline,
            lambda driver, gateway: _alert(
                driver, gateway, accept=False, button_label=button_label
            ),
        )


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
