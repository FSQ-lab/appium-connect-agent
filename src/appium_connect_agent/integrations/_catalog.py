"""Protocol-neutral catalog for the fixed Integrations tool surface."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from pydantic import BaseModel, TypeAdapter, ValidationError

from ._models import (
    AttributesObserveRequest,
    CapabilitiesRequest,
    DeviceBackRequest,
    DeviceBackResult,
    DeviceListRequest,
    DeviceListResult,
    ElementClickRequest,
    ElementClickResult,
    ElementGestureRequest,
    ElementGestureResult,
    ElementImeActionRequest,
    ElementImeActionResult,
    ElementTextRequest,
    ElementTextResult,
    McpCapabilityResult,
    McpToolNames,
    ObservationResult,
    ObserveRequest,
    RuntimeCheckRequest,
    RuntimeCheckResult,
    SessionCloseRequest,
    SessionCloseResult,
    SessionOpenRequest,
    SessionOpenResult,
    SessionStatusRequest,
    SessionStatusResult,
    ToolCallToolNames,
)

if TYPE_CHECKING:
    from ._application import Application

JsonValue: TypeAlias = (
    str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None
)
_Invoke = Callable[["Application", BaseModel], Awaitable[BaseModel]]
_TOOL_NAME = re.compile(r"^[a-z0-9_]{1,32}$")
_FSQ_KEYWORDS = frozenset(
    {
        "$defs",
        "$ref",
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "anyOf",
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
        "minItems",
        "maxItems",
    }
)
_TRANSFORMABLE_KEYWORDS = frozenset({"discriminator", "oneOf", "uniqueItems"})
_SUPPORTED_FORMATS = frozenset(
    {
        "date-time",
        "time",
        "date",
        "duration",
        "email",
        "hostname",
        "ipv4",
        "ipv6",
        "uuid",
    }
)
_UNIQUE_ATTRIBUTES_PATH = (
    "$defs",
    "AttributesObserveRequest",
    "properties",
    "attributes",
)


class SchemaProjectionError(ValueError):
    """The target FSQ backends cannot represent a request schema safely."""


@dataclass(frozen=True, slots=True)
class ToolAnnotations:
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool


@dataclass(frozen=True, slots=True)
class ToolSpec:
    mcp_name: str
    tool_name: str
    handler_symbol: str
    description: str
    request_annotation: Any
    request_adapter: TypeAdapter[Any]
    result_model: type[BaseModel]
    annotations: ToolAnnotations
    invoke_validated: _Invoke


class ToolCatalog:
    """Immutable declarations and deterministic schema projections for twelve tools."""

    def __init__(self, specs: tuple[ToolSpec, ...]) -> None:
        if len(specs) != 12:
            raise ValueError("tool catalog must contain exactly twelve tools")
        if len({spec.mcp_name for spec in specs}) != len(specs):
            raise ValueError("MCP tool names must be unique")
        if len({spec.tool_name for spec in specs}) != len(specs):
            raise ValueError("ToolCall names must be unique")
        if len({spec.handler_symbol for spec in specs}) != len(specs):
            raise ValueError("MCP handler symbols must be unique")
        for spec in specs:
            if _TOOL_NAME.fullmatch(spec.tool_name) is None:
                raise ValueError("ToolCall name is outside the fixed contract")
            if not spec.mcp_name or not spec.handler_symbol or not spec.description:
                raise ValueError("tool catalog metadata must not be empty")
        _verify_attributes_uniqueness_validator()
        self._specs = specs
        self._by_mcp_name = {spec.mcp_name: spec for spec in specs}
        self._by_tool_name = {spec.tool_name: spec for spec in specs}
        self._mcp_names = cast(
            McpToolNames, tuple(spec.mcp_name for spec in self._specs)
        )
        self._tool_names = cast(
            ToolCallToolNames, tuple(spec.tool_name for spec in self._specs)
        )

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return self._specs

    @property
    def mcp_names(self) -> McpToolNames:
        return self._mcp_names

    @property
    def tool_names(self) -> ToolCallToolNames:
        return self._tool_names

    def by_mcp_name(self, name: str) -> ToolSpec:
        try:
            return self._by_mcp_name[name]
        except KeyError:
            raise KeyError("unknown MCP tool") from None

    def by_tool_name(self, name: str) -> ToolSpec:
        try:
            return self._by_tool_name[name]
        except KeyError:
            raise KeyError("unknown ToolCall tool") from None

    def fsq_schema(self, name: str) -> dict[str, JsonValue]:
        spec = self.by_tool_name(name)
        raw = spec.request_adapter.json_schema()
        projected = _project_schema(raw, root=raw, path=())
        return cast(dict[str, JsonValue], projected)


def _resolve_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise SchemaProjectionError("only local JSON Schema references are supported")
    current: Any = root
    for token in reference[2:].split("/"):
        if not isinstance(current, dict):
            raise SchemaProjectionError("JSON Schema reference has an invalid target")
        decoded = token.replace("~1", "/").replace("~0", "~")
        if decoded not in current:
            raise SchemaProjectionError("JSON Schema reference does not exist")
        current = current[decoded]
    if not isinstance(current, dict):
        raise SchemaProjectionError("JSON Schema reference target must be an object")
    return current


def _is_finite_number(value: object) -> bool:
    if type(value) not in {int, float}:
        return False
    try:
        return isfinite(cast(int | float, value))
    except OverflowError:
        return False


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool)):
        return True
    if type(value) in {int, float}:
        return _is_finite_number(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item) for key, item in value.items()
        )
    return False


def _discriminator_identity(value: object, path: tuple[str, ...]) -> tuple[str, object]:
    if isinstance(value, bool):
        return ("boolean", value)
    if type(value) in {int, float}:
        numeric_value = cast(int | float, value)
        try:
            finite = isfinite(numeric_value)
            numeric = float(numeric_value)
        except OverflowError:
            raise SchemaProjectionError(
                f"unrepresentable discriminator const at {path!r}"
            ) from None
        if not finite:
            raise SchemaProjectionError(f"non-finite discriminator const at {path!r}")
        return ("number", numeric)
    if isinstance(value, str):
        return ("string", value)
    if value is None:
        return ("null", None)
    raise SchemaProjectionError(f"discriminator const must be scalar at {path!r}")


def _validate_schema_node(
    node: dict[str, Any], root: dict[str, Any], path: tuple[str, ...]
) -> None:
    reference = node.get("$ref")
    if reference is not None:
        if not isinstance(reference, str):
            raise SchemaProjectionError(f"$ref must be a string at {path!r}")
        _resolve_ref(root, reference)

    schema_type = node.get("type")
    if schema_type is not None:
        values = schema_type if isinstance(schema_type, list) else [schema_type]
        valid_types = {
            "object",
            "array",
            "string",
            "number",
            "integer",
            "boolean",
            "null",
        }
        if (
            not values
            or any(
                not isinstance(value, str) or value not in valid_types
                for value in values
            )
            or len(values) != len(set(values))
        ):
            raise SchemaProjectionError(f"invalid type at {path!r}")

    required = node.get("required")
    if required is not None:
        if (
            not isinstance(required, list)
            or any(not isinstance(name, str) for name in required)
            or len(required) != len(set(required))
        ):
            raise SchemaProjectionError(f"invalid required at {path!r}")
        properties = node.get("properties")
        if isinstance(properties, dict) and not set(required).issubset(properties):
            raise SchemaProjectionError(f"required is outside properties at {path!r}")

    if "additionalProperties" in node and node["additionalProperties"] is not False:
        raise SchemaProjectionError(f"additionalProperties must be false at {path!r}")

    for key in ("title", "description", "format", "pattern"):
        if key in node and not isinstance(node[key], str):
            raise SchemaProjectionError(f"{key} must be a string at {path!r}")
    if "format" in node and node["format"] not in _SUPPORTED_FORMATS:
        raise SchemaProjectionError(f"unsupported format at {path!r}")
    if "pattern" in node:
        try:
            re.compile(node["pattern"])
        except re.error:
            raise SchemaProjectionError(f"invalid pattern at {path!r}") from None

    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        if key in node and (type(node[key]) is not int or node[key] < 0):
            raise SchemaProjectionError(
                f"{key} must be a non-negative integer at {path!r}"
            )

    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        if key in node and not _is_finite_number(node[key]):
            raise SchemaProjectionError(f"{key} must be finite at {path!r}")

    if "enum" in node:
        enum = node["enum"]
        if (
            not isinstance(enum, list)
            or not enum
            or not all(_is_json_value(value) for value in enum)
        ):
            raise SchemaProjectionError(f"invalid enum at {path!r}")
        encoded = [json.dumps(value, sort_keys=True, allow_nan=False) for value in enum]
        if len(encoded) != len(set(encoded)):
            raise SchemaProjectionError(f"duplicate enum value at {path!r}")
    for key in ("const", "default"):
        if key in node and not _is_json_value(node[key]):
            raise SchemaProjectionError(f"invalid {key} at {path!r}")
    if "const" in node and "enum" in node and node["const"] not in node["enum"]:
        raise SchemaProjectionError(f"const is outside enum at {path!r}")

    if (
        "minLength" in node
        and "maxLength" in node
        and node["minLength"] > node["maxLength"]
    ):
        raise SchemaProjectionError(f"inverted string bounds at {path!r}")
    if (
        "minItems" in node
        and "maxItems" in node
        and node["minItems"] > node["maxItems"]
    ):
        raise SchemaProjectionError(f"inverted array bounds at {path!r}")
    if "minimum" in node and "maximum" in node and node["minimum"] > node["maximum"]:
        raise SchemaProjectionError(f"inverted numeric bounds at {path!r}")


def _verify_disjoint_one_of(
    node: dict[str, Any], root: dict[str, Any], path: tuple[str, ...]
) -> None:
    discriminator = node.get("discriminator")
    variants = node.get("oneOf")
    if (
        not isinstance(discriminator, dict)
        or not isinstance(variants, list)
        or not variants
    ):
        raise SchemaProjectionError(f"unsupported oneOf shape at {path!r}")
    property_name = discriminator.get("propertyName")
    if not isinstance(property_name, str) or not property_name:
        raise SchemaProjectionError(f"invalid discriminator at {path!r}")
    constants: list[tuple[str, object]] = []
    for variant in variants:
        if not isinstance(variant, dict):
            raise SchemaProjectionError(f"invalid oneOf branch at {path!r}")
        target = variant
        reference = variant.get("$ref")
        if reference is not None:
            if not isinstance(reference, str):
                raise SchemaProjectionError(f"invalid oneOf reference at {path!r}")
            target = _resolve_ref(root, reference)
        properties = target.get("properties")
        if not isinstance(properties, dict):
            raise SchemaProjectionError(f"oneOf branch has no properties at {path!r}")
        discriminator_schema = properties.get(property_name)
        if (
            not isinstance(discriminator_schema, dict)
            or "const" not in discriminator_schema
        ):
            raise SchemaProjectionError(
                f"oneOf branch has no discriminator const at {path!r}"
            )
        constants.append(_discriminator_identity(discriminator_schema["const"], path))
    if len(set(constants)) != len(constants):
        raise SchemaProjectionError(f"oneOf discriminator values overlap at {path!r}")


def _project_schema(
    node: dict[str, Any], *, root: dict[str, Any], path: tuple[str, ...]
) -> dict[str, Any]:
    unsupported = set(node) - _FSQ_KEYWORDS - _TRANSFORMABLE_KEYWORDS
    if unsupported:
        raise SchemaProjectionError(
            f"unsupported JSON Schema keywords at {path!r}: {sorted(unsupported)!r}"
        )
    _validate_schema_node(node, root, path)
    if "oneOf" in node:
        if "anyOf" in node:
            raise SchemaProjectionError(f"oneOf and anyOf overlap at {path!r}")
        _verify_disjoint_one_of(node, root, path)
    elif "discriminator" in node:
        raise SchemaProjectionError(f"discriminator without oneOf at {path!r}")

    projected: dict[str, Any] = {}
    for key, value in node.items():
        if key == "discriminator":
            continue
        if key == "uniqueItems":
            if path != _UNIQUE_ATTRIBUTES_PATH or value is not True:
                raise SchemaProjectionError(f"unsupported uniqueItems at {path!r}")
            continue
        if key in {"$defs", "properties"}:
            if not isinstance(value, dict) or any(
                not isinstance(name, str) for name in value
            ):
                raise SchemaProjectionError(f"{key} must be an object at {path!r}")
            projected[key] = {
                name: _project_schema(child, root=root, path=(*path, key, name))
                for name, child in value.items()
                if isinstance(child, dict)
            }
            if len(projected[key]) != len(value):
                raise SchemaProjectionError(
                    f"{key} child must be an object at {path!r}"
                )
            continue
        if key == "items":
            if not isinstance(value, dict):
                raise SchemaProjectionError(f"items must be an object at {path!r}")
            projected[key] = _project_schema(value, root=root, path=(*path, "items"))
            continue
        if key in {"anyOf", "oneOf"}:
            if not isinstance(value, list) or not value:
                raise SchemaProjectionError(f"{key} must be a non-empty array")
            output_key = "anyOf" if key == "oneOf" else key
            projected[output_key] = [
                _project_schema(child, root=root, path=(*path, key, str(index)))
                for index, child in enumerate(value)
                if isinstance(child, dict)
            ]
            if len(projected[output_key]) != len(value):
                raise SchemaProjectionError(
                    f"{key} child must be an object at {path!r}"
                )
            continue
        projected[key] = deepcopy(value)
    return projected


def _verify_attributes_uniqueness_validator() -> None:
    try:
        AttributesObserveRequest.model_validate(
            {
                "schema_version": 1,
                "session_handle": "s_" + ("a" * 32),
                "mode": "attributes",
                "locator": {"by": "id", "value": "value"},
                "attributes": ["id", "id"],
                "timeout_seconds": 90.0,
            }
        )
    except ValidationError:
        return
    raise SchemaProjectionError("attributes uniqueness validator is not active")


async def _capabilities(application: Application, request: BaseModel) -> BaseModel:
    del request
    return application.capabilities()


async def _runtime_check(application: Application, request: BaseModel) -> BaseModel:
    value = cast(RuntimeCheckRequest, request)
    return await application.runtime_check(value.mode, value.timeout_seconds)


async def _devices_list(application: Application, request: BaseModel) -> BaseModel:
    value = cast(DeviceListRequest, request)
    return await application.devices_list(value.timeout_seconds)


async def _session_open(application: Application, request: BaseModel) -> BaseModel:
    return await application.session_open(cast(SessionOpenRequest, request))


async def _session_status(application: Application, request: BaseModel) -> BaseModel:
    value = cast(SessionStatusRequest, request)
    return application.session_status(value.session_handle)


async def _session_close(application: Application, request: BaseModel) -> BaseModel:
    value = cast(SessionCloseRequest, request)
    return await application.session_close(value.session_handle, value.timeout_seconds)


async def _observe(application: Application, request: BaseModel) -> BaseModel:
    return await application.observe(cast(ObserveRequest, request))


async def _click(application: Application, request: BaseModel) -> BaseModel:
    return await application.click(cast(ElementClickRequest, request))


async def _text(application: Application, request: BaseModel) -> BaseModel:
    return await application.text(cast(ElementTextRequest, request))


async def _back(application: Application, request: BaseModel) -> BaseModel:
    return await application.back(cast(DeviceBackRequest, request))


async def _ime_action(application: Application, request: BaseModel) -> BaseModel:
    return await application.ime_action(cast(ElementImeActionRequest, request))


async def _gesture(application: Application, request: BaseModel) -> BaseModel:
    return await application.gesture(cast(ElementGestureRequest, request))


def _spec(
    mcp_name: str,
    tool_name: str,
    handler_symbol: str,
    description: str,
    request_annotation: Any,
    result_model: type[BaseModel],
    annotations: ToolAnnotations,
    invoke_validated: _Invoke,
) -> ToolSpec:
    return ToolSpec(
        mcp_name=mcp_name,
        tool_name=tool_name,
        handler_symbol=handler_symbol,
        description=description,
        request_annotation=request_annotation,
        request_adapter=TypeAdapter(request_annotation),
        result_model=result_model,
        annotations=annotations,
        invoke_validated=invoke_validated,
    )


_READ_LOCAL = ToolAnnotations(True, False, True, False)
_READ_OPEN = ToolAnnotations(True, False, True, True)
_WRITE_OPEN = ToolAnnotations(False, True, False, True)

TOOL_CATALOG = ToolCatalog(
    (
        _spec(
            "appium.capabilities.get",
            "appium_capabilities_get",
            "capabilities_get",
            "Return fixed integration capabilities and qualification limits.",
            CapabilitiesRequest,
            McpCapabilityResult,
            _READ_LOCAL,
            _capabilities,
        ),
        _spec(
            "appium.runtime.check",
            "appium_runtime_check",
            "runtime_check",
            "Run one bounded static or external Runtime readiness check.",
            RuntimeCheckRequest,
            RuntimeCheckResult,
            _READ_OPEN,
            _runtime_check,
        ),
        _spec(
            "appium.devices.list",
            "appium_devices_list",
            "devices_list",
            "List Android devices through the bootstrapped ADB executable.",
            DeviceListRequest,
            DeviceListResult,
            _READ_OPEN,
            _devices_list,
        ),
        _spec(
            "appium.session.open",
            "appium_session_open",
            "session_open",
            "Open the single Application-owned Android Session.",
            SessionOpenRequest,
            SessionOpenResult,
            ToolAnnotations(False, False, False, True),
            _session_open,
        ),
        _spec(
            "appium.session.status",
            "appium_session_status",
            "session_status",
            "Return the local snapshot for one opaque Session handle.",
            SessionStatusRequest,
            SessionStatusResult,
            _READ_LOCAL,
            _session_status,
        ),
        _spec(
            "appium.session.close",
            "appium_session_close",
            "session_close",
            "Close one Application-owned Session or its retained tombstone.",
            SessionCloseRequest,
            SessionCloseResult,
            ToolAnnotations(False, True, True, True),
            _session_close,
        ),
        _spec(
            "appium.ui.observe",
            "appium_ui_observe",
            "ui_observe",
            "Observe one Native tree, Element attribute set, or raw structure scope.",
            ObserveRequest,
            ObservationResult,
            _READ_OPEN,
            _observe,
        ),
        _spec(
            "appium.element.click",
            "appium_element_click",
            "element_click",
            "Perform one single, double, or long click on an explicitly located Native Element.",
            ElementClickRequest,
            ElementClickResult,
            _WRITE_OPEN,
            _click,
        ),
        _spec(
            "appium.element.text",
            "appium_element_text",
            "element_text",
            "Send, clear, or replace text on one explicitly located Element.",
            ElementTextRequest,
            ElementTextResult,
            _WRITE_OPEN,
            _text,
        ),
        _spec(
            "appium.device.back",
            "appium_device_back",
            "device_back",
            "Send one caller-requested back command to the bound Device.",
            DeviceBackRequest,
            DeviceBackResult,
            _WRITE_OPEN,
            _back,
        ),
        _spec(
            "appium.element.ime_action",
            "appium_element_ime_action",
            "element_ime_action",
            "Perform one explicit editor action on an explicitly located Native Element.",
            ElementImeActionRequest,
            ElementImeActionResult,
            _WRITE_OPEN,
            _ime_action,
        ),
        _spec(
            "appium.element.gesture",
            "appium_element_gesture",
            "element_gesture",
            "Swipe, scroll, scroll to a restricted target, or drag an explicitly located Native Element.",
            ElementGestureRequest,
            ElementGestureResult,
            _WRITE_OPEN,
            _gesture,
        ),
    )
)
