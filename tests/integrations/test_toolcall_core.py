from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import re
import sys
from contextlib import AbstractContextManager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Thread
from threading import Event as ThreadEvent
from typing import Any, cast

import anyio
import pytest
from mcp import Client

from appium_connect_agent import automation
from appium_connect_agent.automation import (
    CommandError,
    DeviceInfo,
    ResourceStateError,
    SessionInfo,
)
from appium_connect_agent.contracts import LocalSettings
from appium_connect_agent.integrations import (
    TOOL_CATALOG,
    Application,
    ApplicationError,
    JsonValue,
    SchemaProjectionError,
    SyncApplication,
    _application,
)
from appium_connect_agent.integrations._catalog import _project_schema
from appium_connect_agent.integrations._models import (
    CapabilityResult,
    RuntimeCheckResult,
    ToolCallCapabilityResult,
    ToolErrorData,
)
from appium_connect_agent.integrations._server import create_server
from appium_connect_agent.runtime import DiagnosticCheck, DiagnosticReport

from .conftest import McpHarness

_TOOL_NAMES = (
    "appium_capabilities_get",
    "appium_runtime_check",
    "appium_devices_list",
    "appium_session_open",
    "appium_session_status",
    "appium_session_close",
    "appium_ui_observe",
    "appium_element_click",
    "appium_element_text",
    "appium_device_back",
)
_INPUT_SCHEMA_SHA256 = {
    "appium.capabilities.get": "f53a26611f0f62347fe10b6e09ebea6a17d1040b5d069dc0af2d2d632b7818c4",
    "appium.runtime.check": "dbf076e1e7892a57ee7aa3a8ac641600630e7990841291246e0afef9ce8d40ee",
    "appium.devices.list": "0965356f84e112a1670527d6186c0f47ad95fb44c978343dfb163d363a219f55",
    "appium.session.open": "2fa7e03371dfe7b559de922759fe53a75db222bc4cb4c8360c021e5670bef7d5",
    "appium.session.status": "e7d106bc945981291193fd8ff9509cfc92f51d73cde71db5169b18422e3c66de",
    "appium.session.close": "702d080d90efbe49179f282489e8cc1ae537700c121f0479401ed69c04488ace",
    "appium.ui.observe": "310d885d7f095ed9c96624852413d1b6c8495abbd24088809aa492e669314cf9",
    "appium.element.click": "738b9045b86d6b75f97e3f601258240af5f635f08947b51880d4ccd6c9bf53d1",
    "appium.element.text": "109542fda082a344ed20ad2249f5eb66cadad88aeee5e51c136fb9380632dbd6",
    "appium.device.back": "f5b1986f683b37b974a549156afb4907bc66539228fc6930e10c2cb3bea6455d",
}
_OPENAI_SCHEMA_SHA256 = {
    "appium_capabilities_get": "5adb3919717cd87cc52ba5d526ac4ef34fe0980531f4b0f6e23a0fae09be46da",
    "appium_runtime_check": "999b923faa4dd034d53cd942d2cdd8d75add3ef57630e78672c4dfc83aa8d240",
    "appium_devices_list": "9f5d7d28e2de3e7fc2e34f33548dd1135f5dc682ea1367e4ef08c7e325723ce3",
    "appium_session_open": "2b631b47b21f9f4b3725777628e14c5e74c469cc81ff806b093f669bc69126da",
    "appium_session_status": "db08632cc7de86cb3edf049477b318fb79e80b90b8626bf631d28d62aaf697a5",
    "appium_session_close": "6b5b665bc41f8e09c804114963479e60387186819f28340e409598997c0c508d",
    "appium_ui_observe": "829193a3d9e9826e6e2e350a733e75e2b0db9ae1f5bbc808edb20121a3716a20",
    "appium_element_click": "2c87f917f75c4abf0da7f377c857a2c3a87f5a14148be6ba4282ee7bbd931bc5",
    "appium_element_text": "e50dae9c228824ffcd836f716c1d29221e73d73f7264d12306b611d645d0833a",
    "appium_device_back": "ed7a312d325d4adb48c05de9a3d16fb85eb6251c097f050267d0df59f34e0557",
}
_GOOGLE_SCHEMA_SHA256 = {
    "appium_capabilities_get": "9c74a083afb10b3e5f05f989dccd9ac4097be39a3916ada18093b1ad237eba67",
    "appium_runtime_check": "95eafda7633b0cd4de7b92d3cb1d40d58284440d5490e02ba55d375726ff722b",
    "appium_devices_list": "4df93d90ec8aed3cfc5ce3780e6b0e176d261e2cef28558fc29a20fc0fa2760b",
    "appium_session_open": "f00c7d780a910b1facab92e14fef959985a9ca8dfe1bd6b6c93aafd229f1639a",
    "appium_session_status": "f485e180967ffc88fad4bb5b3f62aff74fad0fb1833ae520ebbbc5d45389fe0b",
    "appium_session_close": "c5da739f0c6eaedc2ac392f050d9c3467c9ab515a5f02592920a124b901ad4a7",
    "appium_ui_observe": "0c14ed3ca32b67551a11ebae78fb067343cac700f0ff5d2dde926a3c824c4789",
    "appium_element_click": "4de91a77d5c915024e9f6145eb2871d7ed2c873d4ff870fb426cc603e9430759",
    "appium_element_text": "ac6d41cf457dd0fed064f016fd177ee021136e9acf2df4cc043efa4ecf1463b1",
    "appium_device_back": "65b4a1222ea4b9c70e1ee14d045ea2a142d80f8c36ea747f9e4f5b89e7dbad7a",
}
_OPENAI_KEYWORDS = {
    "$defs",
    "$ref",
    "definitions",
    "type",
    "title",
    "description",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "anyOf",
    "allOf",
    "enum",
    "const",
    "default",
    "format",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
}
_GOOGLE_KEYWORDS = {
    "$defs",
    "$ref",
    "type",
    "title",
    "description",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "prefixItems",
    "anyOf",
    "enum",
    "const",
    "default",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minItems",
    "maxItems",
    "minLength",
    "maxLength",
    "pattern",
}


