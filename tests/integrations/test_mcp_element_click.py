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
from pydantic import TypeAdapter

from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations._application import Application, ApplicationError
from appium_connect_agent.integrations._models import ElementClickRequest
from tests.automation._action_protocol import (
    ActionProtocolService,
    ResponsePlan,
    elements,
    stale_error,
    w3c_error,
)

from .conftest import CANARY, SECRET_PATH, TOOL_NAMES, McpHarness


def _request(**values: object) -> dict[str, object]:
    request = {"schema_version": 1, **values}
    if "locator" in values and "mode" not in values and "intent" not in values:
        request.setdefault("kind", "single")
    return {"request": request}


def _locator(
    by: str = "id",
    value: str = "target",
    *,
    package: str | None = "com.example",
    raw_id: bool = False,
    parent: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "by": by,
        "value": value,
        "package": package,
        "raw_id": raw_id,
        "parent": parent,
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
    text = _text(result)
    assert marker in text
    return cast(dict[str, Any], json.loads(text.split(marker, 1)[1]))


def _schema_target(root: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in value:
        target: object = root
        for component in value["$ref"].removeprefix("#/").split("/"):
            assert isinstance(target, dict)
            target = target[component]
        assert isinstance(target, dict)
        value = cast(dict[str, Any], target)
    return value


async def _open(client: Client, device_id: str = "click-device") -> str:
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


def test_click_is_eighth_destructive_tool_with_strict_schema(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> list[Tool]:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            return (await client.list_tools()).tools

    tools = anyio.run(scenario)
    assert tuple(tool.name for tool in tools) == TOOL_NAMES
    click = tools[7]
    assert click.annotations is not None
    assert click.annotations.model_dump(
        mode="json", by_alias=True, exclude_none=False
    ) == {
        "title": None,
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }

    input_root = click.input_schema
    assert input_root["type"] == "object"
    assert input_root["required"] == ["request"]
    request_schema = _schema_target(input_root, input_root["properties"]["request"])
    assert request_schema["discriminator"]["propertyName"] == "kind"
    branches = [
        _schema_target(input_root, branch) for branch in request_schema["oneOf"]
    ]
    assert [branch["properties"]["kind"]["const"] for branch in branches] == [
        "single",
        "double",
        "long",
    ]
    for branch in branches:
        assert branch["additionalProperties"] is False
        assert set(branch["required"]) == {
            "schema_version",
            "session_handle",
            "locator",
            "kind",
        }
        assert branch["properties"]["wait_timeout_seconds"] == {
            "default": 15.0,
            "exclusiveMinimum": 0.0,
            "maximum": 120.0,
            "title": "Wait Timeout Seconds",
            "type": "number",
        }
        assert branch["properties"]["timeout_seconds"] == {
            "default": 90.0,
            "exclusiveMinimum": 0.0,
            "maximum": 120.0,
            "title": "Timeout Seconds",
            "type": "number",
        }
        locator_schema = _schema_target(input_root, branch["properties"]["locator"])
        assert locator_schema["additionalProperties"] is False
        assert set(locator_schema["required"]) == {"by", "value"}
    assert "duration_ms" not in branches[0]["properties"]
    assert "duration_ms" not in branches[1]["properties"]
    assert branches[2]["properties"]["duration_ms"] == {
        "default": 500,
        "maximum": 60000,
        "minimum": 1,
        "title": "Duration Ms",
        "type": "integer",
    }

    assert click.output_schema is not None
    output_root = _schema_target(click.output_schema, click.output_schema)
    assert output_root["additionalProperties"] is False
    assert set(output_root["required"]) == {
        "schema_version",
        "call_id",
        "execution",
        "operation_id",
        "request_state",
        "warnings",
        "automation_module_status",
        "data",
    }
    data_schema = _schema_target(click.output_schema, output_root["properties"]["data"])
    assert data_schema["additionalProperties"] is False
    assert set(data_schema["required"]) == {"action", "session_state", "busy"}
    assert data_schema["properties"]["action"]["enum"] == [
        "click",
        "double_click",
        "long_click",
    ]
    assert data_schema["properties"]["session_state"]["const"] == "active"
    assert data_schema["properties"]["busy"]["const"] is False


def test_click_schema_rejects_invalid_requests_before_handler(
    mcp_harness: McpHarness,
) -> None:
    handle = "s_" + ("a" * 32)
    valid = {
        "schema_version": 1,
        "session_handle": handle,
        "locator": _locator(),
        "kind": "single",
    }
    invalid = [
        {key: value for key, value in valid.items() if key != "locator"},
        {**valid, "extra": True},
        {**valid, "wait_timeout_seconds": True},
        {**valid, "wait_timeout_seconds": 0.0},
        {**valid, "timeout_seconds": "90"},
        {**valid, "timeout_seconds": 120.0001},
        {**valid, "locator": {**_locator(), "extra": True}},
    ]

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            for request in invalid:
                result = await client.call_tool(TOOL_NAMES[7], {"request": request})
                assert result.is_error is True
                assert result.structured_content is None

    anyio.run(scenario)
    assert mcp_harness.events() == [{"event": "server_stopped", "result": 0}]


def test_click_uses_one_public_action_and_returns_active_idle(
    mcp_harness: McpHarness,
) -> None:
    with ActionProtocolService() as service:
        service.matches[(None, "id", "com.example:id/target")] = ["target"]
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client)
                clicked = _structured(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle=handle,
                            locator=_locator(),
                            wait_timeout_seconds=2.0,
                            timeout_seconds=10.0,
                        ),
                    )
                )
                assert clicked["execution"] == "completed"
                assert clicked["operation_id"] is None
                assert clicked["request_state"] is None
                assert clicked["warnings"] == []
                assert clicked["data"] == {
                    "action": "click",
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

    assert service.operation_kinds() == ["find", "displayed", "enabled", "action"]
    assert len(service.of_kind("action")) == 1
    action = service.of_kind("action")[0]
    assert action.body == {
        "script": "mobile: clickGesture",
        "args": [{"elementId": "target"}],
    }
    assert len(service.of_kind("quit")) == 1


@pytest.mark.parametrize(
    ("matches", "expected_code", "expected_state"),
    [
        ([], "condition_timeout", "not_sent"),
        (["one", "two"], "target_ambiguous", "response_received"),
    ],
)
def test_click_zero_or_multiple_targets_do_not_send_action(
    mcp_harness: McpHarness,
    matches: list[str],
    expected_code: str,
    expected_state: str,
) -> None:
    with ActionProtocolService() as service:
        service.matches[(None, "id", "com.example:id/missing")] = matches
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "condition-device")
                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle=handle,
                            locator=_locator(value="missing"),
                            wait_timeout_seconds=0.05,
                            timeout_seconds=2.0,
                        ),
                    )
                )
                assert failed["code"] == expected_code
                assert failed["request_state"] == expected_state
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "active"
                assert failed["operation_id"] is not None
                assert service.of_kind("action") == []
                await _close(client, handle)

        anyio.run(scenario)


