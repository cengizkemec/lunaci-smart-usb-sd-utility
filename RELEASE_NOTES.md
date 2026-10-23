# Lunaci Smart USB & SD Card Utility v1.3.3

**Release date:** 2026-10-23

A readability and safety follow-up to v1.3.2 — unnamed drives are no longer forced to
the "LUNACI" volume label, and both themes were re-audited against WCAG AA contrast.

## Download

| File | Description |
| --- | --- |
| `LunaciSetup.exe` | **Recommended.** Installer (Turkish + English wizard), creates Start Menu and optional desktop shortcut. |
| `LunaciSmartUSBCardUtility.exe` | Portable single-file executable — just run it, no installation needed. |

> Administrator rights are requested automatically (UAC) on startup, because
> `diskpart`, `chkdsk`, ISO mounting and raw ISO writing require elevation.

## What's new in 1.3.3

### Fixed: unnamed drives no longer get a "LUNACI" label

- For a drive without a volume label the label field now starts **empty**, and the
  drive stays unnamed unless you type a label yourself.
- The automatically saved default from older versions (`LUNACI`) is **cleared once**
  on the first launch after updating, so existing users do not silently relabel media.
- The fix covers every place a format can happen: **Format**, **auto quick-format
  before writing**, and **RAW-disk repair**.
- A real label already present on the drive is still shown as the starting value and is
  preserved unless you change it.

### Readability: WCAG AA contrast re-audited in both themes

- Every text/background pair was measured: primary, secondary and danger buttons, their
  hover states, segmented controls, option menus, entries and placeholders, and all
  console log levels.
- Text stays at **≥ 4.5:1**; non-text indicators (checkbox/radio fills, progress bars,
  switches) stay at **≥ 3:1**.
- **Dark theme** keeps the Telegram-inspired look: the brighter accent (`#5288C1`) is
  used for non-text elements, while buttons keep the deeper blue that keeps white text
  readable.
- **Light theme:** the selected segment now uses a light blue tint with dark text.
  Previously dark text sat on the dark accent colour (only 3.1:1) and was hard to read.
- Light-theme `INFO` and `WARN` log colours were darkened for the console background.
- New repeatable check: `python tools/contrast_audit.py` reports every pair and fails on
  a regression.

### Build

- Version bumped to **1.3.3** in the application and in the Inno Setup installer.
- Portable EXE and installer rebuilt from the same sources and smoke-tested.

## Everything from 1.3.2

- **Fixed the update prompt** that could grow taller than the screen and push the
  Install button out of reach. It is now a proper window with a fixed heading, a
  scrollable release-notes area, and always-visible **Download and Install / Later**
  buttons (`Enter` confirms, `Esc` closes).
- The dialog is centred and clamped to the screen.

## Everything from 1.3.1

- **One console instead of two panels** — the live file list and the timestamped log
  share a single console; file rows stay as one block at the bottom while log lines flow
  in above them.
- **A single progress bar** — the duplicate transfer progress bar was removed.
- **Readable buttons in dark mode** — accent colours and white text reach WCAG AA.

## Everything from 1.3.0

- **Live transfer console** — every file is listed with size, status and per-file speed,
  plus a running `done/total` summary.
- **Bootable ISO writing (Rufus-style)** — automatic mode detection, Windows
  `install.wim` splitting to `install.swm` (FAT32/UEFI), `bootsect` for BIOS boot, and a
  raw (DD) mode for Linux/`isohybrid` images.
- **Automatic self-update from GitHub** with release notes and a background download.
- **Completion sound** (toggleable).
- **Readability pass** over the dark and light themes.

## Stability and performance

- Non-blocking device polling with plug/unplug events.
- All long operations run off the UI thread and are safely cancellable.
- Batched console updates keep the interface responsive under heavy output.
- `diskpart` / `chkdsk` calls have hard timeouts and a cancel watchdog.

## Requirements

- Windows 10 / 11 (x64)
- Administrator rights (requested automatically)

## Getting started

1. Plug in your USB stick or SD card — it is detected automatically.
2. Pick a file system (defaults to the device's current one) and press **Format**.
   Leave the label empty to keep the drive unnamed.
3. Copy a folder, write an ISO, extract a ZIP, or run a health test.

---

Full change log: see `CHANGELOG` in the repository, or open **Check for Updates**
inside the app.
