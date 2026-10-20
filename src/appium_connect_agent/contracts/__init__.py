"""Shared resolved settings; no filesystem access or discovery."""

from dataclasses import dataclass, fields
from pathlib import Path

__all__ = ["LocalSettings"]


@dataclass(frozen=True, kw_only=True)
class LocalSettings:
    appium_executable: Path | None = None
    appium_home: Path | None = None
    node_executable: Path | None = None
    npm_executable: Path | None = None
    java_home: Path | None = None
    android_sdk_root: Path | None = None

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None and (
                not isinstance(value, Path) or not value.is_absolute()
            ):
                raise ValueError(f"{field.name} must be an absolute Path or None")
