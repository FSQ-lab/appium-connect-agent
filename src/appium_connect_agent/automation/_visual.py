"""AIF-13 unified visual perception and grounding orchestration."""

from __future__ import annotations

import math
import time
from datetime import datetime
from typing import TYPE_CHECKING, cast

from appium.webdriver.webdriver import WebDriver
from selenium.webdriver.remote.command import Command

from ._models import (
    AutomationError,
    Bounds,
    CommandError,
    DisplaySize,
    ImageRegion,
    InvalidRequestError,
    OperationCancelledError,
    OperationTimeoutError,
    Point,
    VisualImageMatch,
    VisualInspection,
    VisualMode,
    VisualProvider,
    VisualProviderRequest,
    VisualProviderResponse,
    VisualTargetCandidate,
)
from ._observation import _canonical
from ._system_actions import (
    _decode_screenshot_base64,
    _parse_display_size,
    _parse_ios_display_size,
    _parse_png_container,
    _SingleFrameRequiredError,
)

if TYPE_CHECKING:
    from ._session import _SessionOperationGateway

_MAX_PROMPT_CHARS = 16_384
_MAX_SUMMARY_UTF8_BYTES = 32_768
_MAX_LABEL_CHARS = 1_024
_MAX_CANDIDATES_LIMIT = 20
_MAX_COORDINATE = 2_147_483_647


