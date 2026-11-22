from __future__ import annotations

import base64
import hashlib
import json
import struct
import threading
import zlib
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from appium_connect_agent.automation import (
    Bounds,
    CommandError,
    DisplaySize,
    ExecutionUnknownError,
    ImageRegion,
    InvalidRequestError,
    InvalidSessionStateError,
    OperationCancelledError,
    OperationTimeoutError,
    Point,
    Session,
    SessionBusyError,
    VisualImageMatch,
    VisualInspection,
    VisualMode,
    VisualProvider,
    VisualProviderRequest,
    VisualProviderResponse,
    VisualTargetCandidate,
    create_mac2_session,
    create_xcuitest_session,
    sample_png_color,
)
from appium_connect_agent.automation import _session as session_module
from appium_connect_agent.runtime import OperationControl, RuntimeConnection
from tests.automation._action_protocol import (
    ActionProtocolService,
    Request,
    ResponsePlan,
    assert_error,
    connected,
    session_for,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, data: bytes = b"") -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def _png(
    *idat_parts: bytes,
    width: int = 1080,
    height: int = 2400,
    before_iend: tuple[bytes, ...] = (),
) -> bytes:
    parts = idat_parts if idat_parts else (b"0123456789",)
    return b"".join(
        (
            _PNG_SIGNATURE,
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            *(_chunk(b"IDAT", part) for part in parts),
            *before_iend,
            _chunk(b"IEND"),
        )
    )


def _encoded_png(
    width: int = 1080,
    height: int = 2400,
    *,
    before_iend: tuple[bytes, ...] = (),
) -> tuple[bytes, str]:
    raw = _png(width=width, height=height, before_iend=before_iend)
    return raw, base64.b64encode(raw).decode("ascii")


class VisualProtocolService(ActionProtocolService):
    @staticmethod
    def _kind(request: Request) -> str:
        if request.method == "GET" and request.path.endswith("/screenshot"):
            return "take_screenshot"
        if (
            request.method == "POST"
            and request.path.endswith("/execute/sync")
            and request.body is not None
        ):
            script = request.body.get("script")
            if script == "mobile: deviceInfo":
                return "display_size"
            if script == "mobile: deviceScreenInfo":
                return "ios_display_size"
            if script == "macos: listDisplays":
                return "macos_display_size"
            if script == "mobile: clickGesture":
                return "tap_at"
        return ActionProtocolService._kind(request)

    def _default_payload(self, request: Request, kind: str) -> object:
        if kind == "take_screenshot":
            _, encoded = _encoded_png(1080, 2400)
            return {"value": encoded}
        if kind == "display_size":
            return {"value": {"realDisplaySize": "1080x2400"}}
        if kind == "ios_display_size":
            return {"value": {"screenSize": {"width": 390, "height": 844}}}
        if kind == "macos_display_size":
            return {
                "value": {
                    "1": {
                        "id": 1,
                        "isMain": True,
                        "rect": {"x": 0, "y": 0, "width": 1512, "height": 982},
                    }
                }
            }
        if kind == "tap_at":
            return {"value": None}
        return super()._default_payload(request, kind)


class StubVisualProvider:
    def __init__(
        self,
        fn: Callable[[VisualProviderRequest], VisualProviderResponse]
        | VisualProviderResponse,
    ) -> None:
        self._fn = fn
        self.requests: list[VisualProviderRequest] = []

    def inspect(self, request: VisualProviderRequest) -> VisualProviderResponse:
        self.requests.append(request)
        if callable(self._fn):
            return self._fn(request)
        return self._fn


@pytest.fixture
def service() -> Iterator[VisualProtocolService]:
    current = VisualProtocolService()
    with current:
        yield current


