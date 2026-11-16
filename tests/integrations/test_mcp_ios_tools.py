from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import anyio
import pytest
from mcp import Client
from mcp.types import TextContent

import appium_connect_agent.automation._session as session_module
from appium_connect_agent.automation import CommandError, IosDeviceInfo, SessionInfo
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations import cli
from appium_connect_agent.integrations._application import (
    Application,
    ApplicationError,
    _SessionEntry,
)
from appium_connect_agent.integrations._catalog import TOOL_CATALOG, JsonValue
from appium_connect_agent.integrations._cli_protocol import StopRequest
from appium_connect_agent.integrations._daemon import create_and_serve_daemon
from appium_connect_agent.integrations._models import (
    PrivateRequestValidationError,
    canonical_json,
)
from appium_connect_agent.integrations._server import create_server
from appium_connect_agent.integrations._toolcall import build_tool_bindings
from tests.automation._action_protocol import ActionProtocolService, Request
from tests.automation.test_ios_actions import (
    IosActionProtocolService,
    script_and_payload,
)

from .conftest import McpHarness
from .test_cli_bridge import _run_cli

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


class _IntegrationIosProtocolService(IosActionProtocolService):
    source = (
        '<AppiumAUT><XCUIElementTypeApplication name="app" enabled="true" '
        'visible="true" x="0" y="0" width="402" height="874" index="0">'
        '<XCUIElementTypeStaticText name="target" label="Target" value="Value" '
        'enabled="true" visible="true" accessible="true" hittable="true" '
        'x="10" y="20" width="100" height="40" index="3"/>'
        "</XCUIElementTypeApplication></AppiumAUT>"
    )

    def __init__(self) -> None:
        super().__init__()
        for value in ("target", "container", "source", "destination"):
            self.matches[(None, "accessibility id", value)] = [value]
        self.matches[("container", "accessibility id", "target")] = ["target"]
        self.states.update(
            {
                ("target", "name"): "target",
                ("target", "text"): "Value",
                ("target", "type"): "XCUIElementTypeStaticText",
                ("target", "label"): "Target",
                ("target", "value"): "Value",
                ("target", "placeholderValue"): None,
                ("target", "enabled"): True,
                ("target", "focused"): "false",
                ("target", "selected"): "false",
                ("target", "hittable"): "true",
                ("target", "accessible"): True,
                ("target", "displayed"): True,
                ("target", "index"): "3",
                ("target", "traits"): "StaticText",
            }
        )

    def _default_payload(self, request: Request, kind: str) -> object:
        if request.path.endswith("/source"):
            return {"value": self.source}
        if request.path.endswith("/execute/sync") and request.body is not None:
            script = request.body.get("script")
            if script == "mobile: deviceScreenInfo":
                return {"value": {"screenSize": {"width": 402, "height": 874}}}
            if script == "macos: getClipboard":
                return {"value": base64.b64encode(b"mac clipboard").decode()}
            if script == "macos: setClipboard":
                return {"value": None}
        return super()._default_payload(request, kind)


def _patch_xcuitest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_module,
        "_prepare_xcuitest_derived_data",
        lambda port, operation_id: f"/private/tmp/test-{port}-{operation_id}",
    )


def _real_application(service: ActionProtocolService, surface: str) -> Application:
    return Application(
        LocalSettings(server_url=service.url), None, surface=cast(Any, surface)
    )


def _locator(value: str = "target") -> dict[str, JsonValue]:
    return {"by": "accessibility_id", "value": value}


def _payload_without_random(value: Mapping[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(value))
    result.pop("call_id", None)
    data = result.get("data")
    if isinstance(data, dict):
        data.pop("session_handle", None)
    return cast(dict[str, Any], result)


@contextmanager
def _short_root() -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="aca-ios-", dir="/private/tmp"))
    root.chmod(0o700)
    try:
        yield root
    finally:
        shutil.rmtree(root)


async def _stop_daemon(endpoint: Path) -> None:
    stopped = await cli._exchange(
        endpoint,
        StopRequest(protocol_version=1, operation="daemon.stop"),
        10.0,
    )
    assert stopped.kind == "daemon_stopped"


