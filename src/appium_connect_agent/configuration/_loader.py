"""Bounded ordinary-file reading and seven-field project adaptation."""

import os
import re
import stat
import tomllib
from pathlib import Path
from typing import Literal, cast

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
_FIELDS = (
    *_PATH_FIELDS,
    "server_url",
    "server_mode",
    "managed_host",
    "managed_port",
    "managed_base_path",
)
_VARIABLE = re.compile(
    r"\$(?:[A-Za-z_][A-Za-z0-9_]*|\{[A-Za-z_][A-Za-z0-9_]*\})"
    r"|%[A-Za-z_][A-Za-z0-9_]*%"
)


class _Omitted:
    """Private marker; explicit None remains an invalid argument."""


_OMITTED = _Omitted()


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
    except (ValueError, RecursionError) as error:
        if not _known_parser_limit(error):
            raise
        raise _file_issue(
            "parser_limit",
            "Reduce integer digit counts or array nesting to fit the Python parser limits.",
        ) from None


def _known_parser_limit(error: ValueError | RecursionError) -> bool:
    # Attribute only the verified CPython failures, using public traceback data.
    # These names identify frames; no private parser entry point is called.
    directory = Path(tomllib.__file__).parent
    frames: list[tuple[Path, str]] = []
    trace = error.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        frames.append((Path(code.co_filename), code.co_name))
        trace = trace.tb_next
    if not frames or frames[-1][0].parent != directory:
        return False
    if type(error) is ValueError:
        return frames[-1] == (directory / "_re.py", "match_to_number") and bool(
            re.fullmatch(
                r"Exceeds the limit \([0-9]+ digits\) for integer string conversion: "
                r"value has [0-9]+ digits; use sys\.set_int_max_str_digits\(\) to increase the limit",
                str(error),
            )
        )
    parser = directory / "_parser.py"
    return (
        type(error) is RecursionError
        and str(error) == "maximum recursion depth exceeded"
        and frames[-1][0] == parser
        and frames.count((parser, "parse_array")) > 1
        and frames.count((parser, "parse_value")) > 1
    )


def _validate_fields(
    values: dict[str, object],
    config_file: Path,
    source: Literal["file", "argument"],
    issues: list[ConfigurationIssue],
) -> dict[str, object]:
    validated: dict[str, object] = {}
    for name in _FIELDS:
        if name not in values:
            continue
        value = values[name]
        field = f"runtime.{name}" if source == "file" else name
        if source == "argument" and name in _PATH_FIELDS and isinstance(value, Path):
            value = str(value)
        if name == "managed_port":
            if type(value) is not int or not 1 <= value <= 65535:
                issues.append(
                    ConfigurationIssue(
                        source,
                        field,
                        "invalid_type" if type(value) is not int else "invalid_value",
                        "Use an integer from 1 through 65535 for managed_port.",
                    )
                )
            else:
                validated[name] = value
            continue
        if (
            name in {"server_mode", "managed_host", "managed_base_path"}
            and type(value) is not str
        ):
            issues.append(
                ConfigurationIssue(
                    source,
                    field,
                    "invalid_type",
                    "Use a TOML string for this runtime field."
                    if source == "file"
                    else "Provide a string, or omit the argument.",
                )
            )
            continue
        if not isinstance(value, str):
            issues.append(
                ConfigurationIssue(
                    source,
                    field,
                    "invalid_type",
                    "Use a TOML string for this runtime field."
                    if source == "file"
                    else "Provide a string (or Path for tool paths), or omit the argument.",
                )
            )
        elif not value and name != "managed_base_path":
            issues.append(
                ConfigurationIssue(
                    source,
                    field,
                    "empty_value",
                    "Provide a nonempty value, or omit this field.",
                )
            )
        elif name == "server_url":
            try:
                validated[name] = LocalSettings(server_url=value).server_url
            except ValueError:
                issues.append(
                    ConfigurationIssue(
                        source,
                        field,
                        "invalid_url",
                        "Use a complete HTTP loopback URL with an explicit port and safe base path.",
                    )
                )
        elif name == "server_mode":
            if value not in ("external", "managed"):
                issues.append(
                    ConfigurationIssue(
                        source,
                        field,
                        "invalid_value",
                        "Use exactly external or managed for server_mode.",
                    )
                )
            else:
                validated[name] = value
        elif name == "managed_host":
            if value not in ("127.0.0.1", "::1"):
                issues.append(
                    ConfigurationIssue(
                        source,
                        field,
                        "invalid_value",
                        "Use exactly 127.0.0.1 or ::1 for managed_host.",
                    )
                )
            else:
                validated[name] = value
        elif name == "managed_base_path":
            try:
                validated[name] = LocalSettings(
                    server_mode="managed",
                    managed_host="127.0.0.1",
                    managed_port=1,
                    managed_base_path=value,
                ).managed_base_path
            except ValueError:
                issues.append(
                    ConfigurationIssue(
                        source,
                        field,
                        "invalid_value",
                        "Use an empty or safe absolute ASCII base path without a trailing slash.",
                    )
                )
        elif value.startswith("~") or _VARIABLE.search(value):
            issues.append(
                ConfigurationIssue(
                    source,
                    field,
                    "unsupported_path",
                    "Use a concrete path without home shorthand or variable placeholders.",
                )
            )
        elif "\0" in value:
            issues.append(
                ConfigurationIssue(
                    source, field, "invalid_path", "Use a path without NUL characters."
                )
            )
        else:
            validated[name] = config_file.parent / Path(value)
    return validated


