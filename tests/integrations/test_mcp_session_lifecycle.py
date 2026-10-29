from __future__ import annotations

import json
from typing import Any, cast

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult, Tool

from tests.automation.test_session_lifecycle import ProtocolService, appium_caps

from .conftest import CANARY, SECRET_PATH, TOOL_NAMES, McpHarness

_HANDLE_A = "s_" + ("a" * 32)


def _structured(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is False
    assert type(result.structured_content) is dict
    value = cast(dict[str, Any], result.structured_content)
    assert len(result.content) == 1
    assert getattr(result.content[0], "text", None) == json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return value


def _error(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is True
    assert result.structured_content is None
    assert len(result.content) == 1
    text = getattr(result.content[0], "text", None)
    assert type(text) is str
    marker = "ACA_ERROR "
    assert marker in text
    return cast(dict[str, Any], json.loads(text.split(marker, 1)[1]))


def _request(**values: object) -> dict[str, object]:
    return {"request": {"schema_version": 1, **values}}


async def _open(
    client: Client,
    *,
    device_id: str = "device-primary",
    **values: object,
) -> dict[str, Any]:
    return _structured(
        await client.call_tool(TOOL_NAMES[3], _request(device_id=device_id, **values))
    )


async def _close(client: Client, handle: str, **values: object) -> dict[str, Any]:
    return _structured(
        await client.call_tool(TOOL_NAMES[5], _request(session_handle=handle, **values))
    )


def _event_names(harness: McpHarness) -> list[str]:
    return [event["event"] for event in harness.events()]


async def _wait_for_event(harness: McpHarness, event: str) -> None:
    with anyio.fail_after(2):
        while event not in _event_names(harness):
            await anyio.sleep(0.001)


def _assert_only_clean_server_stop(harness: McpHarness) -> None:
    assert harness.events() == [{"event": "server_stopped", "result": 0}]


def test_six_tools_have_fixed_order_annotations_and_session_schemas(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> list[Tool]:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            return (await client.list_tools()).tools

    tools = anyio.run(scenario)
    assert tuple(tool.name for tool in tools) == TOOL_NAMES
    annotations = [
        tool.annotations.model_dump(mode="json", by_alias=True, exclude_none=False)
        if tool.annotations is not None
        else None
        for tool in tools
    ]
    assert annotations == [
        {
            "title": None,
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        {
            "title": None,
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        {
            "title": None,
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        {
            "title": None,
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        {
            "title": None,
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        {
            "title": None,
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    ]
    for tool in tools:
        assert tool.input_schema["type"] == "object"
        assert tool.input_schema["required"] == ["request"]
        assert tool.output_schema is not None
    assert "capabilities" not in json.dumps(tools[3].input_schema)
    assert "systemPort" not in json.dumps(tools[3].input_schema)
    assert "server_url" not in json.dumps(tools[3].input_schema)


def test_four_app_input_combinations_are_delegated_with_fixed_capabilities(
    mcp_harness: McpHarness,
) -> None:
    apk = mcp_harness.root / "selected.apk"
    apk.write_bytes(b"controlled apk bytes")

    async def scenario() -> None:
        combinations: tuple[dict[str, object], ...] = (
            {},
            {"app_id": "org.example.app"},
            {"app_path": str(apk)},
            {"app_id": "org.example.explicit", "app_path": str(apk)},
        )
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            for index, combination in enumerate(combinations):
                opened = await _open(
                    client,
                    device_id=f"device-{index}",
                    auto_launch=True,
                    force_app_launch=True,
                    should_terminate_app=True,
                    new_command_timeout_seconds=0,
                    **combination,
                )
                data = opened["data"]
                assert data["ownership"] == "mcp"
                assert data["session_state"] == "active"
                assert data["busy"] is False
                assert "appium_session_id" not in json.dumps(opened)
                closed = await _close(client, data["session_handle"])
                assert closed["data"]["session_state"] == "closed"

    anyio.run(scenario)
    creates = [
        event for event in mcp_harness.events() if event["event"] == "create_session"
    ]
    assert len(creates) == 4
    assert [(event["app_id"], event["app_path"]) for event in creates] == [
        (None, None),
        ("org.example.app", None),
        (None, str(apk)),
        ("org.example.explicit", str(apk)),
    ]
    for event in creates:
        assert event["no_reset"] is True
        assert event["full_reset"] is False
        assert event["capabilities"] is None
        assert event["new_command_timeout_seconds"] == 0.0
        assert event["auto_launch"] is True
        assert event["force_app_launch"] is True
        assert event["should_terminate_app"] is True


def test_integer_and_decimal_numbers_are_equivalent_and_strict_negatives_are_zero_io(
    mcp_harness: McpHarness,
) -> None:
    async def accepted(value: int | float) -> tuple[float, float, float]:
        mcp_harness.reset_records()
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            opened = await _open(
                client,
                timeout_seconds=value,
                new_command_timeout_seconds=value,
            )
            await _close(client, opened["data"]["session_handle"])
        connected = next(
            event
            for event in mcp_harness.events()
            if event["event"] == "runtime_connect"
        )
        created = next(
            event
            for event in mcp_harness.events()
            if event["event"] == "create_session"
        )
        return (
            connected["timeout"],
            created["timeout"],
            created["new_command_timeout_seconds"],
        )

    integer = anyio.run(accepted, 60)
    decimal = anyio.run(accepted, 60.0)
    for connected_remaining, create_remaining, command_timeout in (integer, decimal):
        assert command_timeout == 60.0
        assert 0.0 < create_remaining < connected_remaining < 60.0

    invalid: tuple[dict[str, object], ...] = (
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"new_command_timeout_seconds": float("-inf")},
        {"timeout_seconds": True},
        {"timeout_seconds": 0},
        {"timeout_seconds": 300.0001},
        {"timeout_seconds": "60"},
        {"new_command_timeout_seconds": False},
        {"new_command_timeout_seconds": -0.1},
        {"new_command_timeout_seconds": 86400.1},
        {"auto_launch": 1},
        {"device_id": "bad id"},
        {"unknown": 1},
        {"device_id": ""},
        {"device_id": "d" * 1025},
        {"app_id": ""},
        {"app_id": "a" * 256},
        {"app_id": "bad app"},
        {"app_path": "relative.apk"},
        {"app_path": ""},
        {"app_path": "/" + "p" * 4096},
    )
    invalid_json_requests = (
        {"schema_version": 1, "device_id": "d" * 1023 + "\ud800"},
        {
            "schema_version": 1,
            "device_id": "device",
            "app_id": "a" * 254 + "\ud800",
        },
        {
            "schema_version": 1,
            "device_id": "device",
            "app_path": "/tmp/\ud800.apk",
        },
    )

    async def rejected() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            for values in invalid:
                result = await client.call_tool(
                    TOOL_NAMES[3], _request(**{"device_id": "device", **values})
                )
                assert result.is_error is True
                assert result.structured_content is None
            for values in invalid_json_requests:
                encoded = json.dumps(
                    values,
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                result = await client.call_tool(TOOL_NAMES[3], {"request": encoded})
                assert result.is_error is True
                assert result.structured_content is None

    mcp_harness.reset_records()
    anyio.run(rejected)
    _assert_only_clean_server_stop(mcp_harness)


def test_handle_shape_rejects_before_lookup_and_valid_missing_is_canonical(
    mcp_harness: McpHarness,
) -> None:
    invalid: tuple[object, ...] = (
        "",
        "s_" + "a" * 31,
        "s_" + "a" * 33,
        "s_" + "!" * 32,
        "s_" + "a" * 31 + "é",
        True,
    )

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            for handle in invalid:
                for tool_name in (TOOL_NAMES[4], TOOL_NAMES[5]):
                    result = await client.call_tool(
                        tool_name, _request(session_handle=handle)
                    )
                    assert result.is_error is True
                    assert result.structured_content is None
            missing = _error(
                await client.call_tool(
                    TOOL_NAMES[4], _request(session_handle=_HANDLE_A)
                )
            )
            assert missing["code"] == "session_not_found"
            assert missing["request_state"] == "not_sent"
            assert missing["session_handle"] is None
            assert missing["session_state"] is None

    anyio.run(scenario)
    _assert_only_clean_server_stop(mcp_harness)


def test_capacity_runtime_gate_primary_tombstone_and_replacement(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            primary = await _open(client)
            handle = primary["data"]["session_handle"]
            status = _structured(
                await client.call_tool(TOOL_NAMES[4], _request(session_handle=handle))
            )
            assert status["data"] == primary["data"]

            capacity = _error(
                await client.call_tool(TOOL_NAMES[3], _request(device_id="other"))
            )
            assert capacity["code"] == "session_capacity_reached"
            assert capacity["request_state"] == "not_sent"
            assert capacity["session_handle"] is None
            assert capacity["session_state"] is None

            runtime = _error(
                await client.call_tool(
                    TOOL_NAMES[1],
                    _request(mode="external_connection", timeout_seconds=10.0),
                )
            )
            assert runtime["code"] == "runtime_scope_active"
            assert runtime["session_handle"] is None

            closed = await _close(client, handle)
            assert closed["data"]["session_state"] == "closed"
            assert (
                _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handle)
                    )
                )["data"]
                == closed["data"]
            )
            assert (await _close(client, handle))["data"] == closed["data"]

            replacement = await _open(client, device_id="device-replacement")
            assert replacement["data"]["session_handle"] != handle
            await _close(client, replacement["data"]["session_handle"])

    anyio.run(scenario)
    names = _event_names(mcp_harness)
    assert names.count("runtime_connect_enter") == 2
    assert names.count("runtime_connect_exit") == 2
    assert names.count("create_session") == 2
    assert names.count("session_quit") == 2
    assert "runtime_diagnose" not in names


def test_provisional_handle_is_unaddressable_and_open_uses_one_lower_call(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        results: list[CallToolResult] = []
        async with Client(
            mcp_harness.parameters(
                mode="open_stalled",
                environment={"ACA_TEST_HANDLES": json.dumps(["a" * 32])},
            )
        ) as client:

            async def opening() -> None:
                results.append(
                    await client.call_tool(TOOL_NAMES[3], _request(device_id="device"))
                )

            async with anyio.create_task_group() as group:
                group.start_soon(opening)
                with anyio.fail_after(2):
                    while "worker_entered" not in _event_names(mcp_harness):
                        await anyio.sleep(0.001)
                missing = _error(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=_HANDLE_A)
                    )
                )
                assert missing["code"] == "session_not_found"
                assert missing["session_handle"] is None
                assert missing["session_state"] is None
                mcp_harness.release_file.touch()
            assert _structured(results[0])["data"]["session_handle"] == _HANDLE_A
            await _close(client, _HANDLE_A)

    anyio.run(scenario)
    assert _event_names(mcp_harness).count("create_session") == 1


def test_close_in_flight_is_busy_and_blocks_lifecycle_without_lower_calls(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        results: list[CallToolResult] = []
        async with Client(
            mcp_harness.parameters(
                mode="close_stalled",
                environment={"ACA_TEST_HANDLES": json.dumps(["a" * 32])},
            )
        ) as client:
            await _open(client)

            async def closing() -> None:
                results.append(
                    await client.call_tool(
                        TOOL_NAMES[5], _request(session_handle=_HANDLE_A)
                    )
                )

            async with anyio.create_task_group() as group:
                group.start_soon(closing)
                await _wait_for_event(mcp_harness, "worker_entered")
                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=_HANDLE_A)
                    )
                )
                assert status["data"]["session_state"] == "closing"
                assert status["data"]["busy"] is True

                overlapping = _error(
                    await client.call_tool(
                        TOOL_NAMES[5], _request(session_handle=_HANDLE_A)
                    )
                )
                assert overlapping["code"] == "session_busy"
                assert overlapping["request_state"] == "not_sent"
                assert overlapping["session_handle"] == _HANDLE_A
                assert overlapping["session_state"] == "closing"

                capacity = _error(
                    await client.call_tool(
                        TOOL_NAMES[3], _request(device_id="blocked-device")
                    )
                )
                assert capacity["code"] == "session_capacity_reached"
                assert capacity["request_state"] == "not_sent"
                runtime = _error(
                    await client.call_tool(
                        TOOL_NAMES[1],
                        _request(mode="static", timeout_seconds=10.0),
                    )
                )
                assert runtime["code"] == "runtime_scope_active"
                assert runtime["request_state"] == "not_sent"
                names = _event_names(mcp_harness)
                assert names.count("create_session") == 1
                assert names.count("session_quit") == 1
                assert names.count("session_delete") == 0
                assert names.count("runtime_diagnose") == 0
                mcp_harness.release_file.touch()

            closed = _structured(results[0])
            assert closed["data"]["session_state"] == "closed"
            replacement = await _open(client, device_id="replacement-device")
            await _close(client, replacement["data"]["session_handle"])

    anyio.run(scenario)
    names = _event_names(mcp_harness)
    assert names.count("create_session") == 2
    assert names.count("session_quit") == 2
    assert names.count("session_delete") == 2
    assert names.count("runtime_connect_exit") == 2
    stopped = next(
        event for event in mcp_harness.events() if event["event"] == "server_stopped"
    )
    assert stopped["result"] == 0


@pytest.mark.parametrize(
    ("mode", "exit_succeeds"),
    (("runtime_exit_stalled", True), ("runtime_exit_failure_stalled", False)),
)
def test_closed_tombstone_waits_for_runtime_exit_result_and_commits_atomically(
    mcp_harness: McpHarness,
    mode: str,
    exit_succeeds: bool,
) -> None:
    async def scenario() -> None:
        results: list[CallToolResult] = []
        async with Client(
            mcp_harness.parameters(
                mode=mode,
                environment={"ACA_TEST_HANDLES": json.dumps(["a" * 32])},
            )
        ) as client:
            await _open(client)

            async def closing() -> None:
                results.append(
                    await client.call_tool(
                        TOOL_NAMES[5], _request(session_handle=_HANDLE_A)
                    )
                )

            async with anyio.create_task_group() as group:
                group.start_soon(closing)
                await _wait_for_event(mcp_harness, "runtime_connect_exit_entered")
                names = _event_names(mcp_harness)
                assert names.count("session_quit") == 1
                assert names.count("session_delete") == 1
                assert names.count("runtime_connect_exit") == 0
                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=_HANDLE_A)
                    )
                )
                assert status["data"]["session_state"] == "closing"
                assert status["data"]["busy"] is True
                overlapping = _error(
                    await client.call_tool(
                        TOOL_NAMES[5], _request(session_handle=_HANDLE_A)
                    )
                )
                assert overlapping["code"] == "session_busy"
                assert overlapping["request_state"] == "not_sent"
                assert overlapping["session_handle"] == _HANDLE_A
                assert overlapping["session_state"] == "closing"
                blocked_open = _error(
                    await client.call_tool(
                        TOOL_NAMES[3], _request(device_id="blocked-device")
                    )
                )
                assert blocked_open["code"] == "session_capacity_reached"
                blocked_runtime = _error(
                    await client.call_tool(
                        TOOL_NAMES[1],
                        _request(mode="static", timeout_seconds=10.0),
                    )
                )
                assert blocked_runtime["code"] == "runtime_scope_active"
                assert _event_names(mcp_harness).count("runtime_diagnose") == 0
                mcp_harness.release_file.touch()

            if exit_succeeds:
                closed = _structured(results[0])
                assert closed["data"]["session_state"] == "closed"
                replacement = await _open(client, device_id="replacement-device")
                await _close(client, replacement["data"]["session_handle"])
            else:
                failure = _error(results[0])
                assert failure["code"] == "cleanup_failed"
                assert failure["session_handle"] == _HANDLE_A
                assert failure["session_state"] == "closed"
                assert (await _close(client, _HANDLE_A))["data"]["session_state"] == (
                    "closed"
                )
                blocked_open = _error(
                    await client.call_tool(
                        TOOL_NAMES[3], _request(device_id="replacement-device")
                    )
                )
                assert blocked_open["code"] == "session_capacity_reached"
                blocked_runtime = _error(
                    await client.call_tool(
                        TOOL_NAMES[1],
                        _request(mode="static", timeout_seconds=10.0),
                    )
                )
                assert blocked_runtime["code"] == "runtime_scope_active"

    anyio.run(scenario)
    names = _event_names(mcp_harness)
    expected = 2 if exit_succeeds else 1
    assert names.count("session_quit") == expected
    assert names.count("session_delete") == expected
    assert names.count("runtime_connect_exit_entered") == expected
    assert names.count("runtime_connect_exit") == expected
    stopped = next(
        event for event in mcp_harness.events() if event["event"] == "server_stopped"
    )
    assert stopped["result"] == (0 if exit_succeeds else 4)
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (CANARY, SECRET_PATH, "appium-", "automation-", "Traceback"):
        assert forbidden not in stderr


def test_eight_handle_collisions_fail_before_runtime_or_automation(
    mcp_harness: McpHarness,
) -> None:
    forced = ["a" * 32] * 9

    async def scenario() -> None:
        async with Client(
            mcp_harness.parameters(
                mode="session_normal",
                environment={"ACA_TEST_HANDLES": json.dumps(forced)},
            )
        ) as client:
            first = await _open(client)
            await _close(client, first["data"]["session_handle"])
            failure = _error(
                await client.call_tool(TOOL_NAMES[3], _request(device_id="second"))
            )
            assert failure["code"] == "handle_generation_failed"
            assert failure["request_state"] == "not_sent"
            assert failure["session_handle"] is None
            assert failure["session_state"] is None

    anyio.run(scenario)
    names = _event_names(mcp_harness)
    assert names.count("runtime_connect_enter") == 1
    assert names.count("create_session") == 1


def test_tombstones_are_256_fifo_and_reads_do_not_refresh_order(
    mcp_harness: McpHarness,
) -> None:
    tokens = [f"{index:032x}" for index in range(257)]

    async def scenario() -> None:
        async with Client(
            mcp_harness.parameters(
                mode="session_normal",
                environment={"ACA_TEST_HANDLES": json.dumps(tokens)},
            )
        ) as client:
            handles: list[str] = []
            for index in range(256):
                opened = await _open(client, device_id=f"device-{index}")
                handle = opened["data"]["session_handle"]
                handles.append(handle)
                await _close(client, handle)
            for _ in range(3):
                assert (
                    _structured(
                        await client.call_tool(
                            TOOL_NAMES[4], _request(session_handle=handles[0])
                        )
                    )["data"]["session_state"]
                    == "closed"
                )
                await _close(client, handles[0])
            final = await _open(client, device_id="device-256")
            await _close(client, final["data"]["session_handle"])
            evicted = _error(
                await client.call_tool(
                    TOOL_NAMES[4], _request(session_handle=handles[0])
                )
            )
            assert evicted["code"] == "session_not_found"
            assert (
                _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handles[1])
                    )
                )["data"]["session_state"]
                == "closed"
            )

    anyio.run(scenario)


