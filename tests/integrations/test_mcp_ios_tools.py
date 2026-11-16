from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import anyio
import pytest
from mcp import Client

from appium_connect_agent.automation import IosDeviceInfo, SessionInfo
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations._application import (
    Application,
    ApplicationError,
    _SessionEntry,
)
from appium_connect_agent.integrations._catalog import TOOL_CATALOG, JsonValue
from appium_connect_agent.integrations._models import PrivateRequestValidationError
from appium_connect_agent.integrations._server import create_server

_HANDLE = "s_" + ("i" * 32)
_CANARY = "ios-private-canary-中文"


def _request(**values: JsonValue) -> dict[str, JsonValue]:
    return {"schema_version": 1, **values}


class _Recorder:
    def __init__(
        self, calls: list[tuple[str, tuple[object, ...], dict[str, object]]]
    ) -> None:
        self._calls = calls

    def __getattr__(self, name: str) -> Any:
        def invoke(*args: object, **kwargs: object) -> object:
            self._calls.append((name, args, kwargs))
            if name in {"hide_keyboard", "terminate_app", "remove_app"}:
                return True
            if name == "query_app_state":
                return 4
            if name == "get_clipboard_text":
                return "clipboard-result"
            if name == "take_screenshot":
                return b"\x89PNG\r\n\x1a\n" + (b"x" * 50)
            return None

        return invoke


class _IosSession:
    def __init__(self, device_id: str = "SIM-UDID-1") -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.device = _Recorder(self.calls)
        self._element = _Recorder(self.calls)
        self._device_id = device_id

    def session_info(self) -> SessionInfo:
        return SessionInfo(
            id="automation-ios-session",
            appium_session_id="appium-ios-session",
            device_id=self._device_id,
            target_app_id="com.example.ios",
            state="active",
            busy=False,
            platform="ios",
        )

    def element(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("element", args, kwargs))
        return self._element

    def quit(self, *, control: object) -> None:
        self.calls.append(("quit", (), {"control": control}))


class _Scope:
    def __enter__(self) -> object:
        return SimpleNamespace(ownership="external")

    def __exit__(self, *exc_info: object) -> None:
        del exc_info


class _Runtime:
    diagnoses: ClassVar[list[str]] = []

    def __init__(self, settings: LocalSettings) -> None:
        del settings

    def connect(self, *, control: object) -> _Scope:
        del control
        return _Scope()

    def diagnose(self, *, target_driver: str, control: object) -> object:
        del control
        self.diagnoses.append(target_driver)
        from appium_connect_agent.runtime import DiagnosticReport

        return DiagnosticReport(
            operation_id="op-ios-runtime",
            observed_at=datetime(2026, 11, 16, tzinfo=UTC),
            target="iOS" if target_driver == "xcuitest" else "macOS",
            driver="XCUITest" if target_driver == "xcuitest" else "Mac2",
            checks=(),
            observer_errors=(),
        )


def _bound_application(surface: str = "toolcall") -> tuple[Application, _IosSession]:
    application = Application(LocalSettings(), None, surface=cast(Any, surface))
    session = _IosSession()
    application._entry = _SessionEntry(
        handle=_HANDLE,
        platform="ios",
        device_id="SIM-UDID-1",
        target_app_id="com.example.ios",
        state="active",
        busy=False,
        published=True,
        session=cast(Any, session),
    )
    return application, session


def test_three_platform_capabilities_are_identical_across_shells() -> None:
    async def scenario() -> None:
        expected = [
            {"host": "macos", "target": "android_native", "driver": "uiautomator2"},
            {"host": "macos", "target": "macos_desktop", "driver": "mac2"},
            {"host": "macos", "target": "ios_native", "driver": "xcuitest"},
        ]
        for surface in ("toolcall", "cli"):
            application = Application(LocalSettings(), None, surface=cast(Any, surface))
            result = await application.dispatch(
                "appium_capabilities_get", {"schema_version": 1}
            )
            assert result.model_dump(mode="json")["data"]["platforms"] == expected
            await application.aclose()

        mcp_application = Application(LocalSettings(), None, surface="mcp")
        async with Client(create_server(mcp_application)) as client:
            result = await client.call_tool(
                "appium.capabilities.get", {"request": {"schema_version": 1}}
            )
        assert result.structured_content is not None
        assert result.structured_content["data"]["platforms"] == expected

    anyio.run(scenario)