def _combination_issues(
    values: dict[str, object],
    runtime: dict[str, object],
    overrides: dict[str, object],
) -> tuple[ConfigurationIssue, ...]:
    names: set[str] = set()
    if values["server_mode"] == "external":
        if values["managed_host"] is not None:
            names.add("managed_host")
        if values["managed_port"] is not None:
            names.add("managed_port")
        if values["managed_base_path"] != "":
            names.add("managed_base_path")
    else:
        if values["managed_host"] is None:
            names.add("managed_host")
        if values["managed_port"] is None:
            names.add("managed_port")
        for name in ("server_url", "appium_executable", "appium_home"):
            if values[name] is not None:
                names.add(name)
        if names:
            names.add("server_mode")
    mode_source: Literal["file", "argument"] = (
        "argument" if "server_mode" in overrides else "file"
    )
    result: list[ConfigurationIssue] = []
    for name in _FIELDS:
        if name not in names:
            continue
        if name in overrides:
            source: Literal["file", "argument"] = "argument"
        elif name in runtime:
            source = "file"
        else:
            source = mode_source
        field = f"runtime.{name}" if source == "file" else name
        result.append(
            ConfigurationIssue(
                source,
                field,
                "invalid_combination",
                "Choose either external settings or a complete managed host and port.",
            )
        )
    return tuple(result)


def _settings(
    document: dict[str, object], config_file: Path, overrides: dict[str, object]
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
                    "Remove this unknown runtime field; use the documented eleven fields.",
                )
            )
    file_values = _validate_fields(runtime, config_file, "file", issues)
    override_values = _validate_fields(overrides, config_file, "argument", issues)
    defaults = LocalSettings()
    values: dict[str, object] = {name: getattr(defaults, name) for name in _FIELDS}
    values.update(file_values)
    values.update(override_values)
    if not issues:
        issues.extend(_combination_issues(values, runtime, overrides))
    if issues:
        raise ConfigurationError(tuple(issues))
    settings = LocalSettings(
        appium_executable=cast(Path | None, values["appium_executable"]),
        appium_home=cast(Path | None, values["appium_home"]),
        node_executable=cast(Path | None, values["node_executable"]),
        npm_executable=cast(Path | None, values["npm_executable"]),
        java_home=cast(Path | None, values["java_home"]),
        android_sdk_root=cast(Path | None, values["android_sdk_root"]),
        server_url=cast(str | None, values["server_url"]),
        server_mode=cast(Literal["external", "managed"], values["server_mode"]),
        managed_host=cast(Literal["127.0.0.1", "::1"] | None, values["managed_host"]),
        managed_port=cast(int | None, values["managed_port"]),
        managed_base_path=cast(str, values["managed_base_path"]),
    )
    sources = tuple(
        SettingSource(
            field=name,
            source="override"
            if name in overrides
            else "file"
            if name in runtime
            else "default",
            config_file=config_file
            if name in runtime and name not in overrides
            else None,
        )
        for name in _FIELDS
    )
    return settings, sources


def load_configuration(
    config_file: str | Path,
    *,
    appium_executable: str | Path | _Omitted = _OMITTED,
    appium_home: str | Path | _Omitted = _OMITTED,
    node_executable: str | Path | _Omitted = _OMITTED,
    npm_executable: str | Path | _Omitted = _OMITTED,
    java_home: str | Path | _Omitted = _OMITTED,
    android_sdk_root: str | Path | _Omitted = _OMITTED,
    server_url: str | _Omitted = _OMITTED,
    server_mode: str | _Omitted = _OMITTED,
    managed_host: str | _Omitted = _OMITTED,
    managed_port: int | _Omitted = _OMITTED,
    managed_base_path: str | _Omitted = _OMITTED,
) -> LoadedConfiguration:
    """Load one explicit TOML file; success does not imply runtime readiness."""
    selected_file = _locate(config_file)
    document = _parse(_read_file(selected_file))
    arguments = dict(
        zip(
            _FIELDS,
            (
                appium_executable,
                appium_home,
                node_executable,
                npm_executable,
                java_home,
                android_sdk_root,
                server_url,
                server_mode,
                managed_host,
                managed_port,
                managed_base_path,
            ),
            strict=True,
        )
    )
    overrides: dict[str, object] = {
        name: value for name, value in arguments.items() if value is not _OMITTED
    }
    settings, sources = _settings(document, selected_file, overrides)
    return LoadedConfiguration(selected_file, settings, sources)
