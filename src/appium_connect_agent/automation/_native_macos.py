"""Local CoreGraphics desktop primitives, independent of Appium Sessions."""

from __future__ import annotations

import ctypes as C
import math
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from functools import cache
from threading import Event, Lock
from time import monotonic, sleep
from typing import Any, Literal, cast
from uuid import uuid4

from appium_connect_agent.runtime import OperationControl

from ._macos_keyboard import (
    MACOS_MODIFIER_COMMAND,
    MACOS_MODIFIER_CONTROL,
    MACOS_MODIFIER_OPTION,
    MACOS_MODIFIER_SHIFT,
    MacKeyStroke,
)
from ._models import (
    Bounds,
    CommandError,
    InvalidRequestError,
    OperationCancelledError,
    OperationTimeoutError,
    RequestState,
    TargetError,
)

# CoreGraphics CGEventTypes.h and HIToolbox Events.h (ANSI physical keys).
_BUTTONS = {"left": (0, 1, 2), "right": (1, 3, 4), "middle": (2, 25, 26)}
_MOUSE_MOVED, _LEFT_DRAGGED = 5, 6
_CLICK_STATE = 1
_KEY_CODES = dict(
    zip(
        "abcdefghijklmnopqrstuvwxyz0123456789",
        (
            0,
            11,
            8,
            2,
            14,
            3,
            5,
            4,
            34,
            38,
            40,
            37,
            46,
            45,
            31,
            35,
            12,
            15,
            1,
            17,
            32,
            9,
            13,
            7,
            16,
            6,
            29,
            18,
            19,
            20,
            21,
            23,
            22,
            26,
            28,
            25,
        ),
        strict=True,
    )
)
_KEY_CODES.update(
    escape=53,
    return_=36,
    enter=36,
    tab=48,
    space=49,
    backspace=51,
    delete=51,
    forwarddelete=117,
    leftarrow=123,
    rightarrow=124,
    downarrow=125,
    uparrow=126,
    home=115,
    end=119,
    pageup=116,
    pagedown=121,
)
_KEY_CODES["return"] = _KEY_CODES.pop("return_")
_KEY_CODES.update(
    (f"f{number}", code)
    for number, code in enumerate(
        (
            122,
            120,
            99,
            118,
            96,
            97,
            98,
            100,
            101,
            109,
            103,
            111,
            105,
            107,
            113,
            106,
            64,
            79,
            80,
        ),
        1,
    )
)
_KEY_ALIASES = {
    " ": "space",
    "arrowleft": "leftarrow",
    "arrowright": "rightarrow",
    "arrowdown": "downarrow",
    "arrowup": "uparrow",
}
_XCUI_KEYS = {
    f"XCUIKeyboardKey{name}": _KEY_CODES[name.lower()]
    for name in (
        "Delete",
        "Return",
        "Tab",
        "Space",
        "Escape",
        "UpArrow",
        "DownArrow",
        "LeftArrow",
        "RightArrow",
        "ForwardDelete",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        *(f"F{number}" for number in range(1, 20)),
    )
}
_XCUI_KEYS["XCUIKeyboardKeyEnter"] = 76
_MODIFIERS = (
    (MACOS_MODIFIER_SHIFT, 0x00020000),
    (MACOS_MODIFIER_CONTROL, 0x00040000),
    (MACOS_MODIFIER_OPTION, 0x00080000),
    (MACOS_MODIFIER_COMMAND, 0x00100000),
)
_MODIFIER_MASK = sum(bit for bit, _ in _MODIFIERS)
_NEWLINE = re.compile(r"\r\n|\r|\n")
_SURROGATE = re.compile(r"[\ud800-\udfff]")
_DESKTOP_INPUT = Lock()


class _Point(C.Structure):
    _fields_ = (("x", C.c_double), ("y", C.c_double))
    x: float
    y: float


class _Size(C.Structure):
    _fields_ = (("width", C.c_double), ("height", C.c_double))
    width: float
    height: float


class _Rect(C.Structure):
    _fields_ = (("origin", _Point), ("size", _Size))
    origin: _Point
    size: _Size


def _bind(
    library: C.CDLL, name: str, result: type | None, *args: type
) -> Callable[..., Any]:
    function = library[name]
    function.restype = result
    function.argtypes = args
    return function