def _resolve_schema_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    assert reference.startswith("#/")
    current: Any = root
    for token in reference[2:].split("/"):
        assert isinstance(current, dict)
        current = current[token.replace("~1", "/").replace("~0", "~")]
    assert isinstance(current, dict)
    return current


def _local_openai_schema(schema: dict[str, Any]) -> dict[str, Any]:
    root = deepcopy(schema)

    def convert(node: dict[str, Any]) -> dict[str, Any]:
        assert not (set(node) - _OPENAI_KEYWORDS)
        if "$ref" in node:
            assert isinstance(node["$ref"], str)
            _resolve_schema_ref(root, node["$ref"])
        if "additionalProperties" in node:
            assert node["additionalProperties"] is False
        for key in ("$defs", "definitions"):
            if key in node:
                assert isinstance(node[key], dict)
                node[key] = {name: convert(child) for name, child in node[key].items()}
        if node.get("type") == "object":
            node.setdefault("additionalProperties", False)
        properties = node.get("properties")
        if properties is not None:
            assert isinstance(properties, dict)
            node["required"] = list(properties)
            node["properties"] = {
                name: convert(child) for name, child in properties.items()
            }
        if "items" in node:
            assert isinstance(node["items"], dict)
            node["items"] = convert(node["items"])
        if "anyOf" in node:
            assert isinstance(node["anyOf"], list) and node["anyOf"]
            node["anyOf"] = [convert(child) for child in node["anyOf"]]
        if node.get("default", object()) is None:
            node.pop("default")
        reference = node.get("$ref")
        if reference and len(node) > 1:
            resolved = _resolve_schema_ref(root, reference)
            overlay = dict(node)
            overlay.pop("$ref")
            for key, value in overlay.items():
                assert key in {"title", "description", "default"} or (
                    key not in resolved or resolved[key] == value
                )
            return convert({**resolved, **overlay})
        return node

    return convert(root)


def _local_google_schema(schema: dict[str, Any]) -> dict[str, Any]:
    root = deepcopy(schema)
    nodes: list[dict[str, Any]] = []

    def convert(node: dict[str, Any]) -> dict[str, Any]:
        assert isinstance(node, dict) and not (set(node) - _GOOGLE_KEYWORDS)
        nodes.append(node)
        result = dict(node)
        if "const" in result:
            constant = result.pop("const")
            if "enum" in result:
                assert constant in result["enum"]
            result["enum"] = [constant]
        result.pop("default", None)
        for key in ("properties", "$defs"):
            if key in result:
                assert isinstance(result[key], dict)
                result[key] = {
                    name: convert(child) for name, child in result[key].items()
                }
        if "items" in result:
            assert isinstance(result["items"], dict)
            result["items"] = convert(result["items"])
        if "anyOf" in result:
            assert isinstance(result["anyOf"], list) and result["anyOf"]
            result["anyOf"] = [convert(child) for child in result["anyOf"]]
        return result

    result = convert(root)
    identities = {id(node) for node in nodes}
    for node in nodes:
        if "$ref" in node:
            assert id(_resolve_schema_ref(root, node["$ref"])) in identities
    return deepcopy(result)


def _schema_digest(schema: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class _Call:
    name: str
    arguments: dict[str, JsonValue]
    call_id: str = "provider-call-id"


@dataclass(frozen=True)
class _InputFailure:
    name: str
    call_id: str = "provider-call-id"
    message: str = "provider validation detail"


def _keys(value: JsonValue) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(child) for child in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_keys(child) for child in value), set())
    return set()


