from __future__ import annotations

import struct
import zlib
from collections.abc import Iterable
from types import SimpleNamespace

import pytest

from appium_connect_agent.automation import (
    Bounds,
    CommandError,
    DisplaySize,
    ImageRegion,
    InvalidRequestError,
    OperationTimeoutError,
    _sample_color,
    sample_png_color,
)
from appium_connect_agent.runtime import OperationControl

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))


def _png(
    width: int,
    height: int,
    depth: int,
    color_type: int,
    scanlines: bytes,
    *,
    before_idat: Iterable[tuple[bytes, bytes]] = (),
    interlace: int = 0,
    compressed: bytes | None = None,
) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, depth, color_type, 0, 0, interlace)
    chunks = [_chunk(b"IHDR", ihdr)]
    chunks.extend(_chunk(kind, data) for kind, data in before_idat)
    payload = zlib.compress(scanlines) if compressed is None else compressed
    chunks.append(_chunk(b"IDAT", payload))
    chunks.append(_chunk(b"IEND", b""))
    return _SIGNATURE + b"".join(chunks)


def _error_code(error_type: type[CommandError], png: bytes) -> str:
    with pytest.raises(error_type) as caught:
        sample_png_color(png, 0, 0, coordinate_space="image")
    assert caught.value.request_state == "not_sent"
    return caught.value.code


def test_rgba_region_reports_center_extrema_alpha_and_hash() -> None:
    scanlines = (
        b"\0"
        + bytes((0, 191, 243, 255, 10, 20, 30, 0))
        + b"\0"
        + bytes((0, 191, 243, 128, 255, 200, 100, 255))
    )
    png = _png(2, 2, 8, 6, scanlines, before_idat=((b"sRGB", b"\0"),))

    result = sample_png_color(
        png,
        region=ImageRegion(0, 0, 2, 2),
        coordinate_space="image",
        pointer_size=DisplaySize(4, 4),
    )

    assert result.rgb == (255, 200, 100)
    assert result.hex == "#FFC864"
    assert result.image_point == (1, 1)
    assert result.pointer_bounds == Bounds(0, 0, 4, 4)
    assert result.pointer_point == (2, 2)
    assert result.min_rgb == (0, 20, 30)
    assert result.max_rgb == (255, 200, 243)
    assert result.min_alpha == 0
    assert result.opaque is False
    assert result.uniform is False
    assert result.color_space == "srgb"
    assert len(result.png_sha256) == 64


@pytest.mark.parametrize(
    ("depth", "color_type", "row", "chunks", "expected", "alpha"),
    [
        (1, 0, b"\x80", (), (255, 255, 255), 255),
        (8, 0, b"\x7f", ((b"tRNS", b"\x00\x7f"),), (127, 127, 127), 0),
        (8, 2, bytes((1, 2, 3)), (), (1, 2, 3), 255),
        (
            2,
            3,
            b"\x40",
            ((b"PLTE", bytes((9, 8, 7, 1, 2, 3))), (b"tRNS", b"\xff\x04")),
            (1, 2, 3),
            4,
        ),
        (8, 4, bytes((33, 44)), (), (33, 33, 33), 44),
        (8, 6, bytes((5, 6, 7, 8)), (), (5, 6, 7), 8),
    ],
)
def test_supported_color_types_and_transparency(
    depth: int,
    color_type: int,
    row: bytes,
    chunks: tuple[tuple[bytes, bytes], ...],
    expected: tuple[int, int, int],
    alpha: int,
) -> None:
    result = sample_png_color(
        _png(1, 1, depth, color_type, b"\0" + row, before_idat=chunks),
        0,
        0,
        coordinate_space="image",
    )
    assert result.rgb == expected
    assert result.min_alpha == alpha
    assert result.opaque is (alpha == 255)
    assert result.uniform is True


def test_16_bit_rounding_and_raw_uniformity() -> None:
    first = struct.pack(">HHHH", 0x0100, 0x0200, 0x0300, 0xFFFF)
    second = struct.pack(">HHHH", 0x0101, 0x0200, 0x0300, 0xFFFF)
    result = sample_png_color(
        _png(2, 1, 16, 6, b"\0" + first + second),
        region=Bounds(0, 0, 2, 1),
        coordinate_space="image",
    )
    assert result.rgb == (1, 2, 3)
    assert result.min_rgb == result.max_rgb == (1, 2, 3)
    assert result.uniform is False
    assert result.opaque is True


