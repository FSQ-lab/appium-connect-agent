from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import LocalSettings as ExportedSettings


def test_unique_frozen_keyword_value() -> None:
    assert ExportedSettings is LocalSettings
    settings = LocalSettings(appium_home=Path("/not-required-to-exist"))
    assert settings.appium_home == Path("/not-required-to-exist")
    with pytest.raises(FrozenInstanceError):
        settings.appium_home = None  # type: ignore[misc]
    with pytest.raises(TypeError):
        LocalSettings(Path("/absolute"))  # type: ignore[call-arg]


@pytest.mark.parametrize("value", ["/absolute", Path("relative"), 1, True])
@pytest.mark.parametrize("field", list(LocalSettings.__dataclass_fields__))
def test_invalid_settings(value: Any, field: str) -> None:
    with pytest.raises(ValueError):
        LocalSettings(**{field: value})
