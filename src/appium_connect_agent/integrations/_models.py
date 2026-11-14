"""Strict request, result, and error values for the local stdio MCP tools."""

from __future__ import annotations

import json
import math
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Generic, Literal, Self, TypeAlias, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    RootModel,
    SerializerFunctionWrapHandler,
    SkipValidation,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

_MAX_SUCCESS_BYTES = 4 * 1024 * 1024
_CODE_PATTERN = r"^[a-z0-9_]{1,128}$"
_CALL_ID_PATTERN = r"^c_[A-Za-z0-9_-]{22}$"
_ERROR_OPERATION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,128}$"
_SESSION_HANDLE_PATTERN = r"^s_[A-Za-z0-9_-]{32}$"


def _strict_utf8(value: str) -> str:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise ValueError("string must be strict UTF-8") from error
    return value


def _element_text(value: str) -> str:
    encoded = value.encode("utf-8", errors="strict")
    if len(encoded) > 65_536:
        raise ValueError("text exceeds 65,536 UTF-8 bytes")
    if "\x00" in value:
        raise ValueError("text must not contain NUL")
    if value.endswith("\\n"):
        raise ValueError("text must not end with literal backslash-n")
    return value


def _bounded_utf8(value: str, *, maximum: int, label: str) -> str:
    if len(value.encode("utf-8", errors="strict")) > maximum:
        raise ValueError(f"{label} exceeds {maximum:,} UTF-8 bytes")
    return value


def _clipboard_text(value: str) -> str:
    return _bounded_utf8(value, maximum=65_536, label="clipboard text")


def _status_output(value: str) -> str:
    return _bounded_utf8(value, maximum=65_536, label="status bar output")


def _device_label(value: str) -> str:
    return _bounded_utf8(value, maximum=1_024, label="label")


StrictUtf8 = Annotated[str, AfterValidator(_strict_utf8)]
StableCode = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=_CODE_PATTERN),
    AfterValidator(_strict_utf8),
]
CallId = Annotated[
    str,
    Field(min_length=24, max_length=24, pattern=_CALL_ID_PATTERN),
    AfterValidator(_strict_utf8),
]
SessionHandle = Annotated[
    str,
    Field(min_length=34, max_length=34, pattern=_SESSION_HANDLE_PATTERN),
    AfterValidator(_strict_utf8),
]


def _finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be an actual JSON number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError("value must be finite")
    return converted


def _safe_identifier(value: str, label: str) -> str:
    if any(
        character.isspace() or unicodedata.category(character) == "Cc"
        for character in value
    ):
        raise ValueError(f"{label} must not contain whitespace or controls")
    return value


def _mac_app_path(value: str) -> str:
    path = Path(value)
    if (
        not path.is_absolute()
        or any(part in {".", ".."} for part in path.parts)
        or path.suffix.casefold() != ".app"
        or any(unicodedata.category(character) == "Cc" for character in value)
        or len(value.encode("utf-8", errors="strict")) > 4096
    ):
        raise ValueError("invalid macOS application path")
    return value


def _mac_argument(value: str) -> str:
    if "\x00" in value or len(value.encode("utf-8", errors="strict")) > 4096:
        raise ValueError("invalid macOS launch argument")
    return value


_MAC_NAMED_KEYS = frozenset(
    {
        "XCUIKeyboardKeyDelete",
        "XCUIKeyboardKeyReturn",
        "XCUIKeyboardKeyEnter",
        "XCUIKeyboardKeyTab",
        "XCUIKeyboardKeySpace",
        "XCUIKeyboardKeyEscape",
        "XCUIKeyboardKeyUpArrow",
        "XCUIKeyboardKeyDownArrow",
        "XCUIKeyboardKeyLeftArrow",
        "XCUIKeyboardKeyRightArrow",
        *(f"XCUIKeyboardKeyF{index}" for index in range(1, 20)),
        "XCUIKeyboardKeyForwardDelete",
        "XCUIKeyboardKeyHome",
        "XCUIKeyboardKeyEnd",
        "XCUIKeyboardKeyPageUp",
        "XCUIKeyboardKeyPageDown",
        "XCUIKeyboardKeyClear",
        "XCUIKeyboardKeyHelp",
        "XCUIKeyboardKeyCapsLock",
        "XCUIKeyboardKeyShift",
        "XCUIKeyboardKeyControl",
        "XCUIKeyboardKeyOption",
        "XCUIKeyboardKeyCommand",
        "XCUIKeyboardKeyRightShift",
        "XCUIKeyboardKeyRightControl",
        "XCUIKeyboardKeyRightOption",
        "XCUIKeyboardKeyRightCommand",
        "XCUIKeyboardKeySecondaryFn",
    }
)


def _mac_key_name(value: str) -> str:
    if "\x00" in value or (len(value) != 1 and value not in _MAC_NAMED_KEYS):
        raise ValueError("invalid macOS key name")
    return value


_RootT = TypeVar("_RootT")


class PrivateRequestValidationError(Exception):
    """Signal private request rejection without attaching the rejected value."""


class _PrivateRootModel(RootModel[_RootT], Generic[_RootT]):
    model_config = ConfigDict(strict=True, frozen=True, hide_input_in_errors=True)

    @model_validator(mode="wrap")
    @classmethod
    def _redact_invalid_input(
        cls, value: Any, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        try:
            return handler(value)
        except ValidationError:
            raise PrivateRequestValidationError from None


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
    )

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def _actual_schema_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value


class CapabilitiesRequest(_StrictModel):
    schema_version: Literal[1]


class RuntimeCheckRequest(_StrictModel):
    schema_version: Literal[1]
    mode: Literal["static", "external_connection"]
    target_driver: Literal["uiautomator2", "mac2"] = "uiautomator2"
    timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class DeviceListRequest(_StrictModel):
    schema_version: Literal[1]
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=60.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class AutomationModuleStatus(_StrictModel):
    feature_qualification: Literal["aif_01_to_10_individually_done"]
    module_state: Literal["device_validation_blocked_known_clean"]
    module_done: Literal[False]
    automatic_retry_authorized: Literal[False]


AUTOMATION_MODULE_STATUS = AutomationModuleStatus(
    feature_qualification="aif_01_to_10_individually_done",
    module_state="device_validation_blocked_known_clean",
    module_done=False,
    automatic_retry_authorized=False,
)


class AndroidPlatformData(_StrictModel):
    host: Literal["macos"]
    target: Literal["android_native"]
    driver: Literal["uiautomator2"]


class MacosPlatformData(_StrictModel):
    host: Literal["macos"]
    target: Literal["macos_desktop"]
    driver: Literal["mac2"]


PlatformEntryData: TypeAlias = Annotated[
    AndroidPlatformData | MacosPlatformData,
    Field(discriminator="target"),
]