def test_three_platform_capabilities_are_identical_across_shells(
    mcp_harness: McpHarness,
) -> None:
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

        async with Client(mcp_harness.parameters()) as stdio_client:
            stdio_result = await stdio_client.call_tool(
                "appium.capabilities.get", {"request": {"schema_version": 1}}
            )
        assert stdio_result.structured_content is not None
        assert stdio_result.structured_content["data"]["platforms"] == expected

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


def test_real_ios_protocol_exercises_complete_integration_matrix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_xcuitest(monkeypatch)
    app = tmp_path / "Matrix.app"
    app.mkdir()
    (app / "Info.plist").write_bytes(b"plist")
    ipa = tmp_path / "Matrix.ipa"
    ipa.write_bytes(b"ipa")

    with _IntegrationIosProtocolService() as service:

        async def scenario() -> None:
            application = _real_application(service, "toolcall")
            opened = await application.dispatch(
                "appium_session_open",
                _request(
                    platform="ios",
                    udid="IOS-MATRIX-DEVICE",
                    bundle_id="com.example.ios",
                    arguments=["--safe"],
                ),
            )
            handle = cast(str, opened.model_dump(mode="json")["data"]["session_handle"])
            common = {"session_handle": handle}

            tree = await application.dispatch(
                "appium_ui_observe",
                _request(**common, mode="tree", locator=None),
            )
            assert (
                tree.model_dump(mode="json")["data"]["document"]["payload"]["roots"][0][
                    "type"
                ]
                == "Application"
            )
            attributes = await application.dispatch(
                "appium_ui_observe",
                _request(
                    **common,
                    mode="attributes",
                    locator=_locator(),
                    attributes=["accessible", "index", "traits"],
                ),
            )
            observed = attributes.model_dump(mode="json")["data"]["document"][
                "payload"
            ]["attributes"]
            assert [(item["name"], item["value"]) for item in observed] == [
                ("accessible", True),
                ("index", 3),
                ("traits", "StaticText"),
            ]
            structure = await application.dispatch(
                "appium_ui_observe",
                _request(
                    **common,
                    mode="structure",
                    locator=_locator(),
                    structure_scope="target",
                ),
            )
            assert (
                structure.model_dump(mode="json")["data"]["document"]["payload"][
                    "roots"
                ][0]["tag"]
                == "XCUIElementTypeStaticText"
            )

            for kind, extra in (
                ("single", {}),
                ("double", {}),
                ("long", {"duration_ms": 750}),
            ):
                result = await application.dispatch(
                    "appium_element_click",
                    _request(**common, kind=kind, locator=_locator(), **extra),
                )
                assert result.model_dump(mode="json")["execution"] == "completed"
            for intent, text in (("send", "matrix text"), ("clear", None)):
                values: dict[str, JsonValue] = {
                    **common,
                    "intent": intent,
                    "locator": _locator(),
                }
                if text is not None:
                    values["text"] = text
                await application.dispatch("appium_element_text", _request(**values))

            gestures: tuple[dict[str, JsonValue], ...] = (
                {
                    **common,
                    "intent": "macos_swipe",
                    "locator": _locator(),
                    "direction": "left",
                    "velocity": 2.5,
                },
                {
                    **common,
                    "intent": "ios_scroll",
                    "locator": _locator(),
                    "direction": "down",
                    "distance": 0.75,
                },
                {
                    **common,
                    "intent": "scroll_to",
                    "container_locator": _locator("container"),
                    "target_by": "accessibility_id",
                    "target_value": "target",
                    "max_swipes": 3,
                },
                {
                    **common,
                    "intent": "drag_and_drop",
                    "source_locator": _locator("source"),
                    "destination_locator": _locator("destination"),
                    "destination_x_ratio": 1.0,
                    "destination_y_ratio": 0.0,
                    "duration_ms": 500,
                },
            )
            for request in gestures:
                await application.dispatch(
                    "appium_element_gesture", _request(**request)
                )

            await application.dispatch(
                "appium_device_key",
                _request(**common, kind="ios_button", button="home"),
            )
            await application.dispatch(
                "appium_device_keyboard_hide", _request(**common)
            )
            await application.dispatch(
                "appium_device_clipboard",
                _request(**common, intent="set", text="秘密"),
            )
            clipboard = await application.dispatch(
                "appium_device_clipboard", _request(**common, intent="get")
            )
            assert clipboard.model_dump(mode="json")["data"]["text"] == "剪贴板"
            for action in ("accept", "dismiss"):
                await application.dispatch(
                    "appium_device_alert", _request(**common, action=action)
                )
            for intent in ("launch", "activate", "query_state", "terminate"):
                values = {**common, "intent": intent}
                if intent == "launch":
                    values.update(bundle_id="com.example.ios", arguments=["--safe"])
                else:
                    values["app_id"] = "com.example.ios"
                await application.dispatch(
                    "appium_app_lifecycle",
                    _request(**values),
                )
            for package in (app, ipa):
                await application.dispatch(
                    "appium_app_package",
                    _request(**common, intent="install", app_path=str(package)),
                )
            await application.dispatch(
                "appium_app_package",
                _request(**common, intent="remove", app_id="com.example.ios"),
            )
            for target in ("system", "element"):
                values = {
                    **common,
                    "target": target,
                    "keys": [{"key": "a"}],
                }
                if target == "element":
                    values["locator"] = _locator()
                await application.dispatch("appium_macos_keys", _request(**values))
            screenshot = await application.dispatch(
                "appium_device_screenshot", _request(**common)
            )
            assert screenshot.model_dump(mode="json")["data"]["byte_length"] > 0
            await application.dispatch(
                "appium_device_pointer", _request(**common, intent="tap", x=1, y=2)
            )
            await application.dispatch(
                "appium_device_pointer",
                _request(
                    **common,
                    intent="drag",
                    start_x=1,
                    start_y=2,
                    end_x=3,
                    end_y=4,
                    duration_ms=500,
                ),
            )
            await application.dispatch(
                "appium_session_close", _request(session_handle=handle)
            )

            mac_open = await application.dispatch(
                "appium_session_open",
                _request(platform="macos", bundle_id="com.example.macos"),
            )
            mac_handle = cast(
                str, mac_open.model_dump(mode="json")["data"]["session_handle"]
            )
            await application.dispatch(
                "appium_device_clipboard",
                _request(session_handle=mac_handle, intent="set", text="mac clipboard"),
            )
            await application.dispatch(
                "appium_device_clipboard",
                _request(session_handle=mac_handle, intent="get"),
            )
            await application.dispatch(
                "appium_session_close", _request(session_handle=mac_handle)
            )
            await application.aclose()

        anyio.run(scenario)

        requests = service.snapshot()
        assert len([item for item in requests if item.path.endswith("/session")]) == 2
        assert len([item for item in requests if item.method == "DELETE"]) == 2
        assert len([item for item in requests if item.path.endswith("/click")]) == 1
        scripts = [
            script_and_payload(item)
            for item in requests
            if item.path.endswith("/execute/sync")
            and item.body is not None
            and isinstance(item.body.get("args"), list)
            and len(cast(list[object], item.body["args"])) == 1
        ]
        expected_once = {
            "mobile: doubleTap",
            "mobile: touchAndHold",
            "mobile: swipe",
            "mobile: scroll",
            "mobile: dragFromToForDuration",
            "mobile: pressButton",
            "mobile: hideKeyboard",
            "mobile: getClipboard",
            "mobile: setClipboard",
            "mobile: activateApp",
            "mobile: terminateApp",
            "mobile: queryAppState",
            "mobile: launchApp",
            "mobile: removeApp",
        }
        names = [cast(str, name) for name, _payload in scripts]
        for name in expected_once:
            assert names.count(name) == (2 if name == "mobile: scroll" else 1)
        assert names.count("macos: getClipboard") == 1
        assert names.count("macos: setClipboard") == 1
        assert names.count("mobile: installApp") == 2
        assert names.count("mobile: alert") == 2