def _payload(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    assert isinstance(parsed, dict)
    return cast(dict[str, Any], parsed)


def test_catalog_is_fixed_and_fsq_projection_is_safe_and_fresh() -> None:
    assert TOOL_CATALOG.tool_names == _TOOL_NAMES
    assert len(TOOL_CATALOG.mcp_names) == 10
    assert all(re.fullmatch(r"[a-z0-9_]{1,32}", name) for name in _TOOL_NAMES)

    for name in _TOOL_NAMES:
        schema = TOOL_CATALOG.fsq_schema(name)
        assert not ({"oneOf", "discriminator", "uniqueItems"} & _keys(schema))

    observe = TOOL_CATALOG.fsq_schema("appium_ui_observe")
    assert "anyOf" in _keys(observe)
    observe.clear()
    assert TOOL_CATALOG.fsq_schema("appium_ui_observe")


_FSQ_SOURCE_SHA256 = {
    "fsq_agent/agent_engine/_schema.py": (
        "2f3a680956235699e3deb2ffd2cc768bb979c71afbfd41676500a8bb6f3326d8"
    ),
    "fsq_agent/agent_engine/_google_gemini_schema.py": (
        "de4f4820e5bb1418bb61f4d554ba59d94bbd202b28ac06caa5c64cdbaff0025e"
    ),
}


def _resolve_fsq_repo() -> Path:
    configured = os.environ.get("FSQ_REPO_PATH")
    if configured is not None:
        selected = Path(configured).expanduser().resolve()
        if not selected.is_dir():
            pytest.fail(f"FSQ_REPO_PATH is not a directory: {selected}")
        return selected

    repo_root = Path(__file__).resolve().parents[2]
    candidates = (
        repo_root.parent / "FSQ",
        repo_root.parent.parent / "FSQ",
    )
    for candidate in candidates:
        if candidate.is_dir():
            selected = candidate.resolve()
            assert selected in tuple(path.resolve() for path in candidates)
            return selected
    pytest.skip("Sibling FSQ checkout not present in isolated CI environment")


def test_fsq_backend_schema_transforms_match_locked_digests() -> None:
    projected = {name: TOOL_CATALOG.fsq_schema(name) for name in _TOOL_NAMES}
    openai = {
        name: _schema_digest(_local_openai_schema(schema))
        for name, schema in projected.items()
    }
    google = {
        name: _schema_digest(_local_google_schema(schema))
        for name, schema in projected.items()
    }
    assert openai == _OPENAI_SCHEMA_SHA256
    assert google == _GOOGLE_SCHEMA_SHA256

    fsq_repo = _resolve_fsq_repo()
    source_files = {
        relative: (fsq_repo / relative).resolve() for relative in _FSQ_SOURCE_SHA256
    }
    for relative, source_file in source_files.items():
        if not source_file.is_file():
            pytest.fail(f"FSQ converter source is missing: {source_file}")
        digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
        assert digest == _FSQ_SOURCE_SHA256[relative]

    saved_modules = {
        name: module
        for name, module in tuple(sys.modules.items())
        if name == "fsq_agent" or name.startswith("fsq_agent.")
    }
    for name in saved_modules:
        del sys.modules[name]
    sys.path.insert(0, str(fsq_repo))
    try:
        importlib.invalidate_caches()
        strict_module = importlib.import_module("fsq_agent.agent_engine._schema")
        google_module = importlib.import_module(
            "fsq_agent.agent_engine._google_gemini_schema"
        )
        strict_origin = strict_module.__file__
        google_origin = google_module.__file__
        assert strict_origin is not None
        assert google_origin is not None
        assert (
            Path(strict_origin).resolve()
            == source_files["fsq_agent/agent_engine/_schema.py"]
        )
        assert (
            Path(google_origin).resolve()
            == source_files["fsq_agent/agent_engine/_google_gemini_schema.py"]
        )
        actual_openai = {
            name: _schema_digest(strict_module.ensure_strict_json_schema(schema))
            for name, schema in projected.items()
        }
        actual_google = {
            name: _schema_digest(google_module.google_schema(schema))
            for name, schema in projected.items()
        }
    finally:
        sys.path.pop(0)
        for name in tuple(sys.modules):
            if name == "fsq_agent" or name.startswith("fsq_agent."):
                del sys.modules[name]
        sys.modules.update(saved_modules)
    assert actual_openai == _OPENAI_SCHEMA_SHA256
    assert actual_google == _GOOGLE_SCHEMA_SHA256


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "unevaluatedProperties": False},
        {
            "oneOf": [
                {"properties": {"kind": {"const": "same"}}},
                {"properties": {"kind": {"const": "same"}}},
            ],
            "discriminator": {"propertyName": "kind"},
        },
        {"type": "array", "uniqueItems": True},
    ],
)
def test_fsq_projection_rejects_unsafe_schema_shapes(
    schema: dict[str, Any],
) -> None:
    with pytest.raises(SchemaProjectionError):
        _project_schema(schema, root=schema, path=())


