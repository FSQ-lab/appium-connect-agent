from __future__ import annotations

import pytest

from appium_connect_agent.automation import _session_coordination


@pytest.fixture(autouse=True)
def fresh_process_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep intentional uncertain reservations inside their originating test."""
    monkeypatch.setattr(
        _session_coordination,
        "_COORDINATOR",
        _session_coordination._Coordinator(),
    )
