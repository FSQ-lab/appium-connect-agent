from __future__ import annotations

import json
import os
import select
import subprocess
import threading
import time
from types import SimpleNamespace
from typing import Any, cast

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent, Tool

from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations._application import Application, ApplicationError
from appium_connect_agent.integrations._models import DeviceBackRequest
from tests.automation._action_protocol import ResponsePlan, w3c_error
from tests.automation.test_device_actions import DeviceProtocolService

from .conftest import CANARY, SECRET_PATH, TOOL_NAMES, McpHarness


def _request(**values: object) -> dict[str, object]:
    return {"request": {"schema_version": 1, **values}}


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    value = result.content[0]
    assert isinstance(value, TextContent)
    return value.text


def _structured(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is False
    assert result.structured_content is not None
    value = cast(dict[str, Any], result.structured_content)
    assert json.loads(_text(result)) == value
    return value


def _error(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is True
    assert result.structured_content is None
    value = _text(result)
    marker = "ACA_ERROR "
    assert marker in value
    return cast(dict[str, Any], json.loads(value.split(marker, 1)[1]))


def _schema_target(root: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in value:
        target: object = root
        for segment in value["$ref"].removeprefix("#/").split("/"):
            assert isinstance(target, dict)
            target = target[segment]
        assert isinstance(target, dict)
        value = target
    return value


async def _open(client: Client, device_id: str = "back-device") -> str:
    opened = _structured(
        await client.call_tool(
            TOOL_NAMES[3],
            _request(device_id=device_id, app_id="com.example"),
        )
    )
    handle = opened["data"]["session_handle"]
    assert isinstance(handle, str)
    return handle


async def _close(client: Client, handle: str) -> None:
    closed = _structured(
        await client.call_tool(
            TOOL_NAMES[5],
            _request(session_handle=handle, timeout_seconds=60.0),
        )
    )
    assert closed["data"]["session_state"] == "closed"


def test_back_is_tenth_destructive_tool_with_strict_schema(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> list[Tool]:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            return (await client.list_tools()).tools

    tools = anyio.run(scenario)
    assert tuple(tool.name for tool in tools) == TOOL_NAMES
    back = tools[9]
    assert back.annotations is not None
    assert back.annotations.model_dump(
        mode="json", by_alias=True, exclude_none=False
    ) == {
        "title": None,
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }

    input_root = back.input_schema
    assert input_root["type"] == "object"
    assert input_root["required"] == ["request"]
    request_schema = _schema_target(input_root, input_root["properties"]["request"])
    assert request_schema["additionalProperties"] is False
    assert set(request_schema["required"]) == {"schema_version", "session_handle"}
    assert set(request_schema["properties"]) == {
        "schema_version",
        "session_handle",
        "timeout_seconds",
    }
    assert request_schema["properties"]["timeout_seconds"] == {
        "default": 90.0,
        "exclusiveMinimum": 0.0,
        "maximum": 120.0,
        "title": "Timeout Seconds",
        "type": "number",
    }

    assert back.output_schema is not None
    output_root = _schema_target(back.output_schema, back.output_schema)
    assert output_root["additionalProperties"] is False
    data_schema = _schema_target(back.output_schema, output_root["properties"]["data"])
    assert data_schema["additionalProperties"] is False
    assert set(data_schema["required"]) == {"action", "session_state", "busy"}
    assert data_schema["properties"]["action"]["const"] == "back"
    assert data_schema["properties"]["session_state"]["const"] == "active"
    assert data_schema["properties"]["busy"]["const"] is False


def test_back_schema_rejects_invalid_requests_before_handler(
    mcp_harness: McpHarness,
) -> None:
    handle = "s_" + ("a" * 32)
    valid = {"schema_version": 1, "session_handle": handle}
    invalid = [
        {"schema_version": 1},
        {**valid, "extra": True},
        {**valid, "timeout_seconds": True},
        {**valid, "timeout_seconds": "90"},
        {**valid, "timeout_seconds": 0.0},
        {**valid, "timeout_seconds": 120.0001},
        {**valid, "session_handle": "s_" + ("a" * 31)},
    ]

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            for request in invalid:
                result = await client.call_tool(TOOL_NAMES[9], {"request": request})
                assert result.is_error is True
                assert result.structured_content is None

    anyio.run(scenario)
    assert mcp_harness.events() == [{"event": "server_stopped", "result": 0}]


@pytest.mark.parametrize("encoded_request", [False, True])
def test_back_issues_one_exact_public_action_and_returns_active_idle(
    mcp_harness: McpHarness,
    encoded_request: bool,
) -> None:
    with DeviceProtocolService() as service:
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client)
                request: dict[str, object] | str = {
                    "schema_version": 1,
                    "session_handle": handle,
                    "timeout_seconds": 10.0,
                }
                if encoded_request:
                    request = json.dumps(request)
                result = _structured(
                    await client.call_tool(TOOL_NAMES[9], {"request": request})
                )
                assert result["execution"] == "completed"
                assert result["operation_id"] is None
                assert result["request_state"] is None
                assert result["warnings"] == []
                assert result["data"] == {
                    "action": "back",
                    "session_state": "active",
                    "busy": False,
                }
                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handle)
                    )
                )
                assert status["data"]["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert service.operation_kinds() == ["back"]
    assert len(service.of_kind("back")) == 1
    request = service.of_kind("back")[0]
    assert request.method == "POST"
    assert request.path.endswith("/back")
    assert request.body == {}
    assert len(service.of_kind("quit")) == 1


def test_back_known_error_preserves_facts_without_replay(
    mcp_harness: McpHarness,
) -> None:
    secret = f"{CANARY}-back-known"
    with DeviceProtocolService() as service:
        service.queue("back", ResponsePlan(status=500, payload=w3c_error(secret)))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "known-back-device")
                wire = await client.call_tool(
                    TOOL_NAMES[9], _request(session_handle=handle)
                )
                assert secret not in _text(wire)
                failed = _error(wire)
                assert failed["code"] == "command_failed"
                assert failed["request_state"] == "response_received"
                assert failed["completed_steps"] == []
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "active"
                assert isinstance(failed["operation_id"], str)
                assert failed["cleanup_status"] == "completed"
                assert failed["cleanup_error_count"] == 0
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("back")) == 1
    assert len(service.of_kind("quit")) == 1
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (secret, CANARY, SECRET_PATH, "known-back-device", "Traceback"):
        assert forbidden not in stderr


