from __future__ import annotations

import contextlib
import json
import os
import select
import subprocess
import threading
from typing import Any, cast

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult, Tool

from appium_connect_agent.integrations._models import (
    ObservationResult,
    canonical_json,
)
from appium_connect_agent.integrations._server import create_server
from tests.automation.test_observation import (
    ElementProtocolService,
    ResponsePlan,
    basic_xml,
    node_xml,
    w3c_error,
)

from .conftest import CANARY, SECRET_PATH, TOOL_NAMES, McpHarness

_HANDLE_PATTERN_LENGTH = 34
_OBSERVATION_MAX_CANONICAL_BYTES = {
    "tree": 68_124,
    "attributes": 68_130,
    "structure": 68_129,
}
_ATTRIBUTES = (
    "id",
    "text",
    "desc",
    "type",
    "package",
    "enabled",
    "focused",
    "checkable",
    "checked",
    "selected",
    "clickable",
    "focusable",
    "long_clickable",
    "password",
    "scrollable",
    "displayed",
    "bounds",
    "window_id",
)


def _request(**values: object) -> dict[str, object]:
    return {"request": {"schema_version": 1, **values}}


def _text(result: CallToolResult) -> str:
    assert len(result.content) == 1
    value = result.content[0]
    assert value.type == "text"
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


