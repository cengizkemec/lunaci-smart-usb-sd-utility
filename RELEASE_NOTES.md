# Lunaci Smart USB & SD Card Utility v1.3.0

**Release date:** 2026-10-19

This release adds the features requested after v1.2.0: a live transfer console that
lists every file as it moves, Rufus-style **bootable ISO** writing, automatic
self-updating from GitHub, a completion sound, and a full readability pass over the
dark and light themes.

## Download

| File | Description |
| --- | --- |
| `LunaciSetup.exe` | **Recommended.** Installer (Turkish + English wizard), creates Start Menu and optional desktop shortcut. |
| `LunaciSmartUSBCardUtility.exe` | Portable single-file executable — just run it, no installation needed. |

> Administrator rights are requested automatically (UAC) on startup, because
> `diskpart`, `chkdsk`, ISO mounting and raw ISO writing require elevation.

## What's new in 1.3.0

### Live transfer console (like an FTP client)

Copying, ZIP extraction and ISO writing now show **every file** as it is transferred,
with per-file size, status and transfer speed:

- The active file is highlighted while it is being written; finished files are ticked.
- Skipped (already present) and failed files are listed too, so you can see exactly
  what made it to the disk.
- A progress bar and a `done/total · size` summary track the whole job.
- The list stays responsive even for tens of thousands of files (the oldest rows are
  recycled automatically).

### Bootable ISO writing (Rufus-style)

The **ISO Write** dialog now asks which mode to use, and defaults to *Automatic*:

- **Automatic** — detects the image type. Windows installation images are written in
  **bootable (ISO)** mode; everything else (Linux/`isohybrid`, etc.) is written
  **raw (DD)**, which already boots.
- **Raw (DD)** — the previous behaviour: the image is written byte-for-byte to the
  disk. Best for Linux/`isohybrid` images.
- **Bootable (ISO)** — mounts the image read-only, copies its contents onto a
  formatted volume, and sets up the boot records:
  - Windows images: `install.wim` over 4 GB is split into `install.swm` files with
    `dism /Split-Image` so the FAT32/UEFI limit does not break the install.
  - `bootsect` is used to write the BIOS boot code; the UEFI files
    (`EFI\BOOT\BOOTX64.EFI`) are copied from the image, so both BIOS and UEFI boot
    from the same stick.

### Automatic self-update from GitHub

Lunaci now checks the GitHub repository for new versions and can update itself:

- On startup (after ~2.5 s) it silently checks the latest release; you can also press
  **Check for Updates** in the header or in the About window at any time.
- When a newer version is available you get the release notes and a prompt to install.
- Download happens in the background with progress in the log; the app then restarts
  itself with the new executable.
- The setting can be turned off in `config.json` (`auto_update_check`).

### Completion sound

A short system sound plays when a task finishes (format, copy, write, repair,
health test). Toggle it with the new **Sound notification** switch, or via
`sound_on_complete` in `config.json`.

### Readability fixes (dark + light)

Both themes were audited for contrast and the hard-to-read elements were corrected:

- **Log console colours** are now theme-aware. Previously the console used dark-theme
  colours in both modes, making text nearly invisible in light mode and washed out in
  dark mode. Every level (INFO/OK/WARN/ERROR/CMD) now has a colour tuned for the
  active theme, and re-colours instantly when you switch themes.
- **Muted/secondary text** was darkened in light mode and lightened in dark mode so it
  is readable on both card and window backgrounds.
- **Danger and cancel buttons** now use a deeper red with white text (the old red
  failed contrast checks).
- **Transfer console** colours follow the theme as well.

## Stability and performance (carried over from 1.2.0)

- Rewritten, non-blocking device polling with plug/unplug events.
- All long operations run off the UI thread and are safely cancellable.
- Batched log updates keep the interface responsive under heavy output.
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