def test_back_response_unknown_quarantines_without_quit_or_replay(
    mcp_harness: McpHarness,
) -> None:
    with DeviceProtocolService() as service:
        service.queue("back", ResponsePlan(disconnect=True))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "unknown-back-device")
                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[9],
                        _request(session_handle=handle, timeout_seconds=10.0),
                    )
                )
                assert failed["code"] == "execution_unknown"
                assert failed["request_state"] == "response_unknown"
                assert failed["completed_steps"] == []
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "uncertain"
                assert isinstance(failed["operation_id"], str)
                assert failed["cleanup_status"] == "completed"
                assert failed["cleanup_error_count"] == 0
                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handle)
                    )
                )
                assert status["data"]["session_state"] == "uncertain"
                close = _error(
                    await client.call_tool(
                        TOOL_NAMES[5], _request(session_handle=handle)
                    )
                )
                assert close["code"] == "session_uncertain"

        anyio.run(scenario)

    assert len(service.of_kind("back")) == 1
    assert service.of_kind("quit") == []


def test_back_unknown_shutdown_exits_degraded_without_quit(
    mcp_harness: McpHarness,
) -> None:
    with DeviceProtocolService() as service:
        service.queue("back", ResponsePlan(disconnect=True))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )
        env = os.environ.copy()
        env.update(mcp_harness.environment("passthrough"))
        process = subprocess.Popen(
            [
                mcp_harness.python_command,
                str(mcp_harness.launcher),
                *mcp_harness.arguments(),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=mcp_harness.root,
            env=env,
        )
        stdin = process.stdin
        stdout = process.stdout
        assert stdin is not None and stdout is not None

        def send(frame: dict[str, object]) -> None:
            stdin.write(json.dumps(frame, separators=(",", ":")).encode() + b"\n")
            stdin.flush()

        def receive(identifier: int) -> dict[str, Any]:
            readable, _, _ = select.select([stdout], [], [], 5)
            assert readable == [stdout]
            value = cast(dict[str, Any], json.loads(stdout.readline()))
            assert value["id"] == identifier
            return value

        try:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2026-07-28",
                        "capabilities": {},
                        "clientInfo": {"name": "back-eof-test", "version": "1"},
                    },
                }
            )
            receive(1)
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": TOOL_NAMES[3],
                        "arguments": _request(
                            device_id="unknown-shutdown-device",
                            app_id="com.example",
                        ),
                    },
                }
            )
            opened = receive(2)
            content = opened["result"]["content"]
            assert isinstance(content, list) and content[0]["type"] == "text"
            handle = json.loads(content[0]["text"])["data"]["session_handle"]
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": TOOL_NAMES[9],
                        "arguments": _request(session_handle=handle),
                    },
                }
            )
            failed = receive(3)
            assert failed["result"]["isError"] is True
            stdin.close()
            assert process.wait(timeout=10) == 4
        finally:
            if not stdin.closed:
                stdin.close()
            if not stdout.closed:
                stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    assert len(service.of_kind("back")) == 1
    assert service.of_kind("quit") == []