@pytest.mark.parametrize(
    (
        "mode",
        "expected_code",
        "expected_handle",
        "expected_state",
        "request_state",
        "cleanup_count",
    ),
    (
        ("open_known", "session_not_created", False, None, "response_received", 0),
        ("open_not_sent", "operation_cancelled", False, None, "not_sent", 0),
        (
            "open_unknown",
            "session_create_unknown",
            True,
            "uncertain",
            "response_unknown",
            0,
        ),
        (
            "open_retained_not_sent",
            "cleanup_failed",
            True,
            "uncertain",
            "not_sent",
            1,
        ),
    ),
)
def test_open_error_resource_matrix_and_uncertain_quarantine(
    mcp_harness: McpHarness,
    mode: str,
    expected_code: str,
    expected_handle: bool,
    expected_state: str | None,
    request_state: str,
    cleanup_count: int,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode=mode)) as client:
            failure = _error(
                await client.call_tool(
                    TOOL_NAMES[3], _request(device_id="secret-device")
                )
            )
            assert failure["code"] == expected_code
            assert (failure["session_handle"] is not None) is expected_handle
            assert failure["session_state"] == expected_state
            assert failure["request_state"] == request_state
            assert failure["cleanup_error_count"] == cleanup_count
            if expected_handle:
                handle = failure["session_handle"]
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
                assert close["session_handle"] == handle
                assert close["session_state"] == "uncertain"
                capacity = _error(
                    await client.call_tool(
                        TOOL_NAMES[3], _request(device_id="replacement")
                    )
                )
                assert capacity["code"] == "session_capacity_reached"

    anyio.run(scenario)
    names = _event_names(mcp_harness)
    assert names.count("create_session") == 1
    assert names.count("session_quit") == 0
    combined = (
        mcp_harness.stderr_file.read_text(encoding="utf-8")
        if mcp_harness.stderr_file.exists()
        else ""
    )
    for forbidden in (
        CANARY,
        SECRET_PATH,
        "secret-device",
        _HANDLE_A,
        "Traceback",
    ):
        assert forbidden not in combined