def ios_session_for(
    service: VisualProtocolService,
    connection: RuntimeConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> Session:
    monkeypatch.setattr(
        session_module,
        "_prepare_xcuitest_derived_data",
        lambda port, operation_id: f"/private/tmp/test-{port}",
    )
    return create_xcuitest_session(connection, f"IOS-VISUAL-{id(service)}")


def _platform_session(
    service: VisualProtocolService,
    connection: RuntimeConnection,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
) -> Session:
    if platform == "macos":
        return create_mac2_session(connection)
    if platform == "ios":
        return ios_session_for(service, connection, monkeypatch)
    return session_for(service, connection, "visual-platform")


def test_visual_provider_protocol_runtime_checkable() -> None:
    provider = StubVisualProvider(VisualProviderResponse(summary="ok"))
    assert isinstance(provider, VisualProvider)


def _mac_displays(width: int, height: int, *, multi: bool = False) -> dict[str, object]:
    displays: dict[str, object] = {
        "1": {
            "id": 1,
            "isMain": True,
            "rect": {"x": 0, "y": 0, "width": width, "height": height},
        }
    }
    if multi:
        displays["2"] = {
            "id": 2,
            "isMain": False,
            "rect": {"x": width, "y": 0, "width": width, "height": height},
        }
    return displays


def test_inspect_with_ai_extract_mode_three_platforms(
    service: VisualProtocolService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_png, encoded = _encoded_png(600, 800)
    expected_sha256 = hashlib.sha256(raw_png).hexdigest()
    service.queue(
        "take_screenshot",
        ResponsePlan(payload={"value": encoded}),
        ResponsePlan(payload={"value": encoded}),
        ResponsePlan(payload={"value": encoded}),
    )
    service.queue(
        "macos_display_size",
        ResponsePlan(payload={"value": _mac_displays(600, 800)}),
    )
    provider = StubVisualProvider(
        VisualProviderResponse(summary="Canvas shows red circle", candidates=())
    )
    with connected(service) as connection:
        android_session = session_for(service, connection, "visual-extract-android")
        region = ImageRegion(left=10, top=20, right=300, bottom=400)
        result = android_session.device.inspect_with_ai(
            "Describe canvas colors",
            provider=provider,
            mode="extract",
            region=region,
            max_candidates=3,
            control=OperationControl(timeout_seconds=10.0),
        )
        assert isinstance(result, VisualInspection)
        assert result.platform == "android"
        assert result.mode == "extract"
        assert result.image_size == DisplaySize(width=600, height=800)
        assert result.pointer_size is None
        assert result.png_sha256 == expected_sha256
        assert result.region == region
        assert result.summary == "Canvas shows red circle"
        assert result.candidates == ()
        assert len(provider.requests) == 1
        req = provider.requests[0]
        assert req.mode == "extract"
        assert req.prompt == "Describe canvas colors"
        assert req.png_bytes == raw_png
        assert "png_bytes" not in repr(req) or raw_png.decode("latin1") not in repr(req)
        assert (req.image_width, req.image_height) == (600, 800)
        assert req.region == region
        assert req.max_candidates == 3
        assert req.remaining_timeout_seconds is not None
        assert 0.0 < req.remaining_timeout_seconds <= 10.0
        assert service.of_kind("display_size") == []

        json_bytes = result.to_json()
        assert json_bytes is result.to_json()
        assert raw_png not in json_bytes
        decoded = json.loads(json_bytes)
        assert decoded["schema"] == 1
        assert decoded["kind"] == "visual"
        assert decoded["payload"] == {
            "candidates": [],
            "image_size": [600, 800],
            "mode": "extract",
            "platform": "android",
            "png_sha256": expected_sha256,
            "pointer_size": None,
            "region": [10, 20, 300, 400],
            "summary": "Canvas shows red circle",
        }
        with pytest.raises((AttributeError, FrozenInstanceError)):
            result.summary = "mutated"  # type: ignore[misc]
        android_session.quit()

        mac_session = create_mac2_session(connection)
        mac_result = mac_session.device.inspect_with_ai(
            "Read calculator display",
            provider=provider,
            mode="extract",
        )
        assert mac_result.platform == "macos"
        assert mac_result.mode == "extract"
        assert mac_result.pointer_size is None
        assert mac_result.summary == "Canvas shows red circle"
        assert len(service.of_kind("macos_display_size")) == 1
        mac_session.quit()

        ios_session = ios_session_for(service, connection, monkeypatch)
        ios_result = ios_session.device.inspect_with_ai(
            "Read calculator display", provider=provider
        )
        assert ios_result.platform == "ios"
        assert ios_result.pointer_size is None
        assert ios_result.summary == mac_result.summary
        assert ios_result.png_sha256 == expected_sha256
        assert service.of_kind("ios_display_size") == []
        ios_session.quit()


def test_inspect_with_ai_locate_mode_1to1_and_integer_scaled_coordinates(
    service: VisualProtocolService,
) -> None:
    raw_1to1, enc_1to1 = _encoded_png(1080, 2400)
    raw_half, enc_half = _encoded_png(540, 1200)
    raw_double, enc_double = _encoded_png(2160, 4800)
    service.queue(
        "take_screenshot",
        ResponsePlan(payload={"value": enc_1to1}),
        ResponsePlan(payload={"value": enc_half}),
        ResponsePlan(payload={"value": enc_double}),
    )
    service.queue(
        "display_size",
        ResponsePlan(payload={"value": {"realDisplaySize": "1080x2400"}}),
        ResponsePlan(payload={"value": {"realDisplaySize": "1080x2400"}}),
        ResponsePlan(payload={"value": {"realDisplaySize": "1080x2400"}}),
    )

    provider = StubVisualProvider(
        lambda req: VisualProviderResponse(
            summary="Found submit button",
            candidates=(
                VisualImageMatch(
                    label="Submit",
                    image_bounds=Bounds(x=100, y=200, width=80, height=40),
                    confidence=0.95,
                ),
            ),
        )
    )
    with connected(service) as connection:
        session = session_for(service, connection, "visual-locate")
        res1 = session.device.inspect_with_ai(
            "Locate Submit button",
            provider=provider,
            mode="locate",
            region=ImageRegion(left=50, top=150, right=300, bottom=350),
        )
        assert res1.mode == "locate"
        assert res1.image_size == DisplaySize(1080, 2400)
        assert res1.pointer_size == DisplaySize(1080, 2400)
        assert res1.png_sha256 == hashlib.sha256(raw_1to1).hexdigest()
        assert len(res1.candidates) == 1
        cand1 = res1.candidates[0]
        assert cand1 == VisualTargetCandidate(
            label="Submit",
            image_bounds=Bounds(x=100, y=200, width=80, height=40),
            pointer_bounds=Bounds(x=100, y=200, width=80, height=40),
            pointer_center=Point(x=140, y=220),
            confidence=0.95,
        )
        assert service.of_kind("tap_at") == []

        # Integer 2x scale: image 540x1200 -> pointer 1080x2400
        res2 = session.device.inspect_with_ai(
            "Locate Submit button scaled",
            provider=provider,
            mode="locate",
        )
        assert res2.image_size == DisplaySize(540, 1200)
        assert res2.pointer_size == DisplaySize(1080, 2400)
        assert res2.png_sha256 == hashlib.sha256(raw_half).hexdigest()
        cand2 = res2.candidates[0]
        assert cand2.pointer_bounds == Bounds(x=200, y=400, width=160, height=80)
        assert cand2.pointer_center == Point(x=280, y=440)

        # Reverse integer scale: image 2160x4800 -> pointer 1080x2400
        res3 = session.device.inspect_with_ai(
            "Locate Submit button downscaled",
            provider=provider,
            mode="locate",
        )
        assert res3.image_size == DisplaySize(2160, 4800)
        assert res3.pointer_size == DisplaySize(1080, 2400)
        assert res3.png_sha256 == hashlib.sha256(raw_double).hexdigest()
        cand3 = res3.candidates[0]
        assert cand3.pointer_bounds == Bounds(x=50, y=100, width=40, height=20)
        assert cand3.pointer_center == Point(x=70, y=110)
        session.quit()


def test_inspect_with_ai_macos_locate_1x_2x_retina_and_multi_or_mismatch_rejection(
    service: VisualProtocolService,
) -> None:
    _, enc_1x = _encoded_png(1512, 982)
    _, enc_2x = _encoded_png(3024, 1964)
    _, enc_mismatch = _encoded_png(1600, 982)
    service.queue(
        "take_screenshot",
        ResponsePlan(payload={"value": enc_1x}),
        ResponsePlan(payload={"value": enc_2x}),
        ResponsePlan(payload={"value": enc_2x}),
        ResponsePlan(payload={"value": enc_mismatch}),
        ResponsePlan(payload={"value": enc_1x}),
        ResponsePlan(payload={"value": enc_1x}),
    )
    service.queue(
        "macos_display_size",
        ResponsePlan(),
        ResponsePlan(),
        ResponsePlan(
            payload={
                "value": {
                    "1": {
                        "id": 1,
                        "isMain": True,
                        "rect": {"x": 0, "y": 0, "width": 1512, "height": 982},
                    },
                    "2": {
                        "id": 2,
                        "isMain": False,
                        "rect": {"x": 1512, "y": 0, "width": 1920, "height": 1080},
                    },
                }
            }
        ),
        ResponsePlan(),
        ResponsePlan(
            payload={
                "value": {
                    "1": {
                        "id": 1,
                        "isMain": True,
                        "rect": {"x": 0, "y": 0, "width": 1512.0, "height": 982.0},
                    }
                }
            }
        ),
        ResponsePlan(
            payload={
                "value": {
                    "1": {
                        "id": 1,
                        "isMain": True,
                        "rect": {"x": 0, "y": 0, "width": 10**400, "height": 982},
                    }
                }
            }
        ),
    )
    provider = StubVisualProvider(
        VisualProviderResponse(
            summary="Found keypad button",
            candidates=(
                VisualImageMatch(
                    label="Button 7",
                    image_bounds=Bounds(x=200, y=400, width=100, height=60),
                ),
            ),
        )
    )
    with connected(service) as connection:
        mac_session = create_mac2_session(connection)
        res_1x = mac_session.device.inspect_with_ai(
            "Locate Button 7 (1x)",
            provider=provider,
            mode="locate",
        )
        assert res_1x.platform == "macos"
        assert res_1x.pointer_size == DisplaySize(1512, 982)
        assert res_1x.candidates[0].pointer_bounds == Bounds(
            x=200, y=400, width=100, height=60
        )
        assert res_1x.candidates[0].pointer_center == Point(x=250, y=430)

        res_2x = mac_session.device.inspect_with_ai(
            "Locate Button 7 (2x Retina)",
            provider=provider,
            mode="locate",
        )
        assert res_2x.image_size == DisplaySize(3024, 1964)
        assert res_2x.pointer_size == DisplaySize(1512, 982)
        assert res_2x.candidates[0].pointer_bounds == Bounds(
            x=100, y=200, width=50, height=30
        )
        assert res_2x.candidates[0].pointer_center == Point(x=125, y=215)

        for _ in range(4):
            with pytest.raises(CommandError) as caught:
                mac_session.device.inspect_with_ai(
                    "Locate Button 7 rejected",
                    provider=provider,
                    mode="locate",
                )
            assert_error(
                caught.value,
                CommandError,
                "pointer_mapping_unavailable",
                "response_received",
                steps=("screenshot_captured", "display_size_read")
                if caught.value.completed_steps
                == ("screenshot_captured", "display_size_read")
                else ("screenshot_captured",),
            )
            assert caught.value.__cause__ is None
        assert len(provider.requests) == 2
        mac_session.quit()


def test_inspect_with_ai_ios_retina_mapping_and_mismatch_rejection(
    service: VisualProtocolService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, encoded_2x = _encoded_png(780, 1688)
    _, encoded_3x = _encoded_png(1170, 2532)
    _, encoded_mismatch = _encoded_png(800, 1688)
    service.queue(
        "take_screenshot",
        ResponsePlan(payload={"value": encoded_2x}),
        ResponsePlan(payload={"value": encoded_3x}),
        ResponsePlan(payload={"value": encoded_mismatch}),
    )
    provider = StubVisualProvider(
        VisualProviderResponse(
            summary="Found control",
            candidates=(
                VisualImageMatch(
                    label="Control",
                    image_bounds=Bounds(x=300, y=600, width=180, height=120),
                ),
            ),
        )
    )
    with connected(service) as connection:
        session = ios_session_for(service, connection, monkeypatch)
        result_2x = session.device.inspect_with_ai(
            "Locate control", provider=provider, mode="locate"
        )
        assert result_2x.platform == "ios"
        assert result_2x.image_size == DisplaySize(780, 1688)
        assert result_2x.pointer_size == DisplaySize(390, 844)
        assert result_2x.candidates[0].pointer_bounds == Bounds(150, 300, 90, 60)
        assert result_2x.candidates[0].pointer_center == Point(195, 330)

        result_3x = session.device.inspect_with_ai(
            "Locate control", provider=provider, mode="locate"
        )
        assert result_3x.image_size == DisplaySize(1170, 2532)
        assert result_3x.pointer_size == DisplaySize(390, 844)
        assert result_3x.candidates[0].pointer_bounds == Bounds(100, 200, 60, 40)
        assert result_3x.candidates[0].pointer_center == Point(130, 220)

        with pytest.raises(CommandError) as caught:
            session.device.inspect_with_ai(
                "Locate control", provider=provider, mode="locate"
            )
        assert_error(
            caught.value,
            CommandError,
            "pointer_mapping_unavailable",
            "response_received",
            steps=("screenshot_captured", "display_size_read"),
        )
        assert len(provider.requests) == 2
        assert len(service.of_kind("ios_display_size")) == 3
        session.quit()


@pytest.mark.parametrize(
    ("platform", "mode", "kind", "size"),
    [
        ("android", "locate", "display_size", {"realDisplaySize": "1080x0"}),
        (
            "ios",
            "locate",
            "ios_display_size",
            {"screenSize": {"width": True, "height": 844}},
        ),
        (
            "macos",
            "extract",
            "macos_display_size",
            _mac_displays(1080, 2400, multi=True),
        ),
    ],
)
def test_visual_invalid_geometry_fails_without_provider(
    service: VisualProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    mode: VisualMode,
    kind: str,
    size: object,
) -> None:
    service.queue(kind, ResponsePlan(payload={"value": size}))
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    with connected(service) as connection:
        session = _platform_session(service, connection, monkeypatch, platform)
        with pytest.raises(CommandError) as caught:
            session.device.inspect_with_ai("Find icon", provider=provider, mode=mode)
        assert_error(
            caught.value,
            CommandError,
            "pointer_mapping_unavailable",
            "response_received",
            steps=("screenshot_captured",),
        )
        assert len(service.of_kind(kind)) == 1
        assert provider.requests == []
        session.quit()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": "a\x00b"},
        {"prompt": "x" * 16_385},
        {"prompt": 123},
        {"provider": None},
        {"provider": object()},
        {"mode": "assert"},
        {"mode": True},
        {"max_candidates": 0},
        {"max_candidates": 21},
        {"max_candidates": True},
        {"region": (0, 0, 10, 10)},
        {"region": ImageRegion(left=-1, top=0, right=10, bottom=10)},
        {"region": ImageRegion(left=10, top=0, right=10, bottom=10)},
        {"region": ImageRegion(left=0, top=10, right=10, bottom=5)},
        {"region": ImageRegion(left=True, top=0, right=10, bottom=10)},
    ],
)
def test_inspect_with_ai_pure_input_validation_precedes_io(
    service: VisualProtocolService, kwargs: dict[str, Any]
) -> None:
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    call_kwargs: dict[str, Any] = {
        "prompt": "Find icon",
        "provider": provider,
        "mode": "extract",
        "region": None,
        "max_candidates": 5,
    }
    call_kwargs.update(kwargs)
    with connected(service) as connection:
        session = session_for(service, connection, "visual-invalid-input")
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            session.device.inspect_with_ai(**call_kwargs)
        assert_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        assert provider.requests == []
        session.quit()


@pytest.mark.parametrize("apng_chunk", [b"acTL", b"fcTL", b"fdAT"])
def test_inspect_with_ai_rejects_apng_multi_frame_chunks(
    service: VisualProtocolService, apng_chunk: bytes
) -> None:
    _, encoded = _encoded_png(100, 100, before_iend=(_chunk(apng_chunk, b"\x00" * 8),))
    service.queue("take_screenshot", ResponsePlan(payload={"value": encoded}))
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    with connected(service) as connection:
        session = session_for(service, connection, f"visual-apng-{apng_chunk.decode()}")
        with pytest.raises(CommandError) as caught:
            session.device.inspect_with_ai(
                "Inspect frame",
                provider=provider,
                mode="locate",
            )
        assert_error(
            caught.value,
            CommandError,
            "frame_not_single",
            "response_received",
            steps=(),
        )
        assert service.of_kind("display_size") == []
        assert provider.requests == []
        session.quit()


def test_inspect_with_ai_region_exceeding_image_size_fails_before_display_and_provider(
    service: VisualProtocolService,
) -> None:
    _, encoded = _encoded_png(200, 300)
    service.queue("take_screenshot", ResponsePlan(payload={"value": encoded}))
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    with connected(service) as connection:
        session = session_for(service, connection, "visual-region-out-of-image")
        with pytest.raises(InvalidRequestError) as caught:
            session.device.inspect_with_ai(
                "Locate inside region",
                provider=provider,
                mode="locate",
                region=ImageRegion(left=0, top=0, right=201, bottom=300),
            )
        assert_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "response_received",
            steps=("screenshot_captured",),
        )
        assert service.of_kind("display_size") == []
        assert provider.requests == []
        session.quit()


