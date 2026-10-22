import os
import tomllib
from pathlib import Path
from typing import Any

import pytest

from appium_connect_agent.configuration import (
    ConfigurationError,
    _loader,
    load_configuration,
)

LIMIT = 1024 * 1024


def test_missing_file_has_attempt_and_example(tmp_path: Path) -> None:
    config = tmp_path / "missing.toml"
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    issue = caught.value.issues[0]
    assert issue.code == "file_not_found"
    assert str(config) in issue.message
    assert "examples/configuration/minimal.toml" in issue.message


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_non_regular_file_rejected_without_waiting(tmp_path: Path, kind: str) -> None:
    config = tmp_path / "special"
    if kind == "fifo":
        os.mkfifo(config)
    else:
        config.mkdir()
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert caught.value.issues[0].code == "not_regular_file"


def test_unreadable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "private.toml"
    config.write_bytes(b"")

    def denied(*args: object, **kwargs: object) -> int:
        raise PermissionError("private operating system detail")

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert caught.value.issues[0].code == "file_read_error"
    assert "private operating" not in str(caught.value)


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"\xff", "invalid_utf8"),
        (b'[runtime]\nserver_url = "secret', "invalid_toml"),
        (b'[runtime]\nappium_home = "secret"\nappium_home = "again"', "invalid_toml"),
    ],
)
def test_encoding_and_syntax_stop_parse(tmp_path: Path, data: bytes, code: str) -> None:
    config = tmp_path / "bad.toml"
    config.write_bytes(data)
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert len(caught.value.issues) == 1
    assert caught.value.issues[0].code == code
    assert caught.value.issues[0].field is None
    assert "secret" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("size", [LIMIT, LIMIT + 1, LIMIT * 2])
def test_size_limit_inclusive_and_bounded_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: int
) -> None:
    config = tmp_path / "large.toml"
    config.write_bytes(b"#" + b"a" * (size - 1))
    real_read = os.read
    total = 0

    def read(fd: int, length: int) -> bytes:
        nonlocal total
        assert 0 < length <= LIMIT + 1 - total
        result = real_read(fd, length)
        total += len(result)
        return result

    monkeypatch.setattr(os, "read", read)
    if size == LIMIT:
        assert load_configuration(config).settings.server_url is None
        assert total == LIMIT
    else:
        with pytest.raises(ConfigurationError) as caught:
            load_configuration(config)
        assert caught.value.issues[0].code == "file_too_large"
        assert total == LIMIT + 1


def test_short_reads_do_not_truncate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "short.toml"
    config.write_bytes(b'[runtime]\nserver_url = "http://localhost:4723"')
    real_read = os.read

    def short_read(fd: int, length: int) -> bytes:
        return real_read(fd, min(length, 3))

    monkeypatch.setattr(os, "read", short_read)
    assert load_configuration(config).settings.server_url == "http://127.0.0.1:4723"


@pytest.mark.parametrize(
    "outcome", ["success", "syntax", "schema", "size", "stat", "read", "defect"]
)
def test_descriptor_closed_on_every_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    config = tmp_path / "close.toml"
    data = {
        "syntax": b"[",
        "schema": b"runtime = false",
        "size": b"#" + b"a" * LIMIT,
    }.get(outcome, b"")
    config.write_bytes(data)
    real_open, real_close = os.open, os.close
    opened: list[int] = []
    closed: list[int] = []

    def track_open(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def track_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    def os_failure(*args: object) -> Any:
        raise OSError("not exposed")

    def defect(*args: object) -> Any:
        raise RuntimeError("unexpected defect")

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "close", track_close)
    if outcome == "stat":
        monkeypatch.setattr(os, "fstat", os_failure)
    elif outcome == "read":
        monkeypatch.setattr(os, "read", os_failure)
    elif outcome == "defect":
        monkeypatch.setattr(os, "read", defect)
    if outcome == "success":
        load_configuration(config)
    elif outcome == "defect":
        with pytest.raises(RuntimeError, match="unexpected defect"):
            load_configuration(config)
    else:
        with pytest.raises(ConfigurationError):
            load_configuration(config)
    assert len(opened) == 1
    assert closed == opened


def test_unknown_parser_and_settings_defects_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "defect.toml"
    config.write_bytes(b'[runtime]\nserver_url = "http://localhost:4723"')

    def defect(*args: object, **kwargs: object) -> Any:
        raise RuntimeError("unknown defect")

    with monkeypatch.context() as patch:
        patch.setattr(tomllib, "loads", defect)
        with pytest.raises(RuntimeError, match="unknown defect"):
            load_configuration(config)
    with monkeypatch.context() as patch:
        patch.setattr(_loader, "LocalSettings", defect)
        with pytest.raises(RuntimeError, match="unknown defect"):
            load_configuration(config)


def test_location_failure_is_argument_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing_cwd(*args: object) -> Any:
        raise FileNotFoundError("working directory removed")

    monkeypatch.setattr(Path, "cwd", missing_cwd)
    with pytest.raises(ConfigurationError) as caught:
        load_configuration("appium.toml")
    assert caught.value.issues[0].source == "argument"
    assert caught.value.issues[0].code == "file_location"