class _Quartz:
    def __init__(self) -> None:
        cg = C.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        self.main_display = _bind(cg, "CGMainDisplayID", C.c_uint32)
        self.display_bounds = _bind(cg, "CGDisplayBounds", _Rect, C.c_uint32)
        self.preflight = _bind(cg, "CGPreflightPostEventAccess", C.c_bool)
        self.source = _bind(cg, "CGEventSourceCreate", C.c_void_p, C.c_int32)
        self.mouse = _bind(
            cg,
            "CGEventCreateMouseEvent",
            C.c_void_p,
            C.c_void_p,
            C.c_uint32,
            _Point,
            C.c_uint32,
        )
        self.keyboard = _bind(
            cg,
            "CGEventCreateKeyboardEvent",
            C.c_void_p,
            C.c_void_p,
            C.c_uint16,
            C.c_bool,
        )
        self.scroll = _bind(
            cg,
            "CGEventCreateScrollWheelEvent2",
            C.c_void_p,
            C.c_void_p,
            C.c_uint32,
            C.c_uint32,
            C.c_int32,
            C.c_int32,
            C.c_int32,
        )
        self.flags = _bind(cg, "CGEventSetFlags", None, C.c_void_p, C.c_uint64)
        self.integer = _bind(
            cg, "CGEventSetIntegerValueField", None, C.c_void_p, C.c_uint32, C.c_int64
        )
        self.location = _bind(cg, "CGEventSetLocation", None, C.c_void_p, _Point)
        self.unicode = _bind(
            cg,
            "CGEventKeyboardSetUnicodeString",
            None,
            C.c_void_p,
            C.c_ulong,
            C.POINTER(C.c_uint16),
        )
        self.post = _bind(cg, "CGEventPost", None, C.c_uint32, C.c_void_p)
        cf = C.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self.release = _bind(cf, "CFRelease", None, C.c_void_p)


@cache
def _quartz() -> _Quartz:
    return _Quartz()


class _Operation:
    deadline: float | None
    cancellation: Event | None
    posted: bool

    def __init__(self, control: OperationControl | None) -> None:
        self.id = uuid4().hex
        if sys.platform != "darwin":
            raise InvalidRequestError("unsupported_platform", self.id, "not_sent")
        if control is not None and not isinstance(control, OperationControl):
            raise self.invalid()
        self.deadline = (
            None if control is None else monotonic() + control.timeout_seconds
        )
        self.cancellation = None if control is None else control.cancellation
        self.posted = False

    @property
    def state(self) -> RequestState:
        return "response_unknown" if self.posted else "not_sent"

    def invalid(self) -> InvalidRequestError:
        return InvalidRequestError("invalid_argument", self.id, "not_sent")

    def checkpoint(self) -> None:
        if self.cancellation is not None and self.cancellation.is_set():
            raise OperationCancelledError("operation_cancelled", self.id, self.state)
        if self.deadline is not None and monotonic() >= self.deadline:
            raise OperationTimeoutError("operation_timeout", self.id, self.state)

    def pause(self, seconds: float) -> None:
        self.checkpoint()
        if self.deadline is not None:
            seconds = min(seconds, self.deadline - monotonic())
        if seconds > 0:
            if self.cancellation is None:
                sleep(seconds)
            else:
                self.cancellation.wait(seconds)
        self.checkpoint()

    def backend(self) -> _Quartz:
        self.checkpoint()
        try:
            return _quartz()
        except (OSError, AttributeError):
            raise CommandError(
                "native_backend_unavailable", self.id, self.state
            ) from None


def _number(value: float, op: _Operation) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise op.invalid()
    try:
        number = float(value)
    except OverflowError:
        raise op.invalid() from None
    if not math.isfinite(number):
        raise op.invalid()
    return number


def _wheel(value: float, op: _Operation) -> int:
    number = _number(value, op)
    if not -32767 <= number <= 32767 or not number.is_integer():
        raise op.invalid()
    return int(number)


def _flags(modifiers: int, op: _Operation) -> int:
    if type(modifiers) is not int or modifiers & ~_MODIFIER_MASK:
        raise op.invalid()
    return sum(native for bit, native in _MODIFIERS if modifiers & bit)


def _key(value: str | MacKeyStroke, op: _Operation) -> tuple[int, int]:
    key, modifiers = (
        (value.key, value.modifier_flags)
        if isinstance(value, MacKeyStroke)
        else (value, 0)
    )
    if not isinstance(key, str) or not key.isascii():
        raise op.invalid()
    name = key.lower()
    if name.startswith("xcuikeyboardkey"):
        code = _XCUI_KEYS.get(key)
    else:
        code = _KEY_CODES.get(_KEY_ALIASES.get(name, name))
    if code is None:
        raise op.invalid()
    return code, _flags(modifiers, op)


