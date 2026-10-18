# Lunaci Smart USB & SD Card Utility

A modern USB flash drive and SD card tool for Windows 10/11, built with Python +
CustomTkinter. Format, write, repair and health-check your removable media from a
single dark/light-themed desktop app with a live log console.

**Download:** grab [`LunaciSetup.exe`](../../releases/latest) from the Releases page
(portable `LunaciSmartUSBCardUtility.exe` is included in every release too).

## Features

- **Live device detection** — PowerShell → wmic → psutil fallback chain running in the
  background with plug/unplug events. Shows device name, drive letter, capacity, file
  system, bus type (USB/SD), disk number and read-only state. Boot/system disks are
  always excluded for safety.
- **Health status LED** — write/read test with SHA-256 verification: 🟢 Good,
  🟡 Warning, 🔴 Critical. Measures read/write speed and flags slow or failing cards.
  The test is **optional** (manual, run it whenever you want — never blocks startup).
- **Smart formatting** — the current file system is detected and pre-selected as the
  default. FAT32 / NTFS / exFAT via `diskpart`, with **Quick** and **Full (sector-scan)**
  modes plus an automatic `clean + create partition` fallback when the direct format
  fails. Optional **auto quick-format before writing** (on by default).
- **Volume label defaults to the device's current label** — rename it only if you want.
- **Write Folder to Disk** — copies the selected folder to the device root using a
  built-in fast engine or `robocopy`, with **live percentage and write speed** in the
  status bar and log console. Unchanged files (same size/mtime) are skipped. A
  confirmation prompt is always shown before writing (it removes data when
  auto-format is enabled).
- **Zip Folder to Disk** — packs the selected folder into `<Folder>.zip` on the device
  (ZIP_DEFLATED, level 6).
- **Write ISO** — writes an `.iso` image in raw/DD mode (`\\.\X:` via
  CreateFile/WriteFile/FlushFileBuffers), with volume dismount and disk rescan.
- **Write ZIP** — extracts a `.zip` archive to the device root safely (path-traversal
  protected).
- **Repair Disk** — clears `attributes disk/volume readonly` and runs
  `chkdsk /f /r`; automatically recreates the partition on RAW disks.
- **Turkish / English UI** — switch languages from the header; the choice is remembered.
- **Dark / Light / System themes** — follows the Windows theme automatically.
- **Live log console** — timestamped, colour-coded output (diskpart transcripts,
  copy percentages, errors); Clear and Save buttons.
- **Reports** — every successful operation can be saved as a text report in the
  `reports` folder **next to the program** (not in the target folder), with a
  *Browse Reports* button that opens the folder directly.
- **Admin elevation** — UAC prompt at startup for disk-mutating operations; if you
  decline, the app runs in limited mode (read/copy still work).

## Requirements

- Windows 10 / 11
- Python 3.10+ (only when running from source)
- Administrator rights for format / repair / ISO write (the app asks via UAC)

## Install

Download and run **`LunaciSetup.exe`** from the
[latest release](../../releases/latest) — it installs the app, Start-menu and desktop
shortcuts, and creates the `reports` folder.

## Run from source

```powershell
git clone https://github.com/cengizkemec/lunaci-smart-usb-sd-utility.git
cd lunaci-smart-usb-sd-utility
py -m pip install -r requirements.txt
py main.py
```

## Build the executables

```powershell
py -m pip install pyinstaller pillow
py -m PyInstaller --noconfirm --clean lunaci.spec      # → dist\LunaciSmartUSBCardUtility.exe

# Installer (Inno Setup 6)
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" setup.iss   # → dist\LunaciSetup.exe
```

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Entry point: DPI awareness, UAC elevation, window icon |
| `app.py` | CustomTkinter UI, task engine, language/theme switching |
| `i18n.py` | Turkish / English string tables (`tr("key")`) |
| `disk_manager.py` | Device detection + `diskpart` format/repair services |
| `file_ops.py` | Folder copy, raw ISO write, ZIP pack/extract, reports |
| `health.py` | Write/read health test (SHA-256 verification) |
| `config_manager.py` | Settings, paths, version, resource lookup |
| `utils.py` | Emitter/log records, subprocess helpers, elevation |
| `lunaci.spec` / `setup.iss` | PyInstaller / Inno Setup build scripts |

## Safety notes

- Formatting, ISO writing and repair **erase data** — every destructive action asks for
  confirmation first.
- Backing up a folder with **auto quick-format** enabled first erases the disk, so the
  app asks for confirmation there too.
- **FAT32 and the 32 GB limit:** Windows cannot create FAT32 on a volume larger than
  32 GB. Instead of failing (and falling back to a `clean` that would wipe the disk for
  nothing), the app **stops before touching the disk** and tells you to pick exFAT or
  NTFS.
- Cancel is honoured during copy, ISO write, ZIP operations and health tests.
  Cancelling a partial ISO write can leave the device unbootable (the app warns you).
- Every long-running external tool (`diskpart`, `chkdsk`) runs with a timeout and is
  killed together with its child processes, so a stuck tool can never freeze the app.
- Boot/system drives are never listed and cannot be selected.

## License

MIT — see [LICENSE](LICENSE).

---

Made by **Cengiz Kemeç** · [cengizkemec.com.tr](https://cengizkemec.com.tr/)