def test_owner_enter_exit_same_thread_and_cross_phase_budget_decreases(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            opened = await _open(client, timeout_seconds=180)
            await _close(client, opened["data"]["session_handle"], timeout_seconds=60)

    anyio.run(scenario)
    events = mcp_harness.events()
    entered = next(
        event for event in events if event["event"] == "runtime_connect_enter"
    )
    created = next(event for event in events if event["event"] == "create_session")
    exited = next(event for event in events if event["event"] == "runtime_connect_exit")
    quit_event = next(event for event in events if event["event"] == "session_quit")
    assert entered["thread"] == exited["thread"]
    assert 0 < created["timeout"] < entered["timeout"] < 180
    assert 0 < quit_event["timeout"] < 60
    assert entered["has_cancellation"] is True
    assert created["has_cancellation"] is True
    assert quit_event["has_cancellation"] is True


@pytest.mark.parametrize(
    ("mode", "tool_index"),
    (("open_stalled", 3), ("close_stalled", 5)),
)
def test_cancel_wait_commits_late_success_once_without_replay(
    mcp_harness: McpHarness,
    mode: str,
    tool_index: int,
) -> None:
    async def scenario() -> None:
        async with Client(
            mcp_harness.parameters(
                mode=mode,
                environment={"ACA_TEST_HANDLES": json.dumps(["a" * 32])},
            )
        ) as client:
            if tool_index == 5:
                opened = await _open(client)
                assert opened["data"]["session_handle"] == _HANDLE_A
            returned_baseline = sum(
                event["event"] == "worker_returned" and event["outcome"] == "success"
                for event in mcp_harness.events()
            )

            scopes: list[anyio.CancelScope] = []

            async def lifecycle() -> None:
                with anyio.CancelScope() as scope:
                    scopes.append(scope)
                    if tool_index == 3:
                        await client.call_tool(
                            TOOL_NAMES[3], _request(device_id="device")
                        )
                    else:
                        await client.call_tool(
                            TOOL_NAMES[5], _request(session_handle=_HANDLE_A)
                        )

            async with anyio.create_task_group() as group:
                group.start_soon(lifecycle)
                with anyio.fail_after(2):
                    while "worker_entered" not in _event_names(mcp_harness):
                        await anyio.sleep(0.001)
                assert len(scopes) == 1
                scopes[0].cancel()
                with anyio.fail_after(2):
                    while "worker_cancel_observed" not in _event_names(mcp_harness):
                        await anyio.sleep(0.001)
                mcp_harness.release_file.touch()
                with anyio.fail_after(2):
                    while (
                        sum(
                            event["event"] == "worker_returned"
                            and event["outcome"] == "success"
                            for event in mcp_harness.events()
                        )
                        <= returned_baseline
                    ):
                        await anyio.sleep(0.001)

            status = _structured(
                await client.call_tool(
                    TOOL_NAMES[4], _request(session_handle=_HANDLE_A)
                )
            )
            expected = "active" if tool_index == 3 else "closed"
            assert status["data"]["session_state"] == expected
            if tool_index == 3:
                await _close(client, _HANDLE_A)

    anyio.run(scenario)
    events = mcp_harness.events()
    cancelled = next(
        event for event in events if event["event"] == "worker_cancel_observed"
    )
    assert cancelled["cancelled"] is True
    assert (
        _event_names(mcp_harness).count(
            "create_session" if tool_index == 3 else "session_quit"
        )
        == 1
    )


@pytest.mark.parametrize(
    ("mode", "code", "state", "request_state", "cleanup_count"),
    (
        ("close_known", "session_quit_failed", "active", "response_received", 0),
        ("close_not_sent", "operation_cancelled", "active", "not_sent", 0),
        ("close_unknown", "session_close_unknown", "uncertain", "response_unknown", 0),
        ("close_cleanup_failed", "cleanup_failed", "uncertain", "response_unknown", 1),
    ),
)
def test_close_error_resource_matrix_retains_explicit_handle(
    mcp_harness: McpHarness,
    mode: str,
    code: str,
    state: str,
    request_state: str,
    cleanup_count: int,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode=mode)) as client:
            opened = await _open(client)
            handle = opened["data"]["session_handle"]
            failure = _error(
                await client.call_tool(TOOL_NAMES[5], _request(session_handle=handle))
            )
            assert failure["code"] == code
            assert failure["session_handle"] == handle
            assert failure["session_state"] == state
            assert failure["request_state"] == request_state
            assert failure["cleanup_error_count"] == cleanup_count
            status = _structured(
                await client.call_tool(TOOL_NAMES[4], _request(session_handle=handle))
            )
            assert status["data"]["session_state"] == state
            if state == "uncertain":
                repeated = _error(
                    await client.call_tool(
                        TOOL_NAMES[5], _request(session_handle=handle)
                    )
                )
                assert repeated["code"] == "session_uncertain"

    anyio.run(scenario)
    expected_quits = 2 if state == "active" else 1
    assert _event_names(mcp_harness).count("session_quit") == expected_quits