def test_generated_mcp_input_schemas_match_pre_cutover_bytes(tmp_path: Path) -> None:
    async def scenario() -> None:
        application = Application(LocalSettings(), tmp_path / "adb", surface="mcp")
        async with Client(create_server(application)) as client:
            tools = (await client.list_tools()).tools
        observed = {
            tool.name: hashlib.sha256(
                json.dumps(
                    tool.input_schema,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            for tool in tools
        }
        assert observed == _INPUT_SCHEMA_SHA256

    anyio.run(scenario)


def test_tool_bindings_execute_capability_and_use_surface_truth(tmp_path: Path) -> None:
    async def scenario() -> None:
        application = Application(LocalSettings(), tmp_path / "adb", surface="toolcall")
        bindings = application.tool_bindings()
        assert tuple(binding.name for binding in bindings) == _TOOL_NAMES
        assert len({id(binding.parameters_schema) for binding in bindings}) == 10

        result = _payload(
            await bindings[0].invoke(
                _Call("appium_capabilities_get", {"schema_version": 1})
            )
        )
        assert result["data"]["integration_form"] == "toolcall"
        assert result["data"]["transport"] == "in_process"
        assert result["data"]["protocol_target"] is None
        assert tuple(result["data"]["tools"]) == _TOOL_NAMES
        assert "no_cli_product" not in result["data"]["limitations"]
        await application.aclose()
        await application.aclose()

    anyio.run(scenario)


def test_toolcall_validation_errors_are_structured_and_redacted(tmp_path: Path) -> None:
    async def scenario() -> None:
        application = Application(LocalSettings(), tmp_path / "adb", surface="toolcall")
        binding = application.tool_bindings()[0]

        malformed = _payload(
            await binding.invoke(_Call(binding.name, {"schema_version": True}))
        )
        provider_failure = _payload(
            await binding.on_invalid_input(
                _InputFailure(binding.name, message="/private/secret device-123")
            )
        )
        wrong_binding = _payload(
            await binding.invoke(_Call("appium_runtime_check", {"schema_version": 1}))
        )
        for error in (malformed, provider_failure, wrong_binding):
            assert error["code"] == "invalid_argument"
            assert error["request_state"] == "not_sent"
            assert error["cleanup_status"] == "not_needed"
            assert "/private/secret" not in json.dumps(error)
            assert "device-123" not in json.dumps(error)
        assert (
            len(
                {
                    malformed["call_id"],
                    provider_failure["call_id"],
                    wrong_binding["call_id"],
                }
            )
            == 3
        )
        await application.aclose()

    anyio.run(scenario)


@pytest.mark.parametrize(
    "interruption",
    [asyncio.CancelledError(), KeyboardInterrupt(), SystemExit(7)],
)
def test_toolcall_callback_preserves_interruption_and_maps_internal_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interruption: BaseException,
) -> None:
    async def scenario() -> None:
        application = Application(LocalSettings(), tmp_path / "adb", surface="toolcall")
        binding = application.tool_bindings()[0]
        call = _Call(binding.name, {"schema_version": 1})

        async def interrupted(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            raise interruption

        monkeypatch.setattr(application, "dispatch", interrupted)
        with pytest.raises(type(interruption)) as caught:
            await binding.invoke(call)
        assert caught.value is interruption

        async def failed(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            raise RuntimeError("/private/secret device-123")

        monkeypatch.setattr(application, "dispatch", failed)
        internal = _payload(await binding.invoke(call))
        assert internal["code"] == "internal_error"
        assert internal["request_state"] is None
        assert internal["cleanup_status"] == "unknown"
        assert "/private/secret" not in json.dumps(internal)
        assert "device-123" not in json.dumps(internal)
        await application.aclose()

    anyio.run(scenario)


def test_closed_application_rejects_dispatch(tmp_path: Path) -> None:
    async def scenario() -> None:
        application = Application(LocalSettings(), tmp_path / "adb", surface="toolcall")
        await application.aclose()
        with pytest.raises(ApplicationError) as caught:
            await application.dispatch("appium_capabilities_get", {"schema_version": 1})
        assert caught.value.data.code == "application_closed"

    anyio.run(scenario)


def test_sync_application_owns_portal_and_application(tmp_path: Path) -> None:
    application = SyncApplication(LocalSettings(), tmp_path / "adb")
    with application:
        result = application.dispatch("appium_capabilities_get", {"schema_version": 1})
        assert result.model_dump(mode="json")["data"]["integration_form"] == "toolcall"
        with pytest.raises(RuntimeError, match="already entered"):
            application.__enter__()
    application.close()
    with pytest.raises(RuntimeError, match="not entered"):
        application.dispatch("appium_capabilities_get", {"schema_version": 1})


def test_surface_guards_prevent_registry_cross_use(tmp_path: Path) -> None:
    async def scenario() -> None:
        mcp = Application(LocalSettings(), tmp_path / "adb", surface="mcp")
        toolcall = Application(LocalSettings(), tmp_path / "adb", surface="toolcall")
        with pytest.raises(ValueError, match="ToolCall bindings require"):
            mcp.tool_bindings()
        with pytest.raises(ValueError, match="dispatch requires"):
            await mcp.dispatch("appium_capabilities_get", {"schema_version": 1})
        with pytest.raises(ValueError, match="MCP server requires"):
            create_server(toolcall)
        await mcp.aclose()
        await toolcall.aclose()

    anyio.run(scenario)


def test_application_error_text_and_repr_never_render_payload(tmp_path: Path) -> None:
    application = Application(LocalSettings(), tmp_path / "adb", surface="toolcall")
    sensitive = "private_secret_device-123"
    session_handle = "s_" + ("a" * 32)
    data = ToolErrorData(
        schema_version=1,
        call_id="c_aaaaaaaaaaaaaaaaaaaaaa",
        code="internal_error",
        operation_id=sensitive,
        request_state=None,
        completed_steps=(),
        cleanup_status="unknown",
        cleanup_error_count=0,
        warnings=(),
        session_handle=session_handle,
        session_state="uncertain",
    )
    error = ApplicationError(data)
    assert str(error) == "application_error:internal_error"
    assert repr(error) == (
        "ApplicationError(code='internal_error', call_id='c_aaaaaaaaaaaaaaaaaaaaaa')"
    )
    assert sensitive not in str(error)
    assert sensitive not in repr(error)
    assert session_handle not in str(error)
    assert session_handle not in repr(error)
    assert error.data.operation_id == sensitive
    anyio.run(application.aclose)


@pytest.mark.parametrize(
    "schema",
    [
        {"$ref": 1},
        {"$ref": "external.json"},
        {"$ref": "#/$defs/missing", "$defs": {}},
        {"type": True},
        {"type": []},
        {"type": ["string", "string"]},
        {"additionalProperties": {}},
        {"properties": {1: {"type": "string"}}},
        {"properties": {"x": {"type": "string"}}, "required": ["x", "x"]},
        {"properties": {"x": {"type": "string"}}, "required": ["y"]},
        {"minLength": True},
        {"minItems": -1},
        {"minLength": 2, "maxLength": 1},
        {"minimum": 2, "maximum": 1},
        {"minimum": float("nan")},
        {"minimum": 10**400},
        {"format": "unknown"},
        {"pattern": "["},
        {"enum": []},
        {"enum": ["duplicate", "duplicate"]},
        {"enum": ["allowed"], "const": "denied"},
        {"default": {"not-json"}},
        {
            "oneOf": [
                {"properties": {"kind": {"const": 1}}},
                {"properties": {"kind": {"const": 1.0}}},
            ],
            "discriminator": {"propertyName": "kind"},
        },
        {
            "oneOf": [
                {"properties": {"kind": {"const": 10**400}}},
                {"properties": {"kind": {"const": 2}}},
            ],
            "discriminator": {"propertyName": "kind"},
        },
    ],
)
def test_fsq_projection_rejects_malformed_scalar_and_reference_shapes(
    schema: dict[str, Any],
) -> None:
    with pytest.raises(SchemaProjectionError):
        _project_schema(schema, root=schema, path=())


def test_discriminator_identity_distinguishes_boolean_from_number() -> None:
    schema = {
        "oneOf": [
            {"properties": {"kind": {"const": True}}},
            {"properties": {"kind": {"const": 1}}},
        ],
        "discriminator": {"propertyName": "kind"},
    }
    assert "anyOf" in _project_schema(schema, root=schema, path=())


@dataclass
class _LowerState:
    calls: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)
    sessions: list[_FakeSession] = field(default_factory=list)
    quit_started: ThreadEvent | None = None
    quit_release: ThreadEvent | None = None


@dataclass(frozen=True)
class _FakeObservation:
    operation_id: str
    kind: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema": 1,
                "kind": self.kind,
                "operation_id": self.operation_id,
            },
            separators=(",", ":"),
        )


