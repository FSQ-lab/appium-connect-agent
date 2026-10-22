import os
import socket
import subprocess
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from appium_connect_agent.configuration import (
    ConfigurationError,
    ConfigurationIssue,
    LoadedConfiguration,
    SettingSource,
    load_configuration,
)
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import Runtime

FIELDS = (
    "appium_executable",
    "appium_home",
    "node_executable",
    "npm_executable",
    "java_home",
    "android_sdk_root",
    "server_url",
)


def write_config(tmp_path: Path, text: str) -> Path:
    config = tmp_path / "appium.toml"
    config.write_text(text, encoding="utf-8")
    return config


@pytest.mark.parametrize("text", ["", "# only a comment\n", "[runtime]\n"])
def test_defaults(tmp_path: Path, text: str) -> None:
    config = write_config(tmp_path, text)
    loaded = load_configuration(config)
    assert loaded.config_file == config
    assert type(loaded.settings) is LocalSettings
    assert loaded.settings == LocalSettings()
    assert loaded.sources == tuple(
        SettingSource(name, "default", None) for name in FIELDS
    )


def test_minimal_example_and_sources() -> None:
    example = Path(__file__).parents[2] / "examples/configuration/minimal.toml"
    loaded = load_configuration(example)
    assert loaded.settings == LocalSettings(server_url="http://127.0.0.1:4723")
    assert loaded.sources[-1] == SettingSource("server_url", "file", example)
    assert all(source.source == "default" for source in loaded.sources[:-1])


def test_full_file_paths_and_url(tmp_path: Path) -> None:
    text = "[runtime]\n" + "\n".join(
        f'{name} = "./missing/{name}"' for name in FIELDS[:-1]
    )
    config = write_config(
        tmp_path, text + '\nserver_url = "HTTP://LOCALHOST:4723/wd/hub/"'
    )
    loaded = load_configuration(str(config))
    for name in FIELDS[:-1]:
        assert getattr(loaded.settings, name) == tmp_path / "missing" / name
    assert loaded.settings.server_url == "http://127.0.0.1:4723/wd/hub"
    assert loaded.sources == tuple(
        SettingSource(name, "file", config) for name in FIELDS
    )


def test_relative_file_uses_call_time_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config = write_config(project, '[runtime]\nappium_home = "../tools/home"')
    monkeypatch.chdir(tmp_path)
    loaded = load_configuration("project/appium.toml")
    assert loaded.config_file == config
    assert loaded.settings.appium_home == project / "../tools/home"
    monkeypatch.chdir(project)
    assert loaded.config_file == config
    assert loaded.settings.appium_home == project / "../tools/home"


def test_file_symlink_uses_selected_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    selected = tmp_path / "selected"
    target.mkdir()
    selected.mkdir()
    original = write_config(target, '[runtime]\nappium_home = "../tools"')
    link = selected / "link.toml"
    link.symlink_to(original)
    loaded = load_configuration(link)
    assert loaded.config_file == link
    assert loaded.settings.appium_home == selected / "../tools"
    assert loaded.sources[1].config_file == link


def test_tool_symlink_and_absolute_path_are_not_resolved(tmp_path: Path) -> None:
    tool = tmp_path / "tool-link"
    tool.symlink_to(tmp_path / "absent-tool")
    config = write_config(
        tmp_path,
        f'[runtime]\nappium_executable = "{tool}"\nnode_executable = "{tool}/../node"',
    )
    loaded = load_configuration(config)
    assert loaded.settings.appium_executable == tool
    assert loaded.settings.node_executable == tool / "../node"


def test_snapshot_and_public_values_are_immutable(tmp_path: Path) -> None:
    config = write_config(tmp_path, '[runtime]\nserver_url = "http://localhost:4723"')
    old = load_configuration(config)
    config.write_text(
        '[runtime]\nserver_url = "http://localhost:4724"', encoding="utf-8"
    )
    new = load_configuration(config)
    assert old.settings.server_url == "http://127.0.0.1:4723"
    assert new.settings.server_url == "http://127.0.0.1:4724"
    with pytest.raises(FrozenInstanceError):
        old.config_file = config  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        old.settings.server_url = None  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        old.sources[0].source = "file"  # type: ignore[misc]
    issue = ConfigurationIssue("file", "runtime", "invalid_structure", "Use a table.")
    with pytest.raises(FrozenInstanceError):
        issue.message = "changed"  # type: ignore[misc]
    error = ConfigurationError((issue,))
    assert isinstance(error, ValueError)
    assert error.issues == (issue,)
    with pytest.raises(AttributeError):
        error.issues = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        del error.issues
    with pytest.raises(ValueError, match="at least one"):
        ConfigurationError(())
    assert isinstance(old.sources, tuple)
    assert isinstance(error.issues, tuple)
    assert isinstance(LoadedConfiguration(config, LocalSettings(), ()).sources, tuple)