def _assert_closed_objects(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            assert value.get("additionalProperties") is False
        for child in value.values():
            _assert_closed_objects(child)
    elif isinstance(value, list):
        for child in value:
            _assert_closed_objects(child)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


async def _open(client: Client, device_id: str = "controlled-observation") -> str:
    result = _structured(
        await client.call_tool(
            TOOL_NAMES[3], _request(device_id=device_id, app_id="com.example")
        )
    )
    handle = result["data"]["session_handle"]
    assert isinstance(handle, str) and len(handle) == _HANDLE_PATTERN_LENGTH
    return handle


async def _close(client: Client, handle: str) -> dict[str, Any]:
    return _structured(
        await client.call_tool(
            TOOL_NAMES[5], _request(session_handle=handle, timeout_seconds=60)
        )
    )


def _observe_request(handle: str, mode: str, **values: object) -> dict[str, object]:
    return _request(session_handle=handle, mode=mode, **values)


def _locator(
    by: str,
    value: str,
    *,
    package: str | None = None,
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


def _assert_observation(value: dict[str, Any], mode: str, kind: str) -> dict[str, Any]:
    assert value["schema_version"] == 1
    assert value["execution"] == "completed"
    assert value["request_state"] is None
    assert value["warnings"] == []
    assert value["data"]["mode"] == mode
    document = cast(dict[str, Any], value["data"]["document"])
    assert document["schema"] == 1
    assert document["kind"] == kind
    assert value["operation_id"] == document["operation_id"]
    assert document["upstream_completeness"] == "unknown"
    assert len(_canonical(value)) <= 69_632
    return document


def _assert_maximum_outer_bytes(value: dict[str, Any], mode: str) -> ObservationResult:
    maximum = cast(dict[str, Any], json.loads(_canonical(value)))
    document = cast(dict[str, Any], maximum["data"]["document"])
    maximum_operation_id = "o" * 128
    maximum["operation_id"] = maximum_operation_id
    document["operation_id"] = maximum_operation_id
    if mode == "tree":
        node = document["payload"]["roots"][0]
        node["text"] = node["text"][:-96]
        node["text"] = CANARY + node["text"][len(CANARY) :]
    elif mode == "attributes":
        attribute = document["payload"]["attributes"][0]
        attribute["value"] = attribute["value"][:-96]
        attribute["value"] = CANARY + attribute["value"][len(CANARY) :]
    else:
        raw = document["payload"]["roots"][0]
        text_pair = next(pair for pair in raw["attributes"] if pair[0] == "text")
        text_pair[1] = text_pair[1][:-96]
        text_pair[1] = CANARY + text_pair[1][len(CANARY) :]
    maximum["warnings"] = [("w" * 124) + f"{index:04d}" for index in range(16)]
    model = ObservationResult.model_validate_json(_canonical(maximum))
    validated = model.model_dump(mode="json", by_alias=True, warnings=False)
    validated_document = cast(dict[str, Any], validated["data"]["document"])
    assert len(_canonical(validated_document)) == 65_536
    encoded = canonical_json(model).encode("utf-8")
    assert len(encoded) == _OBSERVATION_MAX_CANONICAL_BYTES[mode]
    assert len(encoded) <= 69_632
    return model


def test_observe_is_seventh_read_only_tool_with_strict_discriminated_schemas(
    mcp_harness: McpHarness,
) -> None:
    async def scenario() -> list[Tool]:
        async with Client(mcp_harness.parameters()) as client:
            return (await client.list_tools()).tools

    tools = anyio.run(scenario)
    assert tuple(tool.name for tool in tools) == TOOL_NAMES
    observe = tools[6]
    assert observe.annotations is not None
    assert observe.annotations.model_dump(
        mode="json", by_alias=True, exclude_none=False
    ) == {
        "title": None,
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }

    input_schema = observe.input_schema
    project_definitions = input_schema.get("$defs")
    assert isinstance(project_definitions, dict)
    _assert_closed_objects(project_definitions)
    assert input_schema["type"] == "object"
    assert input_schema["required"] == ["request"]
    request_schema = _schema_target(input_schema, input_schema["properties"]["request"])
    branches = request_schema.get("oneOf", request_schema.get("anyOf"))
    assert isinstance(branches, list) and len(branches) == 3
    resolved = [_schema_target(input_schema, branch) for branch in branches]
    by_mode = {branch["properties"]["mode"].get("const"): branch for branch in resolved}
    assert set(by_mode) == {"tree", "attributes", "structure"}
    assert set(by_mode["tree"]["required"]) == {
        "schema_version",
        "session_handle",
        "mode",
        "locator",
    }
    assert set(by_mode["attributes"]["required"]) == {
        "schema_version",
        "session_handle",
        "mode",
        "locator",
        "attributes",
    }
    assert set(by_mode["structure"]["required"]) == {
        "schema_version",
        "session_handle",
        "mode",
        "locator",
        "structure_scope",
    }
    for branch in resolved:
        assert branch["additionalProperties"] is False
        _assert_closed_objects(branch)
        timeout = branch["properties"]["timeout_seconds"]
        assert timeout["default"] == 90.0
        assert timeout["exclusiveMinimum"] == 0.0
        assert timeout["maximum"] == 120.0

    attribute_schema = by_mode["attributes"]["properties"]["attributes"]
    assert attribute_schema["minItems"] == 1
    assert attribute_schema["maxItems"] == 18
    assert attribute_schema["uniqueItems"] is True
    attribute_items = _schema_target(input_schema, attribute_schema["items"])
    assert tuple(attribute_items["enum"]) == _ATTRIBUTES
    assert set(by_mode["structure"]["properties"]["structure_scope"]["enum"]) == {
        "target",
        "declared_parent",
    }

    output_schema = cast(dict[str, Any], observe.output_schema)
    _assert_closed_objects(output_schema)
    encoded = json.dumps(output_schema, sort_keys=True)
    assert "additionalProperties" in encoded
    assert "operation_id" in encoded
    assert "target_path" in encoded
    assert "upstream_completeness" in encoded
    assert "viewport_relation" in encoded
    assert "not_applicable" in encoded


def test_strict_union_locator_depth_attributes_and_mode_fields_reject_before_io(
    mcp_harness: McpHarness,
) -> None:
    valid_handle = "s_" + ("a" * 32)
    depth_16: dict[str, object] | None = None
    for index in range(16):
        depth_16 = _locator("id", f"node_{index}", parent=depth_16)
    assert depth_16 is not None
    depth_17 = _locator("id", "too_deep", parent=depth_16)
    invalid_requests: tuple[dict[str, object], ...] = (
        _observe_request(valid_handle, "tree"),
        _observe_request(valid_handle, "tree", locator=None, attributes=["text"]),
        _observe_request(valid_handle, "attributes", locator=None, attributes=["text"]),
        _observe_request(
            valid_handle,
            "attributes",
            locator=_locator("id", "target"),
            attributes=[],
        ),
        _observe_request(
            valid_handle,
            "attributes",
            locator=_locator("id", "target"),
            attributes=["text", "text"],
        ),
        _observe_request(
            valid_handle,
            "attributes",
            locator=_locator("id", "target"),
            attributes=[*_ATTRIBUTES, "unknown"],
        ),
        _observe_request(
            valid_handle,
            "structure",
            locator=_locator("id", "target"),
        ),
        _observe_request(
            valid_handle,
            "structure",
            locator=_locator("id", "target"),
            structure_scope="parent",
        ),
        _observe_request(valid_handle, "tree", locator=depth_17),
        _observe_request(
            valid_handle,
            "tree",
            locator=_locator("accessibility id", "wrong spelling"),
        ),
        _observe_request(valid_handle, "tree", locator=None, timeout_seconds=True),
        _observe_request(valid_handle, "tree", locator=None, timeout_seconds=0),
        _observe_request(valid_handle, "tree", locator=None, timeout_seconds=121),
    )

    async def scenario() -> None:
        async with Client(mcp_harness.parameters()) as client:
            for request in invalid_requests:
                result = await client.call_tool(TOOL_NAMES[6], request)
                assert result.is_error is True
                assert result.structured_content is None

    anyio.run(scenario)
    assert mcp_harness.events() == []


def test_controlled_protocol_covers_root_scoped_attributes_and_both_structures(
    mcp_harness: McpHarness,
) -> None:
    target_xml = node_xml(
        resource_id="com.example:id/target",
        desc="Target",
        text="sensitive-visible-value",
        extra='window-id="7" custom=""',
    )
    form_xml = node_xml(
        tag="android.view.ViewGroup",
        resource_id="com.example:id/form",
        children=target_xml,
    )
    parent_locator = _locator("id", "form", package="com.example")
    target_locator = _locator("accessibility_id", "Target", parent=parent_locator)

    with ElementProtocolService() as service:
        service.source = basic_xml(form_xml)
        service.attributes.update(
            {
                ("target", "text"): "",
                ("target", "content-desc"): "Target",
                ("target", "enabled"): "false",
                ("target", "checkable"): "false",
                ("target", "checked"): "true",
                ("target", "displayed"): "true",
            }
        )
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client)
                root = _assert_observation(
                    _structured(
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _observe_request(handle, "tree", locator=None),
                        )
                    ),
                    "tree",
                    "tree",
                )
                assert root["scope"] == {
                    "kind": "root",
                    "locator": None,
                    "range_locator": None,
                }
                assert root["payload"]["roots"][0]["id"] == "form"
                string_request = json.dumps(
                    {
                        "schema_version": 1,
                        "session_handle": handle,
                        "mode": "tree",
                        "locator": None,
                    },
                    separators=(",", ":"),
                )
                string_root = _assert_observation(
                    _structured(
                        await client.call_tool(
                            TOOL_NAMES[6], {"request": string_request}
                        )
                    ),
                    "tree",
                    "tree",
                )
                assert string_root["scope"] == root["scope"]

                scoped = _assert_observation(
                    _structured(
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _observe_request(handle, "tree", locator=target_locator),
                        )
                    ),
                    "tree",
                    "tree",
                )
                assert scoped["scope"]["kind"] == "element"
                assert scoped["scope"]["locator"]["by"] == "accessibility id"
                assert scoped["scope"]["locator"]["parent"]["value"] == (
                    "com.example:id/form"
                )
                assert scoped["payload"]["roots"][0]["text"] == (
                    "sensitive-visible-value"
                )

                attributes = _assert_observation(
                    _structured(
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _observe_request(
                                handle,
                                "attributes",
                                locator=target_locator,
                                attributes=[
                                    "text",
                                    "desc",
                                    "enabled",
                                    "checked",
                                    "bounds",
                                ],
                            ),
                        )
                    ),
                    "attributes",
                    "element",
                )
                values = attributes["payload"]["attributes"]
                assert [item["name"] for item in values] == [
                    "text",
                    "desc",
                    "enabled",
                    "checked",
                    "bounds",
                ]
                assert [(item["state"], item.get("value")) for item in values[:4]] == [
                    ("value", ""),
                    ("value", "Target"),
                    ("value", False),
                    ("not_applicable", None),
                ]
                assert values[-1]["state"] == "value"

                for scope, expected_path in (
                    ("target", [0]),
                    ("declared_parent", [0, 0]),
                ):
                    structure = _assert_observation(
                        _structured(
                            await client.call_tool(
                                TOOL_NAMES[6],
                                _observe_request(
                                    handle,
                                    "structure",
                                    locator=target_locator,
                                    structure_scope=scope,
                                ),
                            )
                        ),
                        "structure",
                        "structure",
                    )
                    assert structure["payload"]["target_path"] == expected_path
                    assert structure["scope"]["kind"] == (
                        "element" if scope == "target" else "declared_parent"
                    )
                    raw = structure["payload"]["roots"][0]
                    if scope == "declared_parent":
                        raw = raw["children"][0]
                    assert ["custom", ""] in raw["attributes"]

                deepest: dict[str, object] | None = None
                for index in range(16):
                    deepest = _locator("id", f"depth_{index}", parent=deepest)
                assert deepest is not None
                nested = node_xml(resource_id="com.example:id/depth_15")
                for index in reversed(range(15)):
                    nested = node_xml(
                        tag="android.view.ViewGroup",
                        resource_id=f"com.example:id/depth_{index}",
                        children=nested,
                    )
                service.source = basic_xml(nested)
                depth_document = _assert_observation(
                    _structured(
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _observe_request(handle, "tree", locator=deepest),
                        )
                    ),
                    "tree",
                    "tree",
                )
                assert depth_document["payload"]["roots"][0]["id"] == "depth_15"

                hidden_large = node_xml(
                    resource_id="com.example:id/hidden",
                    text="x" * 66_000,
                    displayed="false",
                )
                visible = node_xml(resource_id="com.example:id/visible")
                service.source = basic_xml(
                    node_xml(
                        tag="android.view.ViewGroup",
                        resource_id="com.example:id/fallback",
                        displayed="false",
                        children=hidden_large + visible,
                    )
                )
                fallback = _assert_observation(
                    _structured(
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _observe_request(handle, "tree", locator=None),
                        )
                    ),
                    "tree",
                    "tree",
                )
                assert fallback["coverage"] == "visible_with_ancestors"
                assert fallback["complete_for_requested_scope"] is False
                assert [
                    child["id"] for child in fallback["payload"]["roots"][0]["children"]
                ] == ["visible"]
                service.source = basic_xml(form_xml)

                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handle)
                    )
                )
                assert status["data"]["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("source")) == 7
    assert len(service.of_kind("find")) == 2
    assert len(service.of_kind("text")) == 1
    assert len(service.of_kind("rect")) == 1
    assert service.settings["allowInvisibleElements"] is False
    assert service.settings["disableIdLocatorAutocompletion"] is False


def test_document_size_lower_failure_no_cache_and_outer_defensive_limit(
    mcp_harness: McpHarness,
    capsys: pytest.CaptureFixture[str],
) -> None:
    maximum_models: list[ObservationResult] = []
    with ElementProtocolService() as service:
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def call_tree(client: Client, handle: str) -> CallToolResult:
            return await client.call_tool(
                TOOL_NAMES[6], _observe_request(handle, "tree", locator=None)
            )

        async def call_attributes(client: Client, handle: str) -> CallToolResult:
            return await client.call_tool(
                TOOL_NAMES[6],
                _observe_request(
                    handle,
                    "attributes",
                    locator=_locator("id", "com.example:id/target"),
                    attributes=["text"],
                ),
            )

        async def call_structure(client: Client, handle: str) -> CallToolResult:
            return await client.call_tool(
                TOOL_NAMES[6],
                _observe_request(
                    handle,
                    "structure",
                    locator=_locator("id", "com.example:id/target"),
                    structure_scope="target",
                ),
            )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "controlled-size")
                service.source = basic_xml(node_xml(text="first"))
                first = _assert_observation(
                    _structured(await call_tree(client, handle)), "tree", "tree"
                )
                service.source = basic_xml(node_xml(text="second"))
                second = _assert_observation(
                    _structured(await call_tree(client, handle)), "tree", "tree"
                )
                assert first["payload"]["roots"][0]["text"] == "first"
                assert second["payload"]["roots"][0]["text"] == "second"

                service.source = basic_xml(node_xml(text=""))
                baseline = _assert_observation(
                    _structured(await call_tree(client, handle)), "tree", "tree"
                )
                padding = 65_536 - len(_canonical(baseline))
                assert padding > 0
                service.source = basic_xml(node_xml(text="x" * padding))
                maximum_result = _structured(await call_tree(client, handle))
                maximum = _assert_observation(maximum_result, "tree", "tree")
                assert len(_canonical(maximum)) == 65_536
                maximum_models.append(
                    _assert_maximum_outer_bytes(maximum_result, "tree")
                )
                service.source = basic_xml(node_xml(text="x" * (padding + 1)))
                too_large = _error(await call_tree(client, handle))
                assert too_large["code"] == "observation_too_large"
                assert too_large["session_handle"] == handle
                assert too_large["session_state"] == "active"

                service.attributes[("target", "text")] = ""
                attribute_baseline = _assert_observation(
                    _structured(await call_attributes(client, handle)),
                    "attributes",
                    "element",
                )
                attribute_padding = 65_536 - len(_canonical(attribute_baseline))
                assert attribute_padding > 0
                service.attributes[("target", "text")] = "x" * attribute_padding
                attribute_maximum_result = _structured(
                    await call_attributes(client, handle)
                )
                attribute_maximum = _assert_observation(
                    attribute_maximum_result, "attributes", "element"
                )
                assert len(_canonical(attribute_maximum)) == 65_536
                maximum_models.append(
                    _assert_maximum_outer_bytes(attribute_maximum_result, "attributes")
                )
                service.attributes[("target", "text")] = "x" * (attribute_padding + 1)
                attribute_large = _error(await call_attributes(client, handle))
                assert attribute_large["code"] == "observation_too_large"
                assert attribute_large["session_handle"] == handle
                assert attribute_large["session_state"] == "active"

                service.source = basic_xml(
                    node_xml(resource_id="com.example:id/target", text="")
                )
                structure_baseline = _assert_observation(
                    _structured(await call_structure(client, handle)),
                    "structure",
                    "structure",
                )
                structure_padding = 65_536 - len(_canonical(structure_baseline))
                assert structure_padding > 0
                service.source = basic_xml(
                    node_xml(
                        resource_id="com.example:id/target",
                        text="x" * structure_padding,
                    )
                )
                structure_maximum_result = _structured(
                    await call_structure(client, handle)
                )
                structure_maximum = _assert_observation(
                    structure_maximum_result, "structure", "structure"
                )
                assert len(_canonical(structure_maximum)) == 65_536
                maximum_models.append(
                    _assert_maximum_outer_bytes(structure_maximum_result, "structure")
                )
                service.source = basic_xml(
                    node_xml(
                        resource_id="com.example:id/target",
                        text="x" * (structure_padding + 1),
                    )
                )
                structure_large = _error(await call_structure(client, handle))
                assert structure_large["code"] == "observation_too_large"
                assert structure_large["session_handle"] == handle
                assert structure_large["session_state"] == "active"
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("source")) == 8

    class MaximumApplication:
        def __init__(self, models: list[ObservationResult]) -> None:
            self.models = iter(models)

        async def observe(self, request: object) -> ObservationResult:
            del request
            return next(self.models)

        async def shutdown(self) -> None:
            return None

    async def send_maximum_models() -> None:
        server = create_server(cast(Any, MaximumApplication(maximum_models)))
        async with Client(server) as client:
            for mode, model in zip(
                ("tree", "attributes", "structure"), maximum_models, strict=True
            ):
                if mode == "tree":
                    request = _observe_request("s_" + ("a" * 32), mode, locator=None)
                elif mode == "attributes":
                    request = _observe_request(
                        "s_" + ("a" * 32),
                        mode,
                        locator=_locator("id", "target"),
                        attributes=["text"],
                    )
                else:
                    request = _observe_request(
                        "s_" + ("a" * 32),
                        mode,
                        locator=_locator("id", "target"),
                        structure_scope="target",
                    )
                result = await client.call_tool(TOOL_NAMES[6], request)
                expected_value = model.model_dump(
                    mode="json", by_alias=True, warnings=False
                )
                assert result.structured_content == expected_value
                assert json.loads(_text(result)) == expected_value
                assert _text(result) == canonical_json(model)
                assert "document_schema" not in _text(result)
                assert '"schema":1' in _text(result)
                assert CANARY in _text(result)
                assert (
                    len(_text(result).encode("utf-8"))
                    == (_OBSERVATION_MAX_CANONICAL_BYTES[mode])
                )

    anyio.run(send_maximum_models)
    serialization_stderr = capsys.readouterr().err
    assert "PydanticSerializationUnexpectedValue" not in serialization_stderr
    assert CANARY not in serialization_stderr


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_request_state", "expected_state"),
    [
        ("known", "command_failed", "response_received", "active"),
        ("unknown", "execution_unknown", "response_unknown", "uncertain"),
        ("timeout", "operation_timeout", "response_unknown", "uncertain"),
        ("cleanup", "source_invalid", "response_received", "uncertain"),
    ],
)
def test_observation_error_resource_pair_and_uncertain_quarantine(
    mcp_harness: McpHarness,
    failure: str,
    expected_code: str,
    expected_request_state: str,
    expected_state: str,
) -> None:
    with ElementProtocolService() as service:
        if failure == "known":
            service.queue("source", ResponsePlan(status=500, payload=w3c_error(CANARY)))
        elif failure == "unknown":
            service.queue("source", ResponsePlan(disconnect=True))
        elif failure == "timeout":
            service.queue("source", ResponsePlan(delay_seconds=0.2))
        else:
            service.source = f"<hierarchy><node>{CANARY}{SECRET_PATH}"
            service.queue(
                "settings:post",
                ResponsePlan(),
                ResponsePlan(disconnect=True),
            )
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, f"controlled-{failure}")
                value = _error(
                    await client.call_tool(
                        TOOL_NAMES[6],
                        _observe_request(
                            handle,
                            "tree",
                            locator=None,
                            timeout_seconds=0.05 if failure == "timeout" else 90,
                        ),
                    )
                )
                assert value["code"] == expected_code
                assert value["request_state"] == expected_request_state
                assert value["session_handle"] == handle
                assert value["session_state"] == expected_state
                assert value["cleanup_status"] == (
                    "failed" if failure == "cleanup" else "completed"
                )

                status = _structured(
                    await client.call_tool(
                        TOOL_NAMES[4], _request(session_handle=handle)
                    )
                )
                assert status["data"]["session_state"] == expected_state
                if expected_state == "active":
                    await _close(client, handle)
                else:
                    before = len(service.snapshot())
                    close = _error(
                        await client.call_tool(
                            TOOL_NAMES[5], _request(session_handle=handle)
                        )
                    )
                    assert close["code"] == "session_uncertain"
                    assert len(service.snapshot()) == before

        anyio.run(scenario)

    combined = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (CANARY, SECRET_PATH, "Traceback", "controlled-"):
        assert forbidden not in combined