class _FakeRuntime:
    def __init__(self, state: _LowerState) -> None:
        self._state = state

    @staticmethod
    def _report() -> DiagnosticReport:
        return DiagnosticReport(
            operation_id="op_runtime_fake",
            observed_at=datetime(2026, 11, 13, tzinfo=UTC),
            checks=(
                DiagnosticCheck(
                    "service", "pass", "service_ready", ("controlled",), None
                ),
            ),
        )

    def diagnose(self, *, control: object) -> DiagnosticReport:
        del control
        self._state.calls.append("runtime.diagnose")
        return self._report()

    def connect(self, *, control: object) -> AbstractContextManager[Any]:
        del control
        self._state.calls.append("runtime.connect")
        state = self._state
        report = self._report()

        class Scope(AbstractContextManager[Any]):
            def __enter__(self) -> Any:
                state.calls.append("runtime.enter")
                return type(
                    "Connection",
                    (),
                    {
                        "ownership": "external",
                        "report": report,
                        "appium_version": "3.7.0",
                        "compatibility": "declared_compatible",
                    },
                )()

            def __exit__(self, *exc_info: object) -> None:
                del exc_info
                state.calls.append("runtime.exit")

        return Scope()


class _FakeElement:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def inspect(self, *, attributes: object, control: object) -> _FakeObservation:
        del attributes, control
        self._session._fail("observe")
        self._session._state.calls.append("element.inspect")
        return _FakeObservation("op_attributes_fake", "element")

    def inspect_structure(self, *, scope: object, control: object) -> _FakeObservation:
        del scope, control
        self._session._fail("observe")
        self._session._state.calls.append("element.inspect_structure")
        return _FakeObservation("op_structure_fake", "structure")

    def click(self, *, wait_timeout_seconds: float, control: object) -> None:
        del wait_timeout_seconds, control
        self._session._fail("click")
        self._session._state.calls.append("element.click")

    def send_keys(
        self, text: str, *, wait_timeout_seconds: float, control: object
    ) -> None:
        del text, wait_timeout_seconds, control
        self._session._fail("text")
        self._session._state.calls.append("element.send")

    def clear(self, *, wait_timeout_seconds: float, control: object) -> None:
        del wait_timeout_seconds, control
        self._session._fail("text")
        self._session._state.calls.append("element.clear")

    def replace_element_value(
        self, text: str, *, wait_timeout_seconds: float, control: object
    ) -> None:
        del text, wait_timeout_seconds, control
        self._session._fail("text")
        self._session._state.calls.append("element.replace")


class _FakeSession:
    def __init__(
        self, state: _LowerState, device_id: str, target_app_id: str | None
    ) -> None:
        self._state = state
        self.device_id = device_id
        self.target_app_id = target_app_id
        self.state = "active"
        self.busy = False
        self.device = self

    def _fail(self, operation: str) -> None:
        mode = self._state.failures.pop(operation, None)
        if mode is None:
            return
        self.busy = False
        if mode == "unknown":
            self.state = "uncertain"
            raise ResourceStateError(
                f"{operation}_unknown",
                f"op_{operation}_unknown",
                "response_unknown",
                session=cast(automation.Session, self),
                completed_steps=(f"{operation}_requested",),
            )
        raise CommandError(
            f"{operation}_failed",
            f"op_{operation}_known",
            "response_received",
            completed_steps=(f"{operation}_requested",),
        )

    def session_info(self) -> SessionInfo:
        self._state.calls.append("session.info")
        return SessionInfo(
            id="automation-fake",
            appium_session_id="appium-fake",
            device_id=self.device_id,
            target_app_id=self.target_app_id,
            state=cast(Any, self.state),
            busy=self.busy,
        )

    def element(self, *args: object, **kwargs: object) -> _FakeElement:
        del args, kwargs
        self._state.calls.append("session.element")
        return _FakeElement(self)

    def observe_tree(self, *, parent: object, control: object) -> _FakeObservation:
        del parent, control
        self._fail("observe")
        self._state.calls.append("session.observe_tree")
        return _FakeObservation("op_tree_fake", "tree")

    def back(self, *, control: object) -> None:
        del control
        self._fail("back")
        self._state.calls.append("device.back")

    def quit(self, *, control: object) -> None:
        del control
        self._state.calls.append("session.quit")
        self.busy = True
        if self._state.quit_started is not None:
            self._state.quit_started.set()
        if self._state.quit_release is not None and not self._state.quit_release.wait(
            timeout=2
        ):
            raise RuntimeError("controlled quit barrier timed out")
        self._fail("close")
        self.state = "closed"
        self.busy = False


