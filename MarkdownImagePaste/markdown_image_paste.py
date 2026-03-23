"""
MarkdownImagePaste — Sublime Text 4 plugin (Windows only).

Intercepts Ctrl+V in markdown files. If the clipboard contains an image,
saves it to .images/ next to the markdown file and inserts markdown syntax.
Falls through to normal paste for text content.
"""
import os
import struct
import time
import zlib
import ctypes
import ctypes.wintypes

import sublime
import sublime_plugin

# ---------------------------------------------------------------------------
# Windows clipboard constants
# ---------------------------------------------------------------------------

_CF_DIB = 8

# Guard all ctypes.windll usage — windll does not exist on Linux/Mac
try:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    # CF_PNG is a registered (non-standard) format number — resolved once at import
    try:
        _CF_PNG = _user32.RegisterClipboardFormatW("PNG")
    except Exception:
        _CF_PNG = 0
    _WINDOWS = True
except AttributeError:
    # Non-Windows platform (Linux, macOS) — clipboard functions unavailable
    _user32 = None
    _kernel32 = None
    _CF_PNG = 0
    _WINDOWS = False


# ---------------------------------------------------------------------------
# Clipboard reading
# ---------------------------------------------------------------------------

def _clipboard_has_image():
    """
    Fast check for image data on the clipboard.
    Does NOT open the clipboard — safe to call speculatively.
    """
    if not _WINDOWS:
        return False
    return bool(
        (_CF_PNG and _user32.IsClipboardFormatAvailable(_CF_PNG)) or
        _user32.IsClipboardFormatAvailable(_CF_DIB)
    )


def _read_clipboard_format(fmt):
    """
    Open clipboard, copy raw bytes for the given format, close clipboard.
    Retries up to 5 times (1 ms apart) if the clipboard is busy.
    Returns bytes, or None on failure.
    """
    if not _WINDOWS:
        return None

    for _ in range(5):
        if _user32.OpenClipboard(None):
            break
        time.sleep(0.001)
    else:
        return None

    try:
        handle = _user32.GetClipboardData(fmt)
        if not handle:
            return None
        size = _kernel32.GlobalSize(handle)
        if not size:
            return None
        ptr = _kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.string_at(ptr, size)
        finally:
            _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()


def _get_clipboard_image():
    """
    Read an image from the Windows clipboard.
    Returns (image_bytes, extension) or (None, None).
    Priority: CF_PNG (already encoded) > CF_DIB (needs conversion).
    """
    if not _WINDOWS:
        return None, None

    # CF_PNG: bytes are already a valid PNG file
    if _CF_PNG and _user32.IsClipboardFormatAvailable(_CF_PNG):
        data = _read_clipboard_format(_CF_PNG)
        if data and data[:8] == b'\x89PNG\r\n\x1a\n':
            return data, 'png'

    # CF_DIB: raw Device Independent Bitmap — convert to PNG (or BMP fallback)
    if _user32.IsClipboardFormatAvailable(_CF_DIB):
        dib = _read_clipboard_format(_CF_DIB)
        if dib:
            result = _dib_to_png(dib)
            ext = 'bmp' if result[:2] == b'BM' else 'png'
            return result, ext

    return None, None


# ---------------------------------------------------------------------------
# DIB -> PNG conversion
# ---------------------------------------------------------------------------

def _dib_to_png(dib_data):
    """
    Convert raw CF_DIB bytes (BITMAPINFOHEADER + pixels) to PNG bytes.
    Falls back to _dib_to_bmp_bytes() for unsupported formats.

    Supported: 24-bit BGR and 32-bit BGRA with BI_RGB (compression=0).
    Fallback:  BI_BITFIELDS, palette images, or malformed data.
    """
    if len(dib_data) < 40:
        return _dib_to_bmp_bytes(dib_data)

    (biSize, biWidth, biHeight, biPlanes, biBitCount,
     biCompression, biSizeImage, _xppm, _yppm,
     biClrUsed, biClrImportant) = struct.unpack_from('<IiiHHIIiiII', dib_data, 0)

    if biCompression != 0:          # only handle BI_RGB
        return _dib_to_bmp_bytes(dib_data)
    if biBitCount not in (24, 32):  # only 24-bit and 32-bit
        return _dib_to_bmp_bytes(dib_data)

    width  = biWidth
    height = abs(biHeight)
    flip   = biHeight > 0  # positive biHeight = bottom-up row order

    pixel_offset   = biSize + biClrUsed * 4
    bytes_per_pixel = biBitCount // 8
    row_stride      = ((width * bytes_per_pixel + 3) & ~3)

    # Read rows, reversing if the DIB is bottom-up
    rows = []
    for y in range(height):
        src_y  = (height - 1 - y) if flip else y
        offset = pixel_offset + src_y * row_stride
        rows.append(dib_data[offset: offset + width * bytes_per_pixel])

    # Convert BGR(A) -> RGB(A)
    png_rows = []
    if biBitCount == 24:
        color_type = 2  # RGB
        for row in rows:
            buf = bytearray(width * 3)
            for i in range(width):
                buf[i * 3]     = row[i * 3 + 2]  # R
                buf[i * 3 + 1] = row[i * 3 + 1]  # G
                buf[i * 3 + 2] = row[i * 3]       # B
            png_rows.append(bytes(buf))
    else:
        color_type = 6  # RGBA
        for row in rows:
            buf = bytearray(width * 4)
            for i in range(width):
                buf[i * 4]     = row[i * 4 + 2]  # R
                buf[i * 4 + 1] = row[i * 4 + 1]  # G
                buf[i * 4 + 2] = row[i * 4]       # B
                buf[i * 4 + 3] = row[i * 4 + 3]  # A
            png_rows.append(bytes(buf))

    return _encode_png(width, height, 8, color_type, png_rows)


