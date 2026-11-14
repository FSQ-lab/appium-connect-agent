from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import anyio
import pytest
from mcp import Client

from appium_connect_agent.automation import CommandError, SessionInfo
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations import TOOL_CATALOG, Application, cli
from appium_connect_agent.integrations._application import (
    ApplicationError,
    _SessionEntry,
)
from appium_connect_agent.integrations._cli_protocol import StopRequest
from appium_connect_agent.integrations._daemon import create_and_serve_daemon
from appium_connect_agent.integrations._server import create_server
from appium_connect_agent.integrations._toolcall import build_tool_bindings

_HANDLE = "s_" + ("a" * 32)
_SCREENSHOT_TOOL = "appium_device_screenshot"


class _Recorder:
    def __init__(
        self, calls: list[tuple[str, tuple[object, ...], dict[str, object]]]
    ) -> None:
        self._calls = calls

    def __getattr__(self, name: str) -> object:
        def invoke(*args: object, **kwargs: object) -> object:
            self._calls.append((name, args, kwargs))
            if name == "terminate_app":
                return True
            if name == "query_app_state":
                return 4
            return None

        return invoke


class _FailureDevice:
    def __init__(self, failure: BaseException) -> None:
        self._failure = failure

    def click_at(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise self._failure

    def send_keys(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise self._failure

    def launch_app(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise self._failure


class _MacSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.device = _Recorder(self.calls)
        self.element_actions = _Recorder(self.calls)
        self._state = "active"

    def session_info(self) -> SessionInfo:
        return SessionInfo(
            id="session",
            appium_session_id="appium-session",
            device_id="macos:local",
            target_app_id="com.apple.calculator",
            state=cast(Any, self._state),
            busy=False,
            platform="macos",
        )

    def element(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("element", args, kwargs))
        return self.element_actions

    def quit(self, *, control: object) -> None:
        del control
        self._state = "closed"


def _mac_application() -> tuple[Application, _MacSession]:
    application = Application(LocalSettings(), None, surface="toolcall")
    session = _MacSession()
    application._entry = _SessionEntry(
        handle=_HANDLE,
        platform="macos",
        device_id="macos:local",
        target_app_id="com.apple.calculator",
        state="active",
        busy=False,
        published=True,
        session=cast(Any, session),
    )
    return application, session


class _ScreenshotDevice:
    def __init__(self, png: bytes) -> None:
        self._png = png

    def take_screenshot(self, *, control: object) -> bytes:
        del control
        return self._png


class _ScreenshotSession:
    def __init__(self, png: bytes) -> None:
        self.device = _ScreenshotDevice(png)
        self._state = "active"

    def session_info(self) -> SessionInfo:
        return SessionInfo(
            id="session",
            appium_session_id="appium-session",
            device_id="macos:local",
            target_app_id="com.apple.calculator",
            state=cast(Any, self._state),
            busy=False,
            platform="macos",
        )

    def quit(self, *, control: object) -> None:
        del control
        self._state = "closed"


def _application(surface: str, png_size: int) -> Application:
    application = Application(LocalSettings(), None, surface=cast(Any, surface))
    png = b"\x89PNG\r\n\x1a\n" + (b"x" * (png_size - 8))
    application._entry = _SessionEntry(
        handle=_HANDLE,
        platform="macos",
        device_id="macos:local",
        target_app_id="com.apple.calculator",
        state="active",
        busy=False,
        published=True,
        session=cast(Any, _ScreenshotSession(png)),
    )
    return application


def _request() -> dict[str, object]:
    return {"schema_version": 1, "session_handle": _HANDLE}


def _payload_from_mcp_error(result: object) -> dict[str, object]:
    content = cast(Any, getattr(result, "content", None))
    text = getattr(content[0], "text", None)
    assert type(text) is str
    return cast(dict[str, object], json.loads(text.split("ACA_ERROR ", 1)[1]))


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "appium_connect_agent.integrations.cli", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def short_root() -> Iterator[Path]:
    root = Path(tempfile.mkdtemp(prefix="aca-mac-", dir="/private/tmp"))
    root.chmod(0o700)
    try:
        yield root
    finally:
        shutil.rmtree(root)


@pytest.mark.parametrize("png_size", [3_000_000, 3_000_001])
def test_screenshot_boundary_is_identical_in_mcp_toolcall_and_cli(
    png_size: int, short_root: Path
) -> None:
    async def scenario() -> None:
        mcp_application = _application("mcp", png_size)
        async with Client(create_server(mcp_application)) as client:
            mcp_result = await client.call_tool(
                "appium.device.screenshot", {"request": _request()}
            )
        if png_size == 3_000_000:
            assert mcp_result.is_error is False
            assert mcp_result.structured_content["data"]["byte_length"] == png_size
        else:
            assert mcp_result.is_error is True
            mcp_error = _payload_from_mcp_error(mcp_result)
            assert (mcp_error["code"], mcp_error["request_state"]) == (
                "screenshot_too_large",
                "response_received",
            )

        toolcall_application = _application("toolcall", png_size)
        binding = {
            item.name: item for item in build_tool_bindings(toolcall_application)
        }[_SCREENSHOT_TOOL]
        toolcall_payload = json.loads(
            await binding.invoke(
                SimpleNamespace(
                    name=_SCREENSHOT_TOOL,
                    arguments=_request(),
                    call_id="host-call",
                )
            )
        )
        if png_size == 3_000_000:
            assert toolcall_payload["data"]["byte_length"] == png_size
        else:
            assert (
                toolcall_payload["code"],
                toolcall_payload["request_state"],
            ) == ("screenshot_too_large", "response_received")
        await toolcall_application.aclose()

        account = short_root / f"account-{png_size}"
        account.mkdir()
        account.chmod(0o700)
        endpoint = account / "bridge.sock"
        outcome: list[int] = []

        def factory(*args: object, **kwargs: object) -> Application:
            del args, kwargs
            return _application("cli", png_size)

        async def daemon() -> None:
            result = await create_and_serve_daemon(
                LocalSettings(),
                None,
                endpoint,
                30.0,
                application_factory=factory,
                account_directory=account,
                watch_signals=False,
            )
            outcome.append(result.exit_code)

        async with anyio.create_task_group() as group:
            group.start_soon(daemon)
            with anyio.fail_after(2):
                while not endpoint.exists():
                    await anyio.sleep(0.01)
            completed = await anyio.to_thread.run_sync(
                _run_cli,
                "call",
                _SCREENSHOT_TOOL,
                "--json-args",
                json.dumps(_request()),
                "--socket",
                os.fspath(endpoint),
            )
            assert completed.returncode == (0 if png_size == 3_000_000 else 1)
            cli_payload = json.loads(completed.stdout)
            if png_size == 3_000_000:
                assert cli_payload["data"]["byte_length"] == png_size
            else:
                assert (cli_payload["code"], cli_payload["request_state"]) == (
                    "screenshot_too_large",
                    "response_received",
                )
            stopped = await cli._exchange(
                endpoint,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                10.0,
            )
            assert stopped.kind == "daemon_stopped"

        assert outcome == [0]

    anyio.run(scenario)


def test_catalog_exposes_all_twenty_two_tools_in_fixed_order() -> None:
    assert len(TOOL_CATALOG.specs) == 22
    assert TOOL_CATALOG.specs[-3].tool_name == _SCREENSHOT_TOOL
    assert TOOL_CATALOG.specs[-2].tool_name == "appium_device_pointer"
    assert TOOL_CATALOG.specs[-1].tool_name == "appium_macos_keys"


def test_macos_actions_forward_exact_public_automation_calls() -> None:
    async def scenario() -> None:
        application, session = _mac_application()
        common = {"schema_version": 1, "session_handle": _HANDLE}
        locator = {
            "by": "ios_predicate_string",
            "value": "XCUIElementTypeButton",
            "predicate": "label == '1'",
        }
        calls = (
            (
                "appium_element_click",
                {
                    **common,
                    "locator": locator,
                    "kind": "right",
                    "key_modifier_flags": 8,
                },
            ),
            (
                "appium_element_gesture",
                {
                    **common,
                    "intent": "scroll_by",
                    "locator": locator,
                    "delta_x": 1.5,
                    "delta_y": -2.5,
                    "key_modifier_flags": 4,
                },
            ),
            (
                "appium_element_gesture",
                {
                    **common,
                    "intent": "macos_swipe",
                    "locator": locator,
                    "direction": "left",
                    "velocity": 250.0,
                },
            ),
            (
                "appium_app_lifecycle",
                {
                    **common,
                    "intent": "launch",
                    "bundle_id": "com.apple.calculator",
                    "arguments": ["--safe"],
                },
            ),
            (
                "appium_device_pointer",
                {
                    **common,
                    "intent": "click",
                    "x": 2_147_483_647,
                    "y": 17,
                    "button": "right",
                    "key_modifier_flags": 2,
                },
            ),
            (
                "appium_macos_keys",
                {
                    **common,
                    "target": "system",
                    "keys": [
                        {"key": "XCUIKeyboardKeyCommand", "modifier_flags": 8},
                        {"key": "a"},
                    ],
                },
            ),
            (
                "appium_macos_keys",
                {
                    **common,
                    "target": "element",
                    "locator": locator,
                    "keys": [{"key": "XCUIKeyboardKeyReturn"}],
                },
            ),
        )
        results = [
            (await application.dispatch(name, cast(Any, arguments))).model_dump(
                mode="json"
            )
            for name, arguments in calls
        ]
        assert [result["data"] for result in results] == [
            {"action": "right_click", "session_state": "active", "busy": False},
            {
                "intent": "scroll_by",
                "can_scroll_more": None,
                "session_state": "active",
                "busy": False,
            },
            {
                "intent": "macos_swipe",
                "can_scroll_more": None,
                "session_state": "active",
                "busy": False,
            },
            {"intent": "launch", "session_state": "active", "busy": False},
            {"intent": "click", "session_state": "active", "busy": False},
            {"target": "system", "session_state": "active", "busy": False},
            {"target": "element", "session_state": "active", "busy": False},
        ]
        element_call = next(call for call in session.calls if call[0] == "element")
        assert element_call[1] == ("-ios predicate string", "XCUIElementTypeButton")
        assert element_call[2]["predicate"] == "label == '1'"
        with pytest.raises(ApplicationError) as caught:
            await application.dispatch("appium_device_back", cast(Any, common))
        assert (caught.value.data.code, caught.value.data.request_state) == (
            "unsupported_operation",
            "not_sent",
        )
        await application.aclose()

    anyio.run(scenario)


def test_sensitive_macos_inputs_never_reach_errors_or_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive_calls = (
        (
            "appium_device_pointer",
            {
                "schema_version": 1,
                "session_handle": _HANDLE,
                "intent": "click",
                "x": 987654321,
                "y": 17,
            },
            "987654321",
        ),
        (
            "appium_macos_keys",
            {
                "schema_version": 1,
                "session_handle": _HANDLE,
                "target": "system",
                "keys": [{"key": key} for key in "privacy"],
            },
            "privacy",
        ),
        (
            "appium_app_lifecycle",
            {
                "schema_version": 1,
                "session_handle": _HANDLE,
                "intent": "launch",
                "app_path": "/Applications/aca-private.app",
                "arguments": ["aca-private-arg"],
            },
            "aca-private",
        ),
    )

    async def scenario() -> None:
        application, _ = _mac_application()
        invalid_calls = (
            (
                "appium_device_pointer",
                {
                    "schema_version": 1,
                    "session_handle": _HANDLE,
                    "intent": "click",
                    "x": "987654321",
                    "y": 17,
                },
                "987654321",
            ),
            (
                "appium_macos_keys",
                {
                    "schema_version": 1,
                    "session_handle": _HANDLE,
                    "target": "system",
                    "keys": [{"key": "privacy"}],
                },
                "privacy",
            ),
            (
                "appium_app_lifecycle",
                {
                    "schema_version": 1,
                    "session_handle": _HANDLE,
                    "intent": "launch",
                    "app_path": "relative/aca-private.app",
                },
                "aca-private",
            ),
        )
        for tool_name, arguments, secret in invalid_calls:
            with pytest.raises(ApplicationError) as caught:
                await application.dispatch(tool_name, cast(Any, arguments))
            assert secret not in caught.value.data.model_dump_json()
        await application.aclose()

        for failure_kind in ("known", "unknown"):
            for tool_name, arguments, secret in sensitive_calls:
                failure: BaseException
                if failure_kind == "known":
                    failure = CommandError(
                        "command_failed", "op-private", "response_received"
                    )
                else:
                    failure = RuntimeError(f"private input: {secret}")
                failing_application, failing_session = _mac_application()
                failing_session.device = cast(Any, _FailureDevice(failure))
                binding = {
                    item.name: item for item in build_tool_bindings(failing_application)
                }[tool_name]
                payload = await binding.invoke(
                    SimpleNamespace(
                        name=tool_name,
                        arguments=arguments,
                        call_id="host-call",
                    )
                )
                assert secret not in payload
                await failing_application.aclose()

    anyio.run(scenario)
    for _, _, secret in sensitive_calls:
        assert secret not in caplog.text
