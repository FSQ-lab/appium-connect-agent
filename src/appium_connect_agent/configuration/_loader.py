"""Bounded ordinary-file reading and seven-field project adaptation."""

import os
import re
import stat
import tomllib
from pathlib import Path

from appium_connect_agent.contracts import LocalSettings

from ._models import (
    ConfigurationError,
    ConfigurationIssue,
    LoadedConfiguration,
    SettingSource,
)

_MAX_BYTES = 1024 * 1024
_PATH_FIELDS = (
    "appium_executable",
    "appium_home",
    "node_executable",
    "npm_executable",
    "java_home",
    "android_sdk_root",
)
_FIELDS = (*_PATH_FIELDS, "server_url")
_VARIABLE = re.compile(
    r"\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[A-Za-z_][A-Za-z0-9_]*\})"
    r"|%[A-Za-z_][A-Za-z0-9_]*%"
)


def _file_issue(code: str, message: str) -> ConfigurationError:
    return ConfigurationError((ConfigurationIssue("file", None, code, message),))


def _locate(config_file: str | Path) -> Path:
    if not isinstance(config_file, (str, Path)) or config_file == "":
        raise ConfigurationError(
            (
                ConfigurationIssue(
                    "argument",
                    "config_file",
                    "invalid_config_file",
                    "config_file must be a nonempty string or Path to a TOML file.",
                ),
            )
        )
    if "\0" in str(config_file):
        raise ConfigurationError(
            (
                ConfigurationIssue(
                    "argument",
                    "config_file",
                    "invalid_config_file",
                    "config_file must not contain a NUL character.",
                ),
            )
        )
    try:
        return Path(config_file).absolute()
    except OSError:
        raise ConfigurationError(
            (
                ConfigurationIssue(
                    "argument",
                    "config_file",
                    "file_location",
                    "Cannot locate config_file; provide an absolute file path.",
                ),
            )
        ) from None


def _read_file(config_file: Path) -> bytes:
    try:
        # Nonblocking open prevents FIFO waits before checking the opened object.
        fd = os.open(config_file, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise _file_issue(
                    "not_regular_file",
                    "Choose an ordinary TOML file, not a directory or device.",
                )
            chunks: list[bytes] = []
            total = 0
            while total <= _MAX_BYTES:
                chunk = os.read(fd, min(65536, _MAX_BYTES + 1 - total))
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
                total += len(chunk)
            raise _file_issue(
                "file_too_large", "Reduce the TOML file to at most 1 MiB."
            )
        finally:
            os.close(fd)
    except FileNotFoundError:
        raise _file_issue(
            "file_not_found",
            f"Configuration file not found: {config_file}. Create a file using "
            "examples/configuration/minimal.toml, or choose an existing TOML file.",
        ) from None
    except OSError:
        raise _file_issue(
            "file_read_error",
            "Cannot read the TOML file; check its path and read permissions.",
        ) from None


def _parse(data: bytes) -> dict[str, object]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _file_issue(
            "invalid_utf8", "Save the configuration as UTF-8 text."
        ) from None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise _file_issue(
            "invalid_toml", "Correct the TOML syntax, including any duplicate keys."
        ) from None


def _settings(
    document: dict[str, object], config_file: Path
) -> tuple[LocalSettings, tuple[SettingSource, ...]]:
    issues: list[ConfigurationIssue] = []
    for key in document:
        if key != "runtime":
            issues.append(
                ConfigurationIssue(
                    "file",
                    key,
                    "unknown_field",
                    "Only the top-level runtime table is supported.",
                )
            )
    runtime = document.get("runtime", {})
    if not isinstance(runtime, dict):
        issues.append(
            ConfigurationIssue(
                "file", "runtime", "invalid_structure", "Use a [runtime] TOML table."
            )
        )
        runtime = {}
    for key in runtime:
        if key not in _FIELDS:
            issues.append(
                ConfigurationIssue(
                    "file",
                    f"runtime.{key}",
                    "unknown_field",
                    "Remove this unknown runtime field; use the documented seven fields.",
                )
            )
    paths: dict[str, Path] = {}
    server_url: str | None = None
    for name in _FIELDS:
        if name not in runtime:
            continue
        value = runtime[name]
        field = f"runtime.{name}"
        if not isinstance(value, str):
            issues.append(
                ConfigurationIssue(
                    "file",
                    field,
                    "invalid_type",
                    "Use a TOML string for this runtime field.",
                )
            )
        elif not value:
            issues.append(
                ConfigurationIssue(
                    "file",
                    field,
                    "empty_value",
                    "Provide a nonempty value, or omit this field.",
                )
            )
        elif name == "server_url":
            try:
                server_url = LocalSettings(server_url=value).server_url
            except ValueError:
                issues.append(
                    ConfigurationIssue(
                        "file",
                        field,
                        "invalid_url",
                        "Use a complete HTTP loopback URL with an explicit port and safe base path.",
                    )
                )
        elif value.startswith("~") or _VARIABLE.search(value):
            issues.append(
                ConfigurationIssue(
                    "file",
                    field,
                    "unsupported_path",
                    "Use a concrete path without home shorthand or variable placeholders.",
                )
            )
        elif "\0" in value:
            issues.append(
                ConfigurationIssue(
                    "file", field, "invalid_path", "Use a path without NUL characters."
                )
            )
        else:
            # An absolute base preserves symlink paths and literal parent segments.
            paths[name] = config_file.parent / Path(value)
    if issues:
        raise ConfigurationError(tuple(issues))
    settings = LocalSettings(
        appium_executable=paths.get("appium_executable"),
        appium_home=paths.get("appium_home"),
        node_executable=paths.get("node_executable"),
        npm_executable=paths.get("npm_executable"),
        java_home=paths.get("java_home"),
        android_sdk_root=paths.get("android_sdk_root"),
        server_url=server_url,
    )
    sources = tuple(
        SettingSource(
            field=name,
            source="file" if name in runtime else "default",
            config_file=config_file if name in runtime else None,
        )
        for name in _FIELDS
    )
    return settings, sources


def load_configuration(config_file: str | Path) -> LoadedConfiguration:
    """Load one explicit TOML file; success does not imply runtime readiness."""
    selected_file = _locate(config_file)
    document = _parse(_read_file(selected_file))
    settings, sources = _settings(document, selected_file)
    return LoadedConfiguration(selected_file, settings, sources)
