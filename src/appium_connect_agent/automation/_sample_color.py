"""Deterministic, bounded color sampling for non-interlaced PNG frames."""

from __future__ import annotations

import hashlib
import struct
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Never, cast
from uuid import uuid4

from appium_connect_agent.runtime import OperationControl

from ._models import (
    AutomationError,
    Bounds,
    ColorCoordinateSpace,
    ColorSample,
    ColorSpace,
    CommandError,
    DisplaySize,
    ImageRegion,
    InvalidRequestError,
    OperationCancelledError,
    OperationTimeoutError,
    RequestState,
)
from ._visual import _is_proportional_axis_aligned

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_PNG_BYTES = 33_554_432
_MAX_CHUNKS = 65_536
_MAX_PIXELS = 33_554_432
_MAX_ROW_BYTES = 262_144
_MAX_SCANLINE_BYTES = 134_217_728
_MAX_SAMPLE_PIXELS = 1_048_576
_MAX_COORDINATE = 2_147_483_647
_APNG_CHUNKS = frozenset({b"acTL", b"fcTL", b"fdAT"})
_KNOWN_CRITICAL = frozenset({b"IHDR", b"PLTE", b"IDAT", b"IEND"})


class _MalformedPng(ValueError):
    pass


class _UnsupportedPng(ValueError):
    pass


