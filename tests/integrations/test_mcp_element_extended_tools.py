from __future__ import annotations

import json
from typing import Any, cast

import anyio
from mcp import Client
from mcp.types import CallToolResult, TextContent, Tool

from tests.automation._action_protocol import (
    ActionProtocolService,
    ResponsePlan,
    w3c_error,
)

from .conftest import TOOL_NAMES, McpHarness


def _request(**values: object) -> dict[str, object]:
    return {"request": {"schema_version": 1, **values}}


def _locator(value: str) -> dict[str, object]:
    return {"by": "id", "value": value, "package": "com.example"}


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    value = result.content[0]
    assert isinstance(value, TextContent)
    return value.text


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


def _resolve(root: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in value:
        target: object = root
        for component in value["$ref"].removeprefix("#/").split("/"):
            assert isinstance(target, dict)
            target = target[component]
        assert isinstance(target, dict)
        value = cast(dict[str, Any], target)
    return value


async def _open(client: Client, device_id: str) -> str:
    opened = _structured(
        await client.call_tool(
            TOOL_NAMES[3], _request(device_id=device_id, app_id="com.example")
        )
    )
    handle = opened["data"]["session_handle"]
    assert isinstance(handle, str)
    return handle


async def _close(client: Client, handle: str) -> None:
    closed = _structured(
        await client.call_tool(
            TOOL_NAMES[5], _request(session_handle=handle, timeout_seconds=60.0)
        )
    )
    assert closed["data"]["session_state"] == "closed"


def test_ime_and_gesture_remain_destructive_with_disjoint_schemas(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> list[Tool]:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            return (await client.list_tools()).tools

    tools = anyio.run(scenario)
    assert tuple(tool.name for tool in tools) == TOOL_NAMES
    assert len(tools) == 19
    for tool in tools[10:12]:
        assert tool.annotations is not None
        assert tool.annotations.model_dump(
            mode="json", by_alias=True, exclude_none=False
        ) == {
            "title": None,
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        }

    ime_root = tools[10].input_schema
    ime = _resolve(ime_root, ime_root["properties"]["request"])
    assert set(ime["required"]) == {
        "schema_version",
        "session_handle",
        "locator",
        "action",
    }
    assert ime["properties"]["action"]["enum"] == [
        "normal",
        "unspecified",
        "none",
        "go",
        "search",
        "send",
        "next",
        "done",
        "previous",
    ]

    gesture_root = tools[11].input_schema
    gesture = _resolve(gesture_root, gesture_root["properties"]["request"])
    assert gesture["discriminator"]["propertyName"] == "intent"
    branches = [_resolve(gesture_root, branch) for branch in gesture["oneOf"]]
    assert [branch["properties"]["intent"]["const"] for branch in branches] == [
        "swipe",
        "scroll",
        "scroll_to",
        "drag_and_drop",
    ]
    assert branches[0]["properties"]["percent"]["maximum"] == 1.0
    assert branches[1]["properties"]["percent"]["maximum"] == 3.0
    assert branches[2]["properties"]["max_swipes"] == {
        "maximum": 30,
        "minimum": 1,
        "title": "Max Swipes",
        "type": "integer",
    }
    assert branches[3]["properties"]["destination_x_ratio"]["minimum"] == 0.0
    assert branches[3]["properties"]["destination_y_ratio"]["maximum"] == 1.0


def test_double_and_long_click_use_exact_public_action_payloads(
    mcp_harness: McpHarness,
) -> None:
    with ActionProtocolService() as service:
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "extended-click-device")
                for kind, expected_action in (
                    ("double", "double_click"),
                    ("long", "long_click"),
                ):
                    request: dict[str, object] = {
                        "session_handle": handle,
                        "locator": _locator("target"),
                        "kind": kind,
                    }
                    if kind == "long":
                        request["duration_ms"] = 750
                    result = _structured(
                        await client.call_tool(TOOL_NAMES[7], _request(**request))
                    )
                    assert result["data"]["action"] == expected_action
                await _close(client, handle)

        anyio.run(scenario)

    assert [request.body for request in service.of_kind("action")] == [
        {
            "script": "mobile: doubleClickGesture",
            "args": [{"elementId": "target"}],
        },
        {
            "script": "mobile: longClickGesture",
            "args": [{"elementId": "target", "duration": 750}],
        },
    ]


def test_extended_branch_validation_rejects_before_application(
    mcp_harness: McpHarness,
) -> None:
    handle = "s_" + ("a" * 32)
    invalid_calls = (
        (
            TOOL_NAMES[10],
            _request(session_handle=handle, locator=_locator("target"), action="enter"),
        ),
        (
            TOOL_NAMES[10],
            _request(
                session_handle=handle,
                locator=_locator("target"),
                action="done",
                timeout_seconds=True,
            ),
        ),
        (
            TOOL_NAMES[11],
            _request(
                session_handle=handle,
                intent="swipe",
                locator=_locator("target"),
                direction="up",
                percent=0.0,
            ),
        ),
        (
            TOOL_NAMES[11],
            _request(
                session_handle=handle,
                intent="scroll",
                locator=_locator("target"),
                direction="down",
                percent=3.0001,
            ),
        ),
        (
            TOOL_NAMES[11],
            _request(
                session_handle=handle,
                intent="scroll_to",
                container_locator=_locator("container"),
                target_by="id",
                target_value="child",
                max_swipes=True,
            ),
        ),
        (
            TOOL_NAMES[11],
            _request(
                session_handle=handle,
                intent="drag_and_drop",
                source_locator=_locator("source"),
                destination_locator=_locator("destination"),
                destination_x_ratio=-0.001,
                destination_y_ratio=1.0,
            ),
        ),
    )

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            for name, request in invalid_calls:
                result = await client.call_tool(name, request)
                assert result.is_error is True
                assert result.structured_content is None
                assert "ACA_ERROR " not in _text(result)

    anyio.run(scenario)
    assert mcp_harness.events() == [{"event": "server_stopped", "result": 0}]


def test_ime_and_four_gestures_use_public_automation_actions(
    mcp_harness: McpHarness,
) -> None:
    with ActionProtocolService() as service:
        service.states[("target", "focused")] = True
        service.matches[(None, "id", "com.example:id/source")] = ["source"]
        service.matches[(None, "id", "com.example:id/destination")] = ["destination"]
        service.matches[(None, "id", "com.example:id/container")] = ["container"]
        service.matches[("container", "accessibility id", "child")] = ["child"]
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "extended-actions-device")
                ime = _structured(
                    await client.call_tool(
                        TOOL_NAMES[10],
                        _request(
                            session_handle=handle,
                            locator=_locator("target"),
                            action="done",
                        ),
                    )
                )
                assert ime["data"] == {
                    "action": "ime_action",
                    "session_state": "active",
                    "busy": False,
                }

                requests = (
                    {
                        "intent": "swipe",
                        "locator": _locator("target"),
                        "direction": "up",
                        "percent": 0.5,
                    },
                    {
                        "intent": "scroll",
                        "locator": _locator("target"),
                        "direction": "down",
                        "percent": 2.0,
                    },
                    {
                        "intent": "scroll_to",
                        "container_locator": _locator("container"),
                        "target_by": "accessibility_id",
                        "target_value": "child",
                        "target_package": None,
                        "max_swipes": 3,
                    },
                    {
                        "intent": "drag_and_drop",
                        "source_locator": _locator("source"),
                        "destination_locator": _locator("destination"),
                        "destination_x_ratio": 0.25,
                        "destination_y_ratio": 0.75,
                    },
                )
                for request in requests:
                    result = _structured(
                        await client.call_tool(
                            TOOL_NAMES[11],
                            _request(session_handle=handle, **request),
                        )
                    )
                    assert result["data"]["intent"] == request["intent"]
                    if request["intent"] == "scroll":
                        assert result["data"]["can_scroll_more"] is True
                    else:
                        assert result["data"]["can_scroll_more"] is None
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("action")) == 1
    assert service.of_kind("action")[0].body == {
        "script": "mobile: performEditorAction",
        "args": [{"action": "done"}],
    }
    assert service.of_kind("swipe")[0].body == {
        "script": "mobile: swipeGesture",
        "args": [{"elementId": "target", "direction": "up", "percent": 0.5}],
    }
    assert service.of_kind("scroll_gesture")[0].body == {
        "script": "mobile: scrollGesture",
        "args": [{"elementId": "target", "direction": "down", "percent": 2.0}],
    }
    assert service.of_kind("drag")[0].body == {
        "script": "mobile: dragGesture",
        "args": [{"elementId": "source", "endX": 17, "endY": 49}],
    }
    child_finds = [
        request
        for request in service.of_kind("find")
        if "/element/container/elements" in request.path
    ]
    assert len(child_finds) == 1


def test_extended_action_validation_and_command_failure_are_fail_closed(
    mcp_harness: McpHarness,
) -> None:
    with ActionProtocolService() as service:
        service.queue(
            "swipe", ResponsePlan(status=500, payload=w3c_error("swipe failed"))
        )
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "extended-failure-device")
                invalid = await client.call_tool(
                    TOOL_NAMES[11],
                    _request(
                        session_handle=handle,
                        intent="scroll_to",
                        container_locator=_locator("container"),
                        target_by="accessibility_id",
                        target_value="child",
                        target_package="com.example",
                        max_swipes=3,
                    ),
                )
                assert invalid.is_error is True
                assert invalid.structured_content is None
                assert service.operation_kinds() == []

                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[11],
                        _request(
                            session_handle=handle,
                            intent="swipe",
                            locator=_locator("target"),
                            direction="left",
                            percent=0.5,
                        ),
                    )
                )
                assert failed["code"] == "command_failed"
                assert failed["request_state"] == "response_received"
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("swipe")) == 1