def test_click_holds_session_gate_against_observe_and_close(
    mcp_harness: McpHarness,
) -> None:
    started = threading.Event()
    release = threading.Event()
    with ActionProtocolService() as service:
        service.queue("find", ResponsePlan(started=started, release=release))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "busy-click-device")
                first: list[CallToolResult] = []

                async def click() -> None:
                    first.append(
                        await client.call_tool(
                            TOOL_NAMES[7],
                            _request(session_handle=handle, locator=_locator()),
                        )
                    )

                async with anyio.create_task_group() as group:
                    group.start_soon(click)
                    await anyio.to_thread.run_sync(started.wait)
                    observing = _error(
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _request(
                                session_handle=handle,
                                mode="tree",
                                locator=None,
                            ),
                        )
                    )
                    closing = _error(
                        await client.call_tool(
                            TOOL_NAMES[5], _request(session_handle=handle)
                        )
                    )
                    assert observing["code"] == "session_busy"
                    assert closing["code"] == "session_busy"
                    assert observing["request_state"] == "not_sent"
                    assert closing["request_state"] == "not_sent"
                    release.set()

                clicked = _structured(first[0])
                assert clicked["data"]["action"] == "click"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("action")) == 1
    assert len(service.of_kind("quit")) == 1


def test_click_unknown_quarantines_without_close_quit_or_replay(
    mcp_harness: McpHarness,
) -> None:
    locator_canary = f"{CANARY}-click"
    with ActionProtocolService() as service:
        service.queue("action", ResponsePlan(disconnect=True))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "unknown-click-device")
                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle=handle,
                            locator=_locator(
                                "accessibility_id",
                                locator_canary,
                                package=None,
                            ),
                            timeout_seconds=10.0,
                        ),
                    )
                )
                assert failed["code"] == "execution_unknown"
                assert failed["request_state"] == "response_unknown"
                assert failed["session_handle"] == handle
                assert failed["session_state"] == "uncertain"
                assert failed["completed_steps"] == [
                    "target_resolved",
                    "target_displayed",
                    "target_enabled",
                ]
                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handle)
                    )
                )
                assert status["data"]["session_state"] == "uncertain"
                before = len(service.snapshot())
                close = _error(
                    await client.call_tool(
                        TOOL_NAMES[5], _request(session_handle=handle)
                    )
                )
                assert close["code"] == "session_uncertain"
                assert len(service.snapshot()) == before

        anyio.run(scenario)

    assert len(service.of_kind("action")) == 1
    assert service.of_kind("quit") == []
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (
        locator_canary,
        CANARY,
        SECRET_PATH,
        "unknown-click-device",
        "Traceback",
    ):
        assert forbidden not in stderr