def test_runtime_xcuitest_matrix_rejects_external_before_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from appium_connect_agent.integrations import _application

    monkeypatch.setattr(_application, "Runtime", _Runtime)

    async def scenario() -> None:
        application = Application(LocalSettings(), None, surface="toolcall")
        static = await application.dispatch(
            "appium_runtime_check",
            _request(mode="static", target_driver="xcuitest"),
        )
        assert static.model_dump(mode="json")["data"]["report"]["target"] == "iOS"
        with pytest.raises(ApplicationError) as caught:
            await application.dispatch(
                "appium_runtime_check",
                _request(mode="external_connection", target_driver="xcuitest"),
            )
        assert (caught.value.data.code, caught.value.data.request_state) == (
            "unsupported_operation",
            "not_sent",
        )
        assert _Runtime.diagnoses == ["xcuitest"]
        await application.aclose()

    anyio.run(scenario)


def test_ios_device_discovery_needs_no_adb_and_preserves_long_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from appium_connect_agent.integrations import _application

    version = "iOS-" + ("v" * 1024)
    devices = (
        IosDeviceInfo(
            "SIM-1", "Simulator", "simulator", version, "booted", "simulator"
        ),
        IosDeviceInfo("DEVICE-1", "iPhone", "device", "18.1", "connected", "network"),
    )
    monkeypatch.setattr(_application, "list_ios_devices", lambda *, control: devices)

    async def scenario() -> None:
        application = Application(LocalSettings(), None, surface="toolcall")
        result = await application.dispatch(
            "appium_devices_list", _request(platform="ios")
        )
        payload = result.model_dump(mode="json")["data"]
        assert payload["count"] == 2
        assert payload["devices"][0] == {
            "id": "SIM-1",
            "name": "Simulator",
            "connection_state": "booted",
            "kind": "simulator",
            "platform_version": version,
            "interface": "simulator",
        }
        await application.aclose()

    anyio.run(scenario)


def test_ios_session_open_forwards_exact_public_xcuitest_arguments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from appium_connect_agent.integrations import _application

    app_path = (tmp_path / "Private.APP").resolve()
    captured: dict[str, object] = {}
    session = _IosSession("SIM-PRIVATE-1")

    def create(connection: object, udid: str, **kwargs: object) -> _IosSession:
        captured.update(connection=connection, udid=udid, **kwargs)
        return session

    monkeypatch.setattr(_application, "Runtime", _Runtime)
    monkeypatch.setattr(_application, "create_xcuitest_session", create)

    async def scenario() -> None:
        application = Application(LocalSettings(), None, surface="toolcall")
        result = await application.dispatch(
            "appium_session_open",
            _request(
                platform="ios",
                udid="SIM-PRIVATE-1",
                bundle_id="com.example.ios",
                app_path=str(app_path),
                arguments=["--private"],
                xcode_org_id="ORG_1",
                xcode_signing_id="Apple Development",
                updated_wda_bundle_id="com.example.wda",
            ),
        )
        assert result.model_dump(mode="json")["data"]["platform"] == "ios"
        assert captured["udid"] == "SIM-PRIVATE-1"
        assert captured["app_path"] == app_path
        assert captured["arguments"] == ("--private",)
        assert captured["show_xcode_log"] is False
        assert captured["wda_launch_timeout_ms"] is None
        await application.aclose()

    anyio.run(scenario)


