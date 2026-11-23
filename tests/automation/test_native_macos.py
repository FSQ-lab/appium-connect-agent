"""Exercise the public native API with deterministic Quartz events; never post to Aqua."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from threading import Event
from types import SimpleNamespace
from typing import Literal

import pytest

from appium_connect_agent.automation import (
    MACOS_MODIFIER_COMMAND,
    MACOS_MODIFIER_CONTROL,
    MACOS_MODIFIER_OPTION,
    MACOS_MODIFIER_SHIFT,
    Bounds,
    CommandError,
    InvalidRequestError,
    MacKeyStroke,
    NativeMacOSDesktop,
    OperationCancelledError,
    OperationTimeoutError,
    TargetError,
    macos_main_display_bounds,
)
from appium_connect_agent.automation import _native_macos as native
from appium_connect_agent.runtime import OperationControl


@dataclass
class Posted:
    kind: str
    detail: tuple[object, ...]
    at: tuple[float, float] | None = None
    flags: int = -1
    clicks: int = 0
    utf16: tuple[int, ...] = ()


class Quartz:
    def __init__(self) -> None:
        self.allowed = True
        self.preflight_count = 0
        self.display = 7
        self.rect = native._Rect(native._Point(0, 0), native._Size(1512, 982))
        self.posted: list[Posted] = []
        self.handles: dict[int, Posted] = {}
        self.next_id = 1
        self.fail_up = False

    def main_display(self) -> int:
        return self.display

    def display_bounds(self, display: int) -> native._Rect:
        assert display == self.display != 0
        return self.rect

    def preflight(self) -> bool:
        self.preflight_count += 1
        return self.allowed

    def _create(self, event: Posted) -> int:
        handle = self.next_id
        self.next_id += 1
        self.handles[handle] = event
        return handle

    def source(self, state: int) -> int:
        return self._create(Posted("source", (state,)))

    def mouse(self, source: int, kind: int, pt: native._Point, button: int) -> int:
        assert self.handles[source].detail == (-1,)
        return self._create(Posted("mouse", (kind, button), (pt.x, pt.y)))

    def keyboard(self, source: int, key: int, down: bool) -> int | None:
        assert self.handles[source].kind == "source"
        if not down and self.fail_up:
            return None
        return self._create(Posted("key", (key, down)))

    def scroll(self, source: int, *parameters: int) -> int:
        assert self.handles[source].kind == "source"
        return self._create(Posted("scroll", parameters))

    def flags(self, handle: int, value: int) -> None:
        self.handles[handle].flags = value

    def unicode(self, handle: int, length: int, units: Iterator[int]) -> None:
        payload = tuple(units)
        assert len(payload) == length
        self.handles[handle].utf16 = payload

    def integer(self, handle: int, field: int, value: int) -> None:
        assert field == 1  # kCGMouseEventClickState
        self.handles[handle].clicks = value

    def location(self, handle: int, point: native._Point) -> None:
        self.handles[handle].at = (point.x, point.y)

    def post(self, tap: int, handle: int) -> None:
        assert tap == 0  # kCGHIDEventTap
        self.posted.append(replace(self.handles[handle]))

    def release(self, handle: int) -> None:
        del self.handles[handle]


class Clock:
    now = 0.0

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def quartz(monkeypatch: pytest.MonkeyPatch) -> Iterator[Quartz]:
    q = Quartz()
    clock = Clock()
    monkeypatch.setattr(native, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(native, "_quartz", lambda: q)
    monkeypatch.setattr(native, "monotonic", lambda: clock.now)
    monkeypatch.setattr(native, "sleep", clock.advance)
    yield q
    assert q.handles == {}  # covers allocation failures and guard/cancel exits


@pytest.mark.parametrize(
    ("key", "code"),
    [
        ("Escape", 53),
        ("Return", 36),
        ("Enter", 36),
        ("XCUIKeyboardKeyEnter", 76),
        ("XCUIKeyboardKeyReturn", 36),
        ("Tab", 48),
        ("Space", 49),
        (" ", 49),
        ("Backspace", 51),
        ("Delete", 51),
        ("ForwardDelete", 117),
        ("ArrowLeft", 123),
        ("RightArrow", 124),
        ("ArrowDown", 125),
        ("XCUIKeyboardKeyUpArrow", 126),
        ("F1", 122),
        ("F19", 80),
        ("XCUIKeyboardKeyF5", 96),
        ("XCUIKeyboardKeyForwardDelete", 117),
        ("s", 1),
        ("G", 5),
        ("4", 21),
        ("Home", 115),
        ("PageDown", 121),
    ],
)
def test_physical_key_posts_correct_pair(quartz: Quartz, key: str, code: int) -> None:
    NativeMacOSDesktop().send_keys([key])
    assert quartz.posted == [
        Posted("key", (code, True), flags=0),
        Posted("key", (code, False), flags=0),
    ]


def test_modifier_masks_do_not_leak_between_keys_and_pointer(quartz: Quartz) -> None:
    desktop = NativeMacOSDesktop()
    desktop.send_keys(
        [
            MacKeyStroke("g", MACOS_MODIFIER_COMMAND | MACOS_MODIFIER_SHIFT),
            MacKeyStroke("s", MACOS_MODIFIER_OPTION | MACOS_MODIFIER_CONTROL),
            "Escape",
        ]
    )
    desktop.hover_at(10, 20)
    assert [event.flags for event in quartz.posted] == [
        0x120000,
        0,
        0xC0000,
        0,
        0,
        0,
        0,
    ]
    assert [event.detail for event in quartz.posted[:-1]] == [
        (5, True),
        (5, False),
        (1, True),
        (1, False),
        (53, True),
        (53, False),
    ]


def test_unicode_keeps_surrogates_together_and_posts_newlines_as_return(
    quartz: Quartz,
) -> None:
    NativeMacOSDesktop().type_text("123456789😀界\r\nβ\r\n\n文\r")
    downs = quartz.posted[::2]
    expected = [
        (0, (49, 50, 51, 52, 53, 54, 55, 56, 57, 0xD83D, 0xDE00)),
        (0, (0x754C,)),
        (36, ()),
        (0, (0x03B2,)),
        (36, ()),
        (36, ()),
        (0, (0x6587,)),
        (36, ()),
    ]
    assert [(event.detail[0], event.utf16) for event in downs] == expected
    assert [(event.detail, event.utf16) for event in quartz.posted[1::2]] == [
        ((key, False), text) for key, text in expected
    ]
    assert all(event.flags == 0 for event in quartz.posted)


@pytest.mark.parametrize(
    ("button", "number", "down", "up"),
    [
        ("left", 0, 1, 2),
        ("right", 1, 3, 4),
        ("middle", 2, 25, 26),
    ],
)
def test_multiclick_sets_same_count_on_both_events(
    quartz: Quartz,
    button: Literal["left", "right", "middle"],
    number: int,
    down: int,
    up: int,
) -> None:
    NativeMacOSDesktop().click_at(
        -120.5, 9, button=button, click_count=3, modifier_flags=MACOS_MODIFIER_CONTROL
    )
    move, *pairs = quartz.posted
    assert move == Posted("mouse", (5, 0), (-120.5, 9), 0)
    assert [(event.detail, event.clicks, event.flags, event.at) for event in pairs] == [
        ((kind, number), count, 0x40000, (-120.5, 9))
        for count in range(1, 4)
        for kind in (down, up)
    ]


@pytest.mark.parametrize(("unit", "value"), [("pixel", 0), ("line", 1)])
def test_scroll_posts_vertical_then_horizontal_axis_at_pointer(
    quartz: Quartz, unit: Literal["pixel", "line"], value: int
) -> None:
    NativeMacOSDesktop().scroll_at(
        81, -9, -24, 52.0, unit=unit, modifier_flags=MACOS_MODIFIER_SHIFT
    )
    assert quartz.posted == [
        Posted("mouse", (5, 0), (81, -9), 0),
        Posted("scroll", (value, 2, 52, -24, 0), (81, -9), 0x20000),
    ]


def test_drag_interpolates_and_releases_at_destination(quartz: Quartz) -> None:
    NativeMacOSDesktop().drag_between(10, 20, 40, 80, duration_ms=50)
    assert [(event.detail[0], event.at) for event in quartz.posted] == [
        (5, (10, 20)),
        (1, (10, 20)),
        (6, (20, 40)),
        (6, (30, 60)),
        (6, (40, 80)),
        (2, (40, 80)),
    ]


def test_drag_focus_loss_only_releases_at_last_dispatched_point(quartz: Quartz) -> None:
    desktop = NativeMacOSDesktop(foreground_check=lambda: len(quartz.posted) < 3)
    with pytest.raises(TargetError) as error:
        desktop.drag_between(0, 0, 30, 60, duration_ms=50)
    assert (error.value.code, error.value.request_state) == (
        "target_not_foreground",
        "response_unknown",
    )
    assert [(event.detail[0], event.at) for event in quartz.posted] == [
        (5, (0, 0)),
        (1, (0, 0)),
        (6, (10, 20)),
        (2, (10, 20)),
    ]


def test_posted_key_is_released_if_cancelled_and_next_key_is_not_sent(
    quartz: Quartz,
) -> None:
    cancellation = Event()

    def foreground() -> bool:
        if quartz.posted:
            cancellation.set()
        return True

    desktop = NativeMacOSDesktop(foreground_check=foreground)
    with pytest.raises(OperationCancelledError) as error:
        desktop.send_keys(
            [MacKeyStroke("s", MACOS_MODIFIER_COMMAND), "a"],
            control=OperationControl(cancellation=cancellation),
        )
    assert error.value.request_state == "response_unknown"
    assert quartz.posted == [
        Posted("key", (1, True), flags=0x100000),
        Posted("key", (1, False), flags=0),
    ]


def test_click_budget_expires_while_down_and_still_releases(quartz: Quartz) -> None:
    with pytest.raises(OperationTimeoutError) as error:
        NativeMacOSDesktop().click_at(
            7, 8, click_count=2, control=OperationControl(timeout_seconds=0.01)
        )
    assert error.value.request_state == "response_unknown"
    assert [event.detail for event in quartz.posted] == [(5, 0), (1, 0), (2, 0)]


def test_foreground_is_checked_after_last_event(quartz: Quartz) -> None:
    desktop = NativeMacOSDesktop(foreground_check=lambda: len(quartz.posted) < 2)
    with pytest.raises(TargetError) as error:
        desktop.send_keys(["Escape"])
    assert error.value.request_state == "response_unknown"
    assert [event.detail for event in quartz.posted] == [(53, True), (53, False)]


def test_preflight_denial_and_initial_wrong_foreground_do_not_post(
    quartz: Quartz,
) -> None:
    desktop = NativeMacOSDesktop(foreground_check=lambda: False)
    with pytest.raises(TargetError) as error:
        desktop.click_at(100, 100)
    assert (error.value.code, error.value.request_state) == (
        "target_not_foreground",
        "not_sent",
    )
    quartz.allowed = False
    with pytest.raises(CommandError) as denied:
        desktop.type_text("must not appear in the error")
    assert (denied.value.code, denied.value.request_state) == (
        "native_input_permission_denied",
        "not_sent",
    )
    assert quartz.posted == []


def test_guard_error_is_sanitized_and_not_posted(quartz: Quartz) -> None:
    def broken() -> bool:
        raise RuntimeError("PRIVATE")

    with pytest.raises(TargetError) as error:
        NativeMacOSDesktop(foreground_check=broken).send_keys(["a"])
    assert str(error.value) == "foreground_unobservable"
    assert error.value.request_state == "not_sent"
    assert quartz.posted == []


@pytest.mark.parametrize(
    "key", ["XCUIKeyboardKeyA", "XCUIKeyboardKey1", "XCUIKeyboardKeyArrowUp"]
)
def test_nonexistent_xcui_name_rejects_entire_batch(quartz: Quartz, key: str) -> None:
    with pytest.raises(InvalidRequestError) as error:
        NativeMacOSDesktop().send_keys(["s", key])
    assert (error.value.code, error.value.request_state) == (
        "invalid_argument",
        "not_sent",
    )
    assert quartz.posted == []


def test_invalid_batch_and_failed_keyup_allocation_do_not_post(quartz: Quartz) -> None:
    desktop = NativeMacOSDesktop()
    with pytest.raises(InvalidRequestError) as invalid:
        desktop.send_keys(["a", "Cmd+S"])
    assert (invalid.value.code, invalid.value.request_state) == (
        "invalid_argument",
        "not_sent",
    )
    with pytest.raises(InvalidRequestError):
        desktop.type_text("a\ud801")
    with pytest.raises(InvalidRequestError):
        desktop.scroll_at(1, 2, 0.5, 0)
    quartz.fail_up = True
    with pytest.raises(CommandError) as failure:
        desktop.send_keys(["a"])
    assert (failure.value.code, failure.value.request_state) == (
        "native_input_failed",
        "not_sent",
    )
    assert quartz.posted == []


def test_cancellation_before_operation_does_not_preflight(quartz: Quartz) -> None:
    cancellation = Event()
    cancellation.set()
    with pytest.raises(OperationCancelledError) as error:
        NativeMacOSDesktop().hover_at(
            12, 34, control=OperationControl(cancellation=cancellation)
        )
    assert error.value.request_state == "not_sent"
    assert quartz.preflight_count == 0


def test_geometry_does_not_require_input_access(quartz: Quartz) -> None:
    quartz.allowed = False
    assert macos_main_display_bounds() == Bounds(0, 0, 1512, 982)
    assert quartz.preflight_count == 0
    quartz.rect = native._Rect(native._Point(0, 0), native._Size(0, 982))
    with pytest.raises(CommandError) as error:
        macos_main_display_bounds()
    assert (error.value.code, error.value.request_state) == (
        "native_display_unavailable",
        "not_sent",
    )


def test_unsupported_platform_does_not_load_quartz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(native, "sys", SimpleNamespace(platform="linux"))

    def forbidden() -> native._Quartz:
        pytest.fail("unsupported platform attempted to load CoreGraphics")

    monkeypatch.setattr(native, "_quartz", forbidden)
    desktop = NativeMacOSDesktop()
    for call in (lambda: desktop.click_at(1, 2), macos_main_display_bounds):
        with pytest.raises(InvalidRequestError) as error:
            call()
        assert (error.value.code, error.value.request_state) == (
            "unsupported_platform",
            "not_sent",
        )


def test_unavailable_backend_has_stable_error(
    quartz: Quartz, monkeypatch: pytest.MonkeyPatch
) -> None:
    def absent() -> native._Quartz:
        raise OSError("PRIVATE")

    monkeypatch.setattr(native, "_quartz", absent)
    with pytest.raises(CommandError) as error:
        macos_main_display_bounds()
    assert str(error.value) == "native_backend_unavailable"
    assert error.value.request_state == "not_sent"


def test_input_lock_wait_is_bounded(quartz: Quartz) -> None:
    with native._DESKTOP_INPUT, pytest.raises(OperationTimeoutError) as error:
        NativeMacOSDesktop().hover_at(
            1, 2, control=OperationControl(timeout_seconds=0.025)
        )
    assert error.value.request_state == "not_sent"
    assert quartz.posted == []