def _encoded_filter(raw: bytes, previous: bytes, filter_type: int, bpp: int) -> bytes:
    encoded = bytearray(len(raw))
    for index, value in enumerate(raw):
        left = raw[index - bpp] if index >= bpp else 0
        above = previous[index]
        upper_left = previous[index - bpp] if index >= bpp else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = above
        elif filter_type == 3:
            predictor = (left + above) // 2
        else:
            estimate = left + above - upper_left
            distances = (
                abs(estimate - left),
                abs(estimate - above),
                abs(estimate - upper_left),
            )
            predictor = (left, above, upper_left)[distances.index(min(distances))]
        encoded[index] = (value - predictor) & 0xFF
    return bytes(encoded)


def test_all_png_row_filters() -> None:
    rows = [bytes((index, index + 1, index + 2)) for index in range(10, 60, 10)]
    previous = bytes(3)
    encoded = bytearray()
    for filter_type, row in enumerate(rows):
        encoded.append(filter_type)
        encoded.extend(_encoded_filter(row, previous, filter_type, 3))
        previous = row
    png = _png(1, 5, 8, 2, bytes(encoded))
    for y, row in enumerate(rows):
        assert sample_png_color(png, 0, y, coordinate_space="image").rgb == tuple(row)


def test_pointer_mapping_in_both_integer_scale_directions() -> None:
    png = _png(
        2,
        2,
        8,
        2,
        b"\0" + bytes((1, 2, 3, 4, 5, 6)) + b"\0" + bytes((7, 8, 9, 10, 11, 12)),
    )
    down = sample_png_color(png, 2, 2, pointer_size=DisplaySize(4, 4))
    assert down.image_bounds == Bounds(1, 1, 1, 1)
    assert down.rgb == (10, 11, 12)

    up = sample_png_color(
        png,
        region=Bounds(0, 0, 1, 1),
        coordinate_space="image",
        pointer_size=DisplaySize(1, 1),
    )
    assert up.pointer_bounds == Bounds(0, 0, 1, 1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"x": 0},
        {"x": True, "y": 0},
        {"x": 0, "y": 0, "region": Bounds(0, 0, 1, 1)},
        {"region": Bounds(0, 0, 0, 1)},
        {"region": ImageRegion(1, 0, 1, 1)},
        {"x": 0, "y": 0, "coordinate_space": "pixels"},
    ],
)
def test_invalid_selection_is_rejected(kwargs: dict[str, object]) -> None:
    png = _png(1, 1, 8, 2, b"\0\x01\x02\x03")
    with pytest.raises(InvalidRequestError) as caught:
        sample_png_color(png, **kwargs)  # type: ignore[arg-type]
    assert caught.value.code == "invalid_argument"
    assert caught.value.request_state == "not_sent"


def test_bounds_and_pointer_mapping_fail_safely() -> None:
    png = _png(1, 1, 8, 2, b"\0\x01\x02\x03")
    with pytest.raises(InvalidRequestError):
        sample_png_color(png, 1, 0, coordinate_space="image")
    with pytest.raises(CommandError) as missing:
        sample_png_color(png, 0, 0)
    assert missing.value.code == "pointer_mapping_unavailable"
    with pytest.raises(CommandError) as ratio:
        sample_png_color(png, 0, 0, pointer_size=DisplaySize(2, 3))
    assert ratio.value.code == "pointer_mapping_unavailable"


@pytest.mark.parametrize(
    ("chunks", "expected_space", "profile"),
    [
        (
            (
                (b"gAMA", struct.pack(">I", 45455)),
                (b"cHRM", struct.pack(">8I", *(1 for _ in range(8)))),
            ),
            "untagged",
            None,
        ),
        (((b"sRGB", b"\0"),), "srgb", None),
        (
            ((b"iCCP", b"Display P3\0\0" + zlib.compress(b"profile")),),
            "embedded_icc",
            "Display P3",
        ),
        (
            (
                (b"iCCP", b"P3\0\0" + zlib.compress(b"profile")),
                (b"cICP", b"\x0c\x0d\x00\x01"),
            ),
            "cicp",
            "P3",
        ),
    ],
)
def test_color_metadata(
    chunks: tuple[tuple[bytes, bytes], ...],
    expected_space: str,
    profile: str | None,
) -> None:
    result = sample_png_color(
        _png(1, 1, 8, 2, b"\0\x01\x02\x03", before_idat=chunks),
        0,
        0,
        coordinate_space="image",
    )
    assert result.color_space == expected_space
    assert result.icc_profile_name == profile


def test_srgb_iccp_conflict_is_malformed() -> None:
    png = _png(
        1,
        1,
        8,
        2,
        b"\0\x01\x02\x03",
        before_idat=(
            (b"sRGB", b"\0"),
            (b"iCCP", b"Profile\0\0" + zlib.compress(b"profile")),
        ),
    )
    assert _error_code(CommandError, png) == "command_failed"


