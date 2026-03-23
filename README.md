# MarkdownImagePaste

A Sublime Text 4 plugin for Windows that pastes clipboard images directly into Markdown files.

## How it works

Press **Ctrl+V** while editing a Markdown file:

- **Clipboard has an image** → saves it to `.images/` next to your file and inserts `![](.images/image_<timestamp>.png)` at the cursor
- **Clipboard has text** → normal paste, unchanged

Works with screenshots (Win+Shift+S, Snipping Tool) and images copied from browsers or other applications.

## Requirements

- Sublime Text 4 (build 4000+)
- Windows

## Installation

### Via Package Control (recommended)

1. Open the Command Palette (`Ctrl+Shift+P`)
2. Run `Package Control: Install Package`
3. Search for `MarkdownImagePaste`

### Manual

Copy the `MarkdownImagePaste/` folder into your Sublime Text packages directory:

```
%APPDATA%\Sublime Text\Packages\
```

> **Important:** Make sure to include the `.python-version` file. ST4 uses it to select Python 3.8; omitting it will cause import errors.

## Configuration

Open `Preferences → Package Settings → MarkdownImagePaste → Settings`:

```json
{
    // Directory where images are saved (relative to the open Markdown file)
    "image_dir": ".images",

    // When true: cursor lands between [] after paste so you can type alt text
    // When false (default): cursor lands after the closing )
    "prompt_alt_text": false
}
```

> **Note:** `image_dir` is used as a path component relative to your Markdown file. Do not set it to an absolute path or a value containing `..`.

## How images are saved

Images are saved as `image_<unix_ms>.png` (e.g. `image_1742749200123.png`) inside the configured `image_dir`, relative to the open file. The directory is created automatically if it doesn't exist.

Supported clipboard formats (in priority order):

1. **CF_PNG** — already a PNG, saved directly
2. **CF_DIB / CF_DIBV5** — raw Device Independent Bitmap, converted to PNG using pure Python (`struct` + `zlib`)

## Design notes

- No subprocess spawning (Carbon Black / endpoint-security safe)
- No external dependencies — pure Python stdlib + `ctypes`
- Multi-cursor aware: inserts at each cursor position

## License

MIT
