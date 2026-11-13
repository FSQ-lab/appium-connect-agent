from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from typing import Any, cast

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult, Tool

from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations._application import Application, ApplicationError
from appium_connect_agent.integrations._models import ElementTextSendRequest
from tests.automation._action_protocol import (
    ActionProtocolService,
    ResponsePlan,
    w3c_error,
)

from .conftest import CANARY, TOOL_NAMES, McpHarness


def _request(**values: object) -> dict[str, object]:
    return {"request": {"schema_version": 1, **values}}


def _locator(
    value: str = "target",
    *,
    package: str | None = "com.example",
    raw_id: bool = False,
) -> dict[str, object]:
    return {
        "by": "id",
        "value": value,
        "package": package,
        "raw_id": raw_id,
        "parent": None,
    }


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    value = getattr(result.content[0], "text", None)
    assert isinstance(value, str)
    return value


def _structured(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is False
    assert isinstance(result.structured_content, dict)
    value = cast(dict[str, Any], result.structured_content)
    assert json.loads(_text(result)) == value
    return value


def _error(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is True
    assert result.structured_content is None
    marker = "ACA_ERROR "
    value = _text(result)
    assert marker in value
    return cast(dict[str, Any], json.loads(value.split(marker, 1)[1]))


def _schema_target(root: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in value:
        target: object = root
        for component in value["$ref"].removeprefix("#/").split("/"):
            assert isinstance(target, dict)
            target = target[component]
        assert isinstance(target, dict)
        value = cast(dict[str, Any], target)
    return value


async def _open(client: Client, device_id: str = "text-device") -> str:
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


def test_text_is_ninth_destructive_tool_with_discriminated_strict_schema(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> list[Tool]:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            return (await client.list_tools()).tools

    tools = anyio.run(scenario)
    assert tuple(tool.name for tool in tools) == TOOL_NAMES
    text_tool = tools[8]
    assert text_tool.annotations is not None
    assert text_tool.annotations.model_dump(
        mode="json", by_alias=True, exclude_none=False
    ) == {
        "title": None,
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }

    input_root = text_tool.input_schema
    request_union = input_root["properties"]["request"]
    assert request_union["discriminator"] == {
        "mapping": {
            "send": "#/$defs/ElementTextSendRequest",
            "clear": "#/$defs/ElementTextClearRequest",
            "replace": "#/$defs/ElementTextReplaceRequest",
        },
        "propertyName": "intent",
    }
    branches = {
        branch["$ref"].rsplit("/", 1)[1]: _schema_target(input_root, branch)
        for branch in request_union["oneOf"]
    }
    assert set(branches) == {
        "ElementTextSendRequest",
        "ElementTextClearRequest",
        "ElementTextReplaceRequest",
    }
    assert set(branches["ElementTextClearRequest"]["required"]) == {
        "schema_version",
        "session_handle",
        "locator",
        "intent",
    }
    assert "text" not in branches["ElementTextClearRequest"]["properties"]
    for name in ("ElementTextSendRequest", "ElementTextReplaceRequest"):
        assert "text" in branches[name]["required"]
    assert branches["ElementTextSendRequest"]["properties"]["text"]["minLength"] == 1

    assert text_tool.output_schema is not None
    output_root = _schema_target(text_tool.output_schema, text_tool.output_schema)
    data_schema = _schema_target(
        text_tool.output_schema, output_root["properties"]["data"]
    )
    assert set(data_schema["required"]) == {"intent", "session_state", "busy"}
    assert data_schema["properties"]["intent"]["enum"] == [
        "send",
        "clear",
        "replace",
    ]
    assert data_schema["properties"]["session_state"]["const"] == "active"
    assert data_schema["properties"]["busy"]["const"] is False


def test_text_schema_rejects_branch_and_text_boundaries_before_handler(
    mcp_harness: McpHarness,
) -> None:
    handle = "s_" + ("a" * 32)
    common = {
        "schema_version": 1,
        "session_handle": handle,
        "locator": _locator(),
    }
    invalid = [
        {**common, "intent": "send"},
        {**common, "intent": "send", "text": ""},
        {**common, "intent": "send", "text": "contains\x00nul"},
        {**common, "intent": "send", "text": "literal\\n"},
        {**common, "intent": "send", "text": "a" * 65_537},
        {**common, "intent": "replace"},
        {**common, "intent": "replace", "text": "a" * 65_537},
        {**common, "intent": "clear", "text": CANARY},
        {**common, "intent": "unknown"},
        {**common, "intent": "send", "text": "value", "extra": True},
        {**common, "intent": "send", "text": "value", "timeout_seconds": True},
    ]

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            for request in invalid:
                result = await client.call_tool(TOOL_NAMES[8], {"request": request})
                assert result.is_error is True
                assert result.structured_content is None

    anyio.run(scenario)
    assert mcp_harness.events() == [{"event": "server_stopped", "result": 0}]
    assert CANARY not in mcp_harness.stderr_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("intent", "text_value", "kind"),
    [
        ("send", "A中🙂", "send"),
        ("clear", None, "clear"),
        ("replace", "", "replace"),
    ],
)
def test_text_intents_issue_one_exact_public_action_and_return_active_idle(
    mcp_harness: McpHarness,
    intent: str,
    text_value: str | None,
    kind: str,
) -> None:
    with ActionProtocolService() as service:
        service.matches[(None, "id", "com.example:id/target")] = ["target"]
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, f"{intent}-device")
                values: dict[str, object] = {
                    "session_handle": handle,
                    "locator": _locator(),
                    "intent": intent,
                    "wait_timeout_seconds": 2.0,
                    "timeout_seconds": 10.0,
                }
                if text_value is not None:
                    values["text"] = text_value
                result = _structured(
                    await client.call_tool(TOOL_NAMES[8], _request(**values))
                )
                assert result["operation_id"] is None
                assert result["request_state"] is None
                assert result["warnings"] == []
                assert result["data"] == {
                    "intent": intent,
                    "session_state": "active",
                    "busy": False,
                }
                assert "text" not in result["data"]
                await _close(client, handle)

        anyio.run(scenario)

    assert service.operation_kinds() == ["find", "displayed", "enabled", kind]
    assert len(service.of_kind(kind)) == 1
    request = service.of_kind(kind)[0]
    if intent == "send":
        assert request.body == {
            "text": text_value,
            "value": list(cast(str, text_value)),
        }
    elif intent == "clear":
        assert request.body == {}
    else:
        assert request.body == {
            "script": "mobile: replaceElementValue",
            "args": [{"elementId": "target", "text": text_value}],
        }
    assert len(service.of_kind("quit")) == 1


def test_text_accepts_65536_utf8_bytes_and_json_object_string_request(
    mcp_harness: McpHarness,
) -> None:
    value = "中" * 21_845 + "a"
    assert len(value.encode("utf-8")) == 65_536
    with ActionProtocolService() as service:
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "boundary-device")
                encoded = json.dumps(
                    {
                        "schema_version": 1,
                        "session_handle": handle,
                        "locator": _locator(),
                        "intent": "replace",
                        "text": value,
                    },
                    ensure_ascii=False,
                )
                result = _structured(
                    await client.call_tool(TOOL_NAMES[8], {"request": encoded})
                )
                assert result["data"]["intent"] == "replace"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("replace")) == 1
    assert service.of_kind("replace")[0].body == {
        "script": "mobile: replaceElementValue",
        "args": [{"elementId": "target", "text": value}],
    }