def test_real_ios_representative_flow_is_equivalent_across_three_shells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from appium_connect_agent.integrations import _application

    _patch_xcuitest(monkeypatch)
    ios_devices = (
        IosDeviceInfo(
            "IOS-SHELL-DEVICE",
            "Shell iPhone",
            "device",
            "18.1",
            "connected",
            "usb",
        ),
    )
    monkeypatch.setattr(
        _application, "list_ios_devices", lambda *, control: ios_devices
    )

    def normalize(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = [_payload_without_random(payload) for payload in payloads]
        capability_data = normalized[0]["data"]
        capability_data.pop("integration_form")
        capability_data.pop("transport")
        capability_data["protocol_target"] = None
        capability_data["tools"] = [
            name.replace(".", "_") for name in capability_data["tools"]
        ]
        for payload in normalized:
            data = payload.get("data")
            if isinstance(data, dict) and "ownership" in data:
                data["ownership"] = "surface"
        return normalized

    with _IntegrationIosProtocolService() as service:

        async def mcp_flow() -> list[dict[str, Any]]:
            application = _real_application(service, "mcp")
            payloads: list[dict[str, Any]] = []
            async with Client(create_server(application)) as client:
                for name, request in (
                    ("appium.capabilities.get", _request()),
                    ("appium.devices.list", _request(platform="ios")),
                ):
                    result = await client.call_tool(name, {"request": request})
                    assert result.is_error is False
                    payloads.append(cast(dict[str, Any], result.structured_content))
                opened = await client.call_tool(
                    "appium.session.open",
                    {
                        "request": _request(
                            platform="ios",
                            udid="IOS-SHELL-DEVICE",
                            bundle_id="com.example.ios",
                        )
                    },
                )
                open_payload = cast(dict[str, Any], opened.structured_content)
                payloads.append(open_payload)
                handle = cast(str, open_payload["data"]["session_handle"])
                for name, request in (
                    (
                        "appium.device.key",
                        _request(
                            session_handle=handle,
                            kind="ios_button",
                            button="home",
                        ),
                    ),
                    (
                        "appium.element.gesture",
                        _request(
                            session_handle=handle,
                            intent="ios_scroll",
                            locator=_locator(),
                            direction="down",
                            distance=0.5,
                        ),
                    ),
                    ("appium.session.close", _request(session_handle=handle)),
                ):
                    result = await client.call_tool(name, {"request": request})
                    assert result.is_error is False
                    payloads.append(cast(dict[str, Any], result.structured_content))
            return payloads

        async def toolcall_flow() -> list[dict[str, Any]]:
            application = _real_application(service, "toolcall")
            bindings = {item.name: item for item in build_tool_bindings(application)}
            payloads: list[dict[str, Any]] = []

            async def invoke(
                name: str, request: dict[str, JsonValue]
            ) -> dict[str, Any]:
                encoded = await bindings[name].invoke(
                    SimpleNamespace(name=name, arguments=request, call_id="host-call")
                )
                return cast(dict[str, Any], json.loads(encoded))

            payloads.append(await invoke("appium_capabilities_get", _request()))
            payloads.append(
                await invoke("appium_devices_list", _request(platform="ios"))
            )
            opened = await invoke(
                "appium_session_open",
                _request(
                    platform="ios",
                    udid="IOS-SHELL-DEVICE",
                    bundle_id="com.example.ios",
                ),
            )
            payloads.append(opened)
            handle = cast(str, opened["data"]["session_handle"])
            payloads.append(
                await invoke(
                    "appium_device_key",
                    _request(session_handle=handle, kind="ios_button", button="home"),
                )
            )
            payloads.append(
                await invoke(
                    "appium_element_gesture",
                    _request(
                        session_handle=handle,
                        intent="ios_scroll",
                        locator=_locator(),
                        direction="down",
                        distance=0.5,
                    ),
                )
            )
            payloads.append(
                await invoke("appium_session_close", _request(session_handle=handle))
            )
            await application.aclose()
            return payloads

        async def cli_flow() -> list[dict[str, Any]]:
            with _short_root() as root:
                endpoint = root / "bridge.sock"
                account = root / "account"
                account.mkdir()
                account.chmod(0o700)
                outcomes: list[int] = []

                async def daemon() -> None:
                    outcome = await create_and_serve_daemon(
                        LocalSettings(server_url=service.url),
                        None,
                        endpoint,
                        30.0,
                        account_directory=account,
                        watch_signals=False,
                    )
                    outcomes.append(outcome.exit_code)

                async def invoke(
                    name: str, request: dict[str, JsonValue]
                ) -> dict[str, Any]:
                    completed = await anyio.to_thread.run_sync(
                        _run_cli,
                        "call",
                        name,
                        "--json-args",
                        json.dumps(request),
                        "--socket",
                        os.fspath(endpoint),
                    )
                    assert completed.returncode == 0
                    assert completed.stderr == ""
                    return cast(dict[str, Any], json.loads(completed.stdout))

                async with anyio.create_task_group() as group:
                    group.start_soon(daemon)
                    with anyio.fail_after(2):
                        while not endpoint.exists():
                            await anyio.sleep(0.01)
                    payloads = [
                        await invoke("appium_capabilities_get", _request()),
                        await invoke("appium_devices_list", _request(platform="ios")),
                    ]
                    opened = await invoke(
                        "appium_session_open",
                        _request(
                            platform="ios",
                            udid="IOS-SHELL-DEVICE",
                            bundle_id="com.example.ios",
                        ),
                    )
                    payloads.append(opened)
                    handle = cast(str, opened["data"]["session_handle"])
                    payloads.append(
                        await invoke(
                            "appium_device_key",
                            _request(
                                session_handle=handle,
                                kind="ios_button",
                                button="home",
                            ),
                        )
                    )
                    payloads.append(
                        await invoke(
                            "appium_element_gesture",
                            _request(
                                session_handle=handle,
                                intent="ios_scroll",
                                locator=_locator(),
                                direction="down",
                                distance=0.5,
                            ),
                        )
                    )
                    payloads.append(
                        await invoke(
                            "appium_session_close", _request(session_handle=handle)
                        )
                    )
                    await _stop_daemon(endpoint)
                assert outcomes == [0]
                return payloads

        mcp_payloads = anyio.run(mcp_flow)
        toolcall_payloads = anyio.run(toolcall_flow)
        cli_payloads = anyio.run(cli_flow)
        assert (
            normalize(mcp_payloads)
            == normalize(toolcall_payloads)
            == normalize(cli_payloads)
        )
        assert len(service.of_kind("create")) == 3
        assert len(service.of_kind("quit")) == 3
        assert [
            name
            for name, _payload in map(script_and_payload, service.of_kind("action"))
        ].count("mobile: pressButton") == 3


class _FailureTarget:
    def __init__(self, failures: list[BaseException]) -> None:
        self.failures = failures

    def __getattr__(self, name: str) -> Any:
        del name

        def fail(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise self.failures[0]

        return fail


class _FailureSession:
    def __init__(self, platform: str, failures: list[BaseException]) -> None:
        self.platform = platform
        self.target = _FailureTarget(failures)
        self.device = self.target

    def session_info(self) -> SessionInfo:
        return SessionInfo(
            id="failure-session",
            appium_session_id="failure-appium-session",
            device_id="failure-device",
            target_app_id="com.example.failure",
            state="active",
            busy=False,
            platform=cast(Any, self.platform),
        )

    def element(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        return self.target

    def quit(self, *, control: object) -> None:
        del control


def _failure_application(
    surface: str,
    platform: str,
    failures: list[BaseException],
    *,
    session_open: bool,
) -> Application:
    application = Application(
        LocalSettings(server_url="http://127.0.0.1:4723"),
        None,
        surface=cast(Any, surface),
    )
    if not session_open:
        application._entry = _SessionEntry(
            handle=_HANDLE,
            platform=cast(Any, platform),
            device_id="failure-device",
            target_app_id="com.example.failure",
            state="active",
            busy=False,
            published=True,
            session=cast(Any, _FailureSession(platform, failures)),
        )
    return application


def _known_private_failure(canary: str) -> CommandError:
    try:
        raise RuntimeError(f"cause {canary}")
    except RuntimeError as cause:
        try:
            raise CommandError(
                "command_failed",
                "op-private-failure",
                "response_received",
                cleanup_errors=(RuntimeError(f"cleanup {canary}"),),
            ) from cause
        except CommandError as failure:
            return failure


def _private_cases(
    tmp_path: Path,
) -> tuple[
    tuple[str, str, dict[str, JsonValue], dict[str, JsonValue], tuple[str, ...]], ...
]:
    canary = "IOS_PRIVATE_CANARY_20261116"
    app = str((tmp_path / f"{canary}.app").resolve())
    ipa = str((tmp_path / f"{canary}.ipa").resolve())
    common = {"session_handle": _HANDLE}
    return (
        (
            "appium_session_open",
            "ios",
            _request(platform="ios", udid=f"bad {canary}"),
            _request(
                platform="ios",
                udid=canary,
                app_path=app,
                arguments=[canary],
                xcode_org_id=canary,
                xcode_signing_id=f"Apple Development {canary}",
                updated_wda_bundle_id="com.example.private",
            ),
            (canary, app),
        ),
        (
            "appium_session_open",
            "ios",
            _request(platform="ios", udid=f"bad {canary}", app_path=ipa),
            _request(platform="ios", udid=f"{canary}IPA", app_path=ipa),
            (canary, ipa),
        ),
        (
            "appium_device_key",
            "android",
            _request(**common, kind="press", keycode=canary),
            _request(**common, kind="press", keycode=2_147_483_647),
            (canary, "2147483647"),
        ),
        (
            "appium_device_key",
            "ios",
            _request(**common, kind="ios_button", button=canary),
            _request(**common, kind="ios_button", button="home"),
            (canary,),
        ),
        (
            "appium_device_clipboard",
            "ios",
            _request(**common, intent="set", text=canary, label=True),
            _request(**common, intent="set", text=canary, label=canary),
            (canary,),
        ),
        (
            "appium_app_lifecycle",
            "ios",
            _request(**common, intent="launch", app_path=f"relative/{canary}.app"),
            _request(**common, intent="launch", app_path=app, arguments=[canary]),
            (canary, app),
        ),
        (
            "appium_app_package",
            "ios",
            _request(**common, intent="install", app_path=f"relative/{canary}.ipa"),
            _request(**common, intent="install", app_path=ipa),
            (canary, ipa),
        ),
        (
            "appium_device_pointer",
            "ios",
            _request(**common, intent="tap", x=canary, y=1),
            _request(**common, intent="tap", x=987_654_321, y=1),
            (canary, "987654321"),
        ),
        (
            "appium_macos_keys",
            "ios",
            _request(**common, target="system", keys=[{"key": canary + "\n"}]),
            _request(**common, target="system", keys=[{"key": "a"}]),
            (canary,),
        ),
    )


@pytest.mark.parametrize("case_index", range(9))
def test_private_requests_redact_validation_known_and_unknown_failures_on_all_shells(
    case_index: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from appium_connect_agent.integrations import _application

    tool_name, platform, invalid, valid, secrets = _private_cases(tmp_path)[case_index]
    spec = TOOL_CATALOG.by_tool_name(tool_name)
    session_open = tool_name == "appium_session_open"
    failures: list[BaseException] = [RuntimeError("unset")]

    def create(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise failures[0]

    monkeypatch.setattr(_application, "create_xcuitest_session", create)
    caplog.set_level(logging.DEBUG, logger="appium_connect_agent.integrations")

    def assert_private(*values: str) -> None:
        combined = "\n".join(values)
        for secret in secrets:
            assert secret not in combined
        assert "Traceback" not in combined
        assert "boom " not in combined

    async def mcp_call(arguments: dict[str, JsonValue], failure: BaseException) -> str:
        failures[0] = failure
        application = _failure_application(
            "mcp", platform, failures, session_open=session_open
        )
        async with Client(create_server(application)) as client:
            result = await client.call_tool(spec.mcp_name, {"request": arguments})
        assert result.is_error is True
        text = "\n".join(getattr(item, "text", "") for item in result.content)
        assert_private(text)
        return text

    async def toolcall_invalid() -> str:
        application = _failure_application(
            "toolcall", platform, failures, session_open=session_open
        )
        binding = {item.name: item for item in build_tool_bindings(application)}[
            tool_name
        ]
        payload = await binding.on_invalid_input(
            SimpleNamespace(name=tool_name, message=f"invalid {secrets[0]}")
        )
        await application.aclose()
        assert_private(payload)
        return payload

    async def toolcall_call(
        arguments: dict[str, JsonValue], failure: BaseException
    ) -> str:
        failures[0] = failure
        application = _failure_application(
            "toolcall", platform, failures, session_open=session_open
        )
        binding = {item.name: item for item in build_tool_bindings(application)}[
            tool_name
        ]
        payload = await binding.invoke(
            SimpleNamespace(name=tool_name, arguments=arguments, call_id="host-call")
        )
        await application.aclose()
        assert_private(payload)
        return payload

    async def cli_call(arguments: dict[str, JsonValue], failure: BaseException) -> str:
        failures[0] = failure
        with _short_root() as root:
            endpoint = root / "bridge.sock"
            account = root / "account"
            account.mkdir()
            account.chmod(0o700)

            def factory(*args: object, **kwargs: object) -> Application:
                del args, kwargs
                return _failure_application(
                    "cli", platform, failures, session_open=session_open
                )

            async def daemon() -> None:
                await create_and_serve_daemon(
                    LocalSettings(),
                    None,
                    endpoint,
                    30.0,
                    application_factory=factory,
                    account_directory=account,
                    watch_signals=False,
                )

            async with anyio.create_task_group() as group:
                group.start_soon(daemon)
                with anyio.fail_after(2):
                    while not endpoint.exists():
                        await anyio.sleep(0.01)
                completed = await anyio.to_thread.run_sync(
                    _run_cli,
                    "call",
                    tool_name,
                    "--json-args",
                    json.dumps(arguments),
                    "--socket",
                    os.fspath(endpoint),
                )
                assert completed.returncode == 1
                assert_private(completed.stdout, completed.stderr)
                await _stop_daemon(endpoint)
            return completed.stdout

    anyio.run(mcp_call, invalid, RuntimeError("must not dispatch"))
    assert json.loads(anyio.run(toolcall_invalid))["code"] == "invalid_argument"
    assert (
        json.loads(anyio.run(cli_call, invalid, RuntimeError("must not dispatch")))[
            "code"
        ]
        == "invalid_argument"
    )

    known_code = "service_unavailable" if session_open else "command_failed"
    unknown_code = "service_unavailable" if session_open else "internal_error"
    for failure, expected_code in (
        (_known_private_failure(secrets[0]), known_code),
        (RuntimeError(f"boom {secrets[0]}"), unknown_code),
    ):
        mcp_text = anyio.run(mcp_call, valid, failure)
        if expected_code != "internal_error":
            assert (
                json.loads(mcp_text.split("ACA_ERROR ", 1)[1])["code"] == expected_code
            )
        toolcall_payload = anyio.run(toolcall_call, valid, failure)
        assert json.loads(toolcall_payload)["code"] == expected_code
        cli_payload = anyio.run(cli_call, valid, failure)
        assert json.loads(cli_payload)["code"] == expected_code
    captured = capsys.readouterr()
    assert_private(caplog.text, captured.out, captured.err)


def test_512_ios_devices_hit_exact_success_ceiling_and_overflow_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from appium_connect_agent.integrations import _application

    ceiling = 4_194_304
    overflow_canary = "IOS_DEVICE_OVERFLOW_SECRET"
    extra_bytes = [0]

    def devices(*, control: object) -> tuple[IosDeviceInfo, ...]:
        del control
        values = [
            IosDeviceInfo(
                f"SIM-{index:03d}",
                "n",
                "simulator",
                "18.1",
                "booted",
                "simulator",
            )
            for index in range(512)
        ]
        if extra_bytes[0]:
            values[-1] = IosDeviceInfo(
                values[-1].id,
                overflow_canary + "x" * (extra_bytes[0] - len(overflow_canary)),
                "simulator",
                "18.1",
                "booted",
                "simulator",
            )
        return tuple(values)

    monkeypatch.setattr(_application, "list_ios_devices", devices)

    async def calibrate() -> None:
        application = Application(LocalSettings(), None, surface="toolcall")
        baseline = await application.dispatch(
            "appium_devices_list", _request(platform="ios")
        )
        baseline_size = len(canonical_json(baseline).encode())
        extra_bytes[0] = ceiling - baseline_size + 1
        exact = await application.dispatch(
            "appium_devices_list", _request(platform="ios")
        )
        assert exact.model_dump(mode="json")["data"]["count"] == 512
        assert len(canonical_json(exact).encode()) == ceiling
        await application.aclose()

    anyio.run(calibrate)

    async def success_flow() -> None:
        mcp_application = Application(LocalSettings(), None, surface="mcp")
        async with Client(create_server(mcp_application)) as client:
            result = await client.call_tool(
                "appium.devices.list", {"request": _request(platform="ios")}
            )
        assert result.is_error is False
        assert result.structured_content is not None
        assert result.structured_content["data"]["count"] == 512
        assert isinstance(result.content[0], TextContent)
        text = result.content[0].text
        assert len(text.encode()) == ceiling

        toolcall_application = Application(LocalSettings(), None, surface="toolcall")
        binding = {
            item.name: item for item in build_tool_bindings(toolcall_application)
        }["appium_devices_list"]
        encoded = await binding.invoke(
            SimpleNamespace(
                name="appium_devices_list",
                arguments=_request(platform="ios"),
                call_id="host-call",
            )
        )
        assert len(encoded.encode()) == ceiling
        assert json.loads(encoded)["data"]["count"] == 512
        await toolcall_application.aclose()

        with _short_root() as root:
            endpoint = root / "bridge.sock"
            account = root / "account"
            account.mkdir()
            account.chmod(0o700)

            async def daemon() -> None:
                await create_and_serve_daemon(
                    LocalSettings(),
                    None,
                    endpoint,
                    30.0,
                    account_directory=account,
                    watch_signals=False,
                )

            async with anyio.create_task_group() as group:
                group.start_soon(daemon)
                with anyio.fail_after(2):
                    while not endpoint.exists():
                        await anyio.sleep(0.01)
                completed = await anyio.to_thread.run_sync(
                    _run_cli,
                    "call",
                    "appium_devices_list",
                    "--json-args",
                    json.dumps(_request(platform="ios")),
                    "--socket",
                    os.fspath(endpoint),
                )
                assert completed.returncode == 3
                assert completed.stdout == ""
                assert completed.stderr == "bridge_error code=response_too_large\n"
                assert overflow_canary not in completed.stderr
                await _stop_daemon(endpoint)

    anyio.run(success_flow)

    extra_bytes[0] += 1

    async def overflow_flow() -> None:
        toolcall_application = Application(LocalSettings(), None, surface="toolcall")
        binding = {
            item.name: item for item in build_tool_bindings(toolcall_application)
        }["appium_devices_list"]
        encoded = await binding.invoke(
            SimpleNamespace(
                name="appium_devices_list",
                arguments=_request(platform="ios"),
                call_id="host-call",
            )
        )
        assert json.loads(encoded)["code"] == "internal_error"
        assert overflow_canary not in encoded
        await toolcall_application.aclose()

        mcp_application = Application(LocalSettings(), None, surface="mcp")
        async with Client(create_server(mcp_application)) as client:
            mcp_result = await client.call_tool(
                "appium.devices.list", {"request": _request(platform="ios")}
            )
        assert mcp_result.is_error is True
        assert overflow_canary not in "".join(
            getattr(item, "text", "") for item in mcp_result.content
        )

        with _short_root() as root:
            endpoint = root / "bridge.sock"
            account = root / "account"
            account.mkdir()
            account.chmod(0o700)

            async def daemon() -> None:
                await create_and_serve_daemon(
                    LocalSettings(),
                    None,
                    endpoint,
                    30.0,
                    account_directory=account,
                    watch_signals=False,
                )

            async with anyio.create_task_group() as group:
                group.start_soon(daemon)
                with anyio.fail_after(2):
                    while not endpoint.exists():
                        await anyio.sleep(0.01)
                completed = await anyio.to_thread.run_sync(
                    _run_cli,
                    "call",
                    "appium_devices_list",
                    "--json-args",
                    json.dumps(_request(platform="ios")),
                    "--socket",
                    os.fspath(endpoint),
                )
                assert completed.returncode == 3
                assert completed.stdout == ""
                assert completed.stderr == "bridge_error code=protocol_error\n"
                assert overflow_canary not in completed.stderr

    anyio.run(overflow_flow)
