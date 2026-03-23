"""
Tests for DIB->PNG conversion logic.
Runs standalone — no Sublime Text installation required.
"""
import sys
import os
import struct
import types
import zlib

# --- Mock Sublime Text modules so we can import the plugin standalone ---
_sublime = types.ModuleType('sublime')
_sublime_plugin = types.ModuleType('sublime_plugin')
_sublime_plugin.TextCommand = object
sys.modules.setdefault('sublime', _sublime)
sys.modules.setdefault('sublime_plugin', _sublime_plugin)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'MarkdownImagePaste'))
import markdown_image_paste as mip


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_dib(width, height, bit_depth=24, compression=0):
    """Return minimal CF_DIB bytes (BITMAPINFOHEADER + pixel data)."""
    biHeight = -height  # negative = top-down (no row flip needed)
    header = struct.pack(
        '<IiiHHIIiiII',
        40, width, biHeight, 1, bit_depth,
        compression, 0, 0, 0, 0, 0,
    )
    bytes_per_pixel = bit_depth // 8
    row_stride = ((width * bytes_per_pixel + 3) & ~3)
    pixels = bytes(row_stride * height)
    return header + pixels


def is_valid_png(data):
    return data[:8] == b'\x89PNG\r\n\x1a\n'


def parse_png_ihdr(data):
    """Extract (width, height, bit_depth, color_type) from PNG IHDR chunk."""
    # Offset: 8 (sig) + 4 (length) + 4 (type) = 16
    return struct.unpack('>IIBBBBB', data[16:29])[:4]


# ---------------------------------------------------------------------------
# Tests: _dib_to_png
# ---------------------------------------------------------------------------

def test_24bit_dib_produces_valid_png():
    result = mip._dib_to_png(make_dib(4, 4, bit_depth=24))
    assert is_valid_png(result), "Output must start with PNG signature"


def test_32bit_dib_produces_valid_png():
    result = mip._dib_to_png(make_dib(4, 4, bit_depth=32))
    assert is_valid_png(result), "32-bit BGRA DIB must produce valid PNG"


def test_png_dimensions_match_dib():
    result = mip._dib_to_png(make_dib(10, 7, bit_depth=24))
    width, height, _, _ = parse_png_ihdr(result)
    assert width == 10
    assert height == 7


def test_24bit_color_type_is_rgb():
    result = mip._dib_to_png(make_dib(2, 2, bit_depth=24))
    _, _, _, color_type = parse_png_ihdr(result)
    assert color_type == 2  # PNG color type 2 = RGB


def test_32bit_color_type_is_rgba():
    result = mip._dib_to_png(make_dib(2, 2, bit_depth=32))
    _, _, _, color_type = parse_png_ihdr(result)
    assert color_type == 6  # PNG color type 6 = RGBA


def test_bitfields_compression_falls_back_to_bmp():
    result = mip._dib_to_png(make_dib(4, 4, bit_depth=32, compression=3))
    assert result[:2] == b'BM', "BI_BITFIELDS DIB must fall back to BMP bytes"


def test_bottom_up_dib_produces_correct_row_order():
    """
    Positive biHeight = bottom-up rows.
    Row 0 in memory = bottom row visually = should appear LAST in PNG.
    Row 1 in memory = top row visually = should appear FIRST in PNG.
    We use distinct colors to verify the flip actually happened.
    """
    width, height = 2, 2
    # bottom-up: positive biHeight
    header = struct.pack(
        '<IiiHHIIiiII',
        40, width, height, 1, 24,  # positive biHeight = bottom-up
        0, 0, 0, 0, 0, 0,
    )
    # 24-bit BGR, row stride padded to 4 bytes
    # row 0 (memory) = bottom row visually = all red (BGR: 0x00, 0x00, 0xFF)
    # row 1 (memory) = top row visually    = all green (BGR: 0x00, 0xFF, 0x00)
    row_stride = ((width * 3 + 3) & ~3)
    row0_bottom = b'\x00\x00\xff' * width  # red in BGR
    row1_top    = b'\x00\xff\x00' * width  # green in BGR
    # Pad rows to stride
    row0_bottom = row0_bottom + b'\x00' * (row_stride - len(row0_bottom))
    row1_top    = row1_top    + b'\x00' * (row_stride - len(row1_top))
    dib = header + row0_bottom + row1_top

    result = mip._dib_to_png(dib)

    # Verify PNG dimensions
    w, h, _, _ = parse_png_ihdr(result)
    assert w == width
    assert h == height

    # Decompress IDAT and verify first scanline is green (top row after flip)
    # PNG IDAT chunk starts at byte 8+25+12 = 45 (sig + IHDR chunk)
    # chunk layout: 4 len + 4 type + data + 4 crc
    ihdr_chunk_len = struct.unpack_from('>I', result, 8)[0]
    idat_offset = 8 + 4 + 4 + ihdr_chunk_len + 4  # after sig + IHDR chunk
    idat_data_len = struct.unpack_from('>I', result, idat_offset)[0]
    idat_data = result[idat_offset + 8: idat_offset + 8 + idat_data_len]
    raw = zlib.decompress(idat_data)

    # First scanline: filter byte (1 byte) + RGB pixels (width * 3 bytes)
    first_row_pixels = raw[1: 1 + width * 3]
    # Green in RGB is (0, 255, 0)
    assert first_row_pixels == b'\x00\xff\x00' * width, \
        f"First PNG row should be green (top row after bottom-up flip), got {first_row_pixels.hex()}"


# ---------------------------------------------------------------------------
# Tests: _dib_to_bmp_bytes
# ---------------------------------------------------------------------------

def test_bmp_fallback_starts_with_bm_signature():
    result = mip._dib_to_bmp_bytes(make_dib(2, 2, bit_depth=24))
    assert result[:2] == b'BM'


def test_bmp_fallback_file_size_field_is_accurate():
    result = mip._dib_to_bmp_bytes(make_dib(2, 2, bit_depth=24))
    file_size = struct.unpack_from('<I', result, 2)[0]
    assert file_size == len(result)