@pytest.mark.parametrize(
    ("intent", "kind", "payload"),
    [
        ("send", "send", None),
        ("clear", "clear", None),
        ("replace", "replace", {"value": CANARY}),
    ],
)
def test_text_known_final_errors_preserve_partial_facts_and_privacy(
    mcp_harness: McpHarness,
    intent: str,
    kind: str,
    payload: dict[str, object] | None,
) -> None:
    secret = f"{CANARY}-{intent}-private-text"
    response = (
        ResponsePlan(status=500, payload=w3c_error(secret))
        if payload is None
        else ResponsePlan(payload=payload)
    )
    with ActionProtocolService() as service:
        service.queue(kind, response)
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, f"known-{intent}-device")
                values: dict[str, object] = {
                    "session_handle": handle,
                    "locator": _locator(),
                    "intent": intent,
                }
                if intent != "clear":
                    values["text"] = secret
                wire = await client.call_tool(TOOL_NAMES[8], _request(**values))
                assert secret not in _text(wire)
                failed = _error(wire)
                assert failed["code"] == "command_failed"
                assert failed["request_state"] == "response_received"
                assert isinstance(failed["operation_id"], str)
                assert failed["completed_steps"] == [
                    "target_resolved",
                    "target_displayed",
                    "target_enabled",
                ]
                assert failed["cleanup_status"] == "completed"
                assert failed["cleanup_error_count"] == 0
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind(kind)) == 1
    assert len(service.of_kind("quit")) == 1
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert secret not in stderr
    assert "Traceback" not in stderr


def test_text_raw_id_restores_settings_after_success_and_shutdown_quits_once(
    mcp_harness: McpHarness,
) -> None:
    raw_value = "vendor/odd@id"
    with ActionProtocolService() as service:
        service.matches[(None, "id", raw_value)] = ["raw-target"]
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "raw-success-text-device")
                result = _structured(
                    await client.call_tool(
                        TOOL_NAMES[8],
                        _request(
                            session_handle=handle,
                            locator=_locator(raw_value, package=None, raw_id=True),
                            intent="replace",
                            text="safe-value",
                        ),
                    )
                )
                assert result["data"]["session_state"] == "active"
                # Deliberately rely on normal MCP shutdown for the owned Session.

        anyio.run(scenario)

    assert service.settings["disableIdLocatorAutocompletion"] is False
    assert len(service.of_kind("settings:get")) == 1
    assert len(service.of_kind("settings:post")) == 2
    assert len(service.of_kind("replace")) == 1
    assert len(service.of_kind("quit")) == 1


