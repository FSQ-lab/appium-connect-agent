"""Public immutable Mac2 keyboard values."""

from __future__ import annotations

from dataclasses import dataclass

MACOS_MODIFIER_CAPS_LOCK = 1 << 0
MACOS_MODIFIER_SHIFT = 1 << 1
MACOS_MODIFIER_CONTROL = 1 << 2
MACOS_MODIFIER_OPTION = 1 << 3
MACOS_MODIFIER_COMMAND = 1 << 4
MACOS_MODIFIER_FUNCTION = 1 << 5


@dataclass(frozen=True, slots=True)
class MacKeyStroke:
    key: str
    modifier_flags: int = 0