def test_unknown_and_closed_handles_have_exact_observation_resource_pairs(
    mcp_harness: McpHarness,
) -> None:
    missing_handle = "s_" + ("m" * 32)

    async def scenario() -> None:
        async with Client(mcp_harness.parameters(mode="session_normal")) as client:
            missing_arguments = _observe_request(missing_handle, "tree", locator=None)
            missing_arguments["sdk_outer_extra"] = "ignored"
            missing = _error(
                await client.call_tool(
                    TOOL_NAMES[6],
                    missing_arguments,
                )
            )
            assert missing["code"] == "session_not_found"
            assert missing["request_state"] == "not_sent"
            assert missing["session_handle"] is None
            assert missing["session_state"] is None

            handle = await _open(client, "closed-observation")
            await _close(client, handle)
            closed = _error(
                await client.call_tool(
                    TOOL_NAMES[6],
                    _observe_request(handle, "tree", locator=None),
                )
            )
            assert closed["code"] == "session_closed"
            assert closed["request_state"] == "not_sent"
            assert closed["session_handle"] == handle
            assert closed["session_state"] == "closed"

    anyio.run(scenario)
    names = [event["event"] for event in mcp_harness.events()]
    assert names.count("create_session") == 1
    assert names.count("session_quit") == 1


def test_element_validation_busy_close_race_and_no_replay(
    mcp_harness: McpHarness,
) -> None:
    started = threading.Event()
    release = threading.Event()
    with ElementProtocolService() as service:
        service.queue("source", ResponsePlan(started=started, release=release))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "controlled-race")
                invalid = _error(
                    await client.call_tool(
                        TOOL_NAMES[6],
                        _observe_request(
                            handle,
                            "tree",
                            locator=_locator(
                                "xpath",
                                "//target",
                                parent=_locator("id", "form"),
                            ),
                        ),
                    )
                )
                assert invalid["code"] == "unsupported_operation"
                assert invalid["operation_id"] is None
                assert invalid["request_state"] == "not_sent"
                assert invalid["session_handle"] == handle
                assert invalid["session_state"] == "active"

                first: list[CallToolResult] = []

                async def observe() -> None:
                    first.append(
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _observe_request(handle, "tree", locator=None),
                        )
                    )

                async with anyio.create_task_group() as group:
                    group.start_soon(observe)
                    await anyio.to_thread.run_sync(started.wait)
                    overlapping = _error(
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _observe_request(handle, "tree", locator=None),
                        )
                    )
                    closing = _error(
                        await client.call_tool(
                            TOOL_NAMES[5], _request(session_handle=handle)
                        )
                    )
                    assert overlapping["code"] == "session_busy"
                    assert closing["code"] == "session_busy"
                    assert overlapping["request_state"] == "not_sent"
                    assert closing["request_state"] == "not_sent"
                    release.set()
                _assert_observation(_structured(first[0]), "tree", "tree")
                await _close(client, handle)

        anyio.run(scenario)

    assert len(service.of_kind("source")) == 1
    assert len(service.of_kind("quit")) == 1