McpToolNames: TypeAlias = tuple[
    Literal["appium.capabilities.get"],
    Literal["appium.runtime.check"],
    Literal["appium.devices.list"],
    Literal["appium.session.open"],
    Literal["appium.session.status"],
    Literal["appium.session.close"],
    Literal["appium.ui.observe"],
    Literal["appium.element.click"],
    Literal["appium.element.text"],
    Literal["appium.device.back"],
    Literal["appium.element.ime_action"],
    Literal["appium.element.gesture"],
    Literal["appium.device.key"],
    Literal["appium.device.keyboard_hide"],
    Literal["appium.device.clipboard"],
    Literal["appium.device.alert"],
    Literal["appium.device.status_bar"],
    Literal["appium.app.lifecycle"],
    Literal["appium.app.package"],
    Literal["appium.device.screenshot"],
    Literal["appium.device.pointer"],
    Literal["appium.macos.keys"],
]
ToolCallToolNames: TypeAlias = tuple[
    Literal["appium_capabilities_get"],
    Literal["appium_runtime_check"],
    Literal["appium_devices_list"],
    Literal["appium_session_open"],
    Literal["appium_session_status"],
    Literal["appium_session_close"],
    Literal["appium_ui_observe"],
    Literal["appium_element_click"],
    Literal["appium_element_text"],
    Literal["appium_device_back"],
    Literal["appium_element_ime_action"],
    Literal["appium_element_gesture"],
    Literal["appium_device_key"],
    Literal["appium_device_keyboard_hide"],
    Literal["appium_device_clipboard"],
    Literal["appium_device_alert"],
    Literal["appium_device_status_bar"],
    Literal["appium_app_lifecycle"],
    Literal["appium_app_package"],
    Literal["appium_device_screenshot"],
    Literal["appium_device_pointer"],
    Literal["appium_macos_keys"],
]
CapabilityLimitations: TypeAlias = tuple[
    Literal["android_and_macos_native_automation"],
    Literal["no_automatic_post_action_observation"],
    Literal["clipboard_current_caller_only"],
    Literal["status_bar_output_current_caller_only"],
    Literal["local_apk_and_macos_app_paths_only"],
    Literal["package_remove_no_data_deletion_guarantee"],
    Literal["ime_requires_explicit_element_and_action"],
    Literal["explicit_screen_coordinates_only"],
    Literal["no_automatic_navigation"],
    Literal["no_node_cache"],
    Literal["observation_document_65536_bytes"],
    Literal["screenshot_png_3000000_bytes"],
    Literal["single_session_capacity"],
    Literal["opaque_handle_process_local"],
    Literal["no_session_attach_recovery"],
    Literal["no_http_transport"],
    Literal["no_clear_app"],
    Literal["automation_module_e2e_unqualified"],
    Literal["no_specific_host_qualification"],
]


class _CapabilityData(_StrictModel):
    host_compatibility: Literal["unqualified"]
    adb_configured: bool
    platforms: Annotated[
        tuple[PlatformEntryData, ...], Field(min_length=2, max_length=2)
    ]
    limitations: CapabilityLimitations

    @model_validator(mode="after")
    def _fixed_platform_order(self) -> Self:
        if self.platforms != (
            AndroidPlatformData(
                host="macos", target="android_native", driver="uiautomator2"
            ),
            MacosPlatformData(host="macos", target="macos_desktop", driver="mac2"),
        ):
            raise ValueError("platforms must contain the fixed ordered pair")
        return self


class McpCapabilityData(_CapabilityData):
    integration_form: Literal["mcp"]
    transport: Literal["stdio"]
    protocol_target: Literal["2026-07-28"]
    tools: McpToolNames


class ToolCallCapabilityData(_CapabilityData):
    integration_form: Literal["toolcall"]
    transport: Literal["in_process"]
    protocol_target: None
    tools: ToolCallToolNames


class CliCapabilityData(_CapabilityData):
    integration_form: Literal["cli"]
    transport: Literal["unix_socket"]
    protocol_target: None
    tools: ToolCallToolNames


CapabilityData: TypeAlias = Annotated[
    McpCapabilityData | ToolCallCapabilityData | CliCapabilityData,
    Field(discriminator="integration_form"),
]


class CapabilityResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: CapabilityData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


class McpCapabilityResult(CapabilityResult):
    data: McpCapabilityData


class ToolCallCapabilityResult(CapabilityResult):
    data: ToolCallCapabilityData


class CliCapabilityResult(CapabilityResult):
    data: CliCapabilityData


class RuntimeCheck(_StrictModel):
    check_id: StableCode
    reason_code: StableCode
    status: Literal["pass", "fail", "unknown", "not_applicable"]
    evidence: tuple[Annotated[StrictUtf8, Field(max_length=512)], ...] = Field(
        max_length=8
    )
    remediation: Annotated[StrictUtf8, Field(max_length=512)] | None