def _encode_png(width, height, bit_depth, color_type, rows):
    """
    Minimal PNG encoder using only stdlib (struct + zlib).
    rows: list of raw pixel row bytes (no filter byte prepended).
    Uses filter type 0 (None) for simplicity.
    """
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    sig  = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, bit_depth, color_type, 0, 0, 0))
    raw  = b''.join(b'\x00' + row for row in rows)  # filter byte 0 per row
    idat = chunk(b'IDAT', zlib.compress(raw, 9))
    iend = chunk(b'IEND', b'')

    return sig + ihdr + idat + iend


def _dib_to_bmp_bytes(dib_data):
    """
    Wrap raw CF_DIB bytes in a BITMAPFILEHEADER to produce a valid .bmp file.
    Used as fallback for unsupported or unusual DIB formats.
    """
    if len(dib_data) < 40:
        return b''

    (_biSize, _biWidth, _biHeight, _biPlanes, biBitCount,
     _biComp, _biSizeImage, _x, _y,
     biClrUsed, _biClrImp) = struct.unpack_from('<IiiHHIIiiII', dib_data, 0)

    n_colors     = biClrUsed if biClrUsed else (1 << biBitCount if biBitCount <= 8 else 0)
    pixel_offset = 14 + 40 + n_colors * 4
    file_size    = 14 + len(dib_data)
    file_header  = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, pixel_offset)
    return file_header + dib_data


# ---------------------------------------------------------------------------
# Sublime Text command
# ---------------------------------------------------------------------------

class MarkdownImagePasteCommand(sublime_plugin.TextCommand):
    """
    Intercepts Ctrl+V in markdown files.
    Saves clipboard image to .images/ and inserts markdown link.
    Delegates to built-in paste when clipboard has no image.
    """

    def run(self, edit):
        if not _clipboard_has_image():
            self.view.run_command('paste')
            return

        file_path = self.view.file_name()
        if not file_path:
            sublime.status_message(
                'MarkdownImagePaste: save the file before pasting an image'
            )
            return

        image_data, ext = _get_clipboard_image()
        if not image_data:
            # Clipboard changed between check and read — fall through
            self.view.run_command('paste')
            return

        settings        = sublime.load_settings('MarkdownImagePaste.sublime-settings')
        image_dir_name  = settings.get('image_dir', '.images')
        prompt_alt_text = settings.get('prompt_alt_text', False)

        file_dir = os.path.dirname(file_path)
        img_dir  = os.path.join(file_dir, image_dir_name)

        try:
            os.makedirs(img_dir, exist_ok=True)
        except OSError as e:
            sublime.status_message(
                f'MarkdownImagePaste: could not create image directory — {e}'
            )
            return

        filename = f'image_{int(time.time() * 1000)}.{ext}'
        img_path = os.path.join(img_dir, filename)

        try:
            with open(img_path, 'wb') as f:
                f.write(image_data)
        except OSError as e:
            sublime.status_message(
                f'MarkdownImagePaste: could not save image — {e}'
            )
            return

        rel_path  = os.path.relpath(img_path, file_dir).replace('\\', '/')
        md_syntax = f'![]({rel_path})'

        # Insert at each cursor; iterate in reverse order to preserve offsets
        # when multiple cursors are active
        selections = sorted(self.view.sel(), key=lambda r: r.begin(), reverse=True)

        for region in selections:
            insert_point = region.begin()
            self.view.replace(edit, region, md_syntax)

            if prompt_alt_text:
                cursor_pos = insert_point + 2        # between [ and ]
            else:
                cursor_pos = insert_point + len(md_syntax)  # after )

            self.view.sel().subtract(region)
            self.view.sel().add(sublime.Region(cursor_pos, cursor_pos))

    def is_enabled(self):
        if not self.view.sel():
            return False
        scope = self.view.scope_name(self.view.sel()[0].begin())
        return 'text.html.markdown' in scope