def test_back_holds_session_gate_against_all_actions_observe_and_close(
    mcp_harness: McpHarness,
) -> None:
    started = threading.Event()
    release = threading.Event()
    locator = {
        "by": "id",
        "value": "target",
        "package": "com.example",
        "raw_id": False,
        "parent": None,
    }
    with DeviceProtocolService() as service:
        service.queue("back", ResponsePlan(started=started, release=release))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "busy-back-device")
                first: list[CallToolResult] = []

                async def back() -> None:
                    first.append(
                        await client.call_tool(
                            TOOL_NAMES[9], _request(session_handle=handle)
                        )
                    )

                async with anyio.create_task_group() as group:
                    group.start_soon(back)
                    await anyio.to_thread.run_sync(started.wait)
                    competing = [
                        await client.call_tool(
                            TOOL_NAMES[7],
                            _request(session_handle=handle, locator=locator),
                        ),
                        await client.call_tool(
                            TOOL_NAMES[8],
                            _request(
                                session_handle=handle,
                                locator=locator,
                                intent="clear",
                            ),
                        ),
                        await client.call_tool(
                            TOOL_NAMES[9], _request(session_handle=handle)
                        ),
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _request(
                                session_handle=handle,
                                mode="tree",
                                locator=None,
                            ),
                        ),
                        await client.call_tool(
                            TOOL_NAMES[5], _request(session_handle=handle)
                        ),
                    ]
                    for wire in competing:
                        busy = _error(wire)
                        assert busy["code"] == "session_busy"
                        assert busy["request_state"] == "not_sent"
                    release.set()

                assert _structured(first[0])["data"]["action"] == "back"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("back")) == 1
    assert len(service.of_kind("quit")) == 1


def test_back_cancel_waits_for_late_success_without_replay(
    mcp_harness: McpHarness,
) -> None:
    started = threading.Event()
    release = threading.Event()
    with DeviceProtocolService() as service:
        service.queue("back", ResponsePlan(started=started, release=release))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "cancel-back-device")
                scopes: list[anyio.CancelScope] = []

                async def back() -> None:
                    with anyio.CancelScope() as scope:
                        scopes.append(scope)
                        await client.call_tool(
                            TOOL_NAMES[9], _request(session_handle=handle)
                        )

                async with anyio.create_task_group() as group:
                    group.start_soon(back)
                    await anyio.to_thread.run_sync(started.wait)
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

    assert len(service.of_kind("back")) == 1
    assert len(service.of_kind("quit")) == 1


def test_back_timeout_budget_starts_before_registry_admission(
    mcp_harness: McpHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = Application(LocalSettings(), mcp_harness.adb, surface="mcp")
    lower_calls: list[object] = []
    entry = SimpleNamespace(
        handle="s_" + ("a" * 32),
        state="active",
        busy=False,
    )

    def delayed_prepare(handle: str, call_id: str) -> tuple[object, object]:
        del handle, call_id
        time.sleep(0.03)
        return entry, lower_calls

    monkeypatch.setattr(application, "_prepare_ui_operation", delayed_prepare)
    request = DeviceBackRequest.model_validate(
        {
            "schema_version": 1,
            "session_handle": entry.handle,
            "timeout_seconds": 0.01,
        }
    )

    async def scenario() -> dict[str, Any]:
        with pytest.raises(ApplicationError) as caught:
            await application.back(request)
        await application.aclose()
        return caught.value.data.model_dump(mode="json")

    error = anyio.run(scenario)
    assert error["code"] == "operation_timeout"
    assert error["operation_id"] is None
    assert error["request_state"] == "not_sent"
    assert error["cleanup_status"] == "not_needed"
    assert error["cleanup_error_count"] == 0
    assert lower_calls == []


def test_back_pre_start_cancel_does_zero_lower_calls(
    mcp_harness: McpHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = Application(LocalSettings(), mcp_harness.adb, surface="mcp")
    lower_calls: list[object] = []
    entry = SimpleNamespace(
        handle="s_" + ("a" * 32),
        state="active",
        busy=False,
    )
    session = SimpleNamespace(
        device=SimpleNamespace(back=lambda *, control: lower_calls.append(control)),
        session_info=lambda: SimpleNamespace(state="active", busy=False),
    )

    def prepare(handle: str, call_id: str) -> tuple[object, object]:
        del handle, call_id
        return entry, session

    monkeypatch.setattr(application, "_prepare_ui_operation", prepare)
    original_run_budget = application._workers.run_budget

    async def cancel_before_start(budget: Any, function: Any) -> Any:
        budget.cancellation.set()
        return await original_run_budget(budget, function)

    monkeypatch.setattr(application._workers, "run_budget", cancel_before_start)
    request = DeviceBackRequest.model_validate(
        {
            "schema_version": 1,
            "session_handle": entry.handle,
            "timeout_seconds": 10.0,
        }
    )

    async def scenario() -> dict[str, Any]:
        with pytest.raises(ApplicationError) as caught:
            await application.back(request)
        await application.aclose()
        return caught.value.data.model_dump(mode="json")

    error = anyio.run(scenario)
    assert error["code"] == "operation_cancelled"
    assert error["operation_id"] is None
    assert error["request_state"] == "not_sent"
    assert error["cleanup_status"] == "not_needed"
    assert error["cleanup_error_count"] == 0
    assert lower_calls == []
