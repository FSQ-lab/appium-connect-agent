"""Immutable Session-bound locator descriptions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

from appium_connect_agent.runtime import OperationControl

from ._models import (
    ElementAttribute,
    ElementBy,
    ElementInspection,
    InvalidRequestError,
    RawStructureObservation,
)

if TYPE_CHECKING:
    from ._session import Session

_PreparedOperation: TypeAlias = tuple[str, OperationControl | None, float, float | None]

_PACKAGE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_LOCAL_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ALLOWED_BY = frozenset({"id", "accessibility id", "xpath"})
_CREATION_MARKER = object()


class ElementValidationError(ValueError):
    """A locator description is invalid without starting an operation."""

    def __init__(
        self,
        code: Literal[
            "invalid_argument", "unsupported_operation", "element_session_mismatch"
        ],
    ) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True, init=False)
class Element:
    by: ElementBy
    value: str
    package: str | None
    raw_id: bool
    parent: Element | None
    _owner: object = field(repr=False, compare=False)
    _marker: object = field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("Element objects are created by Session.element")

    def inspect(
        self,
        *,
        attributes: tuple[ElementAttribute, ...],
        control: OperationControl | None = None,
    ) -> ElementInspection:
        owner, operation = _bind_operation(self, control)
        return owner._inspect_element(self, operation, attributes=attributes)

    def inspect_structure(
        self,
        *,
        scope: Literal["target", "declared_parent"] = "declared_parent",
        control: OperationControl | None = None,
    ) -> RawStructureObservation:
        owner, operation = _bind_operation(self, control)
        return owner._inspect_structure(self, operation, scope=scope)

    def click(
        self,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._click(self, operation, wait_timeout_seconds=wait_timeout_seconds)

    def double_click(
        self,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._double_click(self, operation, wait_timeout_seconds=wait_timeout_seconds)

    def long_click(
        self,
        *,
        duration_ms: int = 500,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._long_click(
            self,
            operation,
            duration_ms=duration_ms,
            wait_timeout_seconds=wait_timeout_seconds,
        )

    def send_keys(
        self,
        text: str,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._send_keys(
            self, text, operation, wait_timeout_seconds=wait_timeout_seconds
        )

    def clear(
        self,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._clear(self, operation, wait_timeout_seconds=wait_timeout_seconds)

    def replace_element_value(
        self,
        text: str,
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._replace_element_value(
            self, text, operation, wait_timeout_seconds=wait_timeout_seconds
        )

    def swipe_gesture(
        self,
        *,
        direction: Literal["up", "down", "left", "right"],
        percent: float,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._swipe_gesture(
            self,
            operation,
            direction=direction,
            percent=percent,
            wait_timeout_seconds=wait_timeout_seconds,
        )

    def scroll_gesture(
        self,
        *,
        direction: Literal["up", "down", "left", "right"],
        percent: float,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> bool:
        owner, operation = _bind_operation(self, control)
        return owner._scroll_gesture(
            self,
            operation,
            direction=direction,
            percent=percent,
            wait_timeout_seconds=wait_timeout_seconds,
        )

    def scroll(
        self,
        target: Element,
        *,
        max_swipes: int,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._scroll(
            self,
            target,
            operation,
            max_swipes=max_swipes,
            wait_timeout_seconds=wait_timeout_seconds,
        )

    def drag_and_drop(
        self,
        destination: Element,
        *,
        destination_x_ratio: float,
        destination_y_ratio: float,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._drag_and_drop(
            self,
            destination,
            operation,
            destination_x_ratio=destination_x_ratio,
            destination_y_ratio=destination_y_ratio,
            wait_timeout_seconds=wait_timeout_seconds,
        )

    def perform_editor_action(
        self,
        action: Literal[
            "normal",
            "unspecified",
            "none",
            "go",
            "search",
            "send",
            "next",
            "done",
            "previous",
        ],
        *,
        wait_timeout_seconds: float = 15.0,
        control: OperationControl | None = None,
    ) -> None:
        owner, operation = _bind_operation(self, control)
        owner._perform_editor_action(
            self, action, operation, wait_timeout_seconds=wait_timeout_seconds
        )


def _bind_operation(
    element: Element, control: OperationControl | None
) -> tuple[Session, _PreparedOperation]:
    from ._session import Session, _new_operation

    operation = _new_operation(control)
    owner = getattr(element, "_owner", None)
    if (
        not isinstance(element, Element)
        or not isinstance(owner, Session)
        or not all(hasattr(owner, name) for name in Session.__slots__)
    ):
        raise InvalidRequestError("invalid_argument", operation[0], "not_sent")
    return owner, operation


def _create(
    by: ElementBy,
    value: str,
    package: str | None,
    raw_id: bool,
    parent: Element | None,
    owner: object,
) -> Element:
    result = object.__new__(Element)
    object.__setattr__(result, "by", by)
    object.__setattr__(result, "value", value)
    object.__setattr__(result, "package", package)
    object.__setattr__(result, "raw_id", raw_id)
    object.__setattr__(result, "parent", parent)
    object.__setattr__(result, "_owner", owner)
    object.__setattr__(result, "_marker", _CREATION_MARKER)
    return result


def _valid_package(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 255
        and _PACKAGE.fullmatch(value) is not None
    )


def _standard_resource_id(value: str, package: str | None) -> str | None:
    if value.count(":id/") != 1:
        return None
    prefix, local = value.split(":id/")
    if (
        prefix != package
        or not _valid_package(prefix)
        or _LOCAL_ID.fullmatch(local) is None
    ):
        return None
    return local


def _has_control(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _make_element(
    owner: object,
    target_app_id: str | None,
    by: object,
    value: object,
    *,
    parent: object = None,
    package: object = None,
    raw_id: object = False,
) -> Element:
    if not isinstance(by, str) or by not in _ALLOWED_BY:
        raise ElementValidationError("invalid_argument")
    if not isinstance(value, str) or not 1 <= len(value) <= 4_096 or "\0" in value:
        raise ElementValidationError("invalid_argument")
    if type(raw_id) is not bool:
        raise ElementValidationError("invalid_argument")
    if parent is not None:
        if not isinstance(parent, Element):
            raise ElementValidationError("invalid_argument")
        if parent._owner is not owner or parent._marker is not _CREATION_MARKER:
            raise ElementValidationError("element_session_mismatch")
        depth = 1
        seen: set[int] = set()
        ancestor: Element | None = parent
        while ancestor is not None:
            identity = id(ancestor)
            if identity in seen:
                raise ElementValidationError("invalid_argument")
            seen.add(identity)
            if ancestor._owner is not owner or ancestor._marker is not _CREATION_MARKER:
                raise ElementValidationError("element_session_mismatch")
            depth += 1
            ancestor = ancestor.parent
        if depth > 16:
            raise ElementValidationError("invalid_argument")
        if by == "xpath":
            raise ElementValidationError("unsupported_operation")

    strategy = cast(ElementBy, by)
    valid_parent: Element | None = parent if isinstance(parent, Element) else None
    if strategy != "id":
        if package is not None or raw_id:
            raise ElementValidationError("invalid_argument")
        return _create(strategy, value, None, False, valid_parent, owner)

    if raw_id:
        if package is not None or _has_control(value):
            raise ElementValidationError("invalid_argument")
        return _create("id", value, None, True, valid_parent, owner)

    if package is not None and not _valid_package(package):
        raise ElementValidationError("invalid_argument")
    valid_package = cast(str | None, package)
    marker = ":id/"
    if value.count(marker) == 1:
        prefix, local = value.split(marker)
        if not _valid_package(prefix) or _LOCAL_ID.fullmatch(local) is None:
            raise ElementValidationError("invalid_argument")
        if valid_package is not None and valid_package != prefix:
            raise ElementValidationError("invalid_argument")
        return _create("id", value, prefix, False, valid_parent, owner)
    if _LOCAL_ID.fullmatch(value) is None:
        raise ElementValidationError("invalid_argument")
    source = valid_package
    if source is None and _valid_package(target_app_id):
        source = target_app_id
    normalized = f"{source}:id/{value}" if source is not None else value
    return _create("id", normalized, source, False, valid_parent, owner)


def _trusted_chain_error(element: Element, owner: object) -> str | None:
    reversed_chain: list[Element] = []
    seen: set[int] = set()
    current: object = element
    while current is not None:
        if not isinstance(current, Element):
            return "invalid_argument"
        if not all(hasattr(current, name) for name in Element.__slots__):
            return "invalid_argument"
        identity = id(current)
        if identity in seen or len(reversed_chain) == 16:
            return "invalid_argument"
        seen.add(identity)
        if getattr(current, "_marker", None) is not _CREATION_MARKER:
            return "invalid_argument"
        if getattr(current, "_owner", None) is not owner:
            return "element_session_mismatch"
        by = getattr(current, "by", None)
        value = getattr(current, "value", None)
        package = getattr(current, "package", None)
        raw_id = getattr(current, "raw_id", None)
        parent = getattr(current, "parent", None)
        if (
            not isinstance(by, str)
            or by not in _ALLOWED_BY
            or not isinstance(value, str)
            or not 1 <= len(value) <= 4_096
            or "\0" in value
            or type(raw_id) is not bool
        ):
            return "invalid_argument"
        if by != "id":
            if package is not None or raw_id or (by == "xpath" and parent is not None):
                return "invalid_argument"
        elif raw_id:
            if package is not None or _has_control(value):
                return "invalid_argument"
        else:
            if package is not None and not _valid_package(package):
                return "invalid_argument"
            marker = ":id/"
            if value.count(marker) == 1:
                prefix, local = value.split(marker)
                if (
                    not _valid_package(prefix)
                    or _LOCAL_ID.fullmatch(local) is None
                    or package != prefix
                ):
                    return "invalid_argument"
            elif _LOCAL_ID.fullmatch(value) is None or package is not None:
                return "invalid_argument"
        reversed_chain.append(current)
        current = parent
    return None


def _locator_chain(element: Element) -> tuple[Element, ...]:
    reversed_chain: list[Element] = []
    current: Element | None = element
    while current is not None:
        reversed_chain.append(current)
        current = current.parent
    reversed_chain.reverse()
    return tuple(reversed_chain)