@pytest.mark.parametrize("display_str", ["2400x1080", "1080x2209", "1000x2000"])
def test_inspect_with_ai_locate_non_proportional_display_size_fails_closed(
    service: VisualProtocolService, display_str: str
) -> None:
    _, encoded = _encoded_png(1080, 2400)
    service.queue("take_screenshot", ResponsePlan(payload={"value": encoded}))
    service.queue(
        "display_size",
        ResponsePlan(payload={"value": {"realDisplaySize": display_str}}),
    )
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    with connected(service) as connection:
        session = session_for(service, connection, f"visual-mismatch-{display_str}")
        with pytest.raises(CommandError) as caught:
            session.device.inspect_with_ai(
                "Locate button",
                provider=provider,
                mode="locate",
            )
        assert_error(
            caught.value,
            CommandError,
            "pointer_mapping_unavailable",
            "response_received",
            steps=("screenshot_captured", "display_size_read"),
        )
        assert provider.requests == []
        session.quit()


@pytest.mark.parametrize(
    ("mode", "region", "response"),
    [
        ("extract", None, cast(Any, {"summary": "not a dataclass"})),
        ("extract", None, VisualProviderResponse(summary="bad\x00summary")),
        ("extract", None, VisualProviderResponse(summary="x" * 32_769)),
        (
            "extract",
            None,
            VisualProviderResponse(
                summary="extract must not return candidates",
                candidates=(
                    VisualImageMatch(
                        label="btn", image_bounds=Bounds(x=0, y=0, width=10, height=10)
                    ),
                ),
            ),
        ),
        (
            "locate",
            None,
            VisualProviderResponse(
                summary="too many",
                candidates=tuple(
                    VisualImageMatch(
                        label=f"c{i}",
                        image_bounds=Bounds(x=0, y=0, width=10, height=10),
                    )
                    for i in range(3)
                ),
            ),
        ),
        (
            "locate",
            None,
            VisualProviderResponse(
                summary="empty label",
                candidates=(
                    VisualImageMatch(
                        label="   ",
                        image_bounds=Bounds(x=0, y=0, width=10, height=10),
                    ),
                ),
            ),
        ),
        (
            "locate",
            None,
            VisualProviderResponse(
                summary="bad confidence",
                candidates=(
                    VisualImageMatch(
                        label="btn",
                        image_bounds=Bounds(x=0, y=0, width=10, height=10),
                        confidence=1.2,
                    ),
                ),
            ),
        ),
        (
            "locate",
            None,
            VisualProviderResponse(
                summary="bool confidence",
                candidates=(
                    VisualImageMatch(
                        label="btn",
                        image_bounds=Bounds(x=0, y=0, width=10, height=10),
                        confidence=True,
                    ),
                ),
            ),
        ),
        (
            "locate",
            None,
            VisualProviderResponse(
                summary="zero width",
                candidates=(
                    VisualImageMatch(
                        label="btn",
                        image_bounds=Bounds(x=10, y=10, width=0, height=10),
                    ),
                ),
            ),
        ),
        (
            "locate",
            None,
            VisualProviderResponse(
                summary="out of image",
                candidates=(
                    VisualImageMatch(
                        label="btn",
                        image_bounds=Bounds(x=1000, y=10, width=100, height=10),
                    ),
                ),
            ),
        ),
        (
            "locate",
            ImageRegion(left=50, top=50, right=200, bottom=200),
            VisualProviderResponse(
                summary="outside region",
                candidates=(
                    VisualImageMatch(
                        label="btn",
                        image_bounds=Bounds(x=40, y=60, width=50, height=50),
                    ),
                ),
            ),
        ),
    ],
)
def test_inspect_with_ai_rejects_invalid_provider_responses(
    service: VisualProtocolService,
    mode: Any,
    region: ImageRegion | None,
    response: VisualProviderResponse,
) -> None:
    provider = StubVisualProvider(response)
    with connected(service) as connection:
        session = session_for(service, connection, "visual-bad-response")
        with pytest.raises(CommandError) as caught:
            session.device.inspect_with_ai(
                "Inspect screen",
                provider=provider,
                mode=mode,
                region=region,
                max_candidates=2,
            )
        expected_steps = (
            ("screenshot_captured",)
            if mode == "extract"
            else ("screenshot_captured", "display_size_read")
        )
        assert_error(
            caught.value,
            CommandError,
            "invalid_visual_response",
            "response_received",
            steps=expected_steps,
        )
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("platform", ["android", "ios", "macos"])
@pytest.mark.parametrize("controlled", [False, True])
def test_inspect_with_ai_provider_exception_is_wrapped_and_keeps_session_active(
    service: VisualProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    controlled: bool,
) -> None:
    _, encoded = _encoded_png(1512, 982)
    service.queue("take_screenshot", ResponsePlan(payload={"value": encoded}))

    def boom(request: VisualProviderRequest) -> VisualProviderResponse:
        try:
            raise RuntimeError(request.png_bytes)
        except RuntimeError as cause:
            if controlled:
                raise CommandError(
                    "secret token",
                    "provider-operation",
                    "response_unknown",
                    cleanup_errors=(cause,),
                ) from cause
            raise RuntimeError("model gateway failed with secret token") from cause

    provider = StubVisualProvider(boom)
    with connected(service) as connection:
        session = _platform_session(service, connection, monkeypatch, platform)
        with pytest.raises(CommandError) as caught:
            session.device.inspect_with_ai(
                "Extract text",
                provider=provider,
                mode="extract",
            )
        assert_error(
            caught.value,
            CommandError,
            "visual_provider_failed",
            "response_received",
            steps=("screenshot_captured", "display_size_read")
            if platform == "macos"
            else ("screenshot_captured",),
        )
        assert "secret token" not in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None
        assert caught.value.cleanup_errors == ()
        assert caught.value.operation_id != "provider-operation"
        assert session.session_info().state == "active"
        session.quit()


