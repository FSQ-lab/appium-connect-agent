"""Strict request, result, and error values for the local stdio MCP tools."""

from __future__ import annotations

import json
import math
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
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


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

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
    timeout_seconds: float = Field(default=10.0, gt=0.0, le=60.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_float(cls, value: object) -> object:
        if type(value) is not float:
            raise ValueError("timeout_seconds must be a float")
        return value


class DeviceListRequest(_StrictModel):
    schema_version: Literal[1]
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=60.0)

    @field_validator("timeout_seconds", mode="before")
    @classmethod
    def _actual_float(cls, value: object) -> object:
        if type(value) is not float:
            raise ValueError("timeout_seconds must be a float")
        return value


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


class PlatformData(_StrictModel):
    host: Literal["macos"]
    target: Literal["android_native"]
    driver: Literal["uiautomator2"]


class CapabilityData(_StrictModel):
    integration_form: Literal["mcp"]
    transport: Literal["stdio"]
    protocol_target: Literal["2026-07-28"]
    host_compatibility: Literal["unqualified"]
    adb_configured: Literal[True]
    platform: PlatformData
    tools: tuple[
        Literal["appium.capabilities.get"],
        Literal["appium.runtime.check"],
        Literal["appium.devices.list"],
        Literal["appium.session.open"],
        Literal["appium.session.status"],
        Literal["appium.session.close"],
    ]
    limitations: tuple[
        Literal["no_ui_tools"],
        Literal["single_session_capacity"],
        Literal["opaque_handle_process_local"],
        Literal["no_session_attach_recovery"],
        Literal["no_cli_sdk_product"],
        Literal["no_http_transport"],
        Literal["no_clear_app"],
        Literal["automation_module_e2e_unqualified"],
        Literal["no_specific_host_qualification"],
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
    target: Literal["Android"]
    driver: Literal["UiAutomator2"]
    checks: tuple[RuntimeCheck, ...] = Field(max_length=32)
    observer_errors: tuple[Annotated[StrictUtf8, Field(max_length=512)], ...] = Field(
        max_length=8
    )

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


class SessionOpenRequest(_StrictModel):
    schema_version: Literal[1]
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
    ownership: Literal["mcp"]
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


def canonical_json(model: BaseModel) -> str:
    """Return the one canonical JSON representation used on both result channels."""
    value = model.model_dump(mode="json")
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", errors="strict")
    if not isinstance(model, ToolErrorData) and len(encoded) > _MAX_SUCCESS_BYTES:
        raise ValueError("structured result exceeds the defensive ceiling")
    return encoded.decode("utf-8")