def test_closed_runtime_cleanup_failure_is_sticky_and_never_retried(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        async with Client(
            mcp_harness.parameters(mode="runtime_exit_failure")
        ) as client:
            opened = await _open(client)
            handle = opened["data"]["session_handle"]
            failure = _error(
                await client.call_tool(TOOL_NAMES[5], _request(session_handle=handle))
            )
            assert failure["code"] == "cleanup_failed"
            assert failure["session_handle"] == handle
            assert failure["session_state"] == "closed"
            assert (await _close(client, handle))["data"]["session_state"] == "closed"
            blocked = _error(
                await client.call_tool(TOOL_NAMES[3], _request(device_id="replacement"))
            )
            assert blocked["code"] == "session_capacity_reached"
            runtime = _error(
                await client.call_tool(
                    TOOL_NAMES[1], _request(mode="static", timeout_seconds=10.0)
                )
            )
            assert runtime["code"] == "runtime_scope_active"

    anyio.run(scenario)
    names = _event_names(mcp_harness)
    assert names.count("session_quit") == 1
    assert names.count("runtime_connect_exit") == 1
    assert names.count("session_delete") == 1
    stopped = next(
        event for event in mcp_harness.events() if event["event"] == "server_stopped"
    )
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (CANARY, SECRET_PATH, "appium-", "automation-", "Traceback"):
        assert forbidden not in stderr
    assert stopped["result"] == 4


@pytest.mark.parametrize(
    ("mode", "expected_quit", "expected_delete", "expected_exit"),
    (
        ("shutdown_active", 1, 1, 0),
        ("shutdown_close_cancelled", 1, 0, 4),
        ("shutdown_close_timeout", 1, 0, 4),
        ("shutdown_close_known", 1, 1, 4),
        ("shutdown_close_unknown", 1, 1, 4),
        ("shutdown_close_cleanup_failed", 1, 1, 4),
        ("open_unknown", 0, 0, 4),
    ),
)
def test_shutdown_active_failure_and_uncertain_table(
    mcp_harness: McpHarness,
    mode: str,
    expected_quit: int,
    expected_delete: int,
    expected_exit: int,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode=mode)) as client:
            result = await client.call_tool(
                TOOL_NAMES[3], _request(device_id="shutdown-device")
            )
            if mode == "open_unknown":
                assert _error(result)["session_state"] == "uncertain"
            else:
                assert _structured(result)["data"]["session_state"] == "active"

    anyio.run(scenario)
    names = _event_names(mcp_harness)
    assert names.count("session_quit") == expected_quit
    assert names.count("session_delete") == expected_delete
    assert names.count("runtime_connect_exit") == 1
    stopped = next(
        event for event in mcp_harness.events() if event["event"] == "server_stopped"
    )
    assert stopped["result"] == expected_exit
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (
        "shutdown-device",
        CANARY,
        SECRET_PATH,
        "appium-",
        "automation-",
        "Traceback",
    ):
        assert forbidden not in stderr