class _AnimatedPng(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _SampleFrame:
    image_size: DisplaySize
    bit_depth: int
    color_type: int
    row_bytes: int
    scanline_bytes: int
    idat_parts: tuple[memoryview, ...]
    palette: tuple[tuple[int, int, int], ...] | None
    transparency: bytes | None
    color_space: ColorSpace
    icc_profile_name: str | None
    png_sha256: str


def _controlled(
    error_type: type[CommandError],
    code: str,
    operation_id: str,
    request_state: RequestState,
    cause: BaseException,
) -> Never:
    error = error_type(code, operation_id, request_state)
    raise error from cause


def _sample_failure(error: AutomationError) -> AutomationError:
    # A parser/gateway traceback can hold the full screenshot in frame locals.
    # Copy only the stable error facts; raise it after leaving the handler.
    return type(error)(
        error.code,
        error.operation_id,
        error.request_state,
        session=error.session,
        completed_steps=error.completed_steps,
        cleanup_errors=tuple(
            RuntimeError("transport_cleanup_failed") for _ in error.cleanup_errors
        ),
    )


def _invalid(operation_id: str) -> Never:
    raise InvalidRequestError("invalid_argument", operation_id, "not_sent")


def _validate_sample_inputs(
    x: object,
    y: object,
    region: object,
    coordinate_space: object,
    operation_id: str,
) -> tuple[Bounds, ColorCoordinateSpace]:
    """Validate point-or-region selection without consulting a PNG frame."""
    if type(coordinate_space) is not str or coordinate_space not in (
        "pointer",
        "image",
    ):
        _invalid(operation_id)
    valid_space = cast(ColorCoordinateSpace, coordinate_space)

    has_point = x is not None or y is not None
    if has_point == (region is not None):
        _invalid(operation_id)
    if has_point:
        if type(x) is not int or type(y) is not int:
            _invalid(operation_id)
        if not (0 <= x <= _MAX_COORDINATE) or not (0 <= y <= _MAX_COORDINATE):
            _invalid(operation_id)
        return Bounds(x, y, 1, 1), valid_space

    if isinstance(region, Bounds):
        parts = (region.x, region.y, region.width, region.height)
        if any(type(part) is not int for part in parts):
            _invalid(operation_id)
        if not (
            0 <= region.x <= _MAX_COORDINATE
            and 0 <= region.y <= _MAX_COORDINATE
            and 1 <= region.width <= _MAX_COORDINATE
            and 1 <= region.height <= _MAX_COORDINATE
            and region.x + region.width <= _MAX_COORDINATE + 1
            and region.y + region.height <= _MAX_COORDINATE + 1
        ):
            _invalid(operation_id)
        return region, valid_space
    if isinstance(region, ImageRegion):
        parts = (region.left, region.top, region.right, region.bottom)
        if any(type(part) is not int for part in parts):
            _invalid(operation_id)
        if not (
            0 <= region.left < region.right <= _MAX_COORDINATE + 1
            and 0 <= region.top < region.bottom <= _MAX_COORDINATE + 1
        ):
            _invalid(operation_id)
        return (
            Bounds(
                region.left,
                region.top,
                region.right - region.left,
                region.bottom - region.top,
            ),
            valid_space,
        )
    _invalid(operation_id)


def _chunk_type_valid(chunk_type: bytes) -> bool:
    return (
        len(chunk_type) == 4
        and 65 <= chunk_type[2] <= 90
        and all(65 <= value <= 90 or 97 <= value <= 122 for value in chunk_type)
    )


def _keyword(data: bytes) -> str:
    if not 1 <= len(data) <= 79:
        raise _MalformedPng("invalid PNG keyword length")
    if data[0] == 32 or data[-1] == 32 or b"  " in data:
        raise _MalformedPng("invalid PNG keyword spacing")
    if any(not (32 <= value <= 126 or 161 <= value <= 255) for value in data):
        raise _MalformedPng("invalid PNG keyword character")
    return data.decode("latin-1")


def _format_row_bytes(width: int, bit_depth: int, color_type: int) -> tuple[int, int]:
    legal_depths = {
        0: (1, 2, 4, 8, 16),
        2: (8, 16),
        3: (1, 2, 4, 8),
        4: (8, 16),
        6: (8, 16),
    }
    if color_type not in legal_depths or bit_depth not in legal_depths[color_type]:
        raise _UnsupportedPng("unsupported PNG color type or bit depth")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    row_bytes = (width * channels * bit_depth + 7) // 8
    return row_bytes, channels


def _parse_sample_frame(
    png_bytes: bytes,
    operation_id: str,
    request_state: RequestState,
    checkpoint: Callable[[], None],
) -> _SampleFrame:
    """Validate one PNG frame and retain only bounded decoding metadata."""
    try:
        if type(png_bytes) is not bytes:
            raise _MalformedPng("PNG value must be bytes")
        total = len(png_bytes)
        if not (58 <= total <= _MAX_PNG_BYTES) or not png_bytes.startswith(
            _PNG_SIGNATURE
        ):
            raise _MalformedPng("invalid PNG header or container size")

        view = memoryview(png_bytes)
        offset = len(_PNG_SIGNATURE)
        chunk_count = 0
        width = height = bit_depth = color_type = 0
        row_bytes = channels = 0
        saw_ihdr = saw_idat = saw_iend = False
        idat_ended = False
        idat_bytes = 0
        palette: tuple[tuple[int, int, int], ...] | None = None
        transparency: bytes | None = None
        idat_parts: list[memoryview] = []
        saw_srgb = saw_iccp = saw_cicp = False
        saw_gama = saw_chrm = False
        icc_profile_name: str | None = None

        while offset < total:
            checkpoint()
            chunk_count += 1
            if chunk_count > _MAX_CHUNKS or offset + 12 > total:
                raise _MalformedPng("PNG chunk bound or framing exceeded")
            chunk_len = struct.unpack_from(">I", png_bytes, offset)[0]
            chunk_type = png_bytes[offset + 4 : offset + 8]
            if not _chunk_type_valid(chunk_type):
                raise _MalformedPng("invalid PNG chunk type")
            data_start = offset + 8
            data_end = data_start + chunk_len
            chunk_end = data_end + 4
            if chunk_end > total:
                raise _MalformedPng("truncated PNG chunk")
            expected_crc = struct.unpack_from(">I", png_bytes, data_end)[0]
            if zlib.crc32(view[offset + 4 : data_end]) & 0xFFFFFFFF != expected_crc:
                raise _MalformedPng("PNG chunk CRC mismatch")
            data = b"" if chunk_type == b"IDAT" else png_bytes[data_start:data_end]

            if chunk_type in _APNG_CHUNKS:
                raise _AnimatedPng("APNG is not a single frame")
            if not (chunk_type[0] & 0x20) and chunk_type not in _KNOWN_CRITICAL:
                raise _UnsupportedPng("unknown critical PNG chunk")
            if chunk_count == 1:
                if chunk_type != b"IHDR" or chunk_len != 13:
                    raise _MalformedPng("PNG must begin with IHDR")
                (
                    width,
                    height,
                    bit_depth,
                    color_type,
                    compression,
                    filter_method,
                    interlace,
                ) = struct.unpack(">IIBBBBB", data)
                if not (1 <= width <= _MAX_COORDINATE) or not (
                    1 <= height <= _MAX_COORDINATE
                ):
                    raise _MalformedPng("invalid PNG dimensions")
                if compression != 0 or filter_method != 0 or interlace != 0:
                    raise _UnsupportedPng("unsupported PNG encoding")
                row_bytes, channels = _format_row_bytes(width, bit_depth, color_type)
                scanline_bytes = (row_bytes + 1) * height
                if (
                    width * height > _MAX_PIXELS
                    or row_bytes > _MAX_ROW_BYTES
                    or scanline_bytes > _MAX_SCANLINE_BYTES
                ):
                    raise _MalformedPng("PNG decoded resource limit exceeded")
                saw_ihdr = True
            elif chunk_type == b"IHDR":
                raise _MalformedPng("duplicate PNG IHDR")
            elif chunk_type == b"PLTE":
                if saw_idat or palette is not None or color_type in (0, 4):
                    raise _MalformedPng("invalid PNG palette placement")
                if not (3 <= chunk_len <= 768) or chunk_len % 3:
                    raise _MalformedPng("invalid PNG palette")
                entries = tuple(
                    (data[index], data[index + 1], data[index + 2])
                    for index in range(0, chunk_len, 3)
                )
                if color_type == 3 and len(entries) > 1 << bit_depth:
                    raise _MalformedPng("palette exceeds indexed bit depth")
                palette = entries
            elif chunk_type == b"tRNS":
                if saw_idat or transparency is not None:
                    raise _MalformedPng("invalid PNG transparency placement")
                if color_type == 0:
                    if chunk_len != 2 or struct.unpack(">H", data)[0] >= 1 << bit_depth:
                        raise _MalformedPng("invalid grayscale transparency")
                elif color_type == 2:
                    if chunk_len != 6 or any(
                        value >= 1 << bit_depth for value in struct.unpack(">HHH", data)
                    ):
                        raise _MalformedPng("invalid RGB transparency")
                elif color_type == 3:
                    if palette is None or not 1 <= chunk_len <= len(palette):
                        raise _MalformedPng("invalid palette transparency")
                else:
                    raise _MalformedPng("alpha PNG cannot contain tRNS")
                transparency = data
            elif chunk_type == b"sRGB":
                if (
                    saw_idat
                    or palette is not None
                    or saw_srgb
                    or chunk_len != 1
                    or data[0] > 3
                ):
                    raise _MalformedPng("invalid sRGB chunk")
                if saw_iccp:
                    raise _MalformedPng("sRGB and iCCP cannot coexist")
                saw_srgb = True
            elif chunk_type == b"iCCP":
                if saw_idat or palette is not None or saw_iccp:
                    raise _MalformedPng("invalid iCCP placement")
                separator = data.find(b"\0")
                if separator < 0 or separator + 2 >= len(data):
                    raise _MalformedPng("invalid iCCP chunk")
                profile_name = _keyword(data[:separator])
                if data[separator + 1] != 0:
                    raise _MalformedPng("unsupported ICC compression method")
                if saw_srgb:
                    raise _MalformedPng("sRGB and iCCP cannot coexist")
                saw_iccp = True
                icc_profile_name = profile_name
            elif chunk_type == b"cICP":
                if (
                    saw_idat
                    or palette is not None
                    or saw_cicp
                    or chunk_len != 4
                    or data[3] not in (0, 1)
                ):
                    raise _MalformedPng("invalid cICP chunk")
                saw_cicp = True
            elif chunk_type == b"gAMA":
                if (
                    saw_idat
                    or palette is not None
                    or saw_gama
                    or chunk_len != 4
                    or struct.unpack(">I", data)[0] == 0
                ):
                    raise _MalformedPng("invalid gAMA chunk")
                saw_gama = True
            elif chunk_type == b"cHRM":
                if saw_idat or palette is not None or saw_chrm or chunk_len != 32:
                    raise _MalformedPng("invalid cHRM chunk")
                saw_chrm = True
            elif chunk_type == b"IDAT":
                if idat_ended:
                    raise _MalformedPng("non-consecutive IDAT")
                if color_type == 3 and palette is None:
                    raise _MalformedPng("indexed PNG requires PLTE")
                saw_idat = True
                idat_bytes += chunk_len
                idat_parts.append(view[data_start:data_end])
            elif chunk_type == b"IEND":
                if (
                    chunk_len != 0
                    or not saw_idat
                    or idat_bytes < 1
                    or chunk_end != total
                ):
                    raise _MalformedPng("invalid PNG IEND")
                saw_iend = True
                offset = chunk_end
                break
            elif saw_idat:
                idat_ended = True

            offset = chunk_end

        if not saw_ihdr or not saw_iend or offset != total:
            raise _MalformedPng("incomplete PNG container")
        # Keep this assertion local to proven IHDR state; it is not input trust.
        assert row_bytes > 0 and channels > 0
        color_space: ColorSpace = (
            "cicp"
            if saw_cicp
            else "embedded_icc"
            if saw_iccp
            else "srgb"
            if saw_srgb
            else "untagged"
        )
        return _SampleFrame(
            image_size=DisplaySize(width, height),
            bit_depth=bit_depth,
            color_type=color_type,
            row_bytes=row_bytes,
            scanline_bytes=(row_bytes + 1) * height,
            idat_parts=tuple(idat_parts),
            palette=palette,
            transparency=transparency,
            color_space=color_space,
            icc_profile_name=icc_profile_name,
            png_sha256=hashlib.sha256(png_bytes).hexdigest(),
        )
    except _AnimatedPng as cause:
        _controlled(
            CommandError, "frame_not_single", operation_id, request_state, cause
        )
    except _UnsupportedPng as cause:
        _controlled(
            CommandError, "unsupported_png_format", operation_id, request_state, cause
        )
    except _MalformedPng as cause:
        _controlled(CommandError, "command_failed", operation_id, request_state, cause)


def _ceil_ratio(value: int, numerator: int, denominator: int) -> int:
    return (value * numerator + denominator - 1) // denominator


def _map_bounds(bounds: Bounds, source: DisplaySize, target: DisplaySize) -> Bounds:
    left = bounds.x * target.width // source.width
    top = bounds.y * target.height // source.height
    right = _ceil_ratio(bounds.x + bounds.width, target.width, source.width)
    bottom = _ceil_ratio(bounds.y + bounds.height, target.height, source.height)
    return Bounds(left, top, right - left, bottom - top)


def _point(bounds: Bounds) -> tuple[int, int]:
    return bounds.x + bounds.width // 2, bounds.y + bounds.height // 2


def _valid_size(value: object) -> bool:
    return (
        isinstance(value, DisplaySize)
        and type(value.width) is int
        and type(value.height) is int
        and 1 <= value.width <= _MAX_COORDINATE
        and 1 <= value.height <= _MAX_COORDINATE
    )


def _row_filter(
    row: bytearray, previous: bytearray, filter_type: int, bpp: int
) -> None:
    if filter_type == 0:
        return
    if filter_type not in (1, 2, 3, 4):
        raise _MalformedPng("invalid PNG row filter")
    for index, value in enumerate(row):
        left = row[index - bpp] if index >= bpp else 0
        above = previous[index]
        upper_left = previous[index - bpp] if index >= bpp else 0
        if filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = above
        elif filter_type == 3:
            predictor = (left + above) // 2
        else:
            estimate = left + above - upper_left
            left_distance = abs(estimate - left)
            above_distance = abs(estimate - above)
            upper_left_distance = abs(estimate - upper_left)
            predictor = (
                left
                if left_distance <= above_distance
                and left_distance <= upper_left_distance
                else above
                if above_distance <= upper_left_distance
                else upper_left
            )
        row[index] = (value + predictor) & 0xFF


def _packed_sample(row: bytearray, x: int, bit_depth: int) -> int:
    bit_offset = x * bit_depth
    shift = 8 - bit_depth - bit_offset % 8
    return (row[bit_offset // 8] >> shift) & ((1 << bit_depth) - 1)


def _pixel(
    frame: _SampleFrame, row: bytearray, x: int
) -> tuple[tuple[int, int, int], int, int]:
    depth = frame.bit_depth
    kind = frame.color_type
    maximum = (1 << depth) - 1
    samples: tuple[int, ...]
    if kind in (0, 3) and depth < 8:
        samples = (_packed_sample(row, x, depth),)
    else:
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[kind]
        sample_bytes = 2 if depth == 16 else 1
        start = x * channels * sample_bytes
        if sample_bytes == 1:
            samples = tuple(row[start + index] for index in range(channels))
        else:
            samples = tuple(
                (row[start + index] << 8) | row[start + index + 1]
                for index in range(0, channels * 2, 2)
            )

    if kind == 3:
        assert frame.palette is not None
        index = samples[0]
        if index >= len(frame.palette):
            raise _MalformedPng("palette index out of range")
        rgb = frame.palette[index]
        alpha = (
            frame.transparency[index]
            if frame.transparency is not None and index < len(frame.transparency)
            else 255
        )
        return rgb, alpha, 255
    if kind == 0:
        gray = samples[0]
        alpha = maximum
        if frame.transparency is not None:
            transparent = struct.unpack(">H", frame.transparency)[0]
            if transparent > maximum:
                raise _MalformedPng("grayscale tRNS sample out of range")
            if gray == transparent:
                alpha = 0
        return (gray, gray, gray), alpha, maximum
    if kind == 2:
        rgb = cast(tuple[int, int, int], samples)
        alpha = maximum
        if frame.transparency is not None:
            transparent_rgb = struct.unpack(">HHH", frame.transparency)
            if any(value > maximum for value in transparent_rgb):
                raise _MalformedPng("RGB tRNS sample out of range")
            if rgb == transparent_rgb:
                alpha = 0
        return rgb, alpha, maximum
    if kind == 4:
        return (samples[0], samples[0], samples[0]), samples[1], maximum
    return cast(tuple[int, int, int], samples[:3]), samples[3], maximum


def _quantize(value: int, maximum: int) -> int:
    return (value * 255 + maximum // 2) // maximum


def _sample_frame(
    frame: _SampleFrame,
    bounds: Bounds,
    coordinate_space: ColorCoordinateSpace,
    pointer_size: DisplaySize | None,
    operation_id: str,
    request_state: RequestState,
    checkpoint: Callable[[], None],
) -> ColorSample:
    """Map a validated selection and sample its pixels from one parsed frame."""
    image_size = frame.image_size
    try:
        if pointer_size is not None and not _valid_size(pointer_size):
            raise _UnsupportedPng("invalid pointer size")
        if coordinate_space == "pointer":
            if pointer_size is None or not _valid_size(pointer_size):
                raise _UnsupportedPng("pointer size is required")
            if not _is_proportional_axis_aligned(image_size, pointer_size):
                raise _UnsupportedPng("pointer mapping is not proportional")
            if (
                bounds.x + bounds.width > pointer_size.width
                or bounds.y + bounds.height > pointer_size.height
            ):
                raise InvalidRequestError(
                    "invalid_argument", operation_id, request_state
                )
            pointer_bounds = bounds
            image_bounds = _map_bounds(bounds, pointer_size, image_size)
        else:
            if (
                bounds.x + bounds.width > image_size.width
                or bounds.y + bounds.height > image_size.height
            ):
                raise InvalidRequestError(
                    "invalid_argument", operation_id, request_state
                )
            image_bounds = bounds
            pointer_bounds = None
            if pointer_size is not None:
                if not _is_proportional_axis_aligned(image_size, pointer_size):
                    raise _UnsupportedPng("pointer mapping is not proportional")
                pointer_bounds = _map_bounds(bounds, image_size, pointer_size)
        if image_bounds.width * image_bounds.height > _MAX_SAMPLE_PIXELS:
            cause = _MalformedPng("PNG sample region resource limit exceeded")
            _controlled(
                CommandError, "command_failed", operation_id, request_state, cause
            )
    except _UnsupportedPng as cause:
        _controlled(
            CommandError,
            "pointer_mapping_unavailable",
            operation_id,
            request_state,
            cause,
        )

    image_point = _point(image_bounds)
    sample_x, sample_y = image_point
    pointer_point = _point(pointer_bounds) if pointer_bounds is not None else None
    previous = bytearray(frame.row_bytes)
    pending = bytearray()
    decompressor = zlib.decompressobj()
    produced = 0
    row_index = 0
    sample_rgb: tuple[int, int, int] | None = None
    first_raw: tuple[tuple[int, int, int], int, int] | None = None
    uniform = True
    opaque = True
    min_alpha = 255
    min_rgb = [255, 255, 255]
    max_rgb = [0, 0, 0]
    bpp = max(
        1,
        ({0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[frame.color_type] * frame.bit_depth + 7) // 8,
    )
    block_size = 65_536

    def consume(output: bytes) -> None:
        nonlocal produced, row_index, previous, sample_rgb, first_raw, uniform
        nonlocal opaque, min_alpha
        produced += len(output)
        if produced > frame.scanline_bytes:
            raise _MalformedPng("PNG expands beyond declared dimensions")
        pending.extend(output)
        stride = frame.row_bytes + 1
        offset = 0
        end = len(pending) - stride
        while offset <= end:
            checkpoint()
            filter_type = pending[offset]
            row = bytearray(memoryview(pending)[offset + 1 : offset + stride])
            offset += stride
            _row_filter(row, previous, filter_type, bpp)
            if image_bounds.y <= row_index < image_bounds.y + image_bounds.height:
                for x_value in range(
                    image_bounds.x, image_bounds.x + image_bounds.width
                ):
                    if (x_value & 4095) == 0:
                        checkpoint()
                    rgb_raw, alpha_raw, maximum = _pixel(frame, row, x_value)
                    identity = (rgb_raw, alpha_raw, maximum)
                    if first_raw is None:
                        first_raw = identity
                    elif identity != first_raw:
                        uniform = False
                    rgb8 = cast(
                        tuple[int, int, int],
                        tuple(_quantize(value, maximum) for value in rgb_raw),
                    )
                    alpha8 = _quantize(alpha_raw, maximum)
                    if alpha_raw != maximum:
                        opaque = False
                    min_alpha = min(min_alpha, alpha8)
                    for channel in range(3):
                        min_rgb[channel] = min(min_rgb[channel], rgb8[channel])
                        max_rgb[channel] = max(max_rgb[channel], rgb8[channel])
                    if x_value == sample_x and row_index == sample_y:
                        sample_rgb = rgb8
            previous = row
            row_index += 1
        if offset:
            del pending[:offset]

    try:
        for part in frame.idat_parts:
            # zlib exposes unconsumed_tail as bytes. Bound input as well as
            # output so draining a large IDAT cannot repeatedly copy its tail.
            for offset in range(0, len(part), block_size):
                data: bytes | memoryview = part[offset : offset + block_size]
                while True:
                    checkpoint()
                    output = decompressor.decompress(data, block_size)
                    if decompressor.unused_data:
                        raise _MalformedPng("trailing PNG DEFLATE data")
                    consume(output)
                    tail = decompressor.unconsumed_tail
                    if tail:
                        if not output and len(tail) == len(data):
                            raise _MalformedPng("PNG DEFLATE made no progress")
                        data = tail
                    elif len(output) == block_size:
                        data = b""
                    else:
                        break
        if (
            not decompressor.eof
            or decompressor.unused_data
            or decompressor.unconsumed_tail
            or pending
            or produced != frame.scanline_bytes
            or row_index != image_size.height
            or sample_rgb is None
            or first_raw is None
        ):
            raise _MalformedPng("incomplete or trailing PNG DEFLATE stream")
    except (zlib.error, _MalformedPng) as cause:
        _controlled(CommandError, "command_failed", operation_id, request_state, cause)

    return ColorSample(
        rgb=sample_rgb,
        hex=f"#{sample_rgb[0]:02X}{sample_rgb[1]:02X}{sample_rgb[2]:02X}",
        opaque=opaque,
        min_alpha=min_alpha,
        uniform=uniform,
        min_rgb=cast(tuple[int, int, int], tuple(min_rgb)),
        max_rgb=cast(tuple[int, int, int], tuple(max_rgb)),
        color_space=frame.color_space,
        icc_profile_name=frame.icc_profile_name,
        coordinate_space=coordinate_space,
        pointer_point=pointer_point,
        pointer_bounds=pointer_bounds,
        image_point=image_point,
        image_bounds=image_bounds,
        image_size=image_size,
        pointer_size=pointer_size,
        png_sha256=frame.png_sha256,
    )


def sample_png_color(
    png_bytes: bytes,
    x: int | None = None,
    y: int | None = None,
    *,
    region: ImageRegion | Bounds | None = None,
    coordinate_space: Literal["pointer", "image"] = "pointer",
    pointer_size: DisplaySize | None = None,
    control: OperationControl | None = None,
) -> ColorSample:
    """Sample one point or half-open region from a caller-provided PNG frame."""
    operation_id = uuid4().hex
    started = time.monotonic()
    deadline: float | None = None

    def checkpoint() -> None:
        if control is None:
            return
        if control.cancellation is not None and control.cancellation.is_set():
            raise OperationCancelledError(
                "operation_cancelled", operation_id, "not_sent"
            )
        assert deadline is not None
        if time.monotonic() >= deadline:
            raise OperationTimeoutError("operation_timeout", operation_id, "not_sent")

    frame: _SampleFrame | None = None
    try:
        if control is not None:
            if not isinstance(control, OperationControl):
                _invalid(operation_id)
            deadline = started + control.timeout_seconds
        bounds, valid_space = _validate_sample_inputs(
            x, y, region, coordinate_space, operation_id
        )
        if type(png_bytes) is not bytes:
            _invalid(operation_id)
        checkpoint()
        frame = _parse_sample_frame(png_bytes, operation_id, "not_sent", checkpoint)
        checkpoint()
        return _sample_frame(
            frame,
            bounds,
            valid_space,
            pointer_size,
            operation_id,
            "not_sent",
            checkpoint,
        )
    except AutomationError as error:
        failure = _sample_failure(error)
    del png_bytes, frame
    raise failure from None