def _validate_visual_inputs(
    prompt: object,
    provider: object,
    mode: object,
    region: object,
    max_candidates: object,
    operation_id: str,
) -> tuple[str, VisualProvider, VisualMode, ImageRegion | None, int]:
    if type(prompt) is not str:
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
    try:
        prompt.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise InvalidRequestError(
            "invalid_argument", operation_id, "not_sent"
        ) from None
    if (
        not (1 <= len(prompt) <= _MAX_PROMPT_CHARS)
        or "\x00" in prompt
        or not prompt.strip()
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")

    if provider is None or not callable(getattr(provider, "inspect", None)):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")

    if type(mode) is not str or mode not in ("extract", "locate"):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")

    valid_region: ImageRegion | None = None
    if region is not None:
        if not isinstance(region, ImageRegion):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        parts = (region.left, region.top, region.right, region.bottom)
        if any(type(part) is not int for part in parts):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        if not (0 <= region.left < region.right <= _MAX_COORDINATE) or not (
            0 <= region.top < region.bottom <= _MAX_COORDINATE
        ):
            raise InvalidRequestError("invalid_argument", operation_id, "not_sent")
        valid_region = region

    if type(max_candidates) is not int or not (
        1 <= max_candidates <= _MAX_CANDIDATES_LIMIT
    ):
        raise InvalidRequestError("invalid_argument", operation_id, "not_sent")

    return (
        prompt,
        cast(VisualProvider, provider),
        cast(VisualMode, mode),
        valid_region,
        max_candidates,
    )


def _is_proportional_axis_aligned(
    image_size: DisplaySize, pointer_size: DisplaySize
) -> bool:
    iw, ih = image_size.width, image_size.height
    pw, ph = pointer_size.width, pointer_size.height
    if pw >= iw and ph >= ih:
        return (
            pw % iw == 0
            and ph % ih == 0
            and (pw // iw) == (ph // ih)
            and (pw // iw) >= 1
        )
    if iw >= pw and ih >= ph:
        return (
            iw % pw == 0
            and ih % ph == 0
            and (iw // pw) == (ih // ph)
            and (iw // pw) >= 1
        )
    return False


def _map_bounds_to_pointer(
    image_bounds: Bounds,
    image_size: DisplaySize,
    pointer_size: DisplaySize,
) -> tuple[Bounds, Point]:
    iw, ih = image_size.width, image_size.height
    pw, ph = pointer_size.width, pointer_size.height
    px0 = (image_bounds.x * pw) // iw
    py0 = (image_bounds.y * ph) // ih
    px1 = max(px0 + 1, ((image_bounds.x + image_bounds.width) * pw) // iw)
    py1 = max(py0 + 1, ((image_bounds.y + image_bounds.height) * ph) // ih)
    if not (0 <= px0 < px1 <= pw) or not (0 <= py0 < py1 <= ph):
        raise ValueError("mapped pointer bounds out of range")
    p_width = px1 - px0
    p_height = py1 - py0
    center_x = px0 + p_width // 2
    center_y = py0 + p_height // 2
    if not (0 <= center_x < pw) or not (0 <= center_y < ph):
        raise ValueError("mapped pointer center out of range")
    return Bounds(x=px0, y=py0, width=p_width, height=p_height), Point(
        x=center_x, y=center_y
    )


def _validate_provider_response(
    response: object,
    *,
    mode: VisualMode,
    image_size: DisplaySize,
    pointer_size: DisplaySize | None,
    region: ImageRegion | None,
    max_candidates: int,
) -> tuple[str, tuple[VisualTargetCandidate, ...]]:
    if not isinstance(response, VisualProviderResponse):
        raise ValueError("response must be VisualProviderResponse")
    summary = response.summary
    if type(summary) is not str or "\x00" in summary:
        raise ValueError("summary must be a non-NUL string")
    try:
        summary_bytes = summary.encode("utf-8", errors="strict")
    except UnicodeEncodeError as cause:
        raise ValueError("summary is not valid UTF-8") from cause
    if len(summary_bytes) > _MAX_SUMMARY_UTF8_BYTES:
        raise ValueError("summary exceeds byte limit")

    candidates = response.candidates
    if type(candidates) is not tuple or len(candidates) > max_candidates:
        raise ValueError("candidates must be a tuple within max_candidates")
    if mode == "extract":
        if candidates != ():
            raise ValueError("extract mode requires empty candidates tuple")
        return summary, ()

    if pointer_size is None:
        raise ValueError("locate mode requires pointer_size")

    resolved: list[VisualTargetCandidate] = []
    for item in candidates:
        if not isinstance(item, VisualImageMatch):
            raise ValueError("candidate must be VisualImageMatch")
        label = item.label
        if (
            type(label) is not str
            or not (1 <= len(label) <= _MAX_LABEL_CHARS)
            or "\x00" in label
            or not label.strip()
        ):
            raise ValueError("invalid candidate label")
        try:
            label.encode("utf-8", errors="strict")
        except UnicodeEncodeError as cause:
            raise ValueError("candidate label is not valid UTF-8") from cause

        confidence = item.confidence
        normalized_confidence: float | None = None
        if confidence is not None:
            if type(confidence) not in (int, float):
                raise ValueError("confidence must be float, int, or None")
            numeric = float(confidence)
            if not math.isfinite(numeric) or not (0.0 <= numeric <= 1.0):
                raise ValueError("confidence must be within [0.0, 1.0]")
            normalized_confidence = numeric

        bounds = item.image_bounds
        if not isinstance(bounds, Bounds):
            raise ValueError("image_bounds must be Bounds")
        b_parts = (bounds.x, bounds.y, bounds.width, bounds.height)
        if any(type(part) is not int for part in b_parts):
            raise ValueError("image_bounds fields must be int")
        if bounds.width < 1 or bounds.height < 1:
            raise ValueError("image_bounds dimensions must be positive")
        if (
            bounds.x < 0
            or bounds.y < 0
            or bounds.x + bounds.width > image_size.width
            or bounds.y + bounds.height > image_size.height
        ):
            raise ValueError("image_bounds exceeds image dimensions")
        if region is not None and (
            bounds.x < region.left
            or bounds.y < region.top
            or bounds.x + bounds.width > region.right
            or bounds.y + bounds.height > region.bottom
        ):
            raise ValueError("image_bounds falls outside requested region")

        pointer_bounds, pointer_center = _map_bounds_to_pointer(
            bounds, image_size, pointer_size
        )
        resolved.append(
            VisualTargetCandidate(
                label=label,
                image_bounds=bounds,
                pointer_bounds=pointer_bounds,
                pointer_center=pointer_center,
                confidence=normalized_confidence,
            )
        )

    return summary, tuple(resolved)


def _visual_document(
    *,
    operation_id: str,
    observed_at: datetime,
    platform: str,
    mode: VisualMode,
    image_size: DisplaySize,
    pointer_size: DisplaySize | None,
    png_sha256: str,
    region: ImageRegion | None,
    summary: str,
    candidates: tuple[VisualTargetCandidate, ...],
) -> dict[str, object]:
    return {
        "complete_for_requested_scope": True,
        "coverage": "requested_scope",
        "kind": "visual",
        "observed_at": observed_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "operation_id": operation_id,
        "payload": {
            "candidates": [
                {
                    "confidence": candidate.confidence,
                    "image_bounds": [
                        candidate.image_bounds.x,
                        candidate.image_bounds.y,
                        candidate.image_bounds.width,
                        candidate.image_bounds.height,
                    ],
                    "label": candidate.label,
                    "pointer_bounds": [
                        candidate.pointer_bounds.x,
                        candidate.pointer_bounds.y,
                        candidate.pointer_bounds.width,
                        candidate.pointer_bounds.height,
                    ],
                    "pointer_center": [
                        candidate.pointer_center.x,
                        candidate.pointer_center.y,
                    ],
                }
                for candidate in candidates
            ],
            "image_size": [image_size.width, image_size.height],
            "mode": mode,
            "platform": platform,
            "png_sha256": png_sha256,
            "pointer_size": (
                None
                if pointer_size is None
                else [pointer_size.width, pointer_size.height]
            ),
            "region": (
                None
                if region is None
                else [region.left, region.top, region.right, region.bottom]
            ),
            "summary": summary,
        },
        "schema": 1,
        "upstream_completeness": "unknown",
    }


def _inspect_with_ai(
    driver: WebDriver,
    gateway: _SessionOperationGateway,
    *,
    prompt: str,
    provider: VisualProvider,
    mode: VisualMode,
    region: ImageRegion | None,
    max_candidates: int,
    ios: bool = False,
) -> VisualInspection:
    def capture() -> bytes:
        response: object = driver.execute(Command.SCREENSHOT)
        return _decode_screenshot_base64(response)

    png_bytes = gateway.final_action(capture)
    try:
        image_size, maybe_sha256 = _parse_png_container(
            png_bytes, reject_apng=True, compute_sha256=True
        )
        assert maybe_sha256 is not None
        png_sha256 = maybe_sha256
    except _SingleFrameRequiredError as cause:
        raise gateway.failure(
            CommandError, "frame_not_single", "response_received"
        ) from cause
    except ValueError as cause:
        raise gateway.failure(
            CommandError, "command_failed", "response_received"
        ) from cause
    gateway.complete("screenshot_captured")
    gateway.checkpoint(response_received=True)

    if region is not None and (
        region.right > image_size.width or region.bottom > image_size.height
    ):
        raise gateway.failure(
            InvalidRequestError, "invalid_argument", "response_received"
        )

    pointer_size: DisplaySize | None = None
    if mode == "locate":
        pointer_size = gateway.final_action(
            lambda: (
                _parse_ios_display_size(
                    driver.execute_script("mobile: deviceScreenInfo")
                )
                if ios
                else _parse_display_size(driver.execute_script("mobile: deviceInfo"))
            )
        )
        gateway.complete("display_size_read")
        gateway.checkpoint(response_received=True)
        if not _is_proportional_axis_aligned(image_size, pointer_size):
            raise gateway.failure(
                CommandError, "pointer_mapping_unavailable", "response_received"
            )

    gateway.checkpoint(response_received=True)
    remaining: float | None = None
    if gateway.operation_deadline is not None:
        remaining = gateway.operation_deadline - time.monotonic()
        if remaining <= 0:
            gateway.checkpoint(response_received=True)
            raise gateway.failure(
                OperationTimeoutError, "operation_timeout", "response_received"
            )

    provider_request = VisualProviderRequest(
        mode=mode,
        prompt=prompt,
        png_bytes=png_bytes,
        image_width=image_size.width,
        image_height=image_size.height,
        region=region,
        max_candidates=max_candidates,
        remaining_timeout_seconds=remaining,
    )
    try:
        raw_response = provider.inspect(provider_request)
    except (OperationCancelledError, OperationTimeoutError):
        gateway.checkpoint(response_received=True)
        raise
    except AutomationError:
        raise
    except Exception as cause:
        gateway.checkpoint(response_received=True)
        raise gateway.failure(
            CommandError, "visual_provider_failed", "response_received"
        ) from cause

    gateway.checkpoint(response_received=True)
    try:
        summary, candidates = _validate_provider_response(
            raw_response,
            mode=mode,
            image_size=image_size,
            pointer_size=pointer_size,
            region=region,
            max_candidates=max_candidates,
        )
    except ValueError as cause:
        raise gateway.failure(
            CommandError, "invalid_visual_response", "response_received"
        ) from cause

    gateway.complete("visual_inspected")
    observed_at = gateway.observed_at
    if observed_at is None:
        raise RuntimeError("visual inspection has no successful Appium response")
    document = _visual_document(
        operation_id=gateway.operation_id,
        observed_at=observed_at,
        platform=gateway.platform,
        mode=mode,
        image_size=image_size,
        pointer_size=pointer_size,
        png_sha256=png_sha256,
        region=region,
        summary=summary,
        candidates=candidates,
    )
    try:
        encoded = _canonical(document, gateway)
    except (UnicodeEncodeError, ValueError) as cause:
        raise gateway.failure(
            CommandError, "invalid_visual_response", "response_received"
        ) from cause
    if encoded is None:
        raise gateway.failure(
            CommandError, "observation_too_large", "response_received"
        )
    gateway.checkpoint(response_received=True)
    gateway.complete("observation_built")
    return VisualInspection(
        operation_id=gateway.operation_id,
        observed_at=observed_at,
        platform=gateway.platform,
        mode=mode,
        image_size=image_size,
        pointer_size=pointer_size,
        png_sha256=png_sha256,
        region=region,
        summary=summary,
        candidates=candidates,
        _json=encoded,
    )