def test_inspect_with_ai_cancellation_during_provider_call_reports_cancelled(
    service: VisualProtocolService,
) -> None:
    cancel = threading.Event()

    def cancel_inside(request: VisualProviderRequest) -> VisualProviderResponse:
        del request
        cancel.set()
        raise RuntimeError("interrupted by cancellation")

    provider = StubVisualProvider(cancel_inside)
    with connected(service) as connection:
        session = session_for(service, connection, "visual-provider-cancel")
        with pytest.raises(OperationCancelledError) as caught:
            session.device.inspect_with_ai(
                "Extract text",
                provider=provider,
                mode="extract",
                control=OperationControl(timeout_seconds=10.0, cancellation=cancel),
            )
        assert_error(
            caught.value,
            OperationCancelledError,
            "operation_cancelled",
            "response_received",
            steps=("screenshot_captured",),
        )
        assert session.session_info().state == "active"
        session.quit()


def test_inspect_with_ai_screenshot_disconnect_marks_session_uncertain(
    service: VisualProtocolService,
) -> None:
    service.queue("take_screenshot", ResponsePlan(disconnect=True))
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    with connected(service) as connection:
        session = session_for(service, connection, "visual-unknown")
        with pytest.raises(ExecutionUnknownError) as caught:
            session.device.inspect_with_ai(
                "Extract text",
                provider=provider,
                mode="extract",
            )
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
            steps=(),
        )
        assert session.session_info().state == "uncertain"
        assert provider.requests == []
        with pytest.raises(InvalidSessionStateError):
            session.device.inspect_with_ai("Retry", provider=provider)


