# MarkdownImagePaste

A Sublime Text 4 plugin for Windows that pastes clipboard images directly into markdown files.

## How it works

Press **Ctrl+V** while editing a markdown file:
- **Clipboard has an image** → saves it to `.images/` next to your file and inserts `![](relative/path)` at the cursor
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

## Configuration

Open `Preferences → Package Settings → MarkdownImagePaste → Settings`:

```json
{
    // Directory where images are saved (relative to the open markdown file)
    "image_dir": ".images",

    // When true: cursor lands between [] after paste so you can type alt text
    // When false (default): cursor lands after the closing )
    "prompt_alt_text": false
}
```

## License

MIT
