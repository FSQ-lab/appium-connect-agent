from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import LocalSettings as ExportedSettings

_PATH_FIELDS = (
    "appium_executable",
    "appium_home",
    "node_executable",
    "npm_executable",
    "java_home",
    "android_sdk_root",
)


def test_unique_frozen_keyword_value() -> None:
    assert ExportedSettings is LocalSettings
    settings = LocalSettings(appium_home=Path("/not-required-to-exist"))
    assert settings.appium_home == Path("/not-required-to-exist")
    with pytest.raises(FrozenInstanceError):
        settings.appium_home = None  # type: ignore[misc]
    with pytest.raises(TypeError):
        LocalSettings(Path("/absolute"))  # type: ignore[call-arg]


@pytest.mark.parametrize("value", ["/absolute", Path("relative"), 1, True])
@pytest.mark.parametrize("field", _PATH_FIELDS)
def test_invalid_settings(value: Any, field: str) -> None:
    with pytest.raises(ValueError):
        LocalSettings(**{field: value})


def test_managed_settings_are_explicit_frozen_values() -> None:
    settings = LocalSettings(
        server_mode="managed",
        managed_host="::1",
        managed_port=4723,
        managed_base_path="/wd/hub",
    )
    assert settings.server_mode == "managed"
    assert settings.managed_host == "::1"
    assert settings.managed_port == 4723
    assert settings.managed_base_path == "/wd/hub"
    assert len(settings.__dataclass_fields__) == 11
    with pytest.raises(FrozenInstanceError):
        settings.managed_port = 4724  # type: ignore[misc]


class _StringSubclass(str):
    pass


class _IntSubclass(int):
    pass


@pytest.mark.parametrize(
    "values",
    [
        {"server_mode": "other"},
        {"server_mode": _StringSubclass("external")},
        {"server_mode": 1},
        {"managed_host": "localhost"},
        {"managed_host": 1},
        {"managed_host": _StringSubclass("127.0.0.1")},
        {"managed_port": True},
        {"managed_port": 0},
        {"managed_port": 65536},
        {"managed_port": 1.0},
        {"managed_port": _IntSubclass(4723)},
        {"managed_base_path": None},
        {"managed_base_path": _StringSubclass("")},
        {"managed_base_path": "/"},
        {"managed_base_path": "wd/hub"},
        {"managed_base_path": "/wd/hub/"},
        {"managed_base_path": "/wd//hub"},
        {"managed_base_path": "/wd/../hub"},
        {"managed_base_path": "/wd/%68ub"},
        {"managed_base_path": "/wd/é"},
    ],
)
def test_invalid_managed_field_values(values: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        LocalSettings(**values)


@pytest.mark.parametrize(
    "values",
    [
        {"managed_host": "127.0.0.1"},
        {"managed_port": 4723},
        {"managed_base_path": "/wd/hub"},
        {"server_mode": "managed"},
        {
            "server_mode": "managed",
            "managed_host": "127.0.0.1",
            "managed_port": 4723,
            "server_url": "http://127.0.0.1:4723",
        },
        {
            "server_mode": "managed",
            "managed_host": "127.0.0.1",
            "managed_port": 4723,
            "appium_executable": Path("/appium"),
        },
        {
            "server_mode": "managed",
            "managed_host": "127.0.0.1",
            "managed_port": 4723,
            "appium_home": Path("/appium-home"),
        },
    ],
)
def test_modes_reject_ambiguous_settings(values: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        LocalSettings(**values)


def test_default_settings_preserve_external_behavior() -> None:
    assert LocalSettings() == LocalSettings(
        server_mode="external",
        managed_host=None,
        managed_port=None,
        managed_base_path="",
    )
