import os
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from appium_connect_agent.configuration import ConfigurationError, load_configuration


@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("kind", ["integer", "array"])
def test_real_parser_limits_are_structured_and_close_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, override: bool
) -> None:
    value = "9" * 5000 if kind == "integer" else "[" * 600 + "0" + "]" * 600
    text = "# private-config-marker\n[runtime]\nserver_url = " + value
    assert len(text.encode()) < 1024 * 1024
    config = tmp_path / "limits.toml"
    config.write_text(text, encoding="utf-8")
    limits = (sys.get_int_max_str_digits(), sys.getrecursionlimit())
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

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "close", track_close)
    with pytest.raises(ConfigurationError) as caught:
        if override:
            load_configuration(config, server_url="http://localhost:4723")
        else:
            load_configuration(config)
    error = caught.value
    assert len(error.issues) == 1
    assert (error.issues[0].source, error.issues[0].field) == ("file", None)
    assert error.issues[0].code == "parser_limit"
    assert "Reduce" in error.issues[0].message
    assert "private-config-marker" not in str(error)
    assert value not in str(error)
    assert error.__cause__ is None
    assert error.__suppress_context__
    assert len(opened) == 1
    assert closed == opened
    assert (sys.get_int_max_str_digits(), sys.getrecursionlimit()) == limits


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("unknown runtime defect"),
        AttributeError("unknown attribute defect"),
        ValueError("unrelated value defect"),
        RecursionError("unrelated recursion defect"),
        ValueError(
            "Exceeds the limit (4300 digits) for integer string conversion: "
            "value has 5000 digits; use sys.set_int_max_str_digits() to increase the limit"
        ),
        RecursionError("maximum recursion depth exceeded"),
    ],
)
def test_unknown_parser_errors_propagate_same_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    config = tmp_path / "defect.toml"
    config.write_text("", encoding="utf-8")
    real_close = os.close
    closed: list[int] = []

    def defect(*args: object, **kwargs: object) -> Any:
        raise error

    def track_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(tomllib, "loads", defect)
    monkeypatch.setattr(os, "close", track_close)
    with pytest.raises(type(error)) as caught:
        load_configuration(config)
    assert caught.value is error
    assert len(closed) == 1


def test_ordinary_syntax_error_still_has_its_own_code(tmp_path: Path) -> None:
    config = tmp_path / "syntax.toml"
    config.write_text("[runtime", encoding="utf-8")
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert caught.value.issues[0].code == "invalid_toml"