def test_ios_action_dispatch_and_cross_platform_gates() -> None:
    async def scenario() -> None:
        application, session = _bound_application()
        ios_scroll = await application.dispatch(
            "appium_element_gesture",
            _request(
                session_handle=_HANDLE,
                intent="ios_scroll",
                locator={"by": "accessibility_id", "value": "list"},
                direction="down",
                distance=0.5,
            ),
        )
        assert ios_scroll.model_dump(mode="json")["data"]["intent"] == "ios_scroll"
        await application.dispatch(
            "appium_element_gesture",
            _request(
                session_handle=_HANDLE,
                intent="scroll_to",
                container_locator={"by": "id", "value": "container"},
                target_by="ios_predicate_string",
                target_value="label == 'Target'",
                target_predicate="enabled == true",
                max_swipes=3,
            ),
        )
        key = await application.dispatch(
            "appium_device_key",
            _request(session_handle=_HANDLE, kind="ios_button", button="home"),
        )
        assert key.model_dump(mode="json")["data"]["kind"] == "ios_button"
        for name, request in (
            ("appium_device_keyboard_hide", _request(session_handle=_HANDLE)),
            (
                "appium_device_clipboard",
                _request(session_handle=_HANDLE, intent="set", text="private"),
            ),
            (
                "appium_device_alert",
                _request(session_handle=_HANDLE, action="accept"),
            ),
            (
                "appium_app_package",
                _request(
                    session_handle=_HANDLE,
                    intent="remove",
                    app_id="com.example.ios",
                ),
            ),
            (
                "appium_macos_keys",
                _request(
                    session_handle=_HANDLE,
                    target="system",
                    keys=[{"key": "XCUIKeyboardKeyReturn", "modifier_flags": 0}],
                ),
            ),
        ):
            await application.dispatch(name, request)
        with pytest.raises(ApplicationError) as caught:
            await application.dispatch(
                "appium_device_back", _request(session_handle=_HANDLE)
            )
        assert caught.value.data.code == "unsupported_operation"
        names = [name for name, _args, _kwargs in session.calls]
        assert "ios_scroll" in names
        assert "press_button" in names
        assert "hide_keyboard" in names
        assert "set_clipboard_text" in names
        assert "accept_alert" in names
        assert "remove_app" in names
        assert "send_keys" in names
        await application.aclose()

    anyio.run(scenario)


_PRIVATE_CASES: tuple[tuple[str, dict[str, JsonValue]], ...] = (
    ("appium_session_open", _request(platform="ios", udid=_CANARY + "!")),
    (
        "appium_device_key",
        _request(session_handle=_HANDLE, kind="ios_button", button=_CANARY),
    ),
    (
        "appium_device_clipboard",
        _request(session_handle=_HANDLE, intent="set", text=_CANARY, label=True),
    ),
    (
        "appium_app_lifecycle",
        _request(session_handle=_HANDLE, intent="launch", app_path=_CANARY),
    ),
    (
        "appium_app_package",
        _request(session_handle=_HANDLE, intent="install", app_path=_CANARY),
    ),
    (
        "appium_device_pointer",
        _request(session_handle=_HANDLE, intent="tap", x=_CANARY, y=1),
    ),
    (
        "appium_macos_keys",
        _request(session_handle=_HANDLE, target="system", keys=[{"key": _CANARY}]),
    ),
)


@pytest.mark.parametrize(("tool_name", "arguments"), _PRIVATE_CASES)
def test_all_private_root_requests_hide_invalid_input_across_three_shells(
    tool_name: str, arguments: dict[str, JsonValue]
) -> None:
    spec = TOOL_CATALOG.by_tool_name(tool_name)
    with pytest.raises(PrivateRequestValidationError) as direct:
        spec.request_adapter.validate_python(arguments, strict=True)
    assert _CANARY not in str(direct.value)

    async def scenario() -> None:
        for surface in ("toolcall", "cli"):
            application = Application(LocalSettings(), None, surface=cast(Any, surface))
            with pytest.raises(ApplicationError) as caught:
                await application.dispatch(tool_name, arguments)
            assert caught.value.data.code == "invalid_argument"
            assert _CANARY not in str(caught.value)
            await application.aclose()

        mcp_application = Application(LocalSettings(), None, surface="mcp")
        async with Client(create_server(mcp_application)) as client:
            result = await client.call_tool(
                spec.mcp_name,
                {"request": arguments},
            )
        assert result.is_error is True
        assert _CANARY not in "".join(
            block.text for block in result.content if hasattr(block, "text")
        )

    anyio.run(scenario)
