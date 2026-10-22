import inspect
import os
import socket
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from appium_connect_agent.configuration import (
    ConfigurationError,
    SettingSource,
    load_configuration,
)
from appium_connect_agent.contracts import LocalSettings

FIELDS = (
    "appium_executable",
    "appium_home",
    "node_executable",
    "npm_executable",
    "java_home",
    "android_sdk_root",
    "server_url",
)


def write_config(tmp_path: Path, text: str = "") -> Path:
    config = tmp_path / "project.toml"
    config.write_text(text, encoding="utf-8")
    return config


def test_empty_file_plus_url_and_omission(tmp_path: Path) -> None:
    config = write_config(tmp_path)
    loaded = load_configuration(config, server_url="HTTP://LOCALHOST:4723/")
    assert type(loaded.settings) is LocalSettings
    assert loaded.settings == LocalSettings(server_url="http://127.0.0.1:4723")
    assert loaded.config_file == config
    assert loaded.sources == (
        *(SettingSource(name, "default", None) for name in FIELDS[:-1]),
        SettingSource("server_url", "override", None),
    )
    assert load_configuration(config).settings == LocalSettings()


@pytest.mark.parametrize("name", FIELDS)
def test_each_override_wins_and_unpassed_fields_remain(
    tmp_path: Path, name: str
) -> None:
    text = (
        "[runtime]\n"
        + "\n".join(f'{field} = "original/{field}"' for field in FIELDS[:-1])
        + '\nserver_url = "http://localhost:4723"'
    )
    config = write_config(tmp_path, text)
    original = load_configuration(config)
    value = "http://localhost:4724/" if name == "server_url" else f"override/{name}"
    loaded = load_configuration(config, **{name: value})
    expected = "http://127.0.0.1:4724" if name == "server_url" else tmp_path / value
    for field in FIELDS:
        assert getattr(loaded.settings, field) == (
            expected if field == name else getattr(original.settings, field)
        )
    assert loaded.sources == tuple(
        SettingSource(field, "override", None)
        if field == name
        else SettingSource(field, "file", config)
        for field in FIELDS
    )


@pytest.mark.parametrize("name", FIELDS[:-1])
@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("as_path", [False, True])
def test_path_arguments_share_config_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    absolute: bool,
    as_path: bool,
) -> None:
    target = tmp_path / "target"
    selected = tmp_path / "selected"
    target.mkdir()
    selected.mkdir()
    config = write_config(target)
    link = selected / "link.toml"
    link.symlink_to(config)
    monkeypatch.chdir(target)
    path = tmp_path / "missing/../tool" if absolute else Path("missing/../tool")
    value = path if as_path else str(path)
    arguments: dict[str, Any] = {name: value}
    loaded = load_configuration(link, **arguments)
    assert getattr(loaded.settings, name) == selected / path
    assert loaded.config_file == link
    assert loaded.sources[FIELDS.index(name)] == SettingSource(name, "override", None)


@pytest.mark.parametrize("name", FIELDS)
@pytest.mark.parametrize("value", [None, "", True, 4, [], {}])
def test_bad_argument_is_not_omission_or_clear(
    tmp_path: Path, name: str, value: Any
) -> None:
    config = write_config(tmp_path)
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config, **{name: value})
    assert len(caught.value.issues) == 1
    issue = caught.value.issues[0]
    assert (issue.source, issue.field) == ("argument", name)
    assert issue.code == ("empty_value" if value == "" else "invalid_type")


@pytest.mark.parametrize("name", FIELDS[:-1])
@pytest.mark.parametrize("as_path", [False, True])
@pytest.mark.parametrize("value", ["~/tools", "$TOOL/bin", "${TOOL}/bin", "%TOOL%/bin"])
def test_argument_shorthand_rejected(
    tmp_path: Path, name: str, as_path: bool, value: str
) -> None:
    config = write_config(tmp_path)
    arguments: dict[str, Any] = {name: Path(value) if as_path else value}
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config, **arguments)
    assert caught.value.issues[0].code == "unsupported_path"
    assert caught.value.issues[0].source == "argument"