@pytest.mark.parametrize(
    ("mode", "expected_quit", "expected_owner_exit"),
    (
        ("shutdown_provisional_invariant", 0, 0),
        ("shutdown_closing_invariant", 1, 1),
    ),
)
def test_shutdown_provisional_and_closing_invariants_are_degraded_without_retry(
    mcp_harness: McpHarness,
    mode: str,
    expected_quit: int,
    expected_owner_exit: int,
) -> None:
    async def scenario() -> None:
        async with Client(
            mcp_harness.parameters(
                mode=mode,
                environment={"ACA_TEST_HANDLES": json.dumps(["a" * 32])},
            )
        ) as client:
            opened = await client.call_tool(
                TOOL_NAMES[3], _request(device_id="invariant-device")
            )
            if mode == "shutdown_provisional_invariant":
                assert opened.is_error is True
                assert opened.structured_content is None
                return
            assert _structured(opened)["data"]["session_state"] == "active"
            failed_close = await client.call_tool(
                TOOL_NAMES[5], _request(session_handle=_HANDLE_A)
            )
            assert failed_close.is_error is True
            assert failed_close.structured_content is None
            status = _structured(
                await client.call_tool(
                    TOOL_NAMES[4], _request(session_handle=_HANDLE_A)
                )
            )
            assert status["data"]["session_state"] == "closing"
            assert status["data"]["busy"] is True

    anyio.run(scenario)
    names = _event_names(mcp_harness)
    assert names.count("session_quit") == expected_quit
    assert names.count("session_delete") == 0
    assert names.count("runtime_connect_exit") == expected_owner_exit
    stopped = next(
        event for event in mcp_harness.events() if event["event"] == "server_stopped"
    )
    assert stopped["result"] == 4
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (
        "invariant-device",
        CANARY,
        SECRET_PATH,
        "appium-",
        "automation-",
        "Traceback",
    ):
        assert forbidden not in stderr


