from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import anyio
import pytest
from mcp import Client

from appium_connect_agent.automation import CommandError, SessionInfo
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations import TOOL_CATALOG, Application, cli
from appium_connect_agent.integrations import _application as application_module
from appium_connect_agent.integrations._application import (
    ApplicationError,
    _SessionEntry,
)
from appium_connect_agent.integrations._cli_protocol import StopRequest
from appium_connect_agent.integrations._daemon import create_and_serve_daemon
from appium_connect_agent.integrations._models import (
    AppLifecycleRequest,
    AutomationLocatorDocument,
)
from appium_connect_agent.integrations._server import create_server
from appium_connect_agent.integrations._toolcall import build_tool_bindings
from appium_connect_agent.runtime import DiagnosticCheck, DiagnosticReport

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

    def set_clipboard_text(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise self._failure

    def install_app(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise self._failure


class _MacSession:
    def __init__(self, platform: str = "macos") -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.device = _Recorder(self.calls)
        self.element_actions = _Recorder(self.calls)
        self._state = "active"
        self._platform = platform

    def session_info(self) -> SessionInfo:
        return SessionInfo(
            id="session",
            appium_session_id="appium-session",
            device_id=("macos:local" if self._platform == "macos" else "android-1"),
            target_app_id=(
                "com.apple.calculator" if self._platform == "macos" else "com.example"
            ),
            state=cast(Any, self._state),
            busy=False,
            platform=cast(Any, self._platform),
        )

    def element(self, *args: object, **kwargs: object) -> object:
        self.calls.append(("element", args, kwargs))
        return self.element_actions

    def quit(self, *, control: object) -> None:
        del control
        self._state = "closed"


def _bound_application(
    surface: str = "toolcall", platform: str = "macos"
) -> tuple[Application, _MacSession]:
    application = Application(LocalSettings(), None, surface=cast(Any, surface))
    session = _MacSession(platform)
    application._entry = _SessionEntry(
        handle=_HANDLE,
        platform=cast(Any, platform),
        device_id="macos:local" if platform == "macos" else "android-1",
        target_app_id=(
            "com.apple.calculator" if platform == "macos" else "com.example"
        ),
        state="active",
        busy=False,
        published=True,
        session=cast(Any, session),
    )
    return application, session


def _mac_application(
    surface: str = "toolcall",
) -> tuple[Application, _MacSession]:
    return _bound_application(surface, "macos")


_MAC_ATTRIBUTES = (
    "id",
    "text",
    "type",
    "label",
    "title",
    "value",
    "placeholder_value",
    "element_type",
    "enabled",
    "focused",
    "selected",
    "hittable",
    "displayed",
    "bounds",
)


class _AttributeObservation:
    operation_id = "op-mac-attributes"

    @staticmethod
    def to_json() -> str:
        locator = {
            "by": "-ios predicate string",
            "value": "XCUIElementTypeButton",
            "package": None,
            "raw_id": False,
            "parent": None,
            "predicate": "label == '7'",
        }
        return json.dumps(
            {
                "schema": 1,
                "kind": "element",
                "operation_id": "op-mac-attributes",
                "observed_at": "2026-11-14T00:00:00.000000Z",
                "scope": {
                    "kind": "element",
                    "locator": locator,
                    "range_locator": locator,
                },
                "coverage": "requested_scope",
                "complete_for_requested_scope": True,
                "upstream_completeness": "unknown",
                "consistency": "sequential_non_atomic",
                "payload": {
                    "attributes": [
                        {"name": name, "state": "not_applicable"}
                        for name in _MAC_ATTRIBUTES
                    ]
                },
            },
            separators=(",", ":"),
        )


class _AttributeElement:
    def inspect(self, *, attributes: object, control: object) -> _AttributeObservation:
        del control
        assert attributes == _MAC_ATTRIBUTES
        return _AttributeObservation()


def _attribute_application(surface: str) -> Application:
    application, session = _mac_application(surface)
    session.element_actions = cast(Any, _AttributeElement())
    return application


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
    monkeypatch: pytest.MonkeyPatch,
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
            (
                "appium_session_open",
                {
                    "schema_version": 1,
                    "platform": "macos",
                    "app_path": "relative/session-private.app",
                },
                "session-private",
            ),
            (
                "appium_app_package",
                {
                    "schema_version": 1,
                    "session_handle": _HANDLE,
                    "intent": "install",
                    "app_path": "relative/package-private.apk",
                },
                "package-private",
            ),
            (
                "appium_device_clipboard",
                {
                    "schema_version": 1,
                    "session_handle": _HANDLE,
                    "intent": "get",
                    "text": "clipboard-private",
                },
                "clipboard-private",
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

        extra_sensitive_calls = (
            (
                "appium_app_package",
                {
                    "schema_version": 1,
                    "session_handle": _HANDLE,
                    "intent": "install",
                    "app_path": "/tmp/package-private.apk",
                },
                "package-private",
            ),
            (
                "appium_device_clipboard",
                {
                    "schema_version": 1,
                    "session_handle": _HANDLE,
                    "intent": "set",
                    "text": "clipboard-private",
                },
                "clipboard-private",
            ),
        )
        for failure_kind in ("known", "unknown"):
            for tool_name, arguments, secret in extra_sensitive_calls:
                failure = (
                    CommandError("command_failed", "op-private", "response_received")
                    if failure_kind == "known"
                    else RuntimeError(f"private input: {secret}")
                )
                failing_application, failing_session = _bound_application(
                    "toolcall", "android"
                )
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

        open_failure: list[BaseException] = []

        class OpenRuntime:
            def __init__(self, settings: LocalSettings) -> None:
                del settings

            def connect(self, *, control: object) -> AbstractContextManager[Any]:
                del control

                class Scope(AbstractContextManager[Any]):
                    def __enter__(self) -> object:
                        return object()

                    def __exit__(self, *exc_info: object) -> None:
                        del exc_info

                return Scope()

        def create_failing_session(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise open_failure[0]

        monkeypatch.setattr(application_module, "Runtime", OpenRuntime)
        monkeypatch.setattr(
            application_module, "create_mac2_session", create_failing_session
        )
        open_arguments = {
            "schema_version": 1,
            "platform": "macos",
            "app_path": "/Applications/session-private.app",
            "arguments": ["session-private-argument"],
        }
        for failure_kind in ("known", "unknown"):
            open_failure[:] = [
                CommandError("command_failed", "op-private", "response_received")
                if failure_kind == "known"
                else RuntimeError("private input: session-private")
            ]
            open_application = Application(LocalSettings(), None, surface="toolcall")
            binding = {
                item.name: item for item in build_tool_bindings(open_application)
            }["appium_session_open"]
            payload = await binding.invoke(
                SimpleNamespace(
                    name="appium_session_open",
                    arguments=open_arguments,
                    call_id="host-call",
                )
            )
            assert "session-private" not in payload
            await open_application.aclose()

    anyio.run(scenario)
    for secret in (
        *(item[2] for item in sensitive_calls),
        "package-private",
        "clipboard-private",
        "session-private",
    ):
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "app_path",
    [
        "/Applications/./Calculator.app",
        "/Applications/../Calculator.app",
    ],
)
def test_macos_app_path_rejects_lexical_dot_segments(
    app_path: str,
) -> None:
    application, _ = _mac_application()

    async def scenario() -> None:
        with pytest.raises(ApplicationError) as caught:
            await application.dispatch(
                "appium_app_lifecycle",
                cast(
                    Any,
                    {
                        "schema_version": 1,
                        "session_handle": _HANDLE,
                        "intent": "launch",
                        "app_path": app_path,
                    },
                ),
            )
        assert caught.value.data.code == "invalid_argument"
        assert app_path not in caught.value.data.model_dump_json()
        await application.aclose()

    anyio.run(scenario)


@pytest.mark.parametrize(
    "app_path",
    [
        "/Applications//Calculator.app",
        "/Applications/Calculator.app/",
    ],
)
def test_macos_app_path_accepts_posix_empty_separator_segments(
    app_path: str,
) -> None:
    validated = AppLifecycleRequest.model_validate(
        {
            "schema_version": 1,
            "session_handle": _HANDLE,
            "intent": "launch",
            "app_path": app_path,
        }
    )
    assert validated.root.intent == "launch"


def test_automation_locator_document_preserves_predicate_presence() -> None:
    android = {
        "by": "id",
        "value": "com.example:id/value",
        "package": "com.example",
        "raw_id": False,
        "parent": None,
    }
    encoded_android = json.dumps(android, sort_keys=True, separators=(",", ":"))
    android_model = AutomationLocatorDocument.model_validate(android)
    assert android_model.model_dump(mode="json") == android
    assert (
        json.dumps(
            android_model.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        == encoded_android
    )

    for predicate in (None, "label == '7'"):
        macos = {
            "by": "-ios predicate string",
            "value": "XCUIElementTypeButton",
            "package": None,
            "raw_id": False,
            "parent": None,
            "predicate": predicate,
        }
        serialized = AutomationLocatorDocument.model_validate(macos).model_dump(
            mode="json"
        )
        assert "predicate" in serialized
        assert serialized["predicate"] == predicate


def test_runtime_check_covers_all_mode_driver_combinations_before_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeRuntime:
        def __init__(self, settings: LocalSettings) -> None:
            del settings

        @staticmethod
        def report(target_driver: str) -> DiagnosticReport:
            return DiagnosticReport(
                operation_id=f"op-{target_driver}",
                observed_at=datetime(2026, 11, 14, tzinfo=UTC),
                target="macOS" if target_driver == "mac2" else "Android",
                driver="Mac2" if target_driver == "mac2" else "UiAutomator2",
                checks=(DiagnosticCheck("service", "pass", "ready"),),
            )

        def diagnose(self, *, target_driver: str, control: object) -> DiagnosticReport:
            del control
            calls.append(f"diagnose:{target_driver}")
            return self.report(target_driver)

        def connect(self, *, control: object) -> AbstractContextManager[Any]:
            del control
            calls.append("connect")
            report = self.report("uiautomator2")

            class Scope(AbstractContextManager[Any]):
                def __enter__(self) -> Any:
                    calls.append("enter")
                    return SimpleNamespace(
                        report=report,
                        appium_version="3.7.0",
                        compatibility="declared_compatible",
                    )

                def __exit__(self, *exc_info: object) -> None:
                    del exc_info
                    calls.append("exit")

            return Scope()

    monkeypatch.setattr(application_module, "Runtime", FakeRuntime)

    async def scenario() -> None:
        application = Application(LocalSettings(), None, surface="toolcall")
        for mode, target_driver in (
            ("static", "uiautomator2"),
            ("static", "mac2"),
            ("external_connection", "uiautomator2"),
        ):
            result = await application.dispatch(
                "appium_runtime_check",
                cast(
                    Any,
                    {
                        "schema_version": 1,
                        "mode": mode,
                        "target_driver": target_driver,
                    },
                ),
            )
            assert result.model_dump(mode="json")["data"]["mode"] == mode

        application._runtime_gate.acquire()
        try:
            with pytest.raises(ApplicationError) as caught:
                await application.dispatch(
                    "appium_runtime_check",
                    cast(
                        Any,
                        {
                            "schema_version": 1,
                            "mode": "external_connection",
                            "target_driver": "mac2",
                        },
                    ),
                )
        finally:
            application._runtime_gate.release()
        assert (caught.value.data.code, caught.value.data.request_state) == (
            "unsupported_operation",
            "not_sent",
        )
        assert calls == [
            "diagnose:uiautomator2",
            "diagnose:mac2",
            "connect",
            "enter",
            "exit",
        ]
        await application.aclose()

    anyio.run(scenario)


def test_macos_attributes_all_fourteen_pass_through_three_shells(
    short_root: Path,
) -> None:
    arguments = {
        "schema_version": 1,
        "session_handle": _HANDLE,
        "mode": "attributes",
        "locator": {
            "by": "ios_predicate_string",
            "value": "XCUIElementTypeButton",
            "predicate": "label == '7'",
        },
        "attributes": list(_MAC_ATTRIBUTES),
    }

    def assert_payload(payload: dict[str, Any]) -> None:
        document = payload["data"]["document"]
        assert document["kind"] == "element"
        assert [item["name"] for item in document["payload"]["attributes"]] == list(
            _MAC_ATTRIBUTES
        )
        assert document["scope"]["locator"]["predicate"] == "label == '7'"

    async def scenario() -> None:
        mcp_application = _attribute_application("mcp")
        async with Client(create_server(mcp_application)) as client:
            mcp_result = await client.call_tool(
                "appium.ui.observe", {"request": arguments}
            )
        assert mcp_result.is_error is False
        assert_payload(cast(dict[str, Any], mcp_result.structured_content))

        toolcall_application = _attribute_application("toolcall")
        binding = {
            item.name: item for item in build_tool_bindings(toolcall_application)
        }["appium_ui_observe"]
        toolcall_payload = json.loads(
            await binding.invoke(
                SimpleNamespace(
                    name="appium_ui_observe",
                    arguments=arguments,
                    call_id="host-call",
                )
            )
        )
        assert_payload(toolcall_payload)
        await toolcall_application.aclose()

        account = short_root / "attributes-account"
        account.mkdir()
        account.chmod(0o700)
        endpoint = account / "bridge.sock"
        outcome: list[int] = []

        def factory(*args: object, **kwargs: object) -> Application:
            del args, kwargs
            return _attribute_application("cli")

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
                "appium_ui_observe",
                "--json-args",
                json.dumps(arguments),
                "--socket",
                os.fspath(endpoint),
            )
            assert completed.returncode == 0
            assert_payload(json.loads(completed.stdout))
            stopped = await cli._exchange(
                endpoint,
                StopRequest(protocol_version=1, operation="daemon.stop"),
                10.0,
            )
            assert stopped.kind == "daemon_stopped"
        assert outcome == [0]

    anyio.run(scenario)


@pytest.mark.parametrize(
    ("payload_extra", "expected_skip_app_kill"),
    [
        ({}, True),
        ({"skip_app_kill": None}, True),
        ({"skip_app_kill": True}, True),
        ({"skip_app_kill": False}, False),
    ],
)
def test_macos_session_open_defaults_skip_app_kill_to_true_and_passes_explicit_bool(
    monkeypatch: pytest.MonkeyPatch,
    payload_extra: dict[str, object],
    expected_skip_app_kill: bool,
) -> None:
    captured_kwargs: list[dict[str, object]] = []

    class OpenRuntime:
        def __init__(self, settings: LocalSettings) -> None:
            del settings

        def connect(self, *, control: object) -> AbstractContextManager[Any]:
            del control

            class Scope(AbstractContextManager[Any]):
                def __enter__(self) -> Any:
                    return SimpleNamespace(
                        server_url="http://127.0.0.1:4723", ownership="external"
                    )

                def __exit__(self, *exc_info: object) -> None:
                    del exc_info

            return Scope()

    def fake_create_mac2_session(*args: object, **kwargs: object) -> _MacSession:
        del args
        captured_kwargs.append(dict(kwargs))
        return _MacSession("macos")

    monkeypatch.setattr(application_module, "Runtime", OpenRuntime)
    monkeypatch.setattr(
        application_module, "create_mac2_session", fake_create_mac2_session
    )

    async def scenario() -> None:
        application = Application(LocalSettings(), None, surface="toolcall")
        result = await application.dispatch(
            "appium_session_open",
            cast(
                Any,
                {
                    "schema_version": 1,
                    "platform": "macos",
                    "bundle_id": "com.apple.calculator",
                    **payload_extra,
                },
            ),
        )
        assert result.model_dump(mode="json")["data"]["platform"] == "macos"
        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["skip_app_kill"] is expected_skip_app_kill
        await application.aclose()

    anyio.run(scenario)
