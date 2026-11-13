"""Shared resolved settings; no filesystem access or discovery."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ._url import normalize_base_path, normalize_server_url

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
    server_mode: Literal["external", "managed"] = "external"
    managed_host: Literal["127.0.0.1", "::1"] | None = None
    managed_port: int | None = None
    managed_base_path: str = ""

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
        if type(self.server_mode) is not str or self.server_mode not in (
            "external",
            "managed",
        ):
            raise ValueError("server_mode must be 'external' or 'managed'")
        if self.managed_host is not None and (
            type(self.managed_host) is not str
            or self.managed_host not in ("127.0.0.1", "::1")
        ):
            raise ValueError("managed_host must be a numeric loopback address or None")
        if self.managed_port is not None and (
            type(self.managed_port) is not int or not 1 <= self.managed_port <= 65535
        ):
            raise ValueError("managed_port must be an integer from 1 through 65535")
        if type(self.managed_base_path) is not str:
            raise ValueError("managed_base_path must be a string")
        normalized_base_path = normalize_base_path(
            self.managed_base_path, trim_trailing_slash=False
        )
        object.__setattr__(self, "managed_base_path", normalized_base_path)
        if self.server_mode == "external":
            if (
                self.managed_host is not None
                or self.managed_port is not None
                or self.managed_base_path
            ):
                raise ValueError("external mode forbids managed runtime settings")
        elif self.managed_host is None or self.managed_port is None:
            raise ValueError("managed mode requires managed_host and managed_port")
        elif (
            self.server_url is not None
            or self.appium_executable is not None
            or self.appium_home is not None
        ):
            raise ValueError("managed mode conflicts with external Appium settings")