def test_click_accepts_json_object_string_and_locator_depth_boundary(
    mcp_harness: McpHarness,
) -> None:
    handle = "s_" + ("a" * 32)
    locator = _locator(value="leaf")
    for index in range(15):
        locator = _locator(value=f"parent-{index}", parent=locator)
    overflow = _locator(value="overflow", parent=locator)

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            accepted = _error(
                await client.call_tool(
                    TOOL_NAMES[7],
                    {
                        "request": json.dumps(
                            {
                                "schema_version": 1,
                                "session_handle": handle,
                                "locator": locator,
                                "kind": "single",
                                "wait_timeout_seconds": 1.0,
                                "timeout_seconds": 2.0,
                            }
                        )
                    },
                )
            )
            assert accepted["code"] == "session_not_found"
            rejected = await client.call_tool(
                TOOL_NAMES[7],
                _request(session_handle=handle, locator=overflow),
            )
            assert rejected.is_error is True
            assert "ACA_ERROR " not in _text(rejected)
            spelling = await client.call_tool(
                TOOL_NAMES[7],
                _request(
                    session_handle=handle,
                    locator=_locator("accessibility id", package=None),
                ),
            )
            assert spelling.is_error is True
            assert "ACA_ERROR " not in _text(spelling)

    anyio.run(scenario)
    assert mcp_harness.events() == [{"event": "server_stopped", "result": 0}]


@pytest.mark.parametrize(
    ("locator", "matches", "expected_find"),
    [
        (
            _locator("accessibility_id", "save", package=None),
            {(None, "accessibility id", "save"): ["target"]},
            {"using": "accessibility id", "value": "save"},
        ),
        (
            _locator("xpath", "//*[@text='Save']", package=None),
            {(None, "xpath", "//*[@text='Save']"): ["target"]},
            {"using": "xpath", "value": "//*[@text='Save']"},
        ),
        (
            _locator(
                "id",
                "target",
                parent=_locator("id", "form"),
            ),
            {
                (None, "id", "com.example:id/form"): ["form"],
                ("form", "id", "com.example:id/target"): ["target"],
            },
            {"using": "id", "value": "com.example:id/target"},
        ),
    ],
)
def test_click_maps_all_locator_strategies_and_parent_chain(
    mcp_harness: McpHarness,
    locator: dict[str, object],
    matches: dict[tuple[str | None, str, str], list[str]],
    expected_find: dict[str, str],
) -> None:
    with ActionProtocolService() as service:
        service.matches.update(matches)
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "locator-click-device")
                clicked = _structured(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(session_handle=handle, locator=locator),
                    )
                )
                assert clicked["data"]["action"] == "click"
                await _close(client, handle)

        anyio.run(scenario)

    finds = service.of_kind("find")
    assert finds[-1].body == expected_find
    assert len(service.of_kind("action")) == 1


def test_click_element_validation_and_closed_or_unknown_handles_do_zero_io(
    mcp_harness: McpHarness,
) -> None:
    with ActionProtocolService() as service:
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "admission-click-device")
                before = len(service.snapshot())
                invalid = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle=handle,
                            locator=_locator("xpath", "//*", package="com.example"),
                        ),
                    )
                )
                assert invalid["code"] == "invalid_argument"
                assert invalid["operation_id"] is None
                assert invalid["request_state"] == "not_sent"
                assert len(service.snapshot()) == before
                await _close(client, handle)
                after_close = len(service.snapshot())
                closed = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(session_handle=handle, locator=_locator()),
                    )
                )
                assert closed["code"] == "session_closed"
                assert closed["session_state"] == "closed"
                unknown = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle="s_" + ("b" * 32),
                            locator=_locator(),
                        ),
                    )
                )
                assert unknown["code"] == "session_not_found"
                assert len(service.snapshot()) == after_close

        anyio.run(scenario)


