from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from typing import Any, Literal, cast

import anyio
import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, Tool
from pydantic import BaseModel, ValidationError

from appium_connect_agent.automation import CommandError, DeviceInfo
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations import _application
from appium_connect_agent.integrations._application import McpApplication
from appium_connect_agent.integrations._models import (
    CapabilityResult,
    DeviceListResult,
    RuntimeCheckResult,
    SessionCloseResult,
    SessionData,
    SessionOpenResult,
    SessionStatusResult,
    ToolErrorData,
    canonical_json,
)
from appium_connect_agent.runtime import OperationControl

from .conftest import (
    AUTOMATION_STATUS,
    CANARY,
    SECRET_PATH,
    TOOL_NAMES,
    McpHarness,
)

CALL_ID = re.compile(r"^c_[A-Za-z0-9_-]{22}$")
SCHEMA_BUNDLE_SHA256 = (
    "dd8e6064dc44aceb3c2c456a61f81dc31f519e6902377c7852f3c0a7fc94a1e6"
)
CAPABILITY_MAX_CANONICAL_BYTES = 3037
RUNTIME_MAX_CANONICAL_BYTES = 622_071
DEVICE_MAX_CANONICAL_BYTES = 2_112_668
SESSION_OPEN_MAX_CANONICAL_BYTES = 5601
SESSION_STATUS_MAX_CANONICAL_BYTES = 5604
SESSION_CLOSE_MAX_CANONICAL_BYTES = 5601
ERROR_MAX_CANONICAL_BYTES = 6835
ERROR_WIRE_BYTES = {
    TOOL_NAMES[0]: 6852,
    TOOL_NAMES[1]: 6849,
    TOOL_NAMES[2]: 6848,
    TOOL_NAMES[3]: 6887,
    TOOL_NAMES[4]: 6889,
    TOOL_NAMES[5]: 6888,
}


def canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    value = getattr(result.content[0], "text", None)
    assert type(value) is str
    return value


def structured(result: CallToolResult) -> dict[str, Any]:
    assert result.is_error is False
    assert type(result.structured_content) is dict
    value = result.structured_content
    assert text(result) == canonical(value)
    return cast(dict[str, Any], value)


def without_call_id(value: dict[str, Any]) -> dict[str, Any]:
    copied = dict(value)
    call_id = copied.pop("call_id")
    assert type(call_id) is str and CALL_ID.fullmatch(call_id)
    return copied


def schema_target(root: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in value:
        reference = value["$ref"]
        assert type(reference) is str and reference.startswith("#/")
        current: Any = root
        for component in reference[2:].split("/"):
            current = current[component.replace("~1", "/").replace("~0", "~")]
        assert type(current) is dict
        value = cast(dict[str, Any], current)
    return value


def assert_closed_objects(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
        for child in value.values():
            assert_closed_objects(child)
    elif isinstance(value, list):
        for child in value:
            assert_closed_objects(child)


def schema_fingerprint(tools: list[Tool]) -> str:
    bundle = [
        tool.model_dump(mode="json", by_alias=True, exclude_none=False)
        for tool in tools
    ]
    return hashlib.sha256(canonical(bundle).encode()).hexdigest()


def maximum_codes(prefix: str, count: int) -> list[str]:
    return [(prefix * 124) + f"{index:04d}" for index in range(count)]


def with_maximum_warnings(value: dict[str, Any]) -> dict[str, Any]:
    copied = cast(dict[str, Any], json.loads(canonical(value)))
    copied["warnings"] = maximum_codes("w", 16)
    return copied


def product_result(model: BaseModel) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=canonical_json(model))],
        structured_content=model.model_dump(mode="python"),
        is_error=False,
    )


def maximum_error_value(*, retained: bool = True) -> ToolErrorData:
    return ToolErrorData(
        schema_version=1,
        call_id="c_" + ("a" * 22),
        code="c" * 128,
        operation_id="o" * 128,
        request_state="response_received",
        completed_steps=tuple(maximum_codes("s", 32)),
        cleanup_status="not_needed",
        cleanup_error_count=32,
        warnings=tuple(maximum_codes("w", 16)),
        session_handle="s_" + ("a" * 32) if retained else None,
        session_state="uncertain" if retained else None,
    )


def assert_remaining_budget(value: object, requested: float) -> None:
    assert type(value) is float
    assert 0.0 < value < requested


def maximum_session_results() -> tuple[
    SessionOpenResult, SessionStatusResult, SessionCloseResult
]:
    common: dict[str, object] = {
        "schema_version": 1,
        "call_id": "c_" + ("a" * 22),
        "execution": "completed",
        "operation_id": None,
        "request_state": None,
        "warnings": (),
        "automation_module_status": AUTOMATION_STATUS,
    }

    def data(
        state: Literal["active", "uncertain", "closing", "closed"],
    ) -> SessionData:
        return SessionData(
            ownership="mcp",
            session_handle="s_" + ("a" * 32),
            session_state=state,
            device_id="\U00010000" * 1024,
            target_app_id="\U00010000" * 255,
            busy=False,
        )

    return (
        SessionOpenResult.model_validate({**common, "data": data("active")}),
        SessionStatusResult.model_validate({**common, "data": data("uncertain")}),
        SessionCloseResult.model_validate({**common, "data": data("closed")}),
    )


async def wait_for_worker(harness: McpHarness, call_index: int) -> None:
    with anyio.fail_after(2):
        while not any(
            event["event"] == "worker_entered" and event.get("call_index") == call_index
            for event in harness.events()
        ):
            await anyio.sleep(0.001)


def assert_common(value: dict[str, Any], operation_id: str | None) -> None:
    assert value["schema_version"] == 1
    assert CALL_ID.fullmatch(value["call_id"])
    assert value["execution"] == "completed"
    assert value["operation_id"] == operation_id
    assert value["request_state"] is None
    assert value["warnings"] == []
    assert value["automation_module_status"] == AUTOMATION_STATUS


