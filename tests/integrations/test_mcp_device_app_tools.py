from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult

from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations import (
    TOOL_CATALOG,
    Application,
    ApplicationError,
    JsonValue,
)
from appium_connect_agent.integrations._models import PrivateRequestValidationError
from tests.automation._action_protocol import ResponsePlan
from tests.automation.test_device_actions import DeviceProtocolService

from .conftest import TOOL_NAMES, McpHarness


def _request(**values: object) -> dict[str, object]:
    return {"request": {"schema_version": 1, **values}}


@dataclass(frozen=True)
class _Call:
    name: str
    arguments: dict[str, JsonValue]
    call_id: str = "device-app-provider-call"


def _payload(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    assert isinstance(parsed, dict)
    return cast(dict[str, Any], parsed)


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    value = result.content[0]
    assert value.type == "text"
    return value.text


def _structured(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is False
    assert result.structured_content is not None
    return cast(dict[str, Any], result.structured_content)


def _error(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is True
    assert result.structured_content is None
    text = _text(result)
    prefix, marker, payload = text.partition("ACA_ERROR ")
    assert marker and (prefix == "" or prefix.startswith("Error executing tool "))
    return _payload(payload)


async def _open(client: Client, device_id: str = "device-app-tools") -> str:
    result = _structured(
        await client.call_tool(TOOL_NAMES[3], _request(device_id=device_id))
    )
    return cast(str, result["data"]["session_handle"])


async def _close(client: Client, handle: str) -> None:
    result = _structured(
        await client.call_tool(TOOL_NAMES[5], _request(session_handle=handle))
    )
    assert result["data"]["session_state"] == "closed"


def test_seven_tools_have_fixed_metadata_and_strict_branch_schemas() -> None:
    expected = (
        (
            "appium.device.key",
            "appium_device_key",
            "device_key",
            "Send one press or long-press Android keycode command to the bound Device.",
        ),
        (
            "appium.device.keyboard_hide",
            "appium_device_keyboard_hide",
            "device_keyboard_hide",
            "Hide the keyboard for the bound Device and return the official boolean.",
        ),
        (
            "appium.device.clipboard",
            "appium_device_clipboard",
            "device_clipboard",
            "Read or replace the bound Device plaintext clipboard.",
        ),
        (
            "appium.device.alert",
            "appium_device_alert",
            "device_alert",
            "Accept or dismiss one official alert on the bound Device.",
        ),
        (
            "appium.device.status_bar",
            "appium_device_status_bar",
            "device_status_bar",
            "Expand or collapse one Android system panel on the bound Device.",
        ),
        (
            "appium.app.lifecycle",
            "appium_app_lifecycle",
            "app_lifecycle",
            "Activate, terminate, or query one explicit application package.",
        ),
        (
            "appium.app.package",
            "appium_app_package",
            "app_package",
            "Install one local APK or remove one explicit application package.",
        ),
    )
    assert (
        tuple(
            (spec.mcp_name, spec.tool_name, spec.handler_symbol, spec.description)
            for spec in TOOL_CATALOG.specs[12:]
        )
        == expected
    )
    assert TOOL_CATALOG.mcp_names == TOOL_NAMES
    assert all(
        (
            not spec.annotations.read_only,
            spec.annotations.destructive,
            not spec.annotations.idempotent,
            spec.annotations.open_world,
        )
        == (True, True, True, True)
        for spec in TOOL_CATALOG.specs[12:]
    )

    handle = "s_" + ("a" * 32)
    valid = {
        "appium_device_key": {
            "schema_version": 1,
            "session_handle": handle,
            "kind": "press",
            "keycode": 0,
            "metastate": -2_147_483_648,
            "flags": 2_147_483_647,
            "timeout_seconds": 120.0,
        },
        "appium_device_keyboard_hide": {
            "schema_version": 1,
            "session_handle": handle,
        },
        "appium_device_clipboard": {
            "schema_version": 1,
            "session_handle": handle,
            "intent": "set",
            "text": "😀" * 16_384,
            "label": "😀" * 256,
        },
        "appium_device_alert": {
            "schema_version": 1,
            "session_handle": handle,
            "action": "accept",
            "button_label": "label",
        },
        "appium_device_status_bar": {
            "schema_version": 1,
            "session_handle": handle,
            "command": "collapse",
        },
        "appium_app_lifecycle": {
            "schema_version": 1,
            "session_handle": handle,
            "intent": "query_state",
            "app_id": "Com.Example_2.App",
        },
        "appium_app_package": {
            "schema_version": 1,
            "session_handle": handle,
            "intent": "install",
            "app_path": "/tmp/example.apk",
            "allow_test_packages": True,
            "timeout_seconds": 360.0,
        },
    }
    for name, arguments in valid.items():
        TOOL_CATALOG.by_tool_name(name).request_adapter.validate_python(
            arguments, strict=True
        )

    invalid = (
        ("appium_device_key", {**valid["appium_device_key"], "keycode": True}),
        (
            "appium_device_clipboard",
            {
                "schema_version": 1,
                "session_handle": handle,
                "intent": "get",
                "text": "must-not-be-accepted",
            },
        ),
        (
            "appium_device_clipboard",
            {**valid["appium_device_clipboard"], "text": "😀" * 16_385},
        ),
        (
            "appium_app_lifecycle",
            {**valid["appium_app_lifecycle"], "app_id": "1invalid.app"},
        ),
        (
            "appium_app_package",
            {
                "schema_version": 1,
                "session_handle": handle,
                "intent": "install",
                "app_path": "relative.apk",
            },
        ),
        (
            "appium_app_package",
            {
                "schema_version": 1,
                "session_handle": handle,
                "intent": "remove",
                "app_id": "com.example",
                "timeout_seconds": 180.1,
            },
        ),
    )
    for name, arguments in invalid:
        with pytest.raises((ValueError, PrivateRequestValidationError)):
            TOOL_CATALOG.by_tool_name(name).request_adapter.validate_python(
                arguments, strict=True
            )


def test_seven_tools_call_only_public_device_operations_and_shape_results(
    mcp_harness: McpHarness, tmp_path: Path
) -> None:
    secret = "clipboard-private-中文😀"
    encoded = base64.b64encode(secret.encode()).decode("ascii")
    apk = (tmp_path / "sample.apk").resolve()
    apk.write_bytes(b"not-read-by-integrations")

    with DeviceProtocolService() as service:
        service.queue("hide_keyboard", ResponsePlan(payload={"value": True}))
        service.queue("get_clipboard_text", ResponsePlan(payload={"value": encoded}))
        service.queue("status_bar", ResponsePlan(payload={"value": "panel-output"}))
        service.queue("terminate_app", ResponsePlan(payload={"value": True}))
        service.queue("query_app_state", ResponsePlan(payload={"value": 4}))
        service.queue("remove_app", ResponsePlan(payload={"value": True}))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client)
                key = _structured(
                    await client.call_tool(
                        TOOL_NAMES[12],
                        _request(
                            session_handle=handle,
                            kind="long_press",
                            keycode=4,
                            metastate=-1,
                            flags=2,
                        ),
                    )
                )
                assert key["data"] == {
                    "session_state": "active",
                    "busy": False,
                    "kind": "long_press",
                }
                pressed = _structured(
                    await client.call_tool(
                        TOOL_NAMES[12],
                        _request(session_handle=handle, kind="press", keycode=3),
                    )
                )
                assert pressed["data"]["kind"] == "press"
                hidden = _structured(
                    await client.call_tool(
                        TOOL_NAMES[13], _request(session_handle=handle)
                    )
                )
                assert hidden["data"]["hidden"] is True

                set_result = _structured(
                    await client.call_tool(
                        TOOL_NAMES[14],
                        _request(
                            session_handle=handle,
                            intent="set",
                            text=secret,
                            label="private-label",
                        ),
                    )
                )
                assert set_result["data"] == {
                    "session_state": "active",
                    "busy": False,
                    "intent": "set",
                }
                get_result = _structured(
                    await client.call_tool(
                        TOOL_NAMES[14],
                        _request(session_handle=handle, intent="get"),
                    )
                )
                assert get_result["data"]["text"] == secret

                alert = _structured(
                    await client.call_tool(
                        TOOL_NAMES[15],
                        _request(
                            session_handle=handle,
                            action="dismiss",
                            button_label="Cancel",
                        ),
                    )
                )
                assert alert["data"]["action"] == "dismiss"
                accepted = _structured(
                    await client.call_tool(
                        TOOL_NAMES[15],
                        _request(session_handle=handle, action="accept"),
                    )
                )
                assert accepted["data"]["action"] == "accept"
                panel = _structured(
                    await client.call_tool(
                        TOOL_NAMES[16],
                        _request(
                            session_handle=handle,
                            command="expandNotifications",
                        ),
                    )
                )
                assert panel["data"]["output"] == "panel-output"
                for command in ("expandSettings", "collapse"):
                    status = _structured(
                        await client.call_tool(
                            TOOL_NAMES[16],
                            _request(session_handle=handle, command=command),
                        )
                    )
                    assert status["data"]["command"] == command

                for intent, expected in (
                    ("activate", {"intent": "activate"}),
                    ("terminate", {"intent": "terminate", "terminated": True}),
                    ("query_state", {"intent": "query_state", "app_state": 4}),
                ):
                    lifecycle = _structured(
                        await client.call_tool(
                            TOOL_NAMES[17],
                            _request(
                                session_handle=handle,
                                intent=intent,
                                app_id="Com.Example_2.App",
                            ),
                        )
                    )
                    assert {key: lifecycle["data"][key] for key in expected} == expected
                    assert "app_id" not in lifecycle["data"]

                installed = _structured(
                    await client.call_tool(
                        TOOL_NAMES[18],
                        _request(
                            session_handle=handle,
                            intent="install",
                            app_path=str(apk),
                            allow_test_packages=True,
                            timeout_seconds=360.0,
                        ),
                    )
                )
                assert installed["data"]["intent"] == "install"
                removed = _structured(
                    await client.call_tool(
                        TOOL_NAMES[18],
                        _request(
                            session_handle=handle,
                            intent="remove",
                            app_id="Com.Example_2.App",
                            timeout_seconds=180.0,
                        ),
                    )
                )
                assert removed["data"]["removed"] is True
                assert "app_id" not in removed["data"]
                await _close(client, handle)

        anyio.run(scenario)

    assert service.of_kind("long_press_keycode")[0].body == {
        "script": "mobile: pressKey",
        "args": [{"keycode": 4, "metastate": -1, "flags": 2, "isLongPress": True}],
    }
    assert service.of_kind("press_keycode")[0].body == {
        "script": "mobile: pressKey",
        "args": [{"keycode": 3}],
    }
    assert service.of_kind("set_clipboard_text")[0].body == {
        "script": "mobile: setClipboard",
        "args": [
            {
                "content": encoded,
                "contentType": "plaintext",
                "label": "private-label",
            }
        ],
    }
    assert service.of_kind("get_clipboard_text")[0].body == {
        "script": "mobile: getClipboard",
        "args": [{"contentType": "plaintext"}],
    }
    assert service.of_kind("dismiss_alert")[0].body == {
        "script": "mobile: dismissAlert",
        "args": [{"buttonLabel": "Cancel"}],
    }
    assert service.of_kind("accept_alert")[0].body == {
        "script": "mobile: acceptAlert",
        "args": [{}],
    }
    status_requests = service.of_kind("status_bar")
    assert [request.body for request in status_requests] == [
        {
            "script": "mobile: statusBar",
            "args": [{"command": "expandNotifications"}],
        },
        {
            "script": "mobile: statusBar",
            "args": [{"command": "expandSettings"}],
        },
        {
            "script": "mobile: statusBar",
            "args": [{"command": "collapse"}],
        },
    ]
    assert service.of_kind("activate_app")[0].body == {
        "script": "mobile: activateApp",
        "args": [{"appId": "Com.Example_2.App"}],
    }
    assert service.of_kind("terminate_app")[0].body == {
        "script": "mobile: terminateApp",
        "args": [{"appId": "Com.Example_2.App", "timeout": 500}],
    }
    assert service.of_kind("query_app_state")[0].body == {
        "script": "mobile: queryAppState",
        "args": [{"appId": "Com.Example_2.App"}],
    }
    assert service.of_kind("install_app")[0].body == {
        "script": "mobile: installApp",
        "args": [
            {
                "appPath": str(apk),
                "replace": True,
                "allowTestPackages": True,
                "timeout": 300_000,
            }
        ],
    }
    assert service.of_kind("remove_app")[0].body == {
        "script": "mobile: removeApp",
        "args": [
            {
                "appId": "Com.Example_2.App",
                "keepData": False,
                "timeout": 100_000,
            }
        ],
    }
    assert secret not in json.dumps(mcp_harness.events(), ensure_ascii=False)


def test_branch_validation_rejects_before_application_and_does_not_echo_secrets(
    mcp_harness: McpHarness,
) -> None:
    secret = "must-not-echo-private-clipboard"
    handle = "s_" + ("a" * 32)
    invalid_calls = (
        (
            TOOL_NAMES[12],
            _request(session_handle=handle, kind="press", keycode=True),
        ),
        (
            TOOL_NAMES[14],
            _request(session_handle=handle, intent="get", text=secret),
        ),
        (
            TOOL_NAMES[14],
            _request(session_handle=handle, intent="set", text=secret, label=True),
        ),
        (
            TOOL_NAMES[17],
            _request(
                session_handle=handle,
                intent="activate",
                app_id="invalid/package",
            ),
        ),
        (
            TOOL_NAMES[18],
            _request(
                session_handle=handle,
                intent="install",
                app_path="relative.apk",
            ),
        ),
    )

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            for name, request in invalid_calls:
                result = await client.call_tool(name, request)
                assert result.is_error is True
                assert result.structured_content is None
                assert secret not in _text(result)

    anyio.run(scenario)
    assert mcp_harness.events() == [{"event": "server_stopped", "result": 0}]


def test_new_tool_known_failures_and_sensitive_values_remain_private(
    mcp_harness: McpHarness, tmp_path: Path
) -> None:
    private_values = (
        "clipboard-known-private",
        "label-known-private",
        "alert-known-private",
        "Private_Known.App",
        str((tmp_path / "private-known.apk").resolve()),
        "status-known-private",
        "2147483647",
    )
    Path(private_values[4]).write_bytes(b"not-read-by-integrations")
    failure_payload = {
        "value": {
            "error": "unknown error",
            "message": " ".join(private_values),
            "stacktrace": "",
        }
    }
    failing_calls = (
        (
            "press_keycode",
            TOOL_NAMES[12],
            _request(session_handle="{handle}", kind="press", keycode=2_147_483_647),
        ),
        (
            "set_clipboard_text",
            TOOL_NAMES[14],
            _request(
                session_handle="{handle}",
                intent="set",
                text=private_values[0],
                label=private_values[1],
            ),
        ),
        (
            "accept_alert",
            TOOL_NAMES[15],
            _request(
                session_handle="{handle}",
                action="accept",
                button_label=private_values[2],
            ),
        ),
        (
            "activate_app",
            TOOL_NAMES[17],
            _request(
                session_handle="{handle}",
                intent="activate",
                app_id=private_values[3],
            ),
        ),
        (
            "install_app",
            TOOL_NAMES[18],
            _request(
                session_handle="{handle}",
                intent="install",
                app_path=private_values[4],
            ),
        ),
    )

    with DeviceProtocolService() as service:
        for kind, _, _ in failing_calls:
            service.queue(kind, ResponsePlan(status=500, payload=failure_payload))
        service.queue("status_bar", ResponsePlan(payload={"value": private_values[5]}))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "private-known-device")
                for _, name, template in failing_calls:
                    request = json.loads(
                        json.dumps(template).replace("{handle}", handle)
                    )
                    error_text = _text(await client.call_tool(name, request))
                    assert "command_failed" in error_text
                    for private in private_values:
                        assert private not in error_text
                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[16],
                        _request(session_handle=handle, command="expandNotifications"),
                    )
                )
                assert status["data"]["output"] == private_values[5]
                await _close(client, handle)

        anyio.run(scenario)

    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for private in private_values:
        assert private not in stderr


