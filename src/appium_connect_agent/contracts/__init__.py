"""Shared resolved settings; no filesystem access or discovery."""

from dataclasses import dataclass
from pathlib import Path

from ._url import normalize_server_url

__all__ = ["LocalSettings"]


@dataclass(frozen=True, kw_only=True)
class LocalSettings:
    appium_executable: Path | None = None
    appium_home: Path | None = None
    node_executable: Path | None = None
    npm_executable: Path | None = None
    java_home: Path | None = None
    android_sdk_root: Path | None = None
    server_url: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "appium_executable",
            "appium_home",
            "node_executable",
            "npm_executable",
            "java_home",
            "android_sdk_root",
        ):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, Path) or not value.is_absolute()
            ):
                raise ValueError(f"{name} must be an absolute Path or None")
        if self.server_url is not None:
            object.__setattr__(
                self, "server_url", normalize_server_url(self.server_url)
            )