class _Input:
    def __init__(
        self,
        quartz: _Quartz,
        source: int,
        op: _Operation,
        foreground: Callable[[], bool] | None,
    ) -> None:
        self.q = quartz
        self.source = source
        self.op = op
        self.foreground = foreground

    def guard(self) -> None:
        self.op.checkpoint()
        if self.foreground is not None:
            try:
                approved: object = self.foreground()
            except Exception:
                approved = None
            self.op.checkpoint()
            if approved is not True:
                code = (
                    "target_not_foreground"
                    if approved is False
                    else "foreground_unobservable"
                )
                raise TargetError(code, self.op.id, self.op.state)

    @contextmanager
    def event(self, event: int | None) -> Iterator[int]:
        if event is None:
            raise CommandError("native_input_failed", self.op.id, self.op.state)
        try:
            yield event
        finally:
            self.q.release(event)

    def post(self, event: int) -> None:
        self.op.posted = (
            True  # CGEventPost is void; an attempted write is not reversible.
        )
        self.q.post(0, event)  # kCGHIDEventTap

    @contextmanager
    def held(self, down: int, up: int) -> Iterator[None]:
        self.guard()
        try:
            self.post(down)
            yield
            self.guard()
        finally:
            # Already allocated before down. Release even after a failed guard, without
            # waiting for the cancellation/deadline or issuing any further normal action.
            self.post(up)

    def move(self, point: _Point) -> None:
        with self.event(self.q.mouse(self.source, _MOUSE_MOVED, point, 0)) as event:
            self.q.flags(event, 0)
            self.guard()
            self.post(event)

    def click(
        self, point: _Point, button: tuple[int, int, int], count: int, flags: int
    ) -> None:
        number, down_type, up_type = button
        self.move(point)
        for index in range(1, count + 1):
            if index > 1:
                self.op.pause(0.04)
            with (
                self.event(self.q.mouse(self.source, down_type, point, number)) as down,
                self.event(self.q.mouse(self.source, up_type, point, number)) as up,
            ):
                self.q.integer(down, _CLICK_STATE, index)
                self.q.integer(up, _CLICK_STATE, index)
                self.q.flags(down, flags)
                self.q.flags(up, flags)
                with self.held(down, up):
                    self.op.pause(0.025)

    def wheel(self, point: _Point, dx: int, dy: int, unit: int, flags: int) -> None:
        with self.event(self.q.scroll(self.source, unit, 2, dy, dx, 0)) as event:
            self.q.location(event, point)
            self.q.flags(event, flags)
            self.move(point)
            self.guard()
            self.post(event)

    def drag(self, start: _Point, end: _Point, duration: float, flags: int) -> None:
        self.move(start)
        steps = math.ceil(duration * 60)
        with (
            self.event(self.q.mouse(self.source, 1, start, 0)) as down,
            self.event(self.q.mouse(self.source, 2, start, 0)) as up,
        ):
            self.q.integer(down, _CLICK_STATE, 1)
            self.q.integer(up, _CLICK_STATE, 1)
            self.q.flags(down, flags)
            self.q.flags(up, flags)
            with self.held(down, up):
                began = monotonic()
                for index in range(1, steps + 1):
                    fraction = index / steps
                    self.op.pause(began + duration * fraction - monotonic())
                    p = _Point(
                        start.x * (1 - fraction) + end.x * fraction,
                        start.y * (1 - fraction) + end.y * fraction,
                    )
                    with self.event(
                        self.q.mouse(self.source, _LEFT_DRAGGED, p, 0)
                    ) as event:
                        self.q.flags(event, flags)
                        self.guard()
                        self.q.location(up, p)
                        self.post(event)

    def stroke(self, key: int, flags: int, text: str = "") -> None:
        with (
            self.event(self.q.keyboard(self.source, key, True)) as down,
            self.event(self.q.keyboard(self.source, key, False)) as up,
        ):
            self.q.flags(down, flags)
            self.q.flags(up, 0)
            if text:
                data = text.encode("utf-16-le")
                units = (C.c_uint16 * (len(data) // 2)).from_buffer_copy(data)
                self.q.unicode(down, len(units), units)
                self.q.unicode(up, len(units), units)
            with self.held(down, up):
                pass


def _text_strokes(text: str) -> Iterator[tuple[int, int, str]]:
    def chunks(start: int, stop: int) -> Iterator[tuple[int, int, str]]:
        # At most 20 UTF-16 code units, and a non-BMP scalar stays in one event.
        for index in range(start, stop, 10):
            yield 0, 0, text[index : min(index + 10, stop)]

    begin = 0
    for newline in _NEWLINE.finditer(text):
        yield from chunks(begin, newline.start())
        yield 36, 0, ""
        begin = newline.end()
    yield from chunks(begin, len(text))


class NativeMacOSDesktop:
    """Post local Quartz input without activating an app or touching Appium."""

    def __init__(self, *, foreground_check: Callable[[], bool] | None = None) -> None:
        self._foreground = foreground_check

    @contextmanager
    def _input(self, op: _Operation) -> Iterator[_Input]:
        if self._foreground is not None and not callable(self._foreground):
            raise op.invalid()
        op.checkpoint()
        # The desktop is shared even across executor objects within this process.
        while not _DESKTOP_INPUT.acquire(blocking=False):
            op.pause(0.01)
        try:
            q = op.backend()
            try:
                if not q.preflight():
                    raise CommandError(
                        "native_input_permission_denied", op.id, op.state
                    )
                op.checkpoint()
                source = cast(int | None, q.source(-1))  # kCGEventSourceStatePrivate
                if source is None:
                    raise CommandError("native_input_failed", op.id, op.state)
                try:
                    stream = _Input(q, source, op, self._foreground)
                    yield stream
                    stream.guard()
                finally:
                    q.release(source)
            except (C.ArgumentError, OSError):
                raise CommandError("native_input_failed", op.id, op.state) from None
        finally:
            _DESKTOP_INPUT.release()

    def click_at(
        self,
        x: float,
        y: float,
        *,
        button: Literal["left", "right", "middle"] = "left",
        click_count: int = 1,
        modifier_flags: int = 0,
        control: OperationControl | None = None,
    ) -> None:
        """Post one to three paired clicks of the selected mouse button."""
        op = _Operation(control)
        point = _Point(_number(x, op), _number(y, op))
        flags = _flags(modifier_flags, op)
        if not isinstance(button, str) or button not in _BUTTONS:
            raise op.invalid()
        if type(click_count) is not int or not 1 <= click_count <= 3:
            raise op.invalid()
        with self._input(op) as stream:
            stream.click(point, _BUTTONS[button], click_count, flags)

    def hover_at(
        self, x: float, y: float, *, control: OperationControl | None = None
    ) -> None:
        """Move the pointer to global display coordinates in logical points."""
        op = _Operation(control)
        point = _Point(_number(x, op), _number(y, op))
        with self._input(op) as stream:
            stream.move(point)

    def scroll_at(
        self,
        x: float,
        y: float,
        delta_x: float,
        delta_y: float,
        *,
        unit: Literal["pixel", "line"] = "pixel",
        modifier_flags: int = 0,
        control: OperationControl | None = None,
    ) -> None:
        """Move to the point and post a two-axis Quartz scroll (positive up/left)."""
        op = _Operation(control)
        point = _Point(_number(x, op), _number(y, op))
        dx, dy = _wheel(delta_x, op), _wheel(delta_y, op)
        flags = _flags(modifier_flags, op)
        if unit not in ("pixel", "line"):
            raise op.invalid()
        with self._input(op) as stream:
            stream.wheel(point, dx, dy, int(unit == "line"), flags)

    def drag_between(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        *,
        duration_ms: int = 250,
        modifier_flags: int = 0,
        control: OperationControl | None = None,
    ) -> None:
        """Post a left-button drag along interpolated global logical points."""
        op = _Operation(control)
        start = _Point(_number(start_x, op), _number(start_y, op))
        end = _Point(_number(end_x, op), _number(end_y, op))
        flags = _flags(modifier_flags, op)
        if type(duration_ms) is not int or not 50 <= duration_ms <= 5000:
            raise op.invalid()
        with self._input(op) as stream:
            stream.drag(start, end, duration_ms / 1000, flags)

    def send_keys(
        self,
        keys: Sequence[str | MacKeyStroke],
        *,
        control: OperationControl | None = None,
    ) -> None:
        """Post physical key strokes with event-local modifier flags."""
        op = _Operation(control)
        op.checkpoint()
        if not isinstance(keys, Sequence) or isinstance(keys, (str, bytes, bytearray)):
            raise op.invalid()
        parsed = []
        for key in keys:
            op.checkpoint()
            parsed.append(_key(key, op))
        with self._input(op) as stream:
            for code, flags in parsed:
                stream.stroke(code, flags)

    def type_text(self, text: str, *, control: OperationControl | None = None) -> None:
        """Post Unicode chunks and explicit Return strokes, without a clipboard."""
        op = _Operation(control)
        op.checkpoint()
        if not isinstance(text, str) or _SURROGATE.search(text) is not None:
            raise op.invalid()
        with self._input(op) as stream:
            for code, flags, chunk in _text_strokes(text):
                stream.stroke(code, flags, chunk)


def macos_main_display_bounds(*, control: OperationControl | None = None) -> Bounds:
    """Read the native main display's global rectangle in logical points."""
    op = _Operation(control)
    q = op.backend()
    try:
        op.checkpoint()
        display = q.main_display()
        if display:
            rect = cast(_Rect, q.display_bounds(display))
            values = (rect.origin.x, rect.origin.y, rect.size.width, rect.size.height)
            op.checkpoint()
            if (
                all(math.isfinite(v) and v.is_integer() for v in values)
                and min(values[2:]) > 0
            ):
                return Bounds(*(int(v) for v in values))
    except (C.ArgumentError, OSError):
        raise CommandError("native_display_unavailable", op.id, op.state) from None
    op.checkpoint()
    raise CommandError("native_display_unavailable", op.id, op.state)
