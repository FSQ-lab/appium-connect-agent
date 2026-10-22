import socket
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.runtime import Runtime


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HTTP://LOCALHOST:4723/", "http://127.0.0.1:4723"),
        ("http://127.2.3.4:1/wd/hub/", "http://127.2.3.4:1/wd/hub"),
        ("http://[0:0:0:0:0:0:0:1]:65535/", "http://[::1]:65535"),
        ("http://127.0.0.1:4723/a-._~9", "http://127.0.0.1:4723/a-._~9"),
    ],
)
def test_normalization(value: str, expected: str) -> None:
    assert LocalSettings(server_url=value).server_url == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://localhost",
        "http://localhost:0",
        "http://localhost:65536",
        "https://localhost:4723",
        "http://example.com:4723",
        "http://192.168.1.1:4723",
        "http://0.0.0.0:4723",
        "http://[::]:4723",
        "http://[::1]suffix:4723",
        "http://[::1]:4723suffix",
        "http://user@localhost:4723",
        "http://localhost:4723?",
        "http://localhost:4723#",
        "http://localhost:4723/%61",
        "http://localhost:4723/..",
        "http://localhost:4723/./",
        "http://localhost:4723//",
        "http://localhost:4723/a b",
        "http://localhost:4723/\n",
        "http://localhost:4723/é",
        "http://localhost:4723/\\",
        "http://localhost:4723/" + "x" * 2048,
        True,
        12,
        Path("/absolute"),
    ],
)
def test_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        LocalSettings(server_url=value)  # type: ignore[arg-type]


def test_construction_zero_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("construction attempted I/O")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    settings = LocalSettings(server_url="http://LOCALHOST:4723/")
    scope = Runtime(settings).connect()
    assert scope is not None
    assert len(settings.__dataclass_fields__) == 7
    with pytest.raises(FrozenInstanceError):
        settings.server_url = None  # type: ignore[misc]


def test_url_limit_is_inclusive() -> None:
    prefix = "http://127.0.0.1:4723/"
    url = prefix + "a" * (2048 - len(prefix))
    assert LocalSettings(server_url=url).server_url == url
    with pytest.raises(ValueError):
        LocalSettings(server_url=url + "a")
