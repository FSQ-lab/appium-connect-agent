"""Private framed protocol shared by the product CLI and local bridge."""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Mapping
from typing import Annotated, Literal, TypeAlias

import anyio
from anyio.abc import ByteReceiveStream, ByteSendStream
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    field_validator,
)

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_BOOTSTRAP_BYTES = 16 * 1024
_FRAME = struct.Struct(">I")


class ProtocolError(Exception):
    """A peer supplied malformed or out-of-contract protocol data."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CallRequest(_StrictModel):
    protocol_version: Literal[1]
    operation: Literal["tool.call"]
    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, JsonValue]


class StatusRequest(_StrictModel):
    protocol_version: Literal[1]
    operation: Literal["daemon.status"]


class StopRequest(_StrictModel):
    protocol_version: Literal[1]
    operation: Literal["daemon.stop"]


BridgeRequest: TypeAlias = Annotated[
    CallRequest | StatusRequest | StopRequest, Field(discriminator="operation")
]
REQUEST_ADAPTER = TypeAdapter(BridgeRequest)


class CallResponse(_StrictModel):
    protocol_version: Literal[1] = 1
    kind: Literal["tool_result"] = "tool_result"
    canonical_json: str
    is_error: bool


class StatusResponse(_StrictModel):
    protocol_version: Literal[1] = 1
    kind: Literal["daemon_status"] = "daemon_status"
    state: Literal["running"] = "running"
    accepting: Literal[True] = True


class StopResponse(_StrictModel):
    protocol_version: Literal[1] = 1
    kind: Literal["daemon_stopped"] = "daemon_stopped"
    shutdown: Literal["clean", "degraded"]


class BridgeErrorResponse(_StrictModel):
    protocol_version: Literal[1] = 1
    kind: Literal["bridge_error"] = "bridge_error"
    code: Literal[
        "protocol_error",
        "daemon_stopping",
        "internal_error",
        "response_too_large",
    ]


BridgeResponse: TypeAlias = Annotated[
    CallResponse | StatusResponse | StopResponse | BridgeErrorResponse,
    Field(discriminator="kind"),
]
RESPONSE_ADAPTER = TypeAdapter(BridgeResponse)


class BootstrapRequest(_StrictModel):
    protocol_version: Literal[1]
    config: str
    adb_executable: str
    socket: str
    idle_timeout_seconds: float

    @field_validator("idle_timeout_seconds")
    @classmethod
    def _finite_idle_timeout(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("idle timeout must be finite and positive")
        return value


BOOTSTRAP_ADAPTER = TypeAdapter(BootstrapRequest)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate JSON member")
        result[key] = value
    return result


def decode_json_object(data: bytes, *, maximum: int) -> dict[str, object]:
    if not data or len(data) > maximum:
        raise ProtocolError("invalid frame size")
    try:
        text = data.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ProtocolError("non-finite JSON number")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ProtocolError) as error:
        raise ProtocolError("invalid JSON object") from error
    if not isinstance(value, dict):
        raise ProtocolError("JSON value must be an object")
    return value


def canonical_json_bytes(value: Mapping[str, object] | BaseModel) -> bytes:
    serializable: object = (
        value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    )
    try:
        return json.dumps(
            serializable,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ProtocolError("value is not canonical JSON") from error


async def receive_exactly(stream: ByteReceiveStream, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        try:
            chunk = await stream.receive(remaining)
        except anyio.EndOfStream as error:
            raise ProtocolError("truncated frame") from error
        if not chunk:
            raise ProtocolError("truncated frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


async def receive_frame(
    stream: ByteReceiveStream, *, maximum: int, timeout_seconds: float = 10.0
) -> bytes:
    try:
        with anyio.fail_after(timeout_seconds):
            header = await receive_exactly(stream, _FRAME.size)
            (length,) = _FRAME.unpack(header)
            if length == 0 or length > maximum:
                raise ProtocolError("invalid frame size")
            return await receive_exactly(stream, length)
    except TimeoutError as error:
        raise ProtocolError("frame timeout") from error


async def send_frame(
    stream: ByteSendStream,
    payload: bytes,
    *,
    maximum: int,
    timeout_seconds: float = 10.0,
) -> None:
    if not payload or len(payload) > maximum:
        raise ProtocolError("invalid frame size")
    try:
        with anyio.fail_after(timeout_seconds):
            await stream.send(_FRAME.pack(len(payload)) + payload)
    except TimeoutError as error:
        raise ProtocolError("frame timeout") from error


def parse_request(payload: bytes) -> BridgeRequest:
    try:
        return REQUEST_ADAPTER.validate_python(
            decode_json_object(payload, maximum=MAX_REQUEST_BYTES), strict=True
        )
    except ValidationError as error:
        raise ProtocolError("invalid request") from error


def parse_response(payload: bytes) -> BridgeResponse:
    try:
        return RESPONSE_ADAPTER.validate_python(
            decode_json_object(payload, maximum=MAX_RESPONSE_BYTES), strict=True
        )
    except ValidationError as error:
        raise ProtocolError("invalid response") from error