def _install_lower_fakes(monkeypatch: pytest.MonkeyPatch, state: _LowerState) -> None:
    monkeypatch.setattr(_application, "Runtime", lambda settings: _FakeRuntime(state))

    def list_devices(
        adb_executable: Path, *, control: object
    ) -> tuple[DeviceInfo, ...]:
        del adb_executable, control
        state.calls.append("devices.list")
        return (DeviceInfo("device-1", "Pixel", "connected"),)

    def create_session(
        connection: object,
        device_id: str,
        **options: object,
    ) -> _FakeSession:
        del connection
        state.calls.append("session.create")
        target = cast(str | None, options.get("app_id"))
        session = _FakeSession(state, device_id, target)
        state.sessions.append(session)
        session._fail("open")
        return session

    monkeypatch.setattr(_application, "list_devices", list_devices)
    monkeypatch.setattr(_application, "create_session", create_session)


async def _invoke_binding(
    bindings: dict[str, Any], name: str, arguments: dict[str, JsonValue]
) -> dict[str, Any]:
    return _payload(await bindings[name].invoke(_Call(name, arguments)))


def _bindings(application: Application) -> dict[str, Any]:
    return {binding.name: binding for binding in application.tool_bindings()}


_VALID_ARGUMENTS: dict[str, dict[str, JsonValue]] = {
    "appium_capabilities_get": {"schema_version": 1},
    "appium_runtime_check": {
        "schema_version": 1,
        "mode": "static",
        "timeout_seconds": 10.0,
    },
    "appium_devices_list": {"schema_version": 1, "timeout_seconds": 30.0},
    "appium_session_open": {"schema_version": 1, "device_id": "device-1"},
    "appium_session_status": {
        "schema_version": 1,
        "session_handle": "s_" + ("a" * 32),
    },
    "appium_session_close": {
        "schema_version": 1,
        "session_handle": "s_" + ("a" * 32),
        "timeout_seconds": 60.0,
    },
    "appium_ui_observe": {
        "schema_version": 1,
        "session_handle": "s_" + ("a" * 32),
        "mode": "tree",
        "locator": None,
        "timeout_seconds": 90.0,
    },
    "appium_element_click": {
        "schema_version": 1,
        "session_handle": "s_" + ("a" * 32),
        "locator": {"by": "id", "value": "target"},
        "wait_timeout_seconds": 15.0,
        "timeout_seconds": 90.0,
    },
    "appium_element_text": {
        "schema_version": 1,
        "session_handle": "s_" + ("a" * 32),
        "locator": {"by": "id", "value": "target"},
        "intent": "clear",
        "wait_timeout_seconds": 15.0,
        "timeout_seconds": 90.0,
    },
    "appium_device_back": {
        "schema_version": 1,
        "session_handle": "s_" + ("a" * 32),
        "timeout_seconds": 90.0,
    },
}