def test_inspect_with_ai_display_size_disconnect_in_locate_marks_session_uncertain(
    service: VisualProtocolService,
) -> None:
    service.queue("display_size", ResponsePlan(disconnect=True))
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    with connected(service) as connection:
        session = session_for(service, connection, "visual-locate-display-unknown")
        with pytest.raises(ExecutionUnknownError) as caught:
            session.device.inspect_with_ai(
                "Locate target",
                provider=provider,
                mode="locate",
            )
        assert_error(
            caught.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
            steps=("screenshot_captured",),
        )
        assert session.session_info().state == "uncertain"
        assert provider.requests == []
        assert len(service.of_kind("display_size")) == 1
        with pytest.raises(InvalidSessionStateError):
            session.device.inspect_with_ai(
                "Retry locate", provider=provider, mode="locate"
            )


def test_inspect_with_ai_invokes_single_pass_png_parser_exactly_once(
    service: VisualProtocolService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import appium_connect_agent.automation._system_actions as system_actions
    import appium_connect_agent.automation._visual as visual_module

    original = system_actions._parse_png_container
    calls: list[tuple[bool, bool]] = []

    def tracked(
        data: bytes, *, reject_apng: bool = False, compute_sha256: bool = False
    ) -> tuple[DisplaySize, str | None]:
        calls.append((reject_apng, compute_sha256))
        return original(data, reject_apng=reject_apng, compute_sha256=compute_sha256)

    monkeypatch.setattr(system_actions, "_parse_png_container", tracked)
    monkeypatch.setattr(visual_module, "_parse_png_container", tracked)
    provider = StubVisualProvider(VisualProviderResponse(summary="single pass"))
    with connected(service) as connection:
        session = session_for(service, connection, "visual-single-pass")
        result = session.device.inspect_with_ai(
            "Check single pass", provider=provider, mode="extract"
        )
        assert result.summary == "single pass"
        assert calls == [(True, True)]
        session.quit()


def test_inspect_with_ai_shares_non_blocking_session_gate(
    service: VisualProtocolService,
) -> None:
    entered = threading.Event()
    release = threading.Event()

    def blocking_provider(request: VisualProviderRequest) -> VisualProviderResponse:
        del request
        entered.set()
        assert release.wait(timeout=5.0)
        return VisualProviderResponse(summary="done")

    provider = StubVisualProvider(blocking_provider)
    with connected(service) as connection:
        session = session_for(service, connection, "visual-busy-gate")
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                session.device.inspect_with_ai("First", provider=provider)
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=worker)
        thread.start()
        assert entered.wait(timeout=5.0)
        with pytest.raises(SessionBusyError) as busy:
            session.device.display_size()
        assert_error(busy.value, SessionBusyError, "session_busy", "not_sent", steps=())
        release.set()
        thread.join(timeout=5.0)
        assert not errors
        session.quit()


