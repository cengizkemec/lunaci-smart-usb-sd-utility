# Lunaci Smart USB & SD Card Utility v1.3.2

**Release date:** 2026-10-19

A small follow-up fix for v1.3.1.

## Download

| File | Description |
| --- | --- |
| `LunaciSetup.exe` | **Recommended.** Installer (Turkish + English wizard), creates Start Menu and optional desktop shortcut. |
| `LunaciSmartUSBCardUtility.exe` | Portable single-file executable — just run it, no installation needed. |

> Administrator rights are requested automatically (UAC) on startup, because
> `diskpart`, `chkdsk`, ISO mounting and raw ISO writing require elevation.

## What's new in 1.3.2

### Fixed: the update prompt could not be confirmed

When a new version was found, the confirmation window printed the **entire** release
notes as its message. With longer notes the dialog grew taller than the screen, so the
**Yes / Install** button was pushed off-screen and could not be clicked — the update
could never be started from inside the app.

The prompt is now a proper window:

- A fixed heading shows the new and current version.
- The release notes are shown in their own **scrollable** area, so any length fits.
- **Download and Install** / **Later** buttons stay pinned at the bottom and are always
  clickable; `Enter` confirms and `Esc` closes.
- The window is centred and clamped to the screen, and the second "apply the update
  now?" prompt is worded as a clear question.

## Everything from 1.3.1

- **One console instead of two panels** — the live file list and the timestamped log
  share a single console; file rows stay as one block at the bottom while log lines flow
  in above them.
- **A single progress bar** — the duplicate transfer progress bar was removed.
- **Readable buttons in dark mode** — the accent colour was deepened so white text
  reaches WCAG AA (≥ 4.5:1) in both themes, and every accent button now uses white text.

## Everything from 1.3.0

- **Live transfer console** (now merged — see above).
- **Bootable ISO writing** (Rufus-style): automatic mode detection, Windows `install.wim`
  splitting to `install.swm`, `bootsect` + UEFI files for BIOS/UEFI boot.
- **Automatic self-update from GitHub** with release notes and background download.
- **Completion sound** (toggleable).
- **Readability pass** over the dark and light themes.

## Stability and performance

- Rewritten, non-blocking device polling with plug/unplug events.
- All long operations run off the UI thread and are safely cancellable.
- Batched console updates keep the interface responsive under heavy output.
- Diskpart/`chkdsk` calls have hard timeouts and a cancel watchdog.

## Requirements

- Windows 10 / 11 (x64)
- Administrator rights (requested automatically)

## Getting started

1. Plug in your USB stick or SD card — it is detected automatically.
2. Pick a file system (defaults to the device's current one) and press **Format**.
3. Copy a folder, write an ISO, extract a ZIP, or run a health test.

---

Full change log: see `CHANGELOG` in the repository, or open **Check for Updates**
inside the app.