class RuntimeReport(_StrictModel):
    operation_id: Annotated[StrictUtf8, Field(min_length=1, max_length=128)]
    observed_at: Annotated[StrictUtf8, Field(min_length=1)]
    host: Literal["macOS"]
    target: Literal["Android", "macOS"]
    driver: Literal["UiAutomator2", "Mac2"]
    checks: tuple[RuntimeCheck, ...] = Field(max_length=32)
    observer_errors: tuple[Annotated[StrictUtf8, Field(max_length=512)], ...] = Field(
        max_length=8
    )

    @model_validator(mode="after")
    def _target_matches_driver(self) -> Self:
        if (self.target, self.driver) not in {
            ("Android", "UiAutomator2"),
            ("macOS", "Mac2"),
        }:
            raise ValueError("target must match driver")
        return self

    @field_validator("observed_at")
    @classmethod
    def _utc_iso8601(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError("observed_at must be ISO 8601") from error
        offset = parsed.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("observed_at must carry a UTC offset")
        if not value.endswith("+00:00"):
            raise ValueError("observed_at must use +00:00")
        return value


class RuntimeConnectionData(_StrictModel):
    ownership: Literal["external"]
    appium_version: Annotated[StrictUtf8, Field(min_length=1, max_length=128)] | None
    compatibility: Literal["declared_compatible", "unverified"]


class RuntimeCheckData(_StrictModel):
    mode: Literal["static", "external_connection"]
    report: RuntimeReport
    connection: RuntimeConnectionData | None

    @model_validator(mode="after")
    def _connection_matches_mode(self) -> RuntimeCheckData:
        if (self.mode == "static") != (self.connection is None):
            raise ValueError("connection must match mode")
        return self


class RuntimeCheckResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: Annotated[StrictUtf8, Field(min_length=1, max_length=128)]
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: RuntimeCheckData

    @model_validator(mode="after")
    def _operation_matches_report(self) -> RuntimeCheckResult:
        if self.operation_id != self.data.report.operation_id:
            raise ValueError("operation_id must match report")
        if len(self.warnings) != len(set(self.warnings)):
            raise ValueError("warnings must be unique")
        return self


class DeviceData(_StrictModel):
    id: Annotated[
        StrictUtf8,
        Field(
            min_length=1,
            max_length=1024,
            pattern=r"^[^\s\x00-\x1f\x7f-\x9f]+$",
        ),
    ]
    name: (
        Annotated[
            StrictUtf8,
            Field(max_length=1024, pattern=r"^[^\x00-\x1f\x7f-\x9f]*$"),
        ]
        | None
    )
    connection_state: Literal["connected", "offline", "unauthorized", "unknown"]

    @field_validator("id")
    @classmethod
    def _safe_id(cls, value: str) -> str:
        if any(
            character.isspace() or unicodedata.category(character) == "Cc"
            for character in value
        ):
            raise ValueError("device id must not contain whitespace or controls")
        return value

    @field_validator("name")
    @classmethod
    def _safe_name(cls, value: str | None) -> str | None:
        if value is not None and any(
            unicodedata.category(character) == "Cc" for character in value
        ):
            raise ValueError("device name must not contain controls")
        return value


class DeviceListData(_StrictModel):
    count: int = Field(ge=0, le=256)
    devices: tuple[DeviceData, ...] = Field(max_length=256)

    @model_validator(mode="after")
    def _count_matches(self) -> DeviceListData:
        if self.count != len(self.devices):
            raise ValueError("count must match devices")
        return self


class DeviceListResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: DeviceListData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


_OBSERVED_AT_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$"
_OBSERVATION_OPERATION_ID = Annotated[StrictUtf8, Field(min_length=1, max_length=128)]
_OBSERVED_AT = Annotated[
    StrictUtf8, Field(min_length=27, max_length=27, pattern=_OBSERVED_AT_PATTERN)
]
_TREE_COVERAGE: TypeAlias = Literal[
    "requested_scope",
    "visible_with_ancestors",
    "visible_with_ancestors_and_offscreen",
]
_STRUCTURE_COVERAGE: TypeAlias = Literal[
    "requested_scope", "visible_with_ancestors_and_target"
]
_ELEMENT_ATTRIBUTE: TypeAlias = Literal[
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
]
_TREE_VALUE_NAME: TypeAlias = Literal[
    "type",
    "id",
    "text",
    "desc",
    "package",
    "enabled",
    "focused",
    "checked",
    "selected",
    "bounds",
    "window_id",
    "label",
    "title",
    "value",
    "placeholder_value",
    "element_type",
]


def _json_array(value: object) -> object:
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, tuple):
        return value
    raise ValueError("value must be an array")