@pytest.mark.parametrize(
    "value", [Path("http:/localhost:4723"), "https://localhost:4723"]
)
def test_url_argument_uses_string_and_shared_validation(
    tmp_path: Path, value: Any
) -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(write_config(tmp_path), server_url=value)
    assert caught.value.issues[0].code == (
        "invalid_type" if isinstance(value, Path) else "invalid_url"
    )


def test_both_sources_errors_aggregate_and_cannot_be_masked(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        '[runtime]\nappium_home = ""\nserver_url = "https://secret.invalid:4723"',
    )
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(
            config,
            appium_home="valid",
            server_url="http://localhost:4723",
            java_home=None,  # type: ignore[arg-type]
        )
    assert {(i.source, i.field, i.code) for i in caught.value.issues} == {
        ("file", "runtime.appium_home", "empty_value"),
        ("file", "runtime.server_url", "invalid_url"),
        ("argument", "java_home", "invalid_type"),
    }
    assert "secret" not in str(caught.value)
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(
            config,
            appium_home=None,  # type: ignore[arg-type]
            server_url="https://private.invalid",
        )
    assert len(caught.value.issues) == 4
    assert "private" not in str(caught.value)


@pytest.mark.parametrize(
    "text", ["other = 1", "runtime = false", "[runtime]\nunknown = 1"]
)
def test_structure_errors_do_not_skip_parameter_errors(
    tmp_path: Path, text: str
) -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(write_config(tmp_path, text), server_url=None)  # type: ignore[arg-type]
    assert {issue.source for issue in caught.value.issues} == {"file", "argument"}


@pytest.mark.parametrize("data", [None, b"[", b"\xff", b"#" * (1024 * 1024 + 1)])
def test_read_parse_failures_stop_before_argument_validation(
    tmp_path: Path, data: bytes | None
) -> None:
    config = tmp_path / "early.toml"
    if data is not None:
        config.write_bytes(data)
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config, server_url=None)  # type: ignore[arg-type]
    assert len(caught.value.issues) == 1
    assert caught.value.issues[0].source == "file"
    assert caught.value.issues[0].code in {
        "file_not_found",
        "invalid_toml",
        "invalid_utf8",
        "file_too_large",
    }


def test_mixed_sources_snapshot_and_no_write_or_extra_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = write_config(tmp_path, '[runtime]\nappium_home = "file-home"')
    before = config.read_bytes()
    real_open = os.open

    def read_config_only(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        assert path == config
        assert flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC) == 0
        return real_open(path, flags, *args, **kwargs)

    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail("override attempted extra I/O")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", read_config_only)
        patch.setattr(type(os.environ), "__getitem__", forbidden)
        patch.setattr(Path, "stat", forbidden)
        patch.setattr(Path, "resolve", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(socket, "getaddrinfo", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        loaded = load_configuration(
            config, node_executable=Path("../node"), server_url="http://localhost:4723"
        )
    assert config.read_bytes() == before
    assert loaded.sources[1] == SettingSource("appium_home", "file", config)
    assert loaded.sources[2] == SettingSource("node_executable", "override", None)
    assert loaded.sources[0] == SettingSource("appium_executable", "default", None)
    with pytest.raises(FrozenInstanceError):
        loaded.sources[2].source = "file"  # type: ignore[misc]
    config.write_text("", encoding="utf-8")
    assert loaded.settings.appium_home == tmp_path / "file-home"
    assert load_configuration(config).settings == LocalSettings()


def test_keyword_interface(tmp_path: Path) -> None:
    parameters = inspect.signature(load_configuration).parameters
    assert tuple(parameters) == ("config_file", *FIELDS)
    assert all(
        parameters[name].kind is inspect.Parameter.KEYWORD_ONLY for name in FIELDS
    )
    assert all(parameters[name].default is not None for name in FIELDS)
    with pytest.raises(TypeError):
        load_configuration(write_config(tmp_path), unknown="x")  # type: ignore[call-arg]
