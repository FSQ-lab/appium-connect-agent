from __future__ import annotations

import base64
import hashlib
import json
import struct
import threading
import zlib
from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError
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
    VisualProvider,
    VisualProviderRequest,
    VisualProviderResponse,
    VisualTargetCandidate,
    create_mac2_session,
    create_xcuitest_session,
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


def test_visual_provider_protocol_runtime_checkable() -> None:
    provider = StubVisualProvider(VisualProviderResponse(summary="ok"))
    assert isinstance(provider, VisualProvider)


def test_inspect_with_ai_extract_mode_android_and_macos(
    service: VisualProtocolService,
) -> None:
    raw_png, encoded = _encoded_png(600, 800)
    expected_sha256 = hashlib.sha256(raw_png).hexdigest()
    service.queue(
        "take_screenshot",
        ResponsePlan(payload={"value": encoded}),
        ResponsePlan(payload={"value": encoded}),
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
        mac_session.quit()


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


def test_inspect_with_ai_macos_locate_rejected_before_io(
    service: VisualProtocolService,
) -> None:
    provider = StubVisualProvider(VisualProviderResponse(summary="unused"))
    with connected(service) as connection:
        mac_session = create_mac2_session(connection)
        before = service.snapshot()
        with pytest.raises(InvalidRequestError) as caught:
            mac_session.device.inspect_with_ai(
                "Locate button",
                provider=provider,
                mode="locate",
            )
        assert_error(
            caught.value,
            InvalidRequestError,
            "pointer_mapping_unavailable",
            "not_sent",
            steps=(),
        )
        assert service.snapshot() == before
        assert provider.requests == []
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


def test_inspect_with_ai_provider_exception_is_wrapped_and_keeps_session_active(
    service: VisualProtocolService,
) -> None:
    def boom(request: VisualProviderRequest) -> VisualProviderResponse:
        del request
        raise RuntimeError("model gateway failed with secret token")

    provider = StubVisualProvider(boom)
    with connected(service) as connection:
        session = session_for(service, connection, "visual-provider-boom")
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
            steps=("screenshot_captured",),
        )
        assert "secret token" not in str(caught.value)
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