class LocatorV1(_StrictModel):
    by: Literal[
        "id",
        "accessibility_id",
        "xpath",
        "name",
        "class_name",
        "ios_predicate_string",
        "ios_class_chain",
    ]
    value: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)]
    package: Annotated[StrictUtf8, Field(max_length=255)] | None = None
    raw_id: bool = False
    predicate: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)] | None = None
    parent: LocatorV1 | None = None

    @field_validator("value", "predicate")
    @classmethod
    def _without_nul(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("locator values must not contain NUL")
        return value

    @model_validator(mode="after")
    def _bounded_chain(self) -> LocatorV1:
        depth = 0
        current: LocatorV1 | None = self
        while current is not None:
            depth += 1
            if depth > 16:
                raise ValueError("locator chain exceeds 16 levels")
            current = current.parent
        return self


class TreeObserveRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    mode: Literal["tree"]
    locator: LocatorV1 | None
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class AttributesObserveRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    mode: Literal["attributes"]
    locator: LocatorV1
    attributes: tuple[_ELEMENT_ATTRIBUTE, ...] = Field(
        min_length=1,
        max_length=18,
        json_schema_extra={"uniqueItems": True},
    )
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("attributes", mode="before")
    @classmethod
    def _attributes_array(cls, value: object) -> object:
        return _json_array(value)

    @field_validator("attributes")
    @classmethod
    def _unique_attributes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("attributes must be unique")
        return value

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class StructureObserveRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    mode: Literal["structure"]
    locator: LocatorV1
    structure_scope: Literal["target", "declared_parent"]
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


ObserveRequest: TypeAlias = Annotated[
    TreeObserveRequest | AttributesObserveRequest | StructureObserveRequest,
    Field(discriminator="mode"),
]


class _ElementClickRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    locator: LocatorV1
    key_modifier_flags: Annotated[int, Field(ge=0, le=63)] | None = None
    wait_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("wait_timeout_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class SingleClickRequest(_ElementClickRequest):
    kind: Literal["single"]


class DoubleClickRequest(_ElementClickRequest):
    kind: Literal["double"]


class RightClickRequest(_ElementClickRequest):
    kind: Literal["right"]


class HoverClickRequest(_ElementClickRequest):
    kind: Literal["hover"]


class LongClickRequest(_ElementClickRequest):
    kind: Literal["long"]
    duration_ms: int = Field(default=500, ge=1, le=60_000)


ElementClickRequest: TypeAlias = Annotated[
    SingleClickRequest
    | DoubleClickRequest
    | RightClickRequest
    | HoverClickRequest
    | LongClickRequest,
    Field(discriminator="kind"),
]


class ElementImeActionRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    locator: LocatorV1
    action: Literal[
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
    wait_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("wait_timeout_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class _ElementGestureRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    wait_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("wait_timeout_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class ElementSwipeRequest(_ElementGestureRequest):
    intent: Literal["swipe"]
    locator: LocatorV1
    direction: Literal["up", "down", "left", "right"]
    percent: float = Field(gt=0.0, le=1.0)

    @field_validator("percent", mode="before")
    @classmethod
    def _actual_percent(cls, value: object) -> float:
        return _finite_number(value)


class ElementScrollRequest(_ElementGestureRequest):
    intent: Literal["scroll"]
    locator: LocatorV1
    direction: Literal["up", "down", "left", "right"]
    percent: float = Field(gt=0.0, le=3.0)

    @field_validator("percent", mode="before")
    @classmethod
    def _actual_percent(cls, value: object) -> float:
        return _finite_number(value)


class ElementScrollToRequest(_ElementGestureRequest):
    intent: Literal["scroll_to"]
    container_locator: LocatorV1
    target_by: Literal["id", "accessibility_id"]
    target_value: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)]
    target_package: Annotated[StrictUtf8, Field(max_length=255)] | None = None
    max_swipes: int = Field(ge=1, le=30)

    @field_validator("target_value")
    @classmethod
    def _target_without_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("target value must not contain NUL")
        return value

    @model_validator(mode="after")
    def _package_only_for_id(self) -> ElementScrollToRequest:
        if self.target_by == "accessibility_id" and self.target_package is not None:
            raise ValueError("target package is only valid for id")
        return self


class ElementDragAndDropRequest(_ElementGestureRequest):
    intent: Literal["drag_and_drop"]
    source_locator: LocatorV1
    destination_locator: LocatorV1
    destination_x_ratio: float = Field(ge=0.0, le=1.0)
    destination_y_ratio: float = Field(ge=0.0, le=1.0)
    duration_ms: Annotated[int, Field(ge=1, le=60_000)] | None = None
    key_modifier_flags: Annotated[int, Field(ge=0, le=63)] | None = None

    @field_validator("destination_x_ratio", "destination_y_ratio", mode="before")
    @classmethod
    def _actual_ratio(cls, value: object) -> float:
        return _finite_number(value)


class ElementScrollByRequest(_ElementGestureRequest):
    intent: Literal["scroll_by"]
    locator: LocatorV1
    delta_x: float
    delta_y: float
    key_modifier_flags: Annotated[int, Field(ge=0, le=63)] | None = None

    @field_validator("delta_x", "delta_y", mode="before")
    @classmethod
    def _actual_delta(cls, value: object) -> float:
        return _finite_number(value)


class ElementMacosSwipeRequest(_ElementGestureRequest):
    intent: Literal["macos_swipe"]
    locator: LocatorV1
    direction: Literal["up", "down", "left", "right"]
    velocity: float | None = Field(default=None, gt=0.0)
    key_modifier_flags: Annotated[int, Field(ge=0, le=63)] | None = None

    @field_validator("velocity", mode="before")
    @classmethod
    def _actual_velocity(cls, value: object) -> float | None:
        return None if value is None else _finite_number(value)


ElementGestureRequest: TypeAlias = Annotated[
    ElementSwipeRequest
    | ElementScrollRequest
    | ElementScrollToRequest
    | ElementDragAndDropRequest
    | ElementScrollByRequest
    | ElementMacosSwipeRequest,
    Field(discriminator="intent"),
]


class _ElementTextRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    locator: LocatorV1
    wait_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("wait_timeout_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class ElementTextSendRequest(_ElementTextRequest):
    intent: Literal["send"]
    text: Annotated[StrictUtf8, Field(min_length=1), AfterValidator(_element_text)]


class ElementTextClearRequest(_ElementTextRequest):
    intent: Literal["clear"]


class ElementTextReplaceRequest(_ElementTextRequest):
    intent: Literal["replace"]
    text: Annotated[StrictUtf8, AfterValidator(_element_text)]


ElementTextRequest: TypeAlias = Annotated[
    ElementTextSendRequest | ElementTextClearRequest | ElementTextReplaceRequest,
    Field(discriminator="intent"),
]


class DeviceBackRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


_DEVICE_LABEL = Annotated[StrictUtf8, AfterValidator(_device_label)]
_CLIPBOARD_TEXT = Annotated[StrictUtf8, AfterValidator(_clipboard_text)]
_STATUS_OUTPUT = Annotated[StrictUtf8, AfterValidator(_status_output)]
_KEYCODE = Annotated[int, Field(ge=0, le=2_147_483_647)]
_SIGNED_INT32 = Annotated[int, Field(ge=-2_147_483_648, le=2_147_483_647)]
_APP_ID = Annotated[
    StrictUtf8,
    Field(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*(?:[.][A-Za-z_][A-Za-z0-9_]*)*$",
    ),
]
_APK_PATH = Annotated[StrictUtf8, Field(pattern=r"^/[\s\S]*[.]apk$")]


class _DeviceActionRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class DeviceKeyRequest(_DeviceActionRequest):
    kind: Literal["press", "long_press"]
    keycode: _KEYCODE
    metastate: _SIGNED_INT32 | None = None
    flags: _SIGNED_INT32 | None = None


class DeviceKeyboardHideRequest(_DeviceActionRequest):
    pass


class DeviceClipboardGetRequest(_DeviceActionRequest):
    intent: Literal["get"]


class DeviceClipboardSetRequest(_DeviceActionRequest):
    intent: Literal["set"]
    text: _CLIPBOARD_TEXT
    label: _DEVICE_LABEL | None = None


DeviceClipboardBranch: TypeAlias = Annotated[
    DeviceClipboardGetRequest | DeviceClipboardSetRequest,
    Field(discriminator="intent"),
]


class DeviceClipboardRequest(_PrivateRootModel[DeviceClipboardBranch]):
    pass


class DeviceAlertRequest(_DeviceActionRequest):
    action: Literal["accept", "dismiss"]
    button_label: _DEVICE_LABEL | None = None


class DeviceStatusBarRequest(_DeviceActionRequest):
    command: Literal["expandNotifications", "expandSettings", "collapse"]


_CROSS_PLATFORM_APP_ID = Annotated[
    StrictUtf8,
    Field(
        min_length=1,
        max_length=255,
        pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,254}$",
    ),
]
_MAC_BUNDLE_ID = Annotated[
    StrictUtf8,
    Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]{0,254}$"),
]
_MAC_APP_PATH = Annotated[
    StrictUtf8, Field(min_length=5, max_length=4096), AfterValidator(_mac_app_path)
]
_MAC_ARG_ITEM = Annotated[
    StrictUtf8, Field(max_length=4096), AfterValidator(_mac_argument)
]


class _AppLifecycleRequest(_DeviceActionRequest):
    pass


class AppActivateRequest(_AppLifecycleRequest):
    intent: Literal["activate"]
    app_id: _CROSS_PLATFORM_APP_ID


class AppTerminateRequest(_AppLifecycleRequest):
    intent: Literal["terminate"]
    app_id: _CROSS_PLATFORM_APP_ID


class AppQueryStateRequest(_AppLifecycleRequest):
    intent: Literal["query_state"]
    app_id: _CROSS_PLATFORM_APP_ID


class AppLaunchRequest(_DeviceActionRequest):
    intent: Literal["launch"]
    bundle_id: _MAC_BUNDLE_ID | None = None
    app_path: _MAC_APP_PATH | None = None
    arguments: Annotated[tuple[_MAC_ARG_ITEM, ...], Field(max_length=64)] | None = None

    @field_validator("arguments", mode="before")
    @classmethod
    def _arguments_array(cls, value: object) -> object:
        return None if value is None else _json_array(value)

    @model_validator(mode="after")
    def _requires_application(self) -> Self:
        if self.bundle_id is None and self.app_path is None:
            raise ValueError("launch requires bundle_id or app_path")
        return self


AppLifecycleBranch: TypeAlias = Annotated[
    AppActivateRequest | AppTerminateRequest | AppQueryStateRequest | AppLaunchRequest,
    Field(discriminator="intent"),
]


class AppLifecycleRequest(_PrivateRootModel[AppLifecycleBranch]):
    pass


class _AppPackageRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle


class AppPackageInstallRequest(_AppPackageRequest):
    intent: Literal["install"]
    app_path: _APK_PATH
    allow_test_packages: bool = False
    timeout_seconds: float = Field(default=180.0, gt=0.0, le=360.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class AppPackageRemoveRequest(_AppPackageRequest):
    intent: Literal["remove"]
    app_id: _APP_ID
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=180.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


AppPackageBranch: TypeAlias = Annotated[
    AppPackageInstallRequest | AppPackageRemoveRequest,
    Field(discriminator="intent"),
]


class AppPackageRequest(_PrivateRootModel[AppPackageBranch]):
    pass


MAX_INTEGRATION_SCREENSHOT_BYTES = 3_000_000
_COORD = Annotated[int, Field(ge=0, le=2_147_483_647)]
_MODIFIER_FLAGS = Annotated[int, Field(ge=0, le=63)]
_MAC_KEY_NAME = Annotated[StrictUtf8, AfterValidator(_mac_key_name)]


class DeviceScreenshotRequest(_DeviceActionRequest):
    pass


class DevicePointerTapRequest(_DeviceActionRequest):
    intent: Literal["tap"]
    x: _COORD
    y: _COORD


class DevicePointerClickRequest(_DeviceActionRequest):
    intent: Literal["click"]
    x: _COORD
    y: _COORD
    button: Literal["left", "right"] = "left"
    double: bool = False
    key_modifier_flags: _MODIFIER_FLAGS | None = None

    @model_validator(mode="after")
    def _right_double_is_invalid(self) -> Self:
        if self.button == "right" and self.double:
            raise ValueError("right click cannot be double")
        return self


class DevicePointerHoverRequest(_DeviceActionRequest):
    intent: Literal["hover"]
    x: _COORD
    y: _COORD
    key_modifier_flags: _MODIFIER_FLAGS | None = None


class DevicePointerScrollRequest(_DeviceActionRequest):
    intent: Literal["scroll"]
    x: _COORD
    y: _COORD
    delta_x: float
    delta_y: float
    key_modifier_flags: _MODIFIER_FLAGS | None = None

    @field_validator("delta_x", "delta_y", mode="before")
    @classmethod
    def _actual_delta(cls, value: object) -> float:
        return _finite_number(value)


class DevicePointerDragRequest(_DeviceActionRequest):
    intent: Literal["drag"]
    start_x: _COORD
    start_y: _COORD
    end_x: _COORD
    end_y: _COORD
    duration_ms: Annotated[int, Field(ge=1, le=60_000)] = 200
    key_modifier_flags: _MODIFIER_FLAGS | None = None


DevicePointerBranch: TypeAlias = Annotated[
    DevicePointerTapRequest
    | DevicePointerClickRequest
    | DevicePointerHoverRequest
    | DevicePointerScrollRequest
    | DevicePointerDragRequest,
    Field(discriminator="intent"),
]


class DevicePointerRequest(_PrivateRootModel[DevicePointerBranch]):
    pass


class MacKeyInput(_StrictModel):
    key: _MAC_KEY_NAME
    modifier_flags: _MODIFIER_FLAGS = 0


class _MacosKeysRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    keys: Annotated[tuple[MacKeyInput, ...], Field(min_length=1, max_length=1024)]
    timeout_seconds: float = Field(default=90.0, gt=0.0, le=120.0)

    @field_validator("keys", mode="before")
    @classmethod
    def _keys_array(cls, value: object) -> object:
        return _json_array(value)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class MacosSystemKeysRequest(_MacosKeysRequest):
    target: Literal["system"]


class MacosElementKeysRequest(_MacosKeysRequest):
    target: Literal["element"]
    locator: LocatorV1
    wait_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)

    @field_validator("wait_timeout_seconds", mode="before")
    @classmethod
    def _actual_wait(cls, value: object) -> float:
        return _finite_number(value)


MacosKeysBranch: TypeAlias = Annotated[
    MacosSystemKeysRequest | MacosElementKeysRequest,
    Field(discriminator="target"),
]


class MacosKeysRequest(_PrivateRootModel[MacosKeysBranch]):
    pass


class AutomationLocatorDocument(_StrictModel):
    by: Literal[
        "id",
        "accessibility id",
        "xpath",
        "name",
        "class name",
        "-ios predicate string",
        "-ios class chain",
    ]
    value: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)]
    package: Annotated[StrictUtf8, Field(max_length=255)] | None
    raw_id: bool
    parent: AutomationLocatorDocument | None
    predicate: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)] | None = None

    @field_validator("value", "predicate")
    @classmethod
    def _without_nul(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("locator values must not contain NUL")
        return value

    @model_validator(mode="after")
    def _bounded_chain(self) -> AutomationLocatorDocument:
        depth = 0
        current: AutomationLocatorDocument | None = self
        while current is not None:
            depth += 1
            if depth > 16:
                raise ValueError("locator chain exceeds 16 levels")
            current = current.parent
        return self

    @model_serializer(mode="wrap")
    def _preserve_predicate_presence(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        serialized = handler(self)
        if not isinstance(serialized, dict):
            raise TypeError("locator serializer returned a non-object")
        if "predicate" not in self.model_fields_set:
            serialized.pop("predicate", None)
        return serialized


class ObservationScopeDocument(_StrictModel):
    kind: Literal["root", "element", "declared_parent"]
    locator: AutomationLocatorDocument | None
    range_locator: AutomationLocatorDocument | None


BoundsDocument: TypeAlias = Annotated[
    tuple[int, int, int, int], BeforeValidator(_json_array)
]
ObservationDocumentValue: TypeAlias = (
    StrictUtf8 | int | float | bool | BoundsDocument | None
)


class ValueObservationDocument(_StrictModel):
    state: Literal["value"]
    value: ObservationDocumentValue


class MissingObservationDocument(_StrictModel):
    state: Literal["missing"]


class UnknownObservationDocument(_StrictModel):
    state: Literal["unknown"]


class NotApplicableObservationDocument(_StrictModel):
    state: Literal["not_applicable"]


ObservedValueDocument: TypeAlias = Annotated[
    ValueObservationDocument
    | MissingObservationDocument
    | UnknownObservationDocument
    | NotApplicableObservationDocument,
    Field(discriminator="state"),
]


class AttributeValueDocument(_StrictModel):
    name: _ELEMENT_ATTRIBUTE
    state: Literal["value"]
    value: ObservationDocumentValue


class AttributeMissingDocument(_StrictModel):
    name: _ELEMENT_ATTRIBUTE
    state: Literal["missing"]


class AttributeUnknownDocument(_StrictModel):
    name: _ELEMENT_ATTRIBUTE
    state: Literal["unknown"]


class AttributeNotApplicableDocument(_StrictModel):
    name: _ELEMENT_ATTRIBUTE
    state: Literal["not_applicable"]


AttributeObservationDocument: TypeAlias = Annotated[
    AttributeValueDocument
    | AttributeMissingDocument
    | AttributeUnknownDocument
    | AttributeNotApplicableDocument,
    Field(discriminator="state"),
]


class SourceMetadataDocument(_StrictModel):
    allow_invisible_elements: bool
    enable_multi_windows: bool
    snapshot_max_depth: int | None


class ViewportDocument(_StrictModel):
    width: ObservedValueDocument
    height: ObservedValueDocument
    rotation: ObservedValueDocument


def _compact_tree_schema(schema: dict[str, Any]) -> None:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    compact_names = set(TreeNodeDocument.model_fields) - {
        "children",
        "visible",
        "viewport_relation",
    }
    for name in compact_names:
        field_schema = properties.get(name)
        if not isinstance(field_schema, dict):
            continue
        variants = field_schema.get("anyOf")
        if isinstance(variants, list):
            non_null = [item for item in variants if item != {"type": "null"}]
            if len(non_null) == 1 and isinstance(non_null[0], dict):
                title = field_schema.get("title")
                field_schema.clear()
                field_schema.update(non_null[0])
                if title is not None:
                    field_schema["title"] = title
            else:
                field_schema["anyOf"] = non_null
        field_schema.pop("default", None)


class TreeNodeDocument(_StrictModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        json_schema_extra=_compact_tree_schema,
    )

    children: tuple[TreeNodeDocument, ...]
    visible: Literal["visible", "partially_visible", "not_visible", "unknown"]
    viewport_relation: Literal[
        "inside",
        "intersects",
        "outside_left",
        "outside_right",
        "outside_above",
        "outside_below",
        "unknown",
    ]
    type: StrictUtf8 | None = None
    type_ns: Literal["android.view", "android.widget", "XCUIElementType"] | None = None
    id: StrictUtf8 | None = None
    text: StrictUtf8 | None = None
    desc: StrictUtf8 | None = None
    package: StrictUtf8 | None = None
    enabled: bool | None = None
    focused: bool | None = None
    checked: bool | None = None
    selected: bool | None = None
    bounds: BoundsDocument | Literal["parent"] | None = None
    window_id: int | None = None
    label: StrictUtf8 | None = None
    title: StrictUtf8 | None = None
    value: StrictUtf8 | None = None
    placeholder_value: StrictUtf8 | None = None
    element_type: int | None = None
    missing: tuple[_TREE_VALUE_NAME, ...] | None = Field(
        default=None,
        min_length=1,
        max_length=16,
        json_schema_extra={"uniqueItems": True},
    )
    unknown: tuple[_TREE_VALUE_NAME, ...] | None = Field(
        default=None,
        min_length=1,
        max_length=16,
        json_schema_extra={"uniqueItems": True},
    )
    na: tuple[_TREE_VALUE_NAME, ...] | None = Field(
        default=None,
        min_length=1,
        max_length=16,
        json_schema_extra={"uniqueItems": True},
    )

    @field_validator("children", "missing", "unknown", "na", mode="before")
    @classmethod
    def _array_fields(cls, value: object) -> object:
        if value is None:
            return None
        return _json_array(value)

    @model_validator(mode="before")
    @classmethod
    def _compact_fields_are_never_null(cls, value: object) -> object:
        if isinstance(value, dict):
            required = {"children", "visible", "viewport_relation"}
            if any(
                item is None for name, item in value.items() if name not in required
            ):
                raise ValueError("compact tree fields cannot be null")
        return value

    @model_validator(mode="after")
    def _unique_state_arrays(self) -> TreeNodeDocument:
        for values in (self.missing, self.unknown, self.na):
            if values is not None and len(values) != len(set(values)):
                raise ValueError("compact tree state arrays must be unique")
        return self

    @model_serializer(mode="wrap")
    def _omit_absent_compact_fields(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, object]:
        serialized = handler(self)
        if not isinstance(serialized, dict):
            raise TypeError("tree node serializer returned a non-object")
        return {key: value for key, value in serialized.items() if value is not None}


class RawNodeDocument(_StrictModel):
    tag: Annotated[StrictUtf8, Field(max_length=256)]
    attributes: tuple[
        tuple[Annotated[StrictUtf8, Field(max_length=256)], StrictUtf8], ...
    ] = Field(max_length=64)
    children: tuple[RawNodeDocument, ...]

    @field_validator("attributes", mode="before")
    @classmethod
    def _attribute_pairs(cls, value: object) -> object:
        converted = _json_array(value)
        assert isinstance(converted, tuple)
        return tuple(_json_array(item) for item in converted)

    @field_validator("children", mode="before")
    @classmethod
    def _children_array(cls, value: object) -> object:
        return _json_array(value)


class TreePayloadDocument(_StrictModel):
    roots: tuple[TreeNodeDocument, ...]
    viewport: ViewportDocument

    @field_validator("roots", mode="before")
    @classmethod
    def _roots_array(cls, value: object) -> object:
        return _json_array(value)


class AttributesPayloadDocument(_StrictModel):
    attributes: tuple[AttributeObservationDocument, ...]

    @field_validator("attributes", mode="before")
    @classmethod
    def _attributes_array(cls, value: object) -> object:
        return _json_array(value)


class StructurePayloadDocument(_StrictModel):
    roots: tuple[RawNodeDocument, ...]
    target_path: tuple[Annotated[int, Field(ge=0)], ...] = Field(max_length=128)

    @field_validator("roots", "target_path", mode="before")
    @classmethod
    def _array_fields(cls, value: object) -> object:
        return _json_array(value)


class TreeObservationDocument(_StrictModel):
    document_schema: Literal[1] = Field(alias="schema")
    kind: Literal["tree"]
    operation_id: _OBSERVATION_OPERATION_ID
    observed_at: _OBSERVED_AT
    scope: ObservationScopeDocument
    coverage: _TREE_COVERAGE
    complete_for_requested_scope: bool
    upstream_completeness: Literal["unknown"]
    source: SourceMetadataDocument
    payload: TreePayloadDocument

    @model_validator(mode="after")
    def _tree_scope_and_completeness(self) -> TreeObservationDocument:
        if self.complete_for_requested_scope != (self.coverage == "requested_scope"):
            raise ValueError("tree coverage must match completeness")
        if self.scope.kind == "root":
            if self.scope.locator is not None or self.scope.range_locator is not None:
                raise ValueError("root tree scope cannot carry a locator")
        elif (
            self.scope.kind != "element"
            or self.scope.locator is None
            or self.scope.locator != self.scope.range_locator
        ):
            raise ValueError("scoped tree must carry one matching Element locator")
        return self


class AttributesObservationDocument(_StrictModel):
    document_schema: Literal[1] = Field(alias="schema")
    kind: Literal["element"]
    operation_id: _OBSERVATION_OPERATION_ID
    observed_at: _OBSERVED_AT
    scope: ObservationScopeDocument
    coverage: Literal["requested_scope"]
    complete_for_requested_scope: Literal[True]
    upstream_completeness: Literal["unknown"]
    consistency: Literal["sequential_non_atomic"]
    payload: AttributesPayloadDocument

    @model_validator(mode="after")
    def _element_scope(self) -> AttributesObservationDocument:
        if (
            self.scope.kind != "element"
            or self.scope.locator is None
            or self.scope.locator != self.scope.range_locator
        ):
            raise ValueError("attribute scope must carry one matching Element locator")
        return self


class StructureObservationDocument(_StrictModel):
    document_schema: Literal[1] = Field(alias="schema")
    kind: Literal["structure"]
    operation_id: _OBSERVATION_OPERATION_ID
    observed_at: _OBSERVED_AT
    scope: ObservationScopeDocument
    coverage: _STRUCTURE_COVERAGE
    complete_for_requested_scope: bool
    upstream_completeness: Literal["unknown"]
    source: SourceMetadataDocument
    payload: StructurePayloadDocument

    @model_validator(mode="after")
    def _structure_scope_and_completeness(self) -> StructureObservationDocument:
        if self.complete_for_requested_scope != (self.coverage == "requested_scope"):
            raise ValueError("structure coverage must match completeness")
        if (
            self.scope.kind not in ("element", "declared_parent")
            or self.scope.locator is None
            or self.scope.range_locator is None
        ):
            raise ValueError("structure scope must carry target and range locators")
        return self


ObservationDocument: TypeAlias = Annotated[
    TreeObservationDocument
    | AttributesObservationDocument
    | StructureObservationDocument,
    Field(discriminator="kind"),
]


class ObservationData(_StrictModel):
    mode: Literal["tree", "attributes", "structure"]
    document: SkipValidation[ObservationDocument]


class ObservationResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: _OBSERVATION_OPERATION_ID
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: ObservationData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value

    pass


class ElementClickData(_StrictModel):
    action: Literal["click", "double_click", "right_click", "hover", "long_click"]
    session_state: Literal["active"]
    busy: Literal[False]


class ElementClickResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: ElementClickData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


class ElementImeActionData(_StrictModel):
    action: Literal["ime_action"]
    session_state: Literal["active"]
    busy: Literal[False]


class ElementImeActionResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: ElementImeActionData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


class ElementSwipeData(_StrictModel):
    intent: Literal["swipe"]
    can_scroll_more: None
    session_state: Literal["active"]
    busy: Literal[False]


class ElementScrollData(_StrictModel):
    intent: Literal["scroll"]
    can_scroll_more: bool
    session_state: Literal["active"]
    busy: Literal[False]


class ElementScrollToData(_StrictModel):
    intent: Literal["scroll_to"]
    can_scroll_more: None
    session_state: Literal["active"]
    busy: Literal[False]


class ElementDragAndDropData(_StrictModel):
    intent: Literal["drag_and_drop"]
    can_scroll_more: None
    session_state: Literal["active"]
    busy: Literal[False]


class ElementScrollByData(_StrictModel):
    intent: Literal["scroll_by"]
    can_scroll_more: None
    session_state: Literal["active"]
    busy: Literal[False]


class ElementMacosSwipeData(_StrictModel):
    intent: Literal["macos_swipe"]
    can_scroll_more: None
    session_state: Literal["active"]
    busy: Literal[False]


ElementGestureData: TypeAlias = Annotated[
    ElementSwipeData
    | ElementScrollData
    | ElementScrollToData
    | ElementDragAndDropData
    | ElementScrollByData
    | ElementMacosSwipeData,
    Field(discriminator="intent"),
]


class ElementGestureResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: ElementGestureData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


class ElementTextData(_StrictModel):
    intent: Literal["send", "clear", "replace"]
    session_state: Literal["active"]
    busy: Literal[False]


class ElementTextResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: ElementTextData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


class DeviceBackData(_StrictModel):
    action: Literal["back"]
    session_state: Literal["active"]
    busy: Literal[False]


class DeviceBackResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: DeviceBackData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


class _DeviceToolData(_StrictModel):
    session_state: Literal["active"]
    busy: Literal[False]


class DeviceKeyData(_DeviceToolData):
    kind: Literal["press", "long_press"]


class DeviceKeyboardHideData(_DeviceToolData):
    hidden: bool


class DeviceClipboardGetData(_DeviceToolData):
    intent: Literal["get"]
    text: _CLIPBOARD_TEXT


class DeviceClipboardSetData(_DeviceToolData):
    intent: Literal["set"]


DeviceClipboardData: TypeAlias = Annotated[
    DeviceClipboardGetData | DeviceClipboardSetData,
    Field(discriminator="intent"),
]


class DeviceAlertData(_DeviceToolData):
    action: Literal["accept", "dismiss"]


class DeviceStatusBarData(_DeviceToolData):
    command: Literal["expandNotifications", "expandSettings", "collapse"]
    output: _STATUS_OUTPUT


class AppLifecycleActivateData(_DeviceToolData):
    intent: Literal["activate"]


class AppLifecycleTerminateData(_DeviceToolData):
    intent: Literal["terminate"]
    terminated: bool


class AppLifecycleQueryStateData(_DeviceToolData):
    intent: Literal["query_state"]
    app_state: Literal[0, 1, 2, 3, 4]


class AppLifecycleLaunchData(_DeviceToolData):
    intent: Literal["launch"]


AppLifecycleData: TypeAlias = Annotated[
    AppLifecycleActivateData
    | AppLifecycleTerminateData
    | AppLifecycleQueryStateData
    | AppLifecycleLaunchData,
    Field(discriminator="intent"),
]


class AppPackageInstallData(_DeviceToolData):
    intent: Literal["install"]


class AppPackageRemoveData(_DeviceToolData):
    intent: Literal["remove"]
    removed: bool


AppPackageData: TypeAlias = Annotated[
    AppPackageInstallData | AppPackageRemoveData,
    Field(discriminator="intent"),
]


class DeviceScreenshotData(_DeviceToolData):
    byte_length: Annotated[int, Field(ge=58, le=MAX_INTEGRATION_SCREENSHOT_BYTES)]
    png_base64: StrictUtf8


class DevicePointerData(_DeviceToolData):
    intent: Literal["tap", "click", "hover", "scroll", "drag"]


class MacosKeysData(_DeviceToolData):
    target: Literal["system", "element"]


class _DeviceToolResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


class DeviceKeyResult(_DeviceToolResult):
    data: DeviceKeyData


class DeviceKeyboardHideResult(_DeviceToolResult):
    data: DeviceKeyboardHideData


class DeviceClipboardResult(_DeviceToolResult):
    data: DeviceClipboardData


class DeviceAlertResult(_DeviceToolResult):
    data: DeviceAlertData


class DeviceStatusBarResult(_DeviceToolResult):
    data: DeviceStatusBarData


class AppLifecycleResult(_DeviceToolResult):
    data: AppLifecycleData


class AppPackageResult(_DeviceToolResult):
    data: AppPackageData


class DeviceScreenshotResult(_DeviceToolResult):
    data: DeviceScreenshotData


class DevicePointerResult(_DeviceToolResult):
    data: DevicePointerData


class MacosKeysResult(_DeviceToolResult):
    data: MacosKeysData


class AndroidSessionOpenRequest(_StrictModel):
    schema_version: Literal[1]
    platform: Literal["android"]
    device_id: Annotated[
        StrictUtf8,
        Field(
            min_length=1,
            max_length=1024,
            pattern=r"^[^\s\x00-\x1f\x7f-\x9f]+$",
        ),
    ]
    app_id: (
        Annotated[
            StrictUtf8,
            Field(
                min_length=1,
                max_length=255,
                pattern=r"^[^\s\x00-\x1f\x7f-\x9f]+$",
            ),
        ]
        | None
    ) = None
    app_path: Annotated[StrictUtf8, Field(min_length=1, max_length=4096)] | None = None
    auto_launch: bool = False
    force_app_launch: bool = False
    should_terminate_app: bool = False
    new_command_timeout_seconds: float = Field(default=500.0, ge=0.0, le=86400.0)
    timeout_seconds: float = Field(default=180.0, gt=0.0, le=300.0)

    @field_validator("device_id")
    @classmethod
    def _device_identifier(cls, value: str) -> str:
        return _safe_identifier(value, "device id")

    @field_validator("app_id")
    @classmethod
    def _application_identifier(cls, value: str | None) -> str | None:
        return None if value is None else _safe_identifier(value, "app id")

    @field_validator("app_path")
    @classmethod
    def _absolute_application_path(cls, value: str | None) -> str | None:
        if value is not None and not Path(value).is_absolute():
            raise ValueError("app_path must be absolute")
        return value

    @field_validator("new_command_timeout_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class MacosSessionOpenRequest(_StrictModel):
    schema_version: Literal[1]
    platform: Literal["macos"]
    bundle_id: _MAC_BUNDLE_ID | None = None
    app_path: _MAC_APP_PATH | None = None
    arguments: Annotated[tuple[_MAC_ARG_ITEM, ...], Field(max_length=64)] | None = None
    no_reset: bool = True
    skip_app_kill: bool | None = None
    new_command_timeout_seconds: float = Field(default=300.0, ge=0.0, le=86400.0)
    timeout_seconds: float = Field(default=180.0, gt=0.0, le=300.0)

    @field_validator("arguments", mode="before")
    @classmethod
    def _arguments_array(cls, value: object) -> object:
        return None if value is None else _json_array(value)

    @field_validator("new_command_timeout_seconds", "timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)

    @model_validator(mode="after")
    def _arguments_require_application(self) -> Self:
        if (
            self.arguments is not None
            and self.bundle_id is None
            and self.app_path is None
        ):
            raise ValueError("arguments require bundle_id or app_path")
        return self


SessionOpenBranch: TypeAlias = Annotated[
    AndroidSessionOpenRequest | MacosSessionOpenRequest,
    Field(discriminator="platform"),
]


class SessionOpenRequest(_PrivateRootModel[SessionOpenBranch]):
    pass


class SessionStatusRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle


class SessionCloseRequest(_StrictModel):
    schema_version: Literal[1]
    session_handle: SessionHandle
    timeout_seconds: float = Field(default=60.0, gt=0.0, le=120.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_number(cls, value: object) -> float:
        return _finite_number(value)


class SessionData(_StrictModel):
    ownership: Literal["mcp", "toolcall", "cli"]
    platform: Literal["android", "macos"]
    session_handle: SessionHandle
    session_state: Literal["active", "uncertain", "closing", "closed"]
    device_id: Annotated[
        StrictUtf8,
        Field(
            min_length=1,
            max_length=1024,
            pattern=r"^[^\s\x00-\x1f\x7f-\x9f]+$",
        ),
    ]
    target_app_id: (
        Annotated[
            StrictUtf8,
            Field(
                min_length=1,
                max_length=255,
                pattern=r"^[^\s\x00-\x1f\x7f-\x9f]+$",
            ),
        ]
        | None
    )
    busy: bool

    @field_validator("device_id")
    @classmethod
    def _device_identifier(cls, value: str) -> str:
        return _safe_identifier(value, "device id")


class _SessionResult(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    execution: Literal["completed"]
    operation_id: None
    request_state: None
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    automation_module_status: AutomationModuleStatus
    data: SessionData

    @field_validator("warnings")
    @classmethod
    def _unique_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("warnings must be unique")
        return value


class SessionOpenResult(_SessionResult):
    @model_validator(mode="after")
    def _opened_active(self) -> SessionOpenResult:
        if self.data.session_state != "active" or self.data.busy:
            raise ValueError("open result must be active and idle")
        return self


class SessionStatusResult(_SessionResult):
    pass


class SessionCloseResult(_SessionResult):
    @model_validator(mode="after")
    def _closed_idle(self) -> SessionCloseResult:
        if self.data.session_state != "closed" or self.data.busy:
            raise ValueError("close result must be closed and idle")
        return self


class ToolErrorData(_StrictModel):
    schema_version: Literal[1]
    call_id: CallId
    code: StableCode
    operation_id: (
        Annotated[
            StrictUtf8,
            Field(min_length=1, max_length=128, pattern=_ERROR_OPERATION_ID_PATTERN),
        ]
        | None
    )
    request_state: Literal["not_sent", "response_received", "response_unknown"] | None
    completed_steps: tuple[StableCode, ...] = Field(
        max_length=32, json_schema_extra={"uniqueItems": True}
    )
    cleanup_status: Literal["not_needed", "completed", "failed", "unknown"]
    cleanup_error_count: int = Field(ge=0, le=32)
    warnings: tuple[StableCode, ...] = Field(
        max_length=16, json_schema_extra={"uniqueItems": True}
    )
    session_handle: SessionHandle | None
    session_state: Literal["active", "uncertain", "closing", "closed"] | None

    @model_validator(mode="after")
    def _unique_arrays_and_resource_pair(self) -> ToolErrorData:
        if len(self.completed_steps) != len(set(self.completed_steps)):
            raise ValueError("completed_steps must be unique")
        if len(self.warnings) != len(set(self.warnings)):
            raise ValueError("warnings must be unique")
        if (self.session_handle is None) != (self.session_state is None):
            raise ValueError("session handle and state must be present together")
        return self


def canonical_value_and_json(model: BaseModel) -> tuple[dict[str, Any], str]:
    """Dump once and derive both MCP success channels from the same Python value."""
    value = model.model_dump(mode="python", by_alias=True, warnings=False)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", errors="strict")
    if isinstance(model, ObservationResult) and len(encoded) > 69_632:
        raise ValueError("observation result exceeds the defensive ceiling")
    if (
        not isinstance(model, (ToolErrorData, ObservationResult))
        and len(encoded) > _MAX_SUCCESS_BYTES
    ):
        raise ValueError("structured result exceeds the defensive ceiling")
    return value, encoded.decode("utf-8")


def canonical_json(model: BaseModel) -> str:
    """Return the one canonical JSON representation used for an error payload."""
    return canonical_value_and_json(model)[1]