def test_inspect_with_ai_timeout_before_and_during_provider(
    service: VisualProtocolService,
) -> None:
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    with connected(service) as connection:
        session = session_for(service, connection, "visual-timeout")
        before = service.snapshot()
        with pytest.raises(OperationTimeoutError) as pre_timeout:
            session.device.inspect_with_ai(
                "Extract text",
                provider=provider,
                control=OperationControl(timeout_seconds=1e-12),
            )
        assert_error(
            pre_timeout.value,
            OperationTimeoutError,
            "operation_timeout",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before

        def slow_provider(request: VisualProviderRequest) -> VisualProviderResponse:
            assert request.remaining_timeout_seconds is not None
            import time as _time

            _time.sleep(0.08)
            return VisualProviderResponse(summary="late")

        slow = StubVisualProvider(slow_provider)
        with pytest.raises(OperationTimeoutError) as post_timeout:
            session.device.inspect_with_ai(
                "Extract text",
                provider=slow,
                control=OperationControl(timeout_seconds=0.05),
            )
        assert_error(
            post_timeout.value,
            OperationTimeoutError,
            "operation_timeout",
            "response_received",
            steps=("screenshot_captured",),
        )
        assert session.session_info().state == "active"
        session.quit()


def test_inspect_with_ai_complete_document_65536_and_65537_boundaries(
    service: VisualProtocolService,
) -> None:
    with connected(service) as connection:
        session = session_for(service, connection, "visual-json-boundary")
        candidates = tuple(
            VisualImageMatch(
                label="中" * 1_024,
                image_bounds=Bounds(x=i * 10, y=i * 10, width=50, height=50),
                confidence=0.5,
            )
            for i in range(20)
        )

        def run_with_summary(summary_text: str) -> VisualInspection:
            provider = StubVisualProvider(
                VisualProviderResponse(summary=summary_text, candidates=candidates)
            )
            return session.device.inspect_with_ai(
                "Locate items",
                provider=provider,
                mode="locate",
                max_candidates=20,
            )

        baseline = run_with_summary("")
        padding = 65_536 - len(baseline.to_json())
        assert 0 < padding <= 32_768
        exact = run_with_summary("s" * padding)
        assert len(exact.to_json()) == 65_536
        with pytest.raises(CommandError) as caught:
            run_with_summary("s" * (padding + 1))
        assert_error(
            caught.value,
            CommandError,
            "observation_too_large",
            "response_received",
            steps=("screenshot_captured", "display_size_read", "visual_inspected"),
        )
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize(
    ("platform", "kind", "size", "scale"),
    [
        ("android", "display_size", {"realDisplaySize": "2x2"}, 1),
        ("ios", "ios_display_size", {"screenSize": {"width": 2, "height": 2}}, 2),
        ("macos", "macos_display_size", _mac_displays(2, 2), 2),
    ],
)
def test_sample_color_matches_offline_exact_frame_and_pointer_footprint(
    service: VisualProtocolService,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    kind: str,
    size: object,
    scale: int,
) -> None:
    extent = 2 * scale
    color = bytes((0, 191, 243, 255))
    other = bytes((255, 255, 255, 255))
    scanlines = b"".join(
        b"\0" + (other * extent if y < scale else other * scale + color * scale)
        for y in range(extent)
    )
    frame = _png(zlib.compress(scanlines), width=extent, height=extent)
    service.queue(
        "take_screenshot",
        ResponsePlan(payload={"value": base64.b64encode(frame).decode("ascii")}),
    )
    service.queue(kind, ResponsePlan(payload={"value": size}))
    with connected(service) as connection:
        session = _platform_session(service, connection, monkeypatch, platform)
        result = session.device.sample_color(1, 1)
        assert result == sample_png_color(frame, 1, 1, pointer_size=DisplaySize(2, 2))
        assert result.hex == "#00BFF3"
        assert result.image_bounds == Bounds(scale, scale, scale, scale)
        assert result.uniform and result.opaque
        assert (
            len(service.of_kind("take_screenshot")) == len(service.of_kind(kind)) == 1
        )
        session.quit()


def test_sample_color_image_region_bypasses_pointer_read_and_rejects_bounds(
    service: VisualProtocolService,
) -> None:
    frame = _png(zlib.compress(b"\0\0\xbf\xf3\xff\0\0\0\xff"), width=2, height=1)
    encoded = base64.b64encode(frame).decode("ascii")
    response = ResponsePlan(payload={"value": encoded})
    service.queue("take_screenshot", response, response)
    with connected(service) as connection:
        session = create_mac2_session(connection)
        result = session.device.sample_color(
            region=Bounds(0, 0, 2, 1), coordinate_space="image"
        )
        assert not result.uniform and result.pointer_size is None
        assert result.min_rgb == (0, 0, 0) and result.max_rgb == (0, 191, 243)
        with pytest.raises(InvalidRequestError) as caught:
            session.device.sample_color(2, 0, coordinate_space="image")
        assert_error(
            caught.value,
            InvalidRequestError,
            "invalid_argument",
            "response_received",
            steps=("screenshot_captured",),
        )
        assert service.of_kind("macos_display_size") == []
        session.quit()


def test_sample_color_apng_before_mapping_and_transport_unknown(
    service: VisualProtocolService,
) -> None:
    _, encoded = _encoded_png(
        2, 2, before_iend=(_chunk(b"acTL", struct.pack(">II", 1, 0)),)
    )
    service.queue(
        "take_screenshot",
        ResponsePlan(payload={"value": encoded}),
        ResponsePlan(disconnect=True),
    )
    with connected(service) as connection:
        session = create_mac2_session(connection)
        with pytest.raises(CommandError) as apng:
            session.device.sample_color(0, 0)
        assert_error(
            apng.value, CommandError, "frame_not_single", "response_received", steps=()
        )
        with pytest.raises(ExecutionUnknownError) as unknown:
            session.device.sample_color(0, 0)
        assert_error(
            unknown.value,
            ExecutionUnknownError,
            "execution_unknown",
            "response_unknown",
            steps=(),
        )
        assert service.of_kind("macos_display_size") == []
        assert session.session_info().state == "uncertain"


def test_sample_color_macos_rejects_ambiguous_pointer_mapping(
    service: VisualProtocolService,
) -> None:
    frame = _png(zlib.compress(b"\0\0\xbf\xf3\xff"), width=1, height=1)
    service.queue(
        "take_screenshot",
        ResponsePlan(payload={"value": base64.b64encode(frame).decode("ascii")}),
    )
    service.queue(
        "macos_display_size",
        ResponsePlan(payload={"value": _mac_displays(1, 1, multi=True)}),
    )
    with connected(service) as connection:
        session = create_mac2_session(connection)
        with pytest.raises(CommandError) as caught:
            session.device.sample_color(0, 0)
        assert_error(
            caught.value,
            CommandError,
            "pointer_mapping_unavailable",
            "response_received",
            steps=("screenshot_captured",),
        )
        assert session.session_info().state == "active"
        session.quit()


@pytest.mark.parametrize("case", ["bad_crc", "out_of_bounds", "row_limit", "deflate"])
def test_sample_color_failures_do_not_retain_the_online_frame(
    service: VisualProtocolService,
    case: str,
) -> None:
    canary = b"phase2-private-screenshot-keynote-canary"
    idat = zlib.compress(b"\0\0\xbf\xf3\xff") if case != "deflate" else b"bad zlib"
    width = 100_000 if case == "row_limit" else 1
    frame = _png(
        idat,
        width=width,
        height=1,
        before_iend=(_chunk(b"tEXt", b"Comment\0" + canary),),
    )
    if case == "bad_crc":
        frame = frame[:29] + bytes((frame[29] ^ 1,)) + frame[30:]
    encoded = base64.b64encode(frame).decode("ascii")
    service.queue("take_screenshot", ResponsePlan(payload={"value": encoded}))

    def assert_safe(value: object) -> None:
        if isinstance(value, memoryview):
            assert_safe(value.obj)
        elif isinstance(value, (bytes, bytearray)):
            assert canary not in value
        elif isinstance(value, (list, tuple)):
            for item in value:
                assert_safe(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                assert_safe(key)
                assert_safe(item)
        elif is_dataclass(value) and not isinstance(value, type):
            for field in fields(value):
                assert_safe(getattr(value, field.name))
        elif isinstance(value, str):
            assert canary.decode("ascii") not in value and encoded not in value

    with connected(service) as connection:
        session = session_for(service, connection, "sample-privacy")
        error_type = InvalidRequestError if case == "out_of_bounds" else CommandError
        with pytest.raises(error_type) as caught:
            session.device.sample_color(
                1 if case == "out_of_bounds" else 0, 0, coordinate_space="image"
            )
        reason = "invalid_argument" if case == "out_of_bounds" else "command_failed"
        steps = ("screenshot_captured",) if case in ("out_of_bounds", "deflate") else ()
        assert_error(caught.value, error_type, reason, "response_received", steps=steps)
        assert caught.value.__cause__ is None and caught.value.__context__ is None
        assert caught.value.cleanup_errors == ()
        trace = caught.value.__traceback__
        assert_safe(vars(caught.value))
        while trace is not None:
            if "/src/appium_connect_agent/" in trace.tb_frame.f_code.co_filename:
                assert_safe(trace.tb_frame.f_locals)
            trace = trace.tb_next
        assert session.session_info().state == "active"
        session.quit()
