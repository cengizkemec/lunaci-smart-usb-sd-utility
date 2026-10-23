# Lunaci Smart USB & SD Card Utility v1.3.3

**Release date:** 2026-10-23

Theme readability improvements and volume label fix.

## Download

| File | Description |
| --- | --- |
| `LunaciSetup.exe` | **Recommended.** Installer (Turkish + English wizard), creates Start Menu and optional desktop shortcut. |
| `LunaciSmartUSBCardUtility.exe` | Portable single-file executable — just run it, no installation needed. |

> Administrator rights are requested automatically (UAC) on startup, because
> `diskpart`, `chkdsk`, ISO mounting and raw ISO writing require elevation.

## What's new in 1.3.3

### Fixed: default volume label "Lunaci" on unnamed drives
Unnamed USB/SD drives no longer get a default "LUNACI" volume label. They stay unnamed unless you explicitly set a label in the format options.

### Improved dark theme readability (Telegram-inspired)
- Button text contrast improved in dark mode so all buttons are easily readable.
- Accent and segmented button colors adjusted for better WCAG contrast while keeping the Telegram-like look (blues on dark backgrounds).
- Option menus and segmented controls now use high-contrast white text in dark theme.

## Everything from 1.3.2

- Fixed update prompt that could grow too tall and push the Install button off-screen.
- Proper scrollable release notes dialog.

## Everything from 1.3.1 and earlier

- Single console for logs and transfers.
- Bootable ISO writing.
- Auto-update from GitHub.
- And more (see previous notes).

## Requirements

- Windows 10 / 11 (x64)
- Administrator rights (requested automatically)

## Getting started

1. Plug in your USB stick or SD card — it is detected automatically.
2. Pick a file system (defaults to the device's current one) and press **Format**.
3. Copy a folder, write an ISO, extract a ZIP, or run a health test.

---

Full change log: see repository history.