def test_cancelled_observation_waits_for_late_success_without_replay(
    mcp_harness: McpHarness,
) -> None:
    started = threading.Event()
    release = threading.Event()
    with ElementProtocolService() as service:
        service.queue("source", ResponsePlan(started=started, release=release))
        mcp_harness.config.write_text(
            f'[runtime]\nserver_url = "{service.url}"\n', encoding="utf-8"
        )

        async def scenario() -> None:
            async with Client(mcp_harness.parameters(mode="passthrough")) as client:
                handle = await _open(client, "controlled-cancel")
                scopes: list[anyio.CancelScope] = []

                async def observe() -> None:
                    with anyio.CancelScope() as scope:
                        scopes.append(scope)
                        await client.call_tool(
                            TOOL_NAMES[6],
                            _observe_request(handle, "tree", locator=None),
                        )

                async with anyio.create_task_group() as group:
                    group.start_soon(observe)
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

    assert len(service.of_kind("source")) == 1
    assert len(service.of_kind("quit")) == 1


@pytest.mark.parametrize("disconnect", ["eof", "broken_stdout"])
def test_inflight_observation_eof_and_broken_stdout_drain_once(
    mcp_harness: McpHarness,
    disconnect: str,
) -> None:
    started = threading.Event()
    release = threading.Event()
    with ElementProtocolService() as service:
        service.queue("source", ResponsePlan(started=started, release=release))
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
                        "clientInfo": {
                            "name": "observation-pipe-test",
                            "version": "1",
                        },
                    },
                }
            )
            initialized = receive(1)
            assert initialized["result"]["instructions"] == (
                "Local readiness, explicit Session lifecycle, Native observation, one "
                "caller-requested Element click, caller-requested Element text send, clear, "
                "or replace, and one caller-requested Device back; no automatic focus, "
                "submit, observation, verification, navigation, action chain, retry, replay, "
                "rollback, attach, recovery, or HTTP tools."
            )
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": TOOL_NAMES[3],
                        "arguments": _request(
                            device_id=f"controlled-{disconnect}", app_id="com.example"
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
                        "name": TOOL_NAMES[6],
                        "arguments": _observe_request(handle, "tree", locator=None),
                    },
                }
            )
            assert started.wait(timeout=5)
            if disconnect == "broken_stdout":
                stdout.close()
            stdin.close()
            release.set()
            assert process.wait(timeout=10) == 0
        finally:
            release.set()
            with contextlib.suppress(BrokenPipeError, ValueError):
                stdin.close()
            with contextlib.suppress(ValueError):
                stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    assert len(service.of_kind("source")) == 1
    assert len(service.of_kind("quit")) == 1
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (CANARY, SECRET_PATH, "controlled-", "Traceback"):
        assert forbidden not in stderr