def test_apng_unsupported_format_and_bad_crc_are_distinct() -> None:
    base_scanline = b"\0\x01\x02\x03"
    apng = _png(
        1,
        1,
        8,
        2,
        base_scanline,
        before_idat=((b"acTL", struct.pack(">II", 1, 0)),),
    )
    assert _error_code(CommandError, apng) == "frame_not_single"
    plain = _png(1, 1, 8, 2, base_scanline)
    late_apng = plain[:-12] + _chunk(b"fcTL", bytes(26)) + plain[-12:]
    assert _error_code(CommandError, late_apng) == "frame_not_single"
    interlaced = _png(1, 1, 8, 2, base_scanline, interlace=1)
    assert _error_code(CommandError, interlaced) == "unsupported_png_format"
    unknown_critical = _png(1, 1, 8, 2, base_scanline, before_idat=((b"ABCD", b""),))
    assert _error_code(CommandError, unknown_critical) == "unsupported_png_format"
    damaged = bytearray(_png(1, 1, 8, 2, base_scanline))
    damaged[-5] ^= 1
    assert _error_code(CommandError, bytes(damaged)) == "command_failed"


@pytest.mark.parametrize(
    "compressed",
    [
        zlib.compress(b"\0\x01\x02"),
        zlib.compress(b"\0\x01\x02\x03")[:-1],
        zlib.compress(b"\0\x01\x02\x03") + b"trailing",
        zlib.compress(b"\0\x01\x02\x03\x04"),
    ],
)
def test_decompression_terminal_and_size_bounds(compressed: bytes) -> None:
    png = _png(1, 1, 8, 2, b"", compressed=compressed)
    assert _error_code(CommandError, png) == "command_failed"


def test_single_large_idat_spanning_inflate_blocks_preserves_last_rows() -> None:
    width, height = 256, 100
    rgb = b"\x00\xbf\xf3"
    pixels = (b"\0" + b"\xff\xff\xff" * width) * (height - 2)
    pixels += (b"\0" + rgb * width) * 2
    compressed = zlib.compress(pixels, level=0)
    assert len(compressed) > 65_536
    png = _png(width, height, 8, 2, b"", compressed=compressed)
    result = sample_png_color(
        png, region=Bounds(255, 98, 1, 2), coordinate_space="image"
    )
    assert result.uniform and result.rgb == (0, 191, 243)


def test_row_and_pixel_resource_limits_precede_decompression() -> None:
    row_too_wide = _png(100_000, 1, 8, 6, b"", compressed=zlib.compress(b"x"))
    assert _error_code(CommandError, row_too_wide) == "command_failed"
    pixels_too_many = _png(8192, 8192, 1, 0, b"", compressed=zlib.compress(b"x"))
    assert _error_code(CommandError, pixels_too_many) == "command_failed"


def test_invalid_filter_and_palette_index_are_decode_failures() -> None:
    bad_filter = _png(1, 1, 8, 2, b"\x05\x01\x02\x03")
    assert _error_code(CommandError, bad_filter) == "command_failed"
    bad_index = _png(
        1,
        1,
        8,
        3,
        b"\0\x01",
        before_idat=((b"PLTE", b"\x01\x02\x03"),),
    )
    assert _error_code(CommandError, bad_index) == "command_failed"


def test_sample_region_resource_limit_is_controlled() -> None:
    width = height = 1_025
    row = b"\0" + bytes((width + 7) // 8)
    png = _png(width, height, 1, 0, row * height)
    with pytest.raises(CommandError) as caught:
        sample_png_color(
            png,
            region=Bounds(0, 0, width, height),
            coordinate_space="image",
        )
    assert caught.value.code == "command_failed"


def test_narrow_png_at_pixel_limit_decodes_last_pixel() -> None:
    width, height = 4, 8_388_608
    frame = _png(width, height, 1, 0, b"\0\0" * (height - 1) + b"\0\x10")
    result = sample_png_color(frame, 3, height - 1, coordinate_space="image")
    assert result.rgb == (255, 255, 255)
    assert result.image_point == (3, height - 1)
    beyond = _png(width, height + 1, 1, 0, b"", compressed=zlib.compress(b"x"))
    assert _error_code(CommandError, beyond) == "command_failed"


def test_narrow_png_respects_deadline_during_scanline_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    height = 65_536
    frame = _png(4, height, 1, 0, b"\0\0" * height)
    ticks = iter(range(height))
    monkeypatch.setattr(
        _sample_color, "time", SimpleNamespace(monotonic=lambda: next(ticks) / 1_000)
    )
    with pytest.raises(OperationTimeoutError) as caught:
        sample_png_color(
            frame,
            3,
            height - 1,
            coordinate_space="image",
            control=OperationControl(timeout_seconds=1.0),
        )
    assert caught.value.request_state == "not_sent"
    assert caught.value.__cause__ is None and caught.value.__context__ is None
