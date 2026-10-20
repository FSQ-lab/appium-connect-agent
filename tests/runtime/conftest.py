from pathlib import Path

import pytest

from appium_connect_agent.runtime import _coordination


@pytest.fixture(autouse=True)
def isolated_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path.resolve() / "account"
    home.mkdir()
    monkeypatch.setattr(_coordination, "_account_home", lambda: home)
    monkeypatch.setenv("PATH", "")