def test_tools_list_is_fixed_and_schemas_express_the_contract(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters()) as client:
            assert client.protocol_version == "2026-07-28"
            first = (await client.list_tools()).tools
            second = (await client.list_tools()).tools

        assert tuple(tool.name for tool in first) == TOOL_NAMES
        digest = schema_fingerprint(first)
        assert digest == schema_fingerprint(second)
        assert digest == SCHEMA_BUNDLE_SHA256

        request_fields = {
            TOOL_NAMES[0]: {"schema_version"},
            TOOL_NAMES[1]: {"schema_version", "mode", "timeout_seconds"},
            TOOL_NAMES[2]: {"schema_version", "timeout_seconds"},
            TOOL_NAMES[3]: {
                "schema_version",
                "device_id",
                "app_id",
                "app_path",
                "auto_launch",
                "force_app_launch",
                "should_terminate_app",
                "new_command_timeout_seconds",
                "timeout_seconds",
            },
            TOOL_NAMES[4]: {"schema_version", "session_handle"},
            TOOL_NAMES[5]: {"schema_version", "session_handle", "timeout_seconds"},
        }
        session_fields = {
            "ownership",
            "session_handle",
            "session_state",
            "device_id",
            "target_app_id",
            "busy",
        }
        result_data_fields = {
            TOOL_NAMES[0]: {
                "integration_form",
                "transport",
                "protocol_target",
                "host_compatibility",
                "adb_configured",
                "platform",
                "tools",
                "limitations",
            },
            TOOL_NAMES[1]: {"mode", "report", "connection"},
            TOOL_NAMES[2]: {"count", "devices"},
            TOOL_NAMES[3]: session_fields,
            TOOL_NAMES[4]: session_fields,
            TOOL_NAMES[5]: session_fields,
        }
        for tool in first:
            input_schema = tool.input_schema
            assert input_schema["type"] == "object"
            assert input_schema["required"] == ["request"]
            request_schema = schema_target(
                input_schema, input_schema["properties"]["request"]
            )
            assert request_schema["type"] == "object"
            assert request_schema["additionalProperties"] is False
            assert_closed_objects(request_schema)
            assert set(request_schema["properties"]) == request_fields[tool.name]
            assert request_schema["properties"]["schema_version"]["const"] == 1

            output_schema = tool.output_schema
            assert output_schema is not None
            output_root = schema_target(output_schema, output_schema)
            assert output_root["type"] == "object"
            assert output_root["additionalProperties"] is False
            assert_closed_objects(output_schema)
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
            call_id_schema = schema_target(
                output_schema, output_root["properties"]["call_id"]
            )
            assert call_id_schema["pattern"] == r"^c_[A-Za-z0-9_-]{22}$"
            warnings_schema = schema_target(
                output_schema, output_root["properties"]["warnings"]
            )
            assert warnings_schema["maxItems"] == 16
            data_schema = schema_target(
                output_schema, output_root["properties"]["data"]
            )
            assert set(data_schema["properties"]) == result_data_fields[tool.name]

        runtime_request = schema_target(
            first[1].input_schema,
            first[1].input_schema["properties"]["request"],
        )
        runtime_timeout = runtime_request["properties"]["timeout_seconds"]
        assert runtime_timeout["default"] == 10.0
        assert runtime_timeout["exclusiveMinimum"] == 0.0
        assert runtime_timeout["maximum"] == 60.0
        assert set(runtime_request["properties"]["mode"]["enum"]) == {
            "static",
            "external_connection",
        }

        device_request = schema_target(
            first[2].input_schema,
            first[2].input_schema["properties"]["request"],
        )
        assert device_request["properties"]["timeout_seconds"]["default"] == 30.0

    anyio.run(scenario)


def test_capabilities_object_and_json_object_string_are_equivalent_and_zero_io(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters()) as client:
            object_result = await client.call_tool(
                TOOL_NAMES[0], {"request": {"schema_version": 1}}
            )
            string_result = await client.call_tool(
                TOOL_NAMES[0], {"request": '{"schema_version":1}'}
            )
        left = without_call_id(structured(object_result))
        right = without_call_id(structured(string_result))
        assert (
            object_result.structured_content["call_id"]
            != (string_result.structured_content["call_id"])
        )
        assert left == right
        assert left == {
            "schema_version": 1,
            "execution": "completed",
            "operation_id": None,
            "request_state": None,
            "warnings": [],
            "automation_module_status": AUTOMATION_STATUS,
            "data": {
                "integration_form": "mcp",
                "transport": "stdio",
                "protocol_target": "2026-07-28",
                "host_compatibility": "unqualified",
                "adb_configured": True,
                "platform": {
                    "host": "macos",
                    "target": "android_native",
                    "driver": "uiautomator2",
                },
                "tools": list(TOOL_NAMES),
                "limitations": [
                    "no_ui_tools",
                    "single_session_capacity",
                    "opaque_handle_process_local",
                    "no_session_attach_recovery",
                    "no_cli_sdk_product",
                    "no_http_transport",
                    "no_clear_app",
                    "automation_module_e2e_unqualified",
                    "no_specific_host_qualification",
                ],
            },
        }

    anyio.run(scenario)
    assert mcp_harness.events() == []


def test_device_object_and_json_object_string_preserve_identical_lower_behavior(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters()) as client:
            object_result = await client.call_tool(
                TOOL_NAMES[2],
                {"request": {"schema_version": 1, "timeout_seconds": 60.0}},
            )
            string_result = await client.call_tool(
                TOOL_NAMES[2],
                {"request": '{"schema_version":1,"timeout_seconds":60.0}'},
            )
        assert without_call_id(structured(object_result)) == without_call_id(
            structured(string_result)
        )

    anyio.run(scenario)
    calls = [
        event for event in mcp_harness.events() if event["event"] == "list_devices"
    ]
    assert len(calls) == 2
    for call in calls:
        assert_remaining_budget(call["timeout"], 60.0)


def test_outer_extra_is_ignored_but_cannot_replace_request(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters()) as client:
            accepted = await client.call_tool(
                TOOL_NAMES[2],
                {
                    "request": {"schema_version": 1, "timeout_seconds": 7.0},
                    "timeout_seconds": 59.0,
                    "extra": {"adb_executable": SECRET_PATH},
                },
            )
            missing = await client.call_tool(TOOL_NAMES[2], {"timeout_seconds": 7.0})
        assert structured(accepted)["data"]["count"] == 2
        assert missing.is_error is True
        assert missing.structured_content is None

    anyio.run(scenario)
    calls = [
        event for event in mcp_harness.events() if event["event"] == "list_devices"
    ]
    assert len(calls) == 1
    assert_remaining_budget(calls[0]["timeout"], 7.0)


