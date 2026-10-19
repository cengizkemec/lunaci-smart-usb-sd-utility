# Lunaci Smart USB & SD Card Utility v1.3.1

**Release date:** 2026-10-19

This is a UI cleanup release. The live transfer list and the log console were split
across two panels and the screen showed two progress bars, which looked cluttered and
hard to follow. They are now merged into a **single console**, there is **one** progress
bar, and the dark-theme buttons are readable again.

## Download

| File | Description |
| --- | --- |
| `LunaciSetup.exe` | **Recommended.** Installer (Turkish + English wizard), creates Start Menu and optional desktop shortcut. |
| `LunaciSmartUSBCardUtility.exe` | Portable single-file executable — just run it, no installation needed. |

> Administrator rights are requested automatically (UAC) on startup, because
> `diskpart`, `chkdsk`, ISO mounting and raw ISO writing require elevation.

## What's new in 1.3.1

### One console instead of two panels

The separate **Live Transfer** panel and the **Log** panel are gone. Everything now
happens in a single console:

- Time-stamped log records and the live file list share one area — no more glancing
  between two boxes.
- File rows always form one tidy block at the **bottom**; new log lines flow in **above**
  them, so the two kinds of information never interleave and the list never looks
  scrambled.
- A file's row is updated **in place** as it moves (active → done / skipped / failed /
  cancelled), so the list stays compact instead of growing one line per event.
- The console fills all remaining window height and is horizontally scrollable, with a
  narrower, cleaner layout overall.

### A single progress bar

The duplicate file-transfer progress bar was removed. The status bar now shows **one**
progress bar for the whole job, alongside the `done/total · size` summary. (The bar in
the device card is the device **occupancy** indicator, a different thing.)

### Readable buttons in dark mode

Button text was rendering near-black on the accent colour, which was hard to read:

- The accent colour was deepened (`#5288C1` → `#3B6FA8` dark / `#3F76B0` light) so
  white text reaches **≥ 4.5:1** contrast (WCAG AA) in both themes.
- All accent buttons (Health, Browse, Copy, Quick Format, ISO Write, the ISO dialog's
  write button, and the device dropdown) now use white text explicitly.
- The red **Cancel** button in the ISO dialog no longer inherits dark text on dark red.
- The selected segment of the file-system / mode pickers matches the new accent colour.

## Everything from 1.3.0

This release builds on v1.3.0, which added:

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
