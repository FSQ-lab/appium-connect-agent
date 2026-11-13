from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from threading import get_ident
from typing import Literal, cast

import anyio
import pytest

import appium_connect_agent.integrations._application as application_module
from appium_connect_agent.automation import ResourceStateError, Session, SessionInfo
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations import Application


class _ServiceInUseError(Exception):
    code = "service_in_use"


class _ManagedScope(AbstractContextManager[object]):
    def __init__(self, events: list[tuple[object, ...]]) -> None:
        self._events = events

    def __enter__(self) -> object:
        self._events.append(("enter", get_ident()))
        return type("Connection", (), {"ownership": "managed"})()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        del exc_type, exc_value, traceback
        self._events.append(("exit", get_ident()))
        if _ManagedRuntime.exit_error is not None:
            raise _ManagedRuntime.exit_error


class _ManagedRuntime:
    events: list[tuple[object, ...]]
    exit_error: BaseException | None
    retain_uncertain: bool

    def __init__(self, settings: LocalSettings) -> None:
        self.settings = settings

    def connect(self, *, control: object = None) -> AbstractContextManager[object]:
        del control
        raise AssertionError("managed Application used external connect")

    def start_managed(
        self,
        *,
        host: str,
        port: int,
        base_path: str = "",
        control: object = None,
    ) -> _ManagedScope:
        assert control is not None
        self.events.append(("start", host, port, base_path))
        return _ManagedScope(self.events)

    def cleanup_managed(self, *, control: object = None) -> None:
        self.events.append(("cleanup", control))


class _Session:
    def __init__(self, device_id: str, target_app_id: str | None) -> None:
        self.device_id = device_id
        self.target_app_id = target_app_id
        self.state: Literal["active", "uncertain", "closed"] = "active"

    def session_info(self) -> SessionInfo:
        return SessionInfo(
            id="automation-id",
            appium_session_id="appium-id",
            device_id=self.device_id,
            target_app_id=self.target_app_id,
            state=self.state,
            busy=False,
        )

    def quit(self, *, control: object = None) -> None:
        assert control is not None
        _ManagedRuntime.events.append(("quit", get_ident()))
        self.state = "closed"


def _create_session(*args: object, **kwargs: object) -> _Session:
    assert len(args) >= 2
    session = _Session(cast(str, args[1]), cast(str | None, kwargs.get("app_id")))
    if _ManagedRuntime.retain_uncertain:
        session.state = "uncertain"
        raise ResourceStateError(
            "session_create_unknown",
            "managed-create",
            "response_unknown",
            session=cast(Session, session),
            completed_steps=("create_requested",),
        )
    return session


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[tuple[object, ...]],
    retain_uncertain: bool,
    exit_error: BaseException | None,
) -> None:
    _ManagedRuntime.events = events
    _ManagedRuntime.retain_uncertain = retain_uncertain
    _ManagedRuntime.exit_error = exit_error
    monkeypatch.setattr(application_module, "Runtime", _ManagedRuntime)
    monkeypatch.setattr(application_module, "create_session", _create_session)


@pytest.mark.parametrize("surface", ["toolcall", "cli"])
def test_managed_session_lifecycle_is_shared_by_non_mcp_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    events: list[tuple[object, ...]] = []
    _install_fakes(monkeypatch, events=events, retain_uncertain=False, exit_error=None)

    async def scenario() -> None:
        application = Application(
            LocalSettings(
                server_mode="managed",
                managed_host="::1",
                managed_port=4723,
                managed_base_path="/wd/hub",
            ),
            tmp_path / "adb",
            surface=cast(Literal["toolcall", "cli"], surface),
        )
        opened = await application.dispatch(
            "appium_session_open",
            {"schema_version": 1, "device_id": "device-1"},
        )
        opened_value = opened.model_dump(mode="json")
        assert opened_value["data"]["ownership"] == surface
        handle = cast(str, opened_value["data"]["session_handle"])
        status = await application.dispatch(
            "appium_session_status",
            {"schema_version": 1, "session_handle": handle},
        )
        assert status.model_dump(mode="json")["data"]["session_state"] == "active"
        closed = await application.dispatch(
            "appium_session_close",
            {"schema_version": 1, "session_handle": handle},
        )
        assert closed.model_dump(mode="json")["data"]["session_state"] == "closed"
        await application.aclose()
        assert application.shutdown_degraded is False

    anyio.run(scenario)
    assert events[0] == ("start", "::1", 4723, "/wd/hub")
    assert [event[0] for event in events] == ["start", "enter", "quit", "exit"]
    assert events[1][1] == events[3][1]


@pytest.mark.parametrize("surface", ["toolcall", "cli"])
def test_managed_uncertain_shutdown_is_degraded_without_destructive_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    events: list[tuple[object, ...]] = []
    _install_fakes(
        monkeypatch,
        events=events,
        retain_uncertain=True,
        exit_error=_ServiceInUseError("usage remains"),
    )

    async def scenario() -> None:
        application = Application(
            LocalSettings(
                server_mode="managed",
                managed_host="127.0.0.1",
                managed_port=4723,
            ),
            tmp_path / "adb",
            surface=cast(Literal["toolcall", "cli"], surface),
        )
        with pytest.raises(application_module.ApplicationError) as caught:
            await application.dispatch(
                "appium_session_open",
                {"schema_version": 1, "device_id": "device-uncertain"},
            )
        assert caught.value.data.code == "session_create_unknown"
        assert caught.value.data.session_state == "uncertain"
        await application.aclose()
        assert application.shutdown_degraded is True

    anyio.run(scenario)
    assert [event[0] for event in events] == ["start", "enter", "exit"]