def test_runtime_and_devices_delegate_once_with_one_finite_control(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        async with Client(mcp_harness.parameters()) as client:
            static_result = await client.call_tool(
                TOOL_NAMES[1],
                {
                    "request": {
                        "schema_version": 1,
                        "mode": "static",
                        "timeout_seconds": 4.5,
                    }
                },
            )
            external_result = await client.call_tool(
                TOOL_NAMES[1],
                {
                    "request": {
                        "schema_version": 1,
                        "mode": "external_connection",
                        "timeout_seconds": 5.5,
                    }
                },
            )
            device_result = await client.call_tool(
                TOOL_NAMES[2],
                {"request": {"schema_version": 1, "timeout_seconds": 6.5}},
            )

        static = structured(static_result)
        assert_common(static, "op_runtime_1")
        assert static["data"]["mode"] == "static"
        assert static["data"]["connection"] is None
        assert static["data"]["report"]["observed_at"].endswith("+00:00")

        external = structured(external_result)
        assert_common(external, "op_runtime_1")
        assert external["data"]["connection"] == {
            "ownership": "external",
            "appium_version": "3.7.0",
            "compatibility": "declared_compatible",
        }
        assert "server_url" not in canonical(external)

        devices = structured(device_result)
        assert_common(devices, None)
        assert devices["data"] == {
            "count": 2,
            "devices": [
                {"id": "alpha", "name": "Pixel_8", "connection_state": "connected"},
                {"id": "zeta", "name": None, "connection_state": "unauthorized"},
            ],
        }

    anyio.run(scenario)
    events = mcp_harness.events()
    assert [event["event"] for event in events] == [
        "runtime_diagnose",
        "runtime_connect",
        "runtime_connect_enter",
        "runtime_connect_exit",
        "list_devices",
    ]
    assert_remaining_budget(events[0]["timeout"], 4.5)
    assert_remaining_budget(events[1]["timeout"], 5.5)
    assert events[2]["timeout"] == events[1]["timeout"]
    assert "timeout" not in events[3]
    assert_remaining_budget(events[4]["timeout"], 6.5)
    assert all(
        event["has_cancellation"] is True
        for event in events
        if "has_cancellation" in event
    )
    assert events[-1]["adb"] == str(mcp_harness.adb)


def test_inner_strict_validation_rejects_before_every_lower_call(
    mcp_harness: McpHarness,
) -> None:
    cases: tuple[tuple[str, object], ...] = (
        (TOOL_NAMES[0], {}),
        (TOOL_NAMES[0], []),
        (TOOL_NAMES[1], {"schema_version": 1}),
        (TOOL_NAMES[2], {}),
        (TOOL_NAMES[0], {"schema_version": 1, "extra": True}),
        (TOOL_NAMES[0], {"schema_version": True}),
        (TOOL_NAMES[1], {"schema_version": 1, "mode": "STATIC"}),
        (
            TOOL_NAMES[1],
            {"schema_version": 1, "mode": "static", "timeout_seconds": "10"},
        ),
        (
            TOOL_NAMES[1],
            {"schema_version": 1, "mode": "static", "timeout_seconds": True},
        ),
        (
            TOOL_NAMES[1],
            {"schema_version": 1, "mode": "static", "timeout_seconds": 10},
        ),
        (
            TOOL_NAMES[1],
            {"schema_version": 1, "mode": "static", "timeout_seconds": float("nan")},
        ),
        (
            TOOL_NAMES[1],
            {"schema_version": 1, "mode": "static", "timeout_seconds": float("-inf")},
        ),
        (
            TOOL_NAMES[1],
            {"schema_version": 1, "mode": "static", "timeout_seconds": 0.0},
        ),
        (
            TOOL_NAMES[1],
            {"schema_version": 1, "mode": "static", "timeout_seconds": 60.0001},
        ),
        (TOOL_NAMES[1], '{"schema_version":1,"mode":"\\ud800"}'),
        (TOOL_NAMES[2], {"schema_version": 1, "timeout_seconds": "NaN"}),
        (TOOL_NAMES[2], {"schema_version": 1, "timeout_seconds": float("inf")}),
        (TOOL_NAMES[2], {"schema_version": 1, "timeout_seconds": 0.0}),
        (TOOL_NAMES[2], {"schema_version": 1, "adb_executable": SECRET_PATH}),
    )

    async def scenario() -> None:
        async with Client(mcp_harness.parameters()) as client:
            for name, request in cases:
                result = await client.call_tool(name, {"request": request})
                assert result.is_error is True
                assert result.structured_content is None

    anyio.run(scenario)
    assert mcp_harness.events() == []
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert SECRET_PATH not in stderr


def test_known_tool_error_is_canonical_bounded_and_sanitized(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> CallToolResult:
        async with Client(mcp_harness.parameters(mode="known")) as client:
            return await client.call_tool(
                TOOL_NAMES[2], {"request": {"schema_version": 1}}
            )

    result = anyio.run(scenario)
    assert result.is_error is True
    assert result.structured_content is None
    prefix = f"Error executing tool {TOOL_NAMES[2]}: ACA_ERROR "
    wire = text(result)
    assert wire.startswith(prefix)
    payload_text = wire.removeprefix(prefix)
    payload = json.loads(payload_text)
    assert payload_text == canonical(payload)
    assert CALL_ID.fullmatch(payload.pop("call_id"))
    assert payload == {
        "schema_version": 1,
        "code": "adb_command_failed",
        "operation_id": "op_devices_1",
        "request_state": "response_received",
        "completed_steps": ["adb_launched"],
        "cleanup_status": "failed",
        "cleanup_error_count": 1,
        "warnings": [],
        "session_handle": None,
        "session_state": None,
    }
    combined = wire + mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert CANARY not in combined
    assert SECRET_PATH not in combined
    assert "RuntimeError" not in combined
    assert str(mcp_harness.config) not in combined
    assert str(mcp_harness.adb) not in combined


def test_runtime_tool_error_has_null_request_state_and_sanitized_cleanup(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> CallToolResult:
        async with Client(mcp_harness.parameters(mode="runtime_known")) as client:
            return await client.call_tool(
                TOOL_NAMES[1],
                {"request": {"schema_version": 1, "mode": "static"}},
            )

    result = anyio.run(scenario)
    assert result.is_error is True
    assert result.structured_content is None
    payload_text = text(result).split("ACA_ERROR ", 1)[1]
    payload = json.loads(payload_text)
    assert payload_text == canonical(payload)
    minimum = ToolErrorData(
        schema_version=1,
        call_id="c_" + ("a" * 22),
        code="c",
        operation_id=None,
        request_state=None,
        completed_steps=(),
        cleanup_status="failed",
        cleanup_error_count=0,
        warnings=(),
        session_handle=None,
        session_state=None,
    )
    assert minimum.operation_id is None
    assert minimum.completed_steps == ()
    assert minimum.warnings == ()
    assert payload["code"] == "operation_timeout"
    assert payload["operation_id"] == "op_runtime_1"
    assert payload["request_state"] is None
    assert payload["completed_steps"] == []
    assert payload["cleanup_status"] == "failed"
    assert payload["cleanup_error_count"] == 1
    combined = text(result) + mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert CANARY not in combined
    assert SECRET_PATH not in combined
    assert str(mcp_harness.config) not in combined
    assert str(mcp_harness.adb) not in combined


def test_error_field_and_array_boundaries_and_exact_wire() -> None:
    maximum = maximum_error_value()
    payload = canonical_json(maximum)
    assert len(payload.encode()) == ERROR_MAX_CANONICAL_BYTES

    valid = maximum.model_dump(mode="python")
    invalid_values: list[dict[str, Any]] = []
    for field, value in (
        ("schema_version", True),
        ("call_id", "c_" + ("a" * 21)),
        ("call_id", "c_" + ("a" * 23)),
        ("call_id", "c_" + ("!" * 22)),
        ("call_id", "c_" + ("a" * 21) + "\ud800"),
        ("call_id", True),
        ("code", ""),
        ("code", "c" * 129),
        ("code", "INVALID"),
        ("code", "c" * 127 + "\ud800"),
        ("code", True),
        ("operation_id", ""),
        ("operation_id", "o" * 129),
        ("operation_id", "invalid operation"),
        ("operation_id", "o" * 127 + "\ud800"),
        ("operation_id", True),
        ("request_state", "sent"),
        ("request_state", True),
        ("cleanup_status", "clean"),
        ("cleanup_status", True),
        ("cleanup_error_count", -1),
        ("cleanup_error_count", 33),
        ("session_handle", ""),
        ("session_handle", "s_" + "a" * 31),
        ("session_handle", "s_" + "a" * 33),
        ("session_handle", "s_" + "!" * 32),
        ("session_handle", "s_" + "a" * 31 + "\ud800"),
        ("session_handle", True),
        ("session_state", "creating"),
        ("session_state", True),
        ("cleanup_error_count", True),
    ):
        invalid = copy.deepcopy(valid)
        invalid[field] = value
        invalid_values.append(invalid)
    for field, prefix in (("completed_steps", "s"), ("warnings", "w")):
        original = cast(tuple[str, ...], valid[field])
        for values in (
            (*original, prefix * 128),
            (*original[:-1], original[0]),
            ("", *original[1:]),
            (prefix * 129, *original[1:]),
            ("INVALID", *original[1:]),
            (prefix * 127 + "\ud800", *original[1:]),
            (True, *original[1:]),
        ):
            invalid = copy.deepcopy(valid)
            invalid[field] = values
            invalid_values.append(invalid)
    resource_pairs: tuple[tuple[object, object], ...] = (
        (None, "uncertain"),
        ("s_" + "a" * 32, None),
    )
    for session_handle, session_state in resource_pairs:
        invalid = copy.deepcopy(valid)
        invalid["session_handle"] = session_handle
        invalid["session_state"] = session_state
        invalid_values.append(invalid)
    for invalid in invalid_values:
        with pytest.raises(ValidationError):
            ToolErrorData.model_validate(invalid)

    async def wire(tool_name: str, wire_payload: str) -> CallToolResult:
        server = MCPServer[None](f"error-wire-{tool_name}")

        @server.tool(name=tool_name)
        async def fail() -> None:
            raise ToolError(f"ACA_ERROR {wire_payload}")

        async with Client(server) as client:
            return await client.call_tool(tool_name, {})

    for tool_index, tool_name in enumerate(TOOL_NAMES):
        wire_value = maximum_error_value(retained=tool_index >= 3)
        wire_payload = canonical_json(wire_value)
        result = anyio.run(wire, tool_name, wire_payload)
        assert result.is_error is True
        assert result.structured_content is None
        expected = f"Error executing tool {tool_name}: ACA_ERROR {wire_payload}"
        assert text(result) == expected
        assert len(expected.encode()) == ERROR_WIRE_BYTES[tool_name]


def test_unknown_exception_has_fixed_client_and_sdk_log_canaries(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> CallToolResult:
        async with Client(mcp_harness.parameters(mode="unknown")) as client:
            return await client.call_tool(
                TOOL_NAMES[2], {"request": {"schema_version": 1}}
            )

    result = anyio.run(scenario)
    assert result.is_error is True
    assert result.structured_content is None
    assert text(result) == f"Error executing tool {TOOL_NAMES[2]}"
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    assert "mcp_sdk_internal_error" in stderr
    for forbidden in (
        CANARY,
        SECRET_PATH,
        str(mcp_harness.config),
        str(mcp_harness.adb),
        "RuntimeError",
        "Traceback",
    ):
        assert forbidden not in text(result)
        assert forbidden not in stderr


def test_response_unknown_and_timeout_are_not_replayed(
    mcp_harness: McpHarness,
) -> None:
    async def call(mode: str, timeout: float) -> CallToolResult:
        mcp_harness.reset_records()
        async with Client(mcp_harness.parameters(mode=mode)) as client:
            result = await client.call_tool(
                TOOL_NAMES[2],
                {"request": {"schema_version": 1, "timeout_seconds": timeout}},
            )
        assert result.is_error is True
        calls = [
            event for event in mcp_harness.events() if event["event"] == "list_devices"
        ]
        assert len(calls) == 1
        return result

    unknown = anyio.run(call, "response_unknown", 3.0)
    timeout = anyio.run(call, "timeout", 0.05)
    assert json.loads(text(unknown).split("ACA_ERROR ", 1)[1])["request_state"] == (
        "response_unknown"
    )
    assert json.loads(text(timeout).split("ACA_ERROR ", 1)[1])["code"] == (
        "operation_timeout"
    )


def test_limiter_queue_exhausts_handler_budget_before_lower_call(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> CallToolResult:
        async with Client(mcp_harness.parameters(mode="limiter_timeout")) as client:
            return await client.call_tool(
                TOOL_NAMES[2],
                {"request": {"schema_version": 1, "timeout_seconds": 0.05}},
            )

    result = anyio.run(scenario)
    assert result.is_error is True
    assert result.structured_content is None
    error = json.loads(text(result).split("ACA_ERROR ", 1)[1])
    assert error["code"] == "operation_timeout"
    assert error["operation_id"] is None
    assert error["request_state"] == "not_sent"
    assert error["completed_steps"] == []
    assert error["cleanup_status"] == "not_needed"
    assert error["cleanup_error_count"] == 0
    event_names = [event["event"] for event in mcp_harness.events()]
    assert event_names.count("limiter_queued") >= 1
    assert "list_devices" not in event_names
    assert "runtime_diagnose" not in event_names
    assert "runtime_connect" not in event_names


def test_cancellation_sets_the_shared_event_waits_for_worker_and_does_not_replay(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        scopes: list[anyio.CancelScope] = []

        async def call_device(client: Client) -> None:
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                await client.call_tool(
                    TOOL_NAMES[2], {"request": {"schema_version": 1}}
                )

        async with Client(mcp_harness.parameters(mode="cancel")) as client:
            async with anyio.create_task_group() as group:
                group.start_soon(call_device, client)
                await wait_for_worker(mcp_harness, 1)
                assert len(scopes) == 1
                scopes[0].cancel()
            after = await client.call_tool(
                TOOL_NAMES[0], {"request": {"schema_version": 1}}
            )
            assert structured(after)["data"]["transport"] == "stdio"

    anyio.run(scenario)
    events = mcp_harness.events()
    assert [event["event"] for event in events].count("list_devices") == 1
    assert {event["event"] for event in events} >= {
        "worker_entered",
        "worker_cancel_observed",
    }
    observed = next(
        event for event in events if event["event"] == "worker_cancel_observed"
    )
    assert observed["cancelled"] is True


def test_late_success_after_cancellation_is_not_replayed_or_reclassified(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> None:
        scopes: list[anyio.CancelScope] = []

        async def call_device(client: Client) -> None:
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                await client.call_tool(
                    TOOL_NAMES[2], {"request": {"schema_version": 1}}
                )

        async with Client(mcp_harness.parameters(mode="late_success")) as client:
            async with anyio.create_task_group() as group:
                group.start_soon(call_device, client)
                await wait_for_worker(mcp_harness, 1)
                assert len(scopes) == 1
                scopes[0].cancel()
            result = await client.call_tool(
                TOOL_NAMES[0], {"request": {"schema_version": 1}}
            )
            assert structured(result)["execution"] == "completed"

    anyio.run(scenario)
    events = mcp_harness.events()
    assert [event["event"] for event in events].count("list_devices") == 1
    observed = next(
        event for event in events if event["event"] == "worker_cancel_observed"
    )
    assert observed["cancelled"] is True


def test_cancel_wait_preserves_late_success_and_one_lower_call(
    mcp_harness: McpHarness,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[threading.Event] = []

    def late_success(
        adb_executable: object,
        *,
        control: OperationControl,
    ) -> tuple[DeviceInfo, ...]:
        del adb_executable
        cancellation = control.cancellation
        assert isinstance(cancellation, threading.Event)
        calls.append(cancellation)
        while not cancellation.is_set():
            time.sleep(0.001)
        return (DeviceInfo("device", None, "connected"),)

    monkeypatch.setattr(_application, "list_devices", late_success)

    async def scenario() -> Any:
        application = McpApplication(LocalSettings(), mcp_harness.adb)
        results: list[Any] = []

        async def invoke() -> None:
            results.append(await application.devices_list(10.0))

        async with anyio.create_task_group() as group:
            group.start_soon(invoke)
            while not calls:
                await anyio.sleep(0.001)
            group.cancel_scope.cancel()
        await application.shutdown()
        assert len(results) == 1
        return results[0]

    result = anyio.run(scenario)
    assert len(calls) == 1
    assert calls[0].is_set()
    assert "cancelled_worker_stalled" not in caplog.text
    assert result.execution == "completed"
    assert result.data.count == 1
    assert result.data.devices[0].id == "device"


def test_cancel_wait_preserves_known_lower_error_and_cleanup(
    mcp_harness: McpHarness,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[threading.Event] = []

    def known_error(
        adb_executable: object,
        *,
        control: OperationControl,
    ) -> tuple[DeviceInfo, ...]:
        del adb_executable
        cancellation = control.cancellation
        assert isinstance(cancellation, threading.Event)
        calls.append(cancellation)
        while not cancellation.is_set():
            time.sleep(0.001)
        raise CommandError(
            "adb_command_failed",
            "op_known_after_cancel",
            "response_received",
            completed_steps=("adb_launched",),
            cleanup_errors=(RuntimeError("private cleanup"),),
        )

    monkeypatch.setattr(_application, "list_devices", known_error)

    async def scenario() -> str:
        application = McpApplication(LocalSettings(), mcp_harness.adb)
        errors: list[ToolError] = []

        async def invoke() -> None:
            try:
                await application.devices_list(10.0)
            except ToolError as error:
                errors.append(error)

        async with anyio.create_task_group() as group:
            group.start_soon(invoke)
            while not calls:
                await anyio.sleep(0.001)
            group.cancel_scope.cancel()
        await application.shutdown()
        assert len(errors) == 1
        return str(errors[0])

    message = anyio.run(scenario)
    assert len(calls) == 1
    assert calls[0].is_set()
    payload = json.loads(message.split("ACA_ERROR ", 1)[1])
    assert payload["code"] == "adb_command_failed"
    assert payload["operation_id"] == "op_known_after_cancel"
    assert payload["request_state"] == "response_received"
    assert payload["completed_steps"] == ["adb_launched"]
    assert payload["cleanup_status"] == "failed"
    assert payload["cleanup_error_count"] == 1
    assert "private cleanup" not in message
    assert "cancelled_worker_stalled" not in caplog.text


def test_overlapping_runtime_calls_fail_busy_without_queueing(
    mcp_harness: McpHarness,
) -> None:
    first: list[CallToolResult] = []

    async def wait_for_event(name: str) -> None:
        with anyio.fail_after(2):
            while not any(event["event"] == name for event in mcp_harness.events()):
                await anyio.sleep(0.01)

    async def scenario() -> None:
        async with (
            Client(mcp_harness.parameters(mode="busy")) as client,
            anyio.create_task_group() as group,
        ):

            async def run_first() -> None:
                first.append(
                    await client.call_tool(
                        TOOL_NAMES[1],
                        {
                            "request": {
                                "schema_version": 1,
                                "mode": "static",
                            }
                        },
                    )
                )

            group.start_soon(run_first)
            try:
                await wait_for_event("runtime_busy_entered")
                second = await client.call_tool(
                    TOOL_NAMES[1],
                    {"request": {"schema_version": 1, "mode": "static"}},
                )
                assert second.is_error is True
                error = json.loads(text(second).split("ACA_ERROR ", 1)[1])
                assert error["code"] == "environment_busy"
                assert error["request_state"] == "not_sent"
            finally:
                mcp_harness.release_file.touch()
        assert len(first) == 1
        assert structured(first[0])["data"]["mode"] == "static"

    anyio.run(scenario)
    assert [event["event"] for event in mcp_harness.events()].count(
        "runtime_diagnose"
    ) == 1


def test_runtime_overlap_is_busy_while_first_call_waits_for_limiter(
    mcp_harness: McpHarness,
) -> None:
    first: list[CallToolResult] = []

    async def wait_for_queue() -> None:
        with anyio.fail_after(2):
            while not any(
                event["event"] == "limiter_queued" for event in mcp_harness.events()
            ):
                await anyio.sleep(0.01)

    async def scenario() -> None:
        async with (
            Client(mcp_harness.parameters(mode="runtime_limiter_busy")) as client,
            anyio.create_task_group() as group,
        ):

            async def run_first() -> None:
                first.append(
                    await client.call_tool(
                        TOOL_NAMES[1],
                        {"request": {"schema_version": 1, "mode": "static"}},
                    )
                )

            group.start_soon(run_first)
            try:
                await wait_for_queue()
                second = await client.call_tool(
                    TOOL_NAMES[1],
                    {"request": {"schema_version": 1, "mode": "static"}},
                )
                assert second.is_error is True
                error = json.loads(text(second).split("ACA_ERROR ", 1)[1])
                assert error["code"] == "environment_busy"
                assert error["operation_id"] is None
                assert error["request_state"] == "not_sent"
                assert error["cleanup_status"] == "not_needed"
                assert not any(
                    event["event"] == "runtime_diagnose"
                    for event in mcp_harness.events()
                )
            finally:
                mcp_harness.release_file.touch()

    anyio.run(scenario)
    assert len(first) == 1
    assert structured(first[0])["data"]["mode"] == "static"
    events = [event["event"] for event in mcp_harness.events()]
    assert events.count("limiter_queued") == 1
    assert events.count("runtime_diagnose") == 1


def replace_nested(value: Any, path: tuple[str, ...], replacement: object) -> Any:
    if not path:
        return replacement
    component, *remaining = path
    if component.isdigit():
        copied_items = list(value)
        index = int(component)
        copied_items[index] = replace_nested(
            copied_items[index], tuple(remaining), replacement
        )
        return tuple(copied_items)
    copied_mapping = dict(value)
    copied_mapping[component] = replace_nested(
        copied_mapping[component], tuple(remaining), replacement
    )
    return copied_mapping


def assert_product_model_invalid(
    model_type: type[BaseModel], value: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        model_type.model_validate(value)


def test_fixed_schema_digest_and_maximum_canonical_bytes(
    mcp_harness: McpHarness,
) -> None:
    async def source_values() -> tuple[list[Tool], list[CallToolResult]]:
        async with Client(mcp_harness.parameters(mode="maximum")) as client:
            tools = (await client.list_tools()).tools
            results = [
                await client.call_tool(
                    TOOL_NAMES[0], {"request": {"schema_version": 1}}
                ),
                await client.call_tool(
                    TOOL_NAMES[1],
                    {
                        "request": {
                            "schema_version": 1,
                            "mode": "external_connection",
                        }
                    },
                ),
                await client.call_tool(
                    TOOL_NAMES[2], {"request": {"schema_version": 1}}
                ),
            ]
            return tools, results

    tools, source_results = anyio.run(source_values)
    timed = [event["timeout"] for event in mcp_harness.events() if "timeout" in event]
    for observed, requested in zip(timed, (10.0, 10.0, 30.0), strict=True):
        assert_remaining_budget(observed, requested)

    capability_dict = with_maximum_warnings(structured(source_results[0]))
    runtime_dict = with_maximum_warnings(structured(source_results[1]))
    device_dict = with_maximum_warnings(structured(source_results[2]))
    capability = CapabilityResult.model_validate_json(canonical(capability_dict))
    runtime = RuntimeCheckResult.model_validate_json(canonical(runtime_dict))
    devices = DeviceListResult.model_validate_json(canonical(device_dict))

    async def send_models() -> list[CallToolResult]:
        server = MCPServer[None]("maximum-product-models")
        open_value, status_value, close_value = maximum_session_results()

        @server.tool(name=TOOL_NAMES[0], structured_output=True)
        async def capability_tool() -> CapabilityResult:
            return cast(CapabilityResult, product_result(capability))

        @server.tool(name=TOOL_NAMES[1], structured_output=True)
        async def runtime_tool() -> RuntimeCheckResult:
            return cast(RuntimeCheckResult, product_result(runtime))

        @server.tool(name=TOOL_NAMES[2], structured_output=True)
        async def device_tool() -> DeviceListResult:
            return cast(DeviceListResult, product_result(devices))

        @server.tool(name=TOOL_NAMES[3], structured_output=True)
        async def open_tool() -> SessionOpenResult:
            return cast(SessionOpenResult, product_result(open_value))

        @server.tool(name=TOOL_NAMES[4], structured_output=True)
        async def status_tool() -> SessionStatusResult:
            return cast(SessionStatusResult, product_result(status_value))

        @server.tool(name=TOOL_NAMES[5], structured_output=True)
        async def close_tool() -> SessionCloseResult:
            return cast(SessionCloseResult, product_result(close_value))

        async with Client(server) as client:
            return [await client.call_tool(name, {}) for name in TOOL_NAMES]

    wire_results = anyio.run(send_models)
    session_models = maximum_session_results()
    models: tuple[BaseModel, ...] = (
        capability,
        runtime,
        devices,
        *session_models,
    )
    expected_sizes = (
        CAPABILITY_MAX_CANONICAL_BYTES,
        RUNTIME_MAX_CANONICAL_BYTES,
        DEVICE_MAX_CANONICAL_BYTES,
        SESSION_OPEN_MAX_CANONICAL_BYTES,
        SESSION_STATUS_MAX_CANONICAL_BYTES,
        SESSION_CLOSE_MAX_CANONICAL_BYTES,
    )
    assert schema_fingerprint(tools) == SCHEMA_BUNDLE_SHA256
    for model, result, expected_size in zip(
        models, wire_results, expected_sizes, strict=True
    ):
        expected = canonical_json(model)
        assert len(expected.encode()) == expected_size
        assert len(expected.encode()) < 4 * 1024 * 1024
        assert result.is_error is False
        assert result.structured_content == model.model_dump(mode="json")
        assert text(result) == expected

    assert runtime.data.report.checks[-1].remediation == "\U00010000" * 512
    assert runtime.data.connection is not None
    assert runtime.data.connection.appium_version == "\U00010000" * 128
    assert devices.data.count == 256
    assert devices.data.devices[-1].id == "\U00010000" * 1024
    assert devices.data.devices[-1].name == "\U00010000" * 1024

    for model in models:
        model_type = type(model)
        valid = model.model_dump(mode="python")
        warnings = tuple(maximum_codes("w", 16))
        for invalid_warnings in (
            (*warnings, "w" * 128),
            (*warnings[:-1], warnings[0]),
            ("", *warnings[1:]),
            ("w" * 129, *warnings[1:]),
            ("INVALID", *warnings[1:]),
            ("w" * 127 + "\ud800", *warnings[1:]),
            (True, *warnings[1:]),
        ):
            invalid = copy.deepcopy(valid)
            invalid["warnings"] = invalid_warnings
            assert_product_model_invalid(model_type, invalid)
        for field, value in (
            ("schema_version", True),
            ("call_id", ""),
            ("call_id", "c_" + "a" * 23),
            ("call_id", "c_" + "!" * 22),
            ("call_id", "c_" + "a" * 21 + "\ud800"),
            ("call_id", True),
        ):
            invalid = copy.deepcopy(valid)
            invalid[field] = value
            assert_product_model_invalid(model_type, invalid)

    capability_values = capability.model_dump(mode="python")
    for field, extra in (("tools", "appium.extra"), ("limitations", "extra")):
        invalid = copy.deepcopy(capability_values)
        invalid["data"][field] = (*invalid["data"][field], extra)
        assert_product_model_invalid(CapabilityResult, invalid)

    runtime_values = runtime.model_dump(mode="python")
    runtime_mutations: tuple[tuple[tuple[str, ...], object], ...] = (
        (("operation_id",), ""),
        (("operation_id",), "o" * 129),
        (("operation_id",), "o" * 127 + "\ud800"),
        (("operation_id",), True),
        (("data", "report", "operation_id"), "different"),
        (("data", "report", "operation_id"), ""),
        (("data", "report", "operation_id"), "o" * 129),
        (("data", "report", "observed_at"), "not-a-time"),
        (("data", "report", "host"), "Linux"),
        (("data", "report", "target"), "iOS"),
        (("data", "report", "driver"), "Other"),
        (("data", "report", "checks", "0", "check_id"), ""),
        (("data", "report", "checks", "0", "check_id"), "c" * 129),
        (("data", "report", "checks", "0", "check_id"), "INVALID"),
        (("data", "report", "checks", "0", "check_id"), True),
        (("data", "report", "checks", "0", "reason_code"), ""),
        (("data", "report", "checks", "0", "reason_code"), "r" * 129),
        (("data", "report", "checks", "0", "reason_code"), "INVALID"),
        (("data", "report", "checks", "0", "reason_code"), True),
        (("data", "report", "checks", "0", "status"), "broken"),
        (("data", "report", "checks", "0", "status"), True),
        (("data", "report", "checks", "0", "evidence", "0"), "e" * 513),
        (("data", "report", "checks", "0", "evidence", "0"), "\ud800"),
        (("data", "report", "checks", "0", "remediation"), "m" * 513),
        (("data", "report", "checks", "0", "remediation"), "\ud800"),
        (("data", "report", "observer_errors", "0"), "o" * 513),
        (("data", "report", "observer_errors", "0"), "\ud800"),
        (("data", "connection", "appium_version"), ""),
        (("data", "connection", "appium_version"), "v" * 129),
        (("data", "connection", "appium_version"), "\ud800"),
        (("data", "connection", "compatibility"), "broken"),
        (("data", "connection", "compatibility"), True),
    )
    for path, mutation_value in runtime_mutations:
        invalid = cast(
            dict[str, Any], replace_nested(runtime_values, path, mutation_value)
        )
        assert_product_model_invalid(RuntimeCheckResult, invalid)
    for path in (
        ("data", "report", "checks"),
        ("data", "report", "checks", "0", "evidence"),
        ("data", "report", "observer_errors"),
    ):
        invalid = copy.deepcopy(runtime_values)
        target: Any = invalid
        for component in path[:-1]:
            target = (
                target[int(component)] if component.isdigit() else target[component]
            )
        values = target[path[-1]]
        target[path[-1]] = (*values, values[0])
        assert_product_model_invalid(RuntimeCheckResult, invalid)

    device_values = devices.model_dump(mode="python")
    device_mutations: tuple[tuple[str, object], ...] = (
        ("id", ""),
        ("id", "d" * 1025),
        ("id", "bad id"),
        ("id", "d" * 1023 + "\ud800"),
        ("id", True),
        ("name", "n" * 1025),
        ("name", "bad\x00name"),
        ("name", "n" * 1023 + "\ud800"),
        ("name", True),
        ("connection_state", "broken"),
        ("connection_state", True),
    )
    for field, device_value in device_mutations:
        invalid = copy.deepcopy(device_values)
        invalid["data"]["devices"][0][field] = device_value
        assert_product_model_invalid(DeviceListResult, invalid)
    for count in (True, -1, 257):
        invalid = copy.deepcopy(device_values)
        invalid["data"]["count"] = count
        assert_product_model_invalid(DeviceListResult, invalid)
    invalid = copy.deepcopy(device_values)
    invalid["data"]["devices"] = (
        *invalid["data"]["devices"],
        invalid["data"]["devices"][0],
    )
    invalid["data"]["count"] = 257
    assert_product_model_invalid(DeviceListResult, invalid)

    for session_model in session_models:
        model_type = type(session_model)
        session_values = session_model.model_dump(mode="python")
        mutations: tuple[tuple[str, object], ...] = (
            ("session_handle", "s_" + "a" * 31),
            ("session_handle", "s_" + "a" * 33),
            ("session_handle", "s_" + "!" * 32),
            ("session_handle", "s_" + "a" * 31 + "\ud800"),
            ("session_handle", True),
            ("session_state", "creating"),
            ("session_state", True),
            ("device_id", ""),
            ("device_id", "d" * 1025),
            ("device_id", "bad id"),
            ("device_id", "d" * 1023 + "\ud800"),
            ("device_id", True),
            ("target_app_id", ""),
            ("target_app_id", "a" * 256),
            ("target_app_id", "a" * 254 + "\ud800"),
            ("target_app_id", True),
            ("busy", 0),
        )
        for field, mutation in mutations:
            invalid = copy.deepcopy(session_values)
            invalid["data"][field] = mutation
            assert_product_model_invalid(model_type, invalid)

    open_values = session_models[0].model_dump(mode="python")
    for field, mutation in (("session_state", "closed"), ("busy", True)):
        invalid = copy.deepcopy(open_values)
        invalid["data"][field] = mutation
        assert_product_model_invalid(SessionOpenResult, invalid)
    close_values = session_models[2].model_dump(mode="python")
    for field, mutation in (("session_state", "active"), ("busy", True)):
        invalid = copy.deepcopy(close_values)
        invalid["data"][field] = mutation
        assert_product_model_invalid(SessionCloseResult, invalid)


def test_output_value_over_public_boundary_fails_instead_of_truncating(
    mcp_harness: McpHarness,
) -> None:
    runtime_modes = (
        "invalid_report_check_id",
        "invalid_report_reason",
        "invalid_report_evidence_count",
        "invalid_report_evidence_item",
        "invalid_report_remediation",
        "invalid_report_checks_count",
        "invalid_report_observer_count",
        "invalid_report_observer_item",
        "invalid_report_operation_id",
        "invalid_report_evidence_utf8",
        "invalid_report_remediation_utf8",
        "invalid_report_observer_utf8",
        "invalid_report_operation_utf8",
        "invalid_report_status",
        "invalid_report_platform",
    )
    device_modes = (
        "invalid_device",
        "invalid_device_name",
        "invalid_device_count",
        "invalid_device_id_whitespace",
        "invalid_device_name_control",
        "invalid_device_id_utf8",
        "invalid_device_name_utf8",
        "invalid_device_state",
    )

    async def call(mode: str, name: str, request: object) -> CallToolResult:
        mcp_harness.reset_records()
        async with Client(mcp_harness.parameters(mode=mode)) as client:
            return await client.call_tool(name, {"request": request})

    cases: list[tuple[str, str, object, str]] = [
        *(
            (
                mode,
                TOOL_NAMES[1],
                {"schema_version": 1, "mode": "static"},
                "runtime_diagnose",
            )
            for mode in runtime_modes
        ),
        *(
            (
                mode,
                TOOL_NAMES[1],
                {"schema_version": 1, "mode": "external_connection"},
                "runtime_connect_enter",
            )
            for mode in (
                "invalid_connection_version",
                "invalid_connection_utf8",
                "invalid_connection_compatibility",
            )
        ),
        *(
            (mode, TOOL_NAMES[2], {"schema_version": 1}, "list_devices")
            for mode in device_modes
        ),
    ]
    for mode, name, request, lower_event in cases:
        result = anyio.run(call, mode, name, request)
        assert result.is_error is True
        assert result.structured_content is None
        assert text(result) == f"Error executing tool {name}"
        events = mcp_harness.events()
        assert [event["event"] for event in events].count(lower_event) == 1
        combined = text(result) + mcp_harness.stderr_file.read_text(encoding="utf-8")
        assert "mcp_sdk_internal_error" in combined
        assert "d" * 1025 not in combined
        assert "n" * 1025 not in combined
        for forbidden in (
            str(mcp_harness.config),
            str(mcp_harness.adb),
            CANARY,
            SECRET_PATH,
            "Traceback",
        ):
            assert forbidden not in combined


def test_empty_device_list_is_a_completed_result(mcp_harness: McpHarness) -> None:
    async def scenario() -> CallToolResult:
        async with Client(mcp_harness.parameters(mode="empty")) as client:
            return await client.call_tool(
                TOOL_NAMES[2], {"request": {"schema_version": 1}}
            )

    result = structured(anyio.run(scenario))
    assert result["data"] == {"count": 0, "devices": []}