def test_new_tool_response_unknown_quarantines_without_replay(
    mcp_harness: McpHarness,
) -> None:
    with DeviceProtocolService() as service:
        service.queue("press_keycode", ResponsePlan(disconnect=True))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "unknown-new-tool-device")
                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[12],
                        _request(session_handle=handle, kind="press", keycode=4),
                    )
                )
                assert failed["code"] == "execution_unknown"
                assert failed["request_state"] == "response_unknown"
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "uncertain"
                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handle)
                    )
                )
                assert status["data"]["session_state"] == "uncertain"

        anyio.run(scenario)

    assert len(service.of_kind("press_keycode")) == 1
    assert service.of_kind("quit") == []


def test_new_tool_gate_cancel_waits_for_late_success_without_replay(
    mcp_harness: McpHarness,
) -> None:
    started = threading.Event()
    release = threading.Event()
    secret = "cancelled-private-clipboard"
    with DeviceProtocolService() as service:
        service.queue(
            "set_clipboard_text", ResponsePlan(started=started, release=release)
        )
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "cancel-new-tool-device")
                scopes: list[anyio.CancelScope] = []

                async def set_clipboard() -> None:
                    with anyio.CancelScope() as scope:
                        scopes.append(scope)
                        await client.call_tool(
                            TOOL_NAMES[14],
                            _request(session_handle=handle, intent="set", text=secret),
                        )

                async with anyio.create_task_group() as group:
                    group.start_soon(set_clipboard)
                    await anyio.to_thread.run_sync(started.wait)
                    busy = _error(
                        await client.call_tool(
                            TOOL_NAMES[12],
                            _request(session_handle=handle, kind="press", keycode=4),
                        )
                    )
                    closing = _error(
                        await client.call_tool(
                            TOOL_NAMES[5], _request(session_handle=handle)
                        )
                    )
                    assert busy["code"] == closing["code"] == "session_busy"
                    assert secret not in json.dumps((busy, closing))
                    assert len(scopes) == 1
                    scopes[0].cancel()
                    release.set()

                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handle)
                    )
                )
                assert status["data"]["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("set_clipboard_text")) == 1
    assert len(service.of_kind("quit")) == 1
    assert secret not in mcp_harness.stderr_file.read_text(encoding="utf-8")


def test_new_tool_strict_lower_results_and_utf8_output_limit(
    mcp_harness: McpHarness,
) -> None:
    oversized = "x" * 65_537
    cases = (
        (
            "hide_keyboard",
            ResponsePlan(payload={"value": "false"}),
            TOOL_NAMES[13],
            _request(session_handle="{handle}"),
        ),
        (
            "get_clipboard_text",
            ResponsePlan(
                payload={"value": base64.b64encode(oversized.encode()).decode("ascii")}
            ),
            TOOL_NAMES[14],
            _request(session_handle="{handle}", intent="get"),
        ),
        (
            "status_bar",
            ResponsePlan(payload={"value": oversized}),
            TOOL_NAMES[16],
            _request(session_handle="{handle}", command="collapse"),
        ),
        (
            "query_app_state",
            ResponsePlan(payload={"value": 2}),
            TOOL_NAMES[17],
            _request(
                session_handle="{handle}", intent="query_state", app_id="Strict.App"
            ),
        ),
    )
    with DeviceProtocolService() as service:
        for kind, plan, _, _ in cases:
            service.queue(kind, plan)
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "strict-result-device")
                for _, _, name, template in cases:
                    request = json.loads(
                        json.dumps(template).replace("{handle}", handle)
                    )
                    failed = _error(await client.call_tool(name, request))
                    assert failed["code"] == "command_failed"
                    assert failed["request_state"] == "response_received"
                    assert failed["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert oversized not in mcp_harness.stderr_file.read_text(encoding="utf-8")


def test_toolcall_callbacks_dispatch_all_seven_new_tools(
    mcp_harness: McpHarness, tmp_path: Path
) -> None:
    apk = (tmp_path / "toolcall.apk").resolve()
    apk.write_bytes(b"not-read-by-integrations")
    with DeviceProtocolService() as service:
        service.queue("hide_keyboard", ResponsePlan(payload={"value": False}))
        service.queue(
            "get_clipboard_text",
            ResponsePlan(payload={"value": base64.b64encode(b"value").decode()}),
        )
        service.queue("status_bar", ResponsePlan(payload={"value": ""}))
        service.queue("query_app_state", ResponsePlan(payload={"value": 3}))
        service.queue("remove_app", ResponsePlan(payload={"value": False}))

        async def scenario() -> None:
            application = Application(
                LocalSettings(server_url=service.url),
                mcp_harness.adb,
                surface="toolcall",
            )
            bindings = {
                binding.name: binding for binding in application.tool_bindings()
            }

            async def invoke(
                name: str, arguments: dict[str, JsonValue]
            ) -> dict[str, Any]:
                return _payload(await bindings[name].invoke(_Call(name, arguments)))

            opened = await invoke(
                "appium_session_open",
                {"schema_version": 1, "device_id": "toolcall-device-app"},
            )
            handle = cast(str, opened["data"]["session_handle"])
            common: dict[str, JsonValue] = {
                "schema_version": 1,
                "session_handle": handle,
            }
            requests: tuple[tuple[str, dict[str, JsonValue]], ...] = (
                ("appium_device_key", {**common, "kind": "press", "keycode": 3}),
                ("appium_device_keyboard_hide", dict(common)),
                ("appium_device_clipboard", {**common, "intent": "get"}),
                (
                    "appium_device_alert",
                    {**common, "action": "accept", "button_label": None},
                ),
                (
                    "appium_device_status_bar",
                    {**common, "command": "collapse"},
                ),
                (
                    "appium_app_lifecycle",
                    {
                        **common,
                        "intent": "query_state",
                        "app_id": "com.example",
                    },
                ),
                (
                    "appium_app_package",
                    {
                        **common,
                        "intent": "install",
                        "app_path": str(apk),
                        "allow_test_packages": False,
                    },
                ),
                (
                    "appium_app_package",
                    {**common, "intent": "remove", "app_id": "com.example"},
                ),
            )
            for name, arguments in requests:
                result = await invoke(name, arguments)
                assert result["execution"] == "completed"
            await invoke(
                "appium_session_close",
                {"schema_version": 1, "session_handle": handle},
            )
            await application.aclose()

        anyio.run(scenario)

    assert [
        kind for kind in service.operation_kinds() if kind not in {"create", "quit"}
    ] == [
        "press_keycode",
        "hide_keyboard",
        "get_clipboard_text",
        "accept_alert",
        "status_bar",
        "query_app_state",
        "install_app",
        "remove_app",
    ]


@pytest.mark.parametrize("surface", ["toolcall", "cli"])
def test_private_validation_is_redacted_in_local_shells(
    mcp_harness: McpHarness,
    caplog: pytest.LogCaptureFixture,
    surface: Literal["toolcall", "cli"],
) -> None:
    handle = "s_" + ("a" * 32)
    private_values = (
        "private-local-shell-clipboard",
        "private-local-shell-label",
        "Private_Local.App",
        "/private-local-shell.apk",
        "2147483647",
    )
    requests = (
        (
            "appium_device_key",
            {
                "schema_version": 1,
                "session_handle": handle,
                "kind": "press",
                "keycode": 2_147_483_647,
                "unexpected": private_values[0],
            },
        ),
        (
            "appium_device_clipboard",
            {
                "schema_version": 1,
                "session_handle": handle,
                "intent": "set",
                "text": private_values[0],
                "label": private_values[1],
                "unexpected": True,
            },
        ),
        (
            "appium_device_alert",
            {
                "schema_version": 1,
                "session_handle": handle,
                "action": "accept",
                "button_label": private_values[1],
                "unexpected": True,
            },
        ),
        (
            "appium_app_lifecycle",
            {
                "schema_version": 1,
                "session_handle": handle,
                "intent": "activate",
                "app_id": private_values[2],
                "unexpected": True,
            },
        ),
        (
            "appium_app_package",
            {
                "schema_version": 1,
                "session_handle": handle,
                "intent": "install",
                "app_path": private_values[3],
                "unexpected": True,
            },
        ),
    )

    async def scenario() -> list[tuple[str, str, dict[str, Any]]]:
        application = Application(LocalSettings(), mcp_harness.adb, surface=surface)
        observed: list[tuple[str, str, dict[str, Any]]] = []
        try:
            for name, request in requests:
                with pytest.raises(ApplicationError) as caught:
                    await application.dispatch(
                        name, cast(dict[str, JsonValue], request)
                    )
                observed.append(
                    (
                        str(caught.value),
                        repr(caught.value),
                        caught.value.data.model_dump(mode="json"),
                    )
                )
            return observed
        finally:
            await application.aclose()

    for text, representation, payload in anyio.run(scenario):
        assert payload["code"] == "invalid_argument"
        for private in private_values:
            assert private not in text
            assert private not in representation
            assert private not in json.dumps(payload)
            assert private not in caplog.text