def test_real_toolcall_lifecycle_runs_all_ten_state_machines(
    mcp_harness: McpHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _LowerState()
    _install_lower_fakes(monkeypatch, state)

    async def scenario() -> None:
        application = Application(LocalSettings(), mcp_harness.adb, surface="toolcall")
        bindings = _bindings(application)
        capability = await _invoke_binding(
            bindings, "appium_capabilities_get", {"schema_version": 1}
        )
        assert capability["data"]["integration_form"] == "toolcall"
        assert capability["data"]["transport"] == "in_process"
        assert "no_cli_product" not in capability["data"]["limitations"]

        for mode in ("static", "external_connection"):
            runtime = await _invoke_binding(
                bindings,
                "appium_runtime_check",
                {"schema_version": 1, "mode": mode, "timeout_seconds": 10},
            )
            assert runtime["data"]["mode"] == mode
        devices = await _invoke_binding(
            bindings,
            "appium_devices_list",
            {"schema_version": 1, "timeout_seconds": 30},
        )
        assert devices["data"]["count"] == 1

        opened = await _invoke_binding(
            bindings,
            "appium_session_open",
            {"schema_version": 1, "device_id": "device-1", "app_id": "demo"},
        )
        handle = cast(str, opened["data"]["session_handle"])
        assert handle.startswith("s_")
        assert opened["data"]["ownership"] == "toolcall"
        assert opened["data"]["session_state"] == "active"
        status = await _invoke_binding(
            bindings,
            "appium_session_status",
            {"schema_version": 1, "session_handle": handle},
        )
        assert status["data"]["session_state"] == "active"

        locator: dict[str, JsonValue] = {"by": "id", "value": "target"}
        observations: tuple[dict[str, JsonValue], ...] = (
            {"mode": "tree", "locator": None},
            {"mode": "attributes", "locator": locator, "attributes": ["text"]},
            {
                "mode": "structure",
                "locator": locator,
                "structure_scope": "target",
            },
        )
        for request in observations:
            observed = await _invoke_binding(
                bindings,
                "appium_ui_observe",
                {
                    "schema_version": 1,
                    "session_handle": handle,
                    "timeout_seconds": 90.0,
                    **request,
                },
            )
            assert observed["data"]["mode"] == request["mode"]

        clicked = await _invoke_binding(
            bindings,
            "appium_element_click",
            {
                "schema_version": 1,
                "session_handle": handle,
                "locator": locator,
                "wait_timeout_seconds": 15.0,
                "timeout_seconds": 90.0,
            },
        )
        assert clicked["data"]["action"] == "click"
        for intent, text in (("send", "value"), ("clear", None), ("replace", "new")):
            arguments: dict[str, JsonValue] = {
                "schema_version": 1,
                "session_handle": handle,
                "locator": locator,
                "intent": intent,
                "wait_timeout_seconds": 15.0,
                "timeout_seconds": 90.0,
            }
            if text is not None:
                arguments["text"] = text
            changed = await _invoke_binding(bindings, "appium_element_text", arguments)
            assert changed["data"]["intent"] == intent
        backed = await _invoke_binding(
            bindings,
            "appium_device_back",
            {
                "schema_version": 1,
                "session_handle": handle,
                "timeout_seconds": 90.0,
            },
        )
        assert backed["data"]["action"] == "back"

        for name in _TOOL_NAMES:
            with pytest.raises(ApplicationError) as caught:
                await application.dispatch(name, {"schema_version": True})
            assert caught.value.data.code == "invalid_argument"

        closed = await _invoke_binding(
            bindings,
            "appium_session_close",
            {
                "schema_version": 1,
                "session_handle": handle,
                "timeout_seconds": 60.0,
            },
        )
        assert closed["data"]["session_state"] == "closed"
        tombstone = await _invoke_binding(
            bindings,
            "appium_session_status",
            {"schema_version": 1, "session_handle": handle},
        )
        assert tombstone["data"]["session_state"] == "closed"
        await application.aclose()

    anyio.run(scenario)
    assert state.calls.count("runtime.diagnose") == 1
    assert state.calls.count("runtime.connect") == 2
    assert state.calls.count("devices.list") == 1
    assert state.calls.count("session.create") == 1
    assert state.calls.count("session.quit") == 1
    assert {"element.send", "element.clear", "element.replace"}.issubset(state.calls)


def test_real_tool_errors_preserve_only_owned_session_resources(
    mcp_harness: McpHarness,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def open_failure(callback: bool) -> tuple[dict[str, Any], str, str]:
        state = _LowerState(failures={"open": "unknown"})
        _install_lower_fakes(monkeypatch, state)
        application = Application(LocalSettings(), mcp_harness.adb, surface="toolcall")
        arguments: dict[str, JsonValue] = {
            "schema_version": 1,
            "device_id": "device-1",
        }
        if callback:
            payload = await _invoke_binding(
                _bindings(application), "appium_session_open", arguments
            )
            text = ""
            representation = ""
        else:
            with pytest.raises(ApplicationError) as caught:
                await application.dispatch("appium_session_open", arguments)
            payload = caught.value.data.model_dump(mode="json")
            text = str(caught.value)
            representation = repr(caught.value)
        await application.aclose()
        return payload, text, representation

    async def operation_failure(operation: str, mode: str) -> dict[str, Any]:
        state = _LowerState()
        _install_lower_fakes(monkeypatch, state)
        application = Application(LocalSettings(), mcp_harness.adb, surface="toolcall")
        bindings = _bindings(application)
        opened = await _invoke_binding(
            bindings,
            "appium_session_open",
            {"schema_version": 1, "device_id": "device-1"},
        )
        handle = cast(str, opened["data"]["session_handle"])
        state.failures[operation] = mode
        locator: dict[str, JsonValue] = {"by": "id", "value": "target"}
        requests: dict[str, tuple[str, dict[str, JsonValue]]] = {
            "observe": (
                "appium_ui_observe",
                {
                    "schema_version": 1,
                    "session_handle": handle,
                    "mode": "tree",
                    "locator": None,
                    "timeout_seconds": 90.0,
                },
            ),
            "click": (
                "appium_element_click",
                {
                    "schema_version": 1,
                    "session_handle": handle,
                    "locator": locator,
                    "wait_timeout_seconds": 15.0,
                    "timeout_seconds": 90.0,
                },
            ),
            "text": (
                "appium_element_text",
                {
                    "schema_version": 1,
                    "session_handle": handle,
                    "locator": locator,
                    "intent": "clear",
                    "wait_timeout_seconds": 15.0,
                    "timeout_seconds": 90.0,
                },
            ),
            "back": (
                "appium_device_back",
                {
                    "schema_version": 1,
                    "session_handle": handle,
                    "timeout_seconds": 90.0,
                },
            ),
            "close": (
                "appium_session_close",
                {
                    "schema_version": 1,
                    "session_handle": handle,
                    "timeout_seconds": 60.0,
                },
            ),
        }
        tool_name, arguments = requests[operation]
        payload = await _invoke_binding(bindings, tool_name, arguments)
        assert payload["session_handle"] == handle
        await application.aclose()
        return payload

    async def no_resource_failures() -> tuple[dict[str, Any], ...]:
        state = _LowerState()
        _install_lower_fakes(monkeypatch, state)
        application = Application(LocalSettings(), mcp_harness.adb, surface="toolcall")
        bindings = _bindings(application)
        missing = await _invoke_binding(
            bindings,
            "appium_session_status",
            {"schema_version": 1, "session_handle": "s_" + ("a" * 32)},
        )
        invalid = await _invoke_binding(
            bindings,
            "appium_capabilities_get",
            {"schema_version": True},
        )
        provider = _payload(
            await bindings["appium_capabilities_get"].on_invalid_input(
                _InputFailure("appium_capabilities_get")
            )
        )

        async def fail_dispatch(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            raise RuntimeError("private internal detail")

        monkeypatch.setattr(application, "dispatch", fail_dispatch)
        internal = await _invoke_binding(
            bindings,
            "appium_capabilities_get",
            {"schema_version": 1},
        )
        await application.aclose()
        return missing, invalid, provider, internal

    caplog.clear()
    direct, text, representation = anyio.run(open_failure, False)
    retained_handle = cast(str, direct["session_handle"])
    assert direct["session_state"] == "uncertain"
    assert retained_handle not in text
    assert retained_handle not in representation
    assert retained_handle not in caplog.text
    callback, _, _ = anyio.run(open_failure, True)
    callback_handle = cast(str, callback["session_handle"])
    assert callback_handle
    assert callback["session_state"] == "uncertain"
    assert callback_handle not in caplog.text

    for operation in ("observe", "click", "text", "back", "close"):
        known = anyio.run(operation_failure, operation, "known")
        unknown = anyio.run(operation_failure, operation, "unknown")
        assert known["session_state"] == "active"
        assert unknown["session_state"] == "uncertain"

    for payload in anyio.run(no_resource_failures):
        assert (payload["session_handle"], payload["session_state"]) == (None, None)


class _MismatchedResultApplication(Application):
    def capabilities(self) -> CapabilityResult:
        return cast(CapabilityResult, RuntimeCheckResult.model_construct())


def test_dispatch_rejects_unexpected_catalog_result_type(tmp_path: Path) -> None:
    async def scenario() -> None:
        application = _MismatchedResultApplication(
            LocalSettings(), tmp_path / "adb", surface="toolcall"
        )
        with pytest.raises(ApplicationError) as caught:
            await application.dispatch("appium_capabilities_get", {"schema_version": 1})
        assert caught.value.data.code == "internal_error"
        assert caught.value.data.request_state is None
        assert caught.value.data.cleanup_status == "unknown"
        await application.aclose()

    anyio.run(scenario)


def test_closed_application_blocks_all_tools_without_lower_calls(
    mcp_harness: McpHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _LowerState()
    _install_lower_fakes(monkeypatch, state)

    async def scenario() -> None:
        application = Application(LocalSettings(), mcp_harness.adb, surface="toolcall")
        bindings = _bindings(application)
        await application.aclose()
        for name in _TOOL_NAMES:
            payload = await _invoke_binding(bindings, name, _VALID_ARGUMENTS[name])
            assert payload["code"] == "application_closed"

    anyio.run(scenario)
    assert state.calls == []


def test_concurrent_aclose_waits_for_one_real_session_quit(
    mcp_harness: McpHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = ThreadEvent()
    release = ThreadEvent()
    state = _LowerState(quit_started=started, quit_release=release)
    _install_lower_fakes(monkeypatch, state)

    async def scenario() -> None:
        application = Application(LocalSettings(), mcp_harness.adb, surface="toolcall")
        await _invoke_binding(
            _bindings(application),
            "appium_session_open",
            {"schema_version": 1, "device_id": "device-1"},
        )
        outcomes: list[bool] = []

        async def close() -> None:
            await application.aclose()
            outcomes.append(application.shutdown_degraded)

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(close)
            tasks.start_soon(close)
            observed = await anyio.to_thread.run_sync(lambda: started.wait(timeout=2))
            assert observed
            release.set()
        assert outcomes == [False, False]

    anyio.run(scenario)
    assert state.calls.count("session.quit") == 1


def test_sync_application_concurrent_enter_and_close_are_serialized(
    tmp_path: Path,
) -> None:
    application = SyncApplication(LocalSettings(), tmp_path / "adb")
    enter_barrier = Barrier(2)
    entered: list[SyncApplication] = []
    enter_errors: list[BaseException] = []

    def enter() -> None:
        enter_barrier.wait()
        try:
            entered.append(application.__enter__())
        except BaseException as error:
            enter_errors.append(error)

    enter_threads = [Thread(target=enter) for _ in range(2)]
    for thread in enter_threads:
        thread.start()
    for thread in enter_threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert entered == [application]
    assert len(enter_errors) == 1
    assert isinstance(enter_errors[0], RuntimeError)
    assert str(enter_errors[0]) == "SyncApplication is already entered"

    close_barrier = Barrier(2)
    close_errors: list[BaseException] = []

    def close() -> None:
        close_barrier.wait()
        try:
            application.close()
        except BaseException as error:
            close_errors.append(error)

    close_threads = [Thread(target=close) for _ in range(2)]
    for thread in close_threads:
        thread.start()
    for thread in close_threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert close_errors == []


def test_cancelled_close_completes_and_remains_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        application = Application(LocalSettings(), tmp_path / "adb", surface="toolcall")
        started = anyio.Event()
        release = anyio.Event()

        async def shutdown() -> None:
            started.set()
            await release.wait()

        monkeypatch.setattr(application._workers, "shutdown", shutdown)

        async def cancel_after_start(scope: anyio.CancelScope) -> None:
            await started.wait()
            release.set()
            scope.cancel()

        with anyio.CancelScope() as scope:
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(cancel_after_start, scope)
                await application.aclose()
        with pytest.raises(ApplicationError) as caught:
            await application.dispatch("appium_capabilities_get", {"schema_version": 1})
        assert caught.value.data.code == "application_closed"
        await application.aclose()

    anyio.run(scenario)


def test_sync_application_serializes_dispatch_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sync_application = SyncApplication(LocalSettings(), tmp_path / "adb")
    sync_application.__enter__()
    application = cast(Application, sync_application._application)
    entered = ThreadEvent()
    release = ThreadEvent()

    async def dispatch(*args: object, **kwargs: object) -> ToolCallCapabilityResult:
        del args, kwargs
        entered.set()
        await anyio.to_thread.run_sync(release.wait)
        return ToolCallCapabilityResult.model_construct()

    monkeypatch.setattr(application, "dispatch", dispatch)
    dispatch_thread = Thread(
        target=lambda: sync_application.dispatch(
            "appium_capabilities_get", {"schema_version": 1}
        )
    )
    close_thread = Thread(target=sync_application.close)
    dispatch_thread.start()
    assert entered.wait(timeout=2)
    close_thread.start()
    assert close_thread.is_alive()
    release.set()
    dispatch_thread.join(timeout=2)
    close_thread.join(timeout=2)
    assert not dispatch_thread.is_alive()
    assert not close_thread.is_alive()
    sync_application.close()