def test_text_raw_restore_failure_preserves_action_and_quarantines_privately(
    mcp_harness: McpHarness,
) -> None:
    raw_value = "vendor/odd@id"
    secret = f"{CANARY}-raw-private-text"
    with ActionProtocolService() as service:
        service.matches[(None, "id", raw_value)] = ["raw-target"]
        service.queue(
            "settings:post",
            ResponsePlan(),
            ResponsePlan(status=500, payload=w3c_error(secret)),
        )
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "raw-failure-text-device")
                wire = await client.call_tool(
                    TOOL_NAMES[8],
                    _request(
                        session_handle=handle,
                        locator=_locator(raw_value, package=None, raw_id=True),
                        intent="replace",
                        text=secret,
                    ),
                )
                assert secret not in _text(wire)
                failed = _error(wire)
                assert failed["code"] == "cleanup_failed"
                assert failed["request_state"] == "response_received"
                assert failed["completed_steps"] == [
                    "settings_read",
                    "settings_changed",
                    "target_resolved",
                    "target_displayed",
                    "target_enabled",
                    "action_completed",
                ]
                assert failed["cleanup_status"] == "failed"
                assert failed["cleanup_error_count"] == 1
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "uncertain"

                before = len(service.snapshot())
                rejected = _error(
                    await client.call_tool(
                        TOOL_NAMES[8],
                        _request(
                            session_handle=handle,
                            locator=_locator(),
                            intent="clear",
                        ),
                    )
                )
                assert rejected["code"] == "session_uncertain"
                assert len(service.snapshot()) == before

        anyio.run(scenario)

    assert len(service.of_kind("replace")) == 1
    assert len(service.of_kind("settings:post")) == 2
    assert service.of_kind("quit") == []
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert secret not in stderr
    assert "Traceback" not in stderr


def test_text_response_unknown_preserves_partial_facts_and_quarantines(
    mcp_harness: McpHarness,
) -> None:
    with ActionProtocolService() as service:
        service.queue("send", ResponsePlan(disconnect=True))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "unknown-text-device")
                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[8],
                        _request(
                            session_handle=handle,
                            locator=_locator(),
                            intent="send",
                            text="private-value",
                        ),
                    )
                )
                assert failed["code"] == "execution_unknown"
                assert failed["request_state"] == "response_unknown"
                assert failed["completed_steps"] == [
                    "target_resolved",
                    "target_displayed",
                    "target_enabled",
                ]
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "uncertain"
                assert "private-value" not in json.dumps(failed)

                before = len(service.snapshot())
                rejected = _error(
                    await client.call_tool(
                        TOOL_NAMES[8],
                        _request(
                            session_handle=handle,
                            locator=_locator(),
                            intent="clear",
                        ),
                    )
                )
                assert rejected["code"] == "session_uncertain"
                close = _error(
                    await client.call_tool(
                        TOOL_NAMES[5], _request(session_handle=handle)
                    )
                )
                assert close["code"] == "session_uncertain"
                assert len(service.snapshot()) == before

        anyio.run(scenario)

    assert len(service.of_kind("send")) == 1
    assert service.of_kind("quit") == []
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert "private-value" not in stderr
    assert "Traceback" not in stderr


def test_text_holds_session_gate_and_cancel_waits_without_replay(
    mcp_harness: McpHarness,
) -> None:
    started = threading.Event()
    release = threading.Event()
    with ActionProtocolService() as service:
        service.queue("replace", ResponsePlan(started=started, release=release))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "cancel-text-device")
                scopes: list[anyio.CancelScope] = []

                async def replace() -> None:
                    with anyio.CancelScope() as scope:
                        scopes.append(scope)
                        await client.call_tool(
                            TOOL_NAMES[8],
                            _request(
                                session_handle=handle,
                                locator=_locator(),
                                intent="replace",
                                text="value",
                            ),
                        )

                async with anyio.create_task_group() as group:
                    group.start_soon(replace)
                    await anyio.to_thread.run_sync(started.wait)
                    busy = _error(
                        await client.call_tool(
                            TOOL_NAMES[8],
                            _request(
                                session_handle=handle,
                                locator=_locator(),
                                intent="clear",
                            ),
                        )
                    )
                    assert busy["code"] == "session_busy"
                    assert busy["request_state"] == "not_sent"
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

    assert len(service.of_kind("replace")) == 1
    assert service.of_kind("clear") == []
    assert len(service.of_kind("quit")) == 1


def test_text_timeout_budget_starts_before_registry_admission(
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
    request = ElementTextSendRequest.model_validate(
        {
            "schema_version": 1,
            "session_handle": entry.handle,
            "locator": _locator(),
            "intent": "send",
            "text": "value",
            "timeout_seconds": 0.01,
        }
    )

    async def scenario() -> dict[str, Any]:
        with pytest.raises(ApplicationError) as caught:
            await application.text(request)
        await application.aclose()
        return caught.value.data.model_dump(mode="json")

    error = anyio.run(scenario)
    assert error["code"] == "operation_timeout"
    assert error["request_state"] == "not_sent"
    assert lower_calls == []