def test_uncertain_observation_stdio_eof_exits_four_without_quit_or_replay(
    mcp_harness: McpHarness,
) -> None:
    locator_canary = f"{CANARY}-locator"
    with ElementProtocolService() as service:
        service.queue("source", ResponsePlan(disconnect=True))
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

        handle = ""
        try:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2026-07-28",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "uncertain-observation-eof",
                            "version": "1",
                        },
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
                            device_id="uncertain-observation-device",
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
                        "name": TOOL_NAMES[6],
                        "arguments": _observe_request(
                            handle,
                            "tree",
                            locator=_locator("id", locator_canary, raw_id=True),
                        ),
                    },
                }
            )
            failed = receive(3)
            error_text = failed["result"]["content"][0]["text"]
            error = json.loads(error_text.split("ACA_ERROR ", 1)[1])
            assert error["request_state"] == "response_unknown"
            assert error["session_handle"] == handle
            assert error["session_state"] == "uncertain"
            stdin.close()
            assert process.wait(timeout=10) == 4
            assert stdout.read() == b""
        finally:
            with contextlib.suppress(BrokenPipeError, ValueError):
                stdin.close()
            with contextlib.suppress(ValueError):
                stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    assert process.poll() == 4
    assert stdin.closed and stdout.closed
    assert len(service.of_kind("source")) == 1
    assert len(service.of_kind("quit")) == 0
    stderr = mcp_harness.stderr_file.read_text(encoding="utf-8")
    for forbidden in (
        handle,
        locator_canary,
        CANARY,
        SECRET_PATH,
        "uncertain-observation-device",
        "Traceback",
    ):
        assert forbidden not in stderr
