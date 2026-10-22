"""Immutable configuration snapshots, provenance and validation issues."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from appium_connect_agent.contracts import LocalSettings


@dataclass(frozen=True, slots=True)
class SettingSource:
    field: str
    source: Literal["file", "default"]
    config_file: Path | None


@dataclass(frozen=True, slots=True)
class LoadedConfiguration:
    config_file: Path
    settings: LocalSettings
    sources: tuple[SettingSource, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))


@dataclass(frozen=True, slots=True)
class ConfigurationIssue:
    source: Literal["file", "argument"]
    field: str | None
    code: str
    message: str


class ConfigurationError(ValueError):
    """Known loading failure; issues never contain raw configuration values."""

    def __init__(self, issues: tuple[ConfigurationIssue, ...]) -> None:
        self._issues = tuple(issues)
        if not self._issues:
            raise ValueError("ConfigurationError requires at least one issue")
        super().__init__("; ".join(issue.message for issue in self._issues))

    @property
    def issues(self) -> tuple[ConfigurationIssue, ...]:
        return self._issues