def test_locked_client_stdio_to_temporary_http_primary_and_replacement(
    mcp_harness: McpHarness,
) -> None:
    apk = mcp_harness.root / "controlled.apk"
    apk.write_bytes(b"not parsed")
    with ProtocolService() as service:
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                first = await _open(
                    client,
                    device_id="controlled-a",
                    app_id="org.example.primary",
                    app_path=str(apk),
                    auto_launch=True,
                    force_app_launch=True,
                    should_terminate_app=True,
                    new_command_timeout_seconds=0,
                )
                first_handle = first["data"]["session_handle"]
                assert (
                    _structured(
                        await client.call_tool(
                            TOOL_NAMES[4], _request(session_handle=first_handle)
                        )
                    )["data"]["session_state"]
                    == "active"
                )
                await _close(client, first_handle)
                replacement = await _open(client, device_id="controlled-b")
                assert replacement["data"]["session_handle"] != first_handle
                await _close(client, replacement["data"]["session_handle"])

        anyio.run(scenario)

    lifecycle = service.lifecycle_requests()
    assert [request.method for request in lifecycle] == [
        "POST",
        "DELETE",
        "POST",
        "DELETE",
    ]
    assert [request.path for request in lifecycle] == [
        "/wd/hub/session",
        "/wd/hub/session/session-1",
        "/wd/hub/session",
        "/wd/hub/session/session-2",
    ]
    first_caps = appium_caps(lifecycle[0])
    assert first_caps == {
        "platformName": "Android",
        "appium:automationName": "UiAutomator2",
        "appium:udid": "controlled-a",
        "appium:autoLaunch": True,
        "appium:forceAppLaunch": True,
        "appium:noReset": True,
        "appium:fullReset": False,
        "appium:shouldTerminateApp": True,
        "appium:newCommandTimeout": 0.0,
        "appium:systemPort": 8200,
        "appium:settings[enableMultiWindows]": True,
        "appium:appPackage": "org.example.primary",
        "appium:app": str(apk),
    }
    second_caps = appium_caps(lifecycle[2])
    assert second_caps["appium:udid"] == "controlled-b"
    assert second_caps["appium:noReset"] is True
    assert second_caps["appium:fullReset"] is False