@pytest.mark.parametrize("value", [None, 1, True, b"file", [], "", "bad\0file"])
def test_bad_file_argument(value: Any) -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(value)
    assert caught.value.issues[0].source == "argument"
    assert caught.value.issues[0].field == "config_file"


@pytest.mark.parametrize("value", ["0", "true", "[]", "{}", "1979-05-27"])
@pytest.mark.parametrize("field", FIELDS)
def test_fields_require_strings(tmp_path: Path, field: str, value: str) -> None:
    config = write_config(tmp_path, f"[runtime]\n{field} = {value}\n")
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert [(i.field, i.code) for i in caught.value.issues] == [
        (f"runtime.{field}", "invalid_type")
    ]


@pytest.mark.parametrize("field", FIELDS)
def test_empty_strings_are_not_defaults(tmp_path: Path, field: str) -> None:
    config = write_config(tmp_path, f'[runtime]\n{field} = ""')
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert caught.value.issues[0].code == "empty_value"


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost",
        "http://example.com:4723",
        "https://localhost:4723",
        "http://localhost:4723/../private",
        "http://user:private@localhost:4723",
    ],
)
def test_url_errors_use_shared_validation(tmp_path: Path, value: str) -> None:
    config = write_config(tmp_path, f'[runtime]\nserver_url = "{value}"')
    with pytest.raises(ValueError):
        LocalSettings(server_url=value)
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert [(issue.field, issue.code) for issue in caught.value.issues] == [
        ("runtime.server_url", "invalid_url")
    ]
    assert value not in str(caught.value)


@pytest.mark.parametrize(
    "value", ["~", "~/tools", "~user/tools", "$HOME/tools", "${SDK}/bin", "x/%SDK%/bin"]
)
def test_path_shorthand_rejected(tmp_path: Path, value: str) -> None:
    config = write_config(tmp_path, f'[runtime]\nappium_home = "{value}"')
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert caught.value.issues[0].code == "unsupported_path"


def test_path_punctuation_is_not_implicitly_expanded(tmp_path: Path) -> None:
    config = write_config(tmp_path, '[runtime]\nappium_home = "cash$/100%/a~b"')
    assert (
        load_configuration(config).settings.appium_home == tmp_path / "cash$/100%/a~b"
    )


@pytest.mark.parametrize("text", ["runtime = 1", "runtime = []", "[[runtime]]"])
def test_runtime_must_be_table(tmp_path: Path, text: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(write_config(tmp_path, text))
    assert caught.value.issues[0].field == "runtime"
    assert caught.value.issues[0].code == "invalid_structure"


def test_aggregates_all_known_fields_and_structure(tmp_path: Path) -> None:
    config = write_config(
        tmp_path,
        'other = 1\n[runtime]\nappium_home = ""\nnode_executable = false\n'
        'npm_executable = "$NPM"\nserver_url = "https://secret@example.com"\n'
        "extra = 3\n[runtime.java_home]\nnested = 1\n",
    )
    with pytest.raises(ConfigurationError) as caught:
        load_configuration(config)
    assert {(i.field, i.code) for i in caught.value.issues} == {
        ("other", "unknown_field"),
        ("runtime.extra", "unknown_field"),
        ("runtime.appium_home", "empty_value"),
        ("runtime.node_executable", "invalid_type"),
        ("runtime.npm_executable", "unsupported_path"),
        ("runtime.java_home", "invalid_type"),
        ("runtime.server_url", "invalid_url"),
    }
    assert all(i.source == "file" for i in caught.value.issues)
    assert "secret" not in str(caught.value)
    assert "$NPM" not in repr(caught.value.issues)


def test_loading_and_runtime_constructor_have_no_extra_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = write_config(
        tmp_path,
        '[runtime]\nappium_home = "absent"\nserver_url = "http://localhost:4723/"',
    )
    before = config.read_bytes()
    real_open = os.open
    opened: list[Path] = []

    def only_config(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        assert path == config
        assert flags & os.O_NONBLOCK
        assert flags & os.O_CLOEXEC
        assert flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC) == 0
        opened.append(path)
        return real_open(path, flags, *args, **kwargs)

    def forbidden(*args: object, **kwargs: object) -> Any:
        pytest.fail("Configuration or Runtime construction attempted extra I/O")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", only_config)
        patch.setattr(os, "getenv", forbidden)
        patch.setattr(type(os.environ), "__getitem__", forbidden)
        patch.setattr(Path, "home", forbidden)
        patch.setattr(Path, "stat", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(Path, "resolve", forbidden)
        patch.setattr(Path, "expanduser", forbidden)
        patch.setattr(socket, "socket", forbidden)
        patch.setattr(socket, "getaddrinfo", forbidden)
        patch.setattr(subprocess, "Popen", forbidden)
        loaded = load_configuration(config)
        runtime = Runtime(loaded.settings)
    assert isinstance(runtime, Runtime)
    assert opened == [config]
    assert config.read_bytes() == before