@pytest.mark.parametrize(
    ("status", "payload"),
    [
        (500, w3c_error("controlled action failure")),
        (200, {"value": "unexpected"}),
    ],
)
def test_click_known_action_errors_preserve_completed_steps_without_replay(
    mcp_harness: McpHarness,
    status: int,
    payload: dict[str, object],
) -> None:
    with ActionProtocolService() as service:
        service.queue("action", ResponsePlan(status=status, payload=payload))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "known-click-device")
                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(session_handle=handle, locator=_locator()),
                    )
                )
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
                assert failed["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("action")) == 1


@pytest.mark.parametrize(
    ("stage", "plans"),
    [
        ("find", (ResponsePlan(payload=elements()), ResponsePlan())),
        (
            "displayed",
            (ResponsePlan(payload={"value": False}), ResponsePlan()),
        ),
        (
            "enabled",
            (ResponsePlan(payload={"value": False}), ResponsePlan()),
        ),
        (
            "displayed",
            (ResponsePlan(status=404, payload=stale_error()),),
        ),
    ],
)
def test_click_waits_through_zero_displayed_enabled_and_pre_action_stale(
    mcp_harness: McpHarness,
    stage: str,
    plans: tuple[ResponsePlan, ...],
) -> None:
    with ActionProtocolService() as service:
        service.queue(stage, *plans)
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "transition-click-device")
                clicked = _structured(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle=handle,
                            locator=_locator(),
                            wait_timeout_seconds=2.0,
                            timeout_seconds=5.0,
                        ),
                    )
                )
                assert clicked["data"]["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind(stage)) >= len(plans)
    assert len(service.of_kind("action")) == 1


def test_click_raw_id_restores_settings_after_success(
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
                handle = await _open(client, "raw-success-click-device")
                clicked = _structured(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle=handle,
                            locator=_locator(
                                "id",
                                raw_value,
                                package=None,
                                raw_id=True,
                            ),
                        ),
                    )
                )
                assert clicked["data"]["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert service.settings["disableIdLocatorAutocompletion"] is False
    assert len(service.of_kind("settings:get")) == 1
    assert len(service.of_kind("settings:post")) == 2
    assert len(service.of_kind("action")) == 1


def test_click_total_budget_truncates_longer_condition_wait(
    mcp_harness: McpHarness,
) -> None:
    with ActionProtocolService() as service:
        service.matches[(None, "id", "com.example:id/missing")] = []
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "budget-click-device")
                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle=handle,
                            locator=_locator(value="missing"),
                            wait_timeout_seconds=2.0,
                            timeout_seconds=0.05,
                        ),
                    )
                )
                assert failed["code"] == "operation_timeout"
                assert failed["request_state"] == "not_sent"
                assert failed["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("find")) == 1
    assert service.of_kind("action") == []


def test_click_raw_id_restores_settings_and_cleanup_failure_quarantines(
    mcp_harness: McpHarness,
) -> None:
    raw_value = "vendor/odd@id"
    with ActionProtocolService() as service:
        service.matches[(None, "id", raw_value)] = ["raw-target"]
        service.queue(
            "settings:post",
            ResponsePlan(),
            ResponsePlan(status=500, payload=w3c_error("restore")),
        )
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "raw-click-device")
                failed = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(
                            session_handle=handle,
                            locator=_locator(
                                "id",
                                raw_value,
                                package=None,
                                raw_id=True,
                            ),
                        ),
                    )
                )
                assert failed["code"] == "cleanup_failed"
                assert failed["request_state"] == "response_received"
                assert failed["completed_steps"][-1] == "action_completed"
                assert failed["cleanup_status"] == "failed"
                assert failed["cleanup_error_count"] == 1
                assert failed["session_state"] == "uncertain"
                before = len(service.snapshot())
                rejected = _error(
                    await client.call_tool(
                        TOOL_NAMES[7],
                        _request(session_handle=handle, locator=_locator()),
                    )
                )
                assert rejected["code"] == "session_uncertain"
                assert len(service.snapshot()) == before

        anyio.run(scenario)

    assert len(service.of_kind("settings:get")) == 1
    assert len(service.of_kind("settings:post")) == 2
    assert len(service.of_kind("action")) == 1
    assert service.of_kind("quit") == []


def test_click_cancel_waits_for_late_success_without_replay(
    mcp_harness: McpHarness,
) -> None:
    started = threading.Event()
    release = threading.Event()
    with ActionProtocolService() as service:
        service.queue("action", ResponsePlan(started=started, release=release))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "cancel-click-device")
                scopes: list[anyio.CancelScope] = []

                async def click() -> None:
                    with anyio.CancelScope() as scope:
                        scopes.append(scope)
                        await client.call_tool(
                            TOOL_NAMES[7],
                            _request(session_handle=handle, locator=_locator()),
                        )

                async with anyio.create_task_group() as group:
                    group.start_soon(click)
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

    assert len(service.of_kind("action")) == 1
    assert len(service.of_kind("quit")) == 1


def test_click_timeout_budget_starts_before_registry_admission(
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
    request = TypeAdapter(ElementClickRequest).validate_python(
        {
            "schema_version": 1,
            "session_handle": entry.handle,
            "locator": _locator(),
            "kind": "single",
            "timeout_seconds": 0.01,
        }
    )

    async def scenario() -> dict[str, Any]:
        with pytest.raises(ApplicationError) as caught:
            await application.click(request)
        await application.aclose()
        return caught.value.data.model_dump(mode="json")

    error = anyio.run(scenario)
    assert error["code"] == "operation_timeout"
    assert error["request_state"] == "not_sent"
    assert lower_calls == []
