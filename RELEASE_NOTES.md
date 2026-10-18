# Lunaci Smart USB & SD Card Utility v1.2.0

**Release date:** 2026-10-18

This release is a major stability and performance update. The whole application was
re-audited end-to-end: the freezing/hanging problems are fixed, device detection is now
near-instantaneous, the interface has been redesigned with a modern Telegram-inspired
theme, and every long-running operation can be cancelled safely.

## Download

| File | Description |
| --- | --- |
| `LunaciSetup.exe` | **Recommended.** Installer (Turkish + English wizard), creates Start Menu and optional desktop shortcut. |
| `LunaciSmartUSBCardUtility.exe` | Portable single-file executable — just run it, no installation needed. |

> Administrator rights are requested automatically (UAC) on startup, because
> `diskpart`, `chkdsk` and raw ISO writing require elevation.

## What's new in 1.2.0

### Stop-the-freeze fixes

The app could previously hang and stop responding. The root causes were found and fixed:

- **Rewritten device polling loop.** A single unexpected event or malformed message can no
  longer kill the refresh timer — the UI keeps updating in every case, and errors are
  written to `error.log` instead of silently freezing the window.
- **Device monitor can no longer die.** The background monitor is fully guarded: even if the
  underlying detection fails, it recovers on the next tick and continues reporting.
- **No more per-line log flood.** Log output is now batched (one widget update per level
  run, one scroll at the end), which removes the biggest UI bottleneck during heavy
  operations (thousands of files no longer freeze the log console).
- **`diskpart` and `chkdsk` now have real timeouts** (10 minutes for quick operations,
  12 hours for full sector-scan) and are killed **together with their child processes**,
  so a stuck external tool can never lock up the application.
- **Settings are written in the background.** `config.json` saves no longer block the
  interface (previously a synchronous write on the main thread, which is especially slow
  when the app lives inside a OneDrive-synced folder). The final write is flushed on exit.
- **Folder existence check is now asynchronous.** Checking the selected source folder no
  longer performs a blocking filesystem/drive call on the UI thread.
- **Cancel is honoured everywhere.** Copy, ISO write, ZIP write/extract and the health test
  all stop within a couple of seconds, and processes are terminated cleanly.

### Performance

- **Instant device detection.** Drive letters are read with a direct Windows API call
  (bitmask) on every tick; the full PowerShell/wmic scan only runs when the set of drives
  actually changes. Idle CPU usage is dramatically lower than in v1.1.0.
- **4 MB transfer buffers** for folder copy and ISO writing, with speed reported in MB/s.
- **Option menus are only rebuilt when their content changes**, instead of every 3 seconds.
- **Reports are written asynchronously**, so generating a report never blocks the UI.

### New Telegram-inspired theme

- Brand-new dark and light colour schemes inspired by Telegram Desktop:
  - **Dark:** deep blue-grey background (`#17212B`), soft cards (`#242F3D`) and the classic
    Telegram blue accent (`#5288C1` / `#6AB3F2` hover).
  - **Light:** clean white/grey cards with the same blue accent.
- Consistent rounded cards, segmented buttons, switches and progress bars.
- "System" mode follows the Windows light/dark setting automatically.
- The theme is a standard CustomTkinter theme file (`assets/theme_lunaci.json`).

### Safety improvements

- **FAT32 > 32 GB is blocked before touching the disk.** Windows cannot create FAT32 on a
  volume larger than 32 GB. Previously the app would fail and then fall back to a
  `clean`, which erased the disk for nothing. Now it refuses up front and tells you to
  choose exFAT or NTFS — your data is left untouched.
- **Confirmation prompt before writing a folder to disk** when auto-format is enabled,
  because that path erases the device first.
- Read-only state can still be cleared automatically during repair.
- Boot/system drives are always excluded and can never be selected.

### Diagnostics

- New `error.log` is written next to the program whenever an unexpected error occurs,
  which makes bug reports much easier.
- `LUNACI_SMOKE_TEST=<seconds>` environment variable runs a short self-check GUI session
  without requesting elevation (useful for troubleshooting; no effect in normal use).

## Verification

This release was validated with an automated 38-check self-test suite covering compilation,
translation completeness, theme integrity, asynchronous settings persistence, the FAT32
guard, process cancellation, a real 1200-file copy + ZIP round-trip on a virtual drive,
monitor resilience and a live GUI session. Additionally, the packaged executable was
launched and smoke-tested to confirm it starts cleanly with no errors.

## Requirements

- Windows 10 or Windows 11 (64-bit)
- Administrator rights for formatting, repairing and ISO writing

## Links

- Website: https://cengizkemec.com.tr/
- Repository: https://github.com/cengizkemec/lunaci-smart-usb-sd-utility
- Made by **Cengiz Kemeç**

---

## Türkçe (özet)

Bu sürüm büyük bir kararlılık ve performans güncellemesidir. Uygulamanın donma/kilitlenme
sorunları giderildi, cihaz algılama neredeyse anlık hâle getirildi, arayüz Telegram
esintili modern bir temayla yeniden tasarlandı ve tüm uzun süren işlemler güvenle iptal
edilebilir hâle geldi.

- Donma nedenleri giderildi: yeniden yazılan cihaz izleme döngüsü, toplu günlük yazımı,
  `diskpart`/`chkdsk` için zaman aşımı + alt süreç sonlandırma, arka planda ayar kaydetme,
  arka planda klasör kontrolü.
- Performans: anlık sürücü algılama (Windows API bitmask), 4 MB aktarım tamponu, MB/s hız.
- Yeni Telegram esintili koyu/açık tema.
- Güvenlik: 32 GB üzeri FAT32 artık diske dokunmadan engellenir.
- Klasöre yazma işlemi için onay penceresi eklendi.
