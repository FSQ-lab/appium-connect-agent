from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from appium_connect_agent.automation import _session_coordination
from appium_connect_agent.runtime import _coordination


@pytest.fixture(autouse=True)
def fresh_process_coordinator() -> Iterator[None]:
    """Keep intentional uncertain reservations inside their originating test."""
    coordinators = (
        _session_coordination._COORDINATOR,
        _session_coordination._MAC2_COORDINATOR,
        _session_coordination._XCUITEST_COORDINATOR,
    )

    def clear_reservations() -> None:
        for coordinator in coordinators:
            with coordinator._lock:
                coordinator._devices.clear()
                coordinator._ports.clear()

    clear_reservations()
    try:
        yield
    finally:
        clear_reservations()


@pytest.fixture(autouse=True)
def isolated_runtime_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent protocol tests from contending with another project worktree."""
    home = tmp_path.resolve() / "runtime-account"
    home.mkdir()
    monkeypatch.setattr(_coordination, "_account_home", lambda: home)
