"""Cihaz algılama (PowerShell / wmic / psutil) ve diskpart tabanlı işlem servisleri."""
from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass, replace
from typing import Callable, List, Optional, Sequence

from i18n import tr
from utils import (Emitter, human_bytes, run_diskpart, run_process,
                   run_powershell, run_shell)

GB = 1024 ** 3

FS_OPTIONS = ("FAT32", "NTFS", "exFAT", "EXT4 (Linux)")

_ERR_KEYWORDS = ("error", "hata", "failed", "failure", "fehl", "cannot",
                 "unable", "redded", "basarisiz", "başarısız", "erisim redd")

_PS_DETECT = r"""
$ErrorActionPreference='SilentlyContinue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}
$list = @()
foreach ($ld in (Get-CimInstance -ClassName Win32_LogicalDisk)) {
  if (-not $ld.DeviceID) { continue }
  $L = ([string]$ld.DeviceID).TrimEnd('\').TrimEnd(':').ToUpper()
  if (-not $L) { continue }
  $part = Get-Partition -DriveLetter $L -ErrorAction SilentlyContinue
  $num = $null; $model=''; $bus=''; $boot=$false; $sys=$false; $health=''; $ro=$false
  if ($part) {
    $num = [int]$part.DiskNumber
    $d = Get-Disk -Number $num -ErrorAction SilentlyContinue
    if ($d) {
      $model = [string]$d.FriendlyName
      $bus = [string]$d.BusType
      $boot = [bool]$d.IsBoot
      $sys = [bool]$d.IsSystem
      $health = [string]$d.HealthStatus
      $ro = [bool]$d.IsReadOnly
    }
  }
  $size = 0; $free = 0
  try { $size = [int64]$ld.Size } catch {}
  try { $free = [int64]$ld.FreeSpace } catch {}
  $list += [pscustomobject]@{
    Letter=$L; DriveType=[int]$ld.DriveType; FileSystem=[string]$ld.FileSystem
    Label=[string]$ld.VolumeName; Size=$size; Free=$free; DiskNumber=$num
    Model=$model; Bus=$bus; IsBoot=$boot; IsSystem=$sys; Health=$health; ReadOnly=$ro
  }
}
if ($list.Count -eq 0) { '[]' } else { ConvertTo-Json -InputObject $list -Compress -Depth 3 }
"""


# ------------------------------------------------------------ veri modeli --

@dataclass
class Device:
    letter: str
    label: str = ""
    fstype: str = ""
    size: int = 0
    free: int = 0
    drive_type: int = 0
    removable: bool = False
    verified: bool = False          # PowerShell/wmic ile doğrulandı mı?
    disk_number: Optional[int] = None
    model: str = ""
    bus: str = ""
    health: str = ""
    readonly: bool = False
    is_system: bool = False

    @property
    def used(self) -> int:
        return max(self.size - self.free, 0)

    @property
    def used_ratio(self) -> float:
        return (self.used / self.size) if self.size else 0.0

    @property
    def is_raw(self) -> bool:
        return not self.fstype or self.fstype.strip().upper() in ("RAW", "BILINMIYOR")

    @property
    def name(self) -> str:
        return self.model or self.label or tr("dev.unknown")

    @property
    def display(self) -> str:
        return f"{self.letter}: {self.name} ({human_bytes(self.size)})"

    @property
    def fstype_display(self) -> str:
        return self.fstype.strip().upper() if self.fstype else tr("dev.raw")

    def suggested_fs(self) -> str:
        opt = fstype_to_option(self.fstype)
        if opt:
            return opt
        return "FAT32" if self.size <= 32 * GB else "exFAT"


def fstype_to_option(fstype: str) -> Optional[str]:
    up = (fstype or "").strip().upper()
    if up == "FAT32":
        return "FAT32"
    if up == "NTFS":
        return "NTFS"
    if up == "EXFAT":
        return "exFAT"
    if up in ("EXT4", "EXT3", "EXT2"):
        return "EXT4 (Linux)"
    return None


# ------------------------------------------------------------ algılama ------

def _int(value) -> int:
    try:
        return int(str(value).strip() or 0)
    except (TypeError, ValueError):
        return 0


def _system_letters() -> set:
    letters = set()
    for env in ("SystemDrive", "HOMEDRIVE"):
        val = os.environ.get(env, "")
        if val:
            letters.add(val[0].upper())
    return letters


def _drive_type(letter: str) -> int:
    try:
        return int(ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\"))
    except Exception:
        return 0


def fast_drive_letters() -> set:
    """GetLogicalDrives bitmask'i — subprocess'siz, milisaniyelik harf listesi."""
    try:
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return {chr(ord("A") + i) for i in range(26) if mask & (1 << i)}
    except Exception:
        return set()


# diskpart sure asmalari (saniye): hizli bicimlendirme 10 dk, tam tarama 12 saat
DP_TIMEOUT_QUICK = 600.0
DP_TIMEOUT_FULL = 12 * 3600.0


def _has_error(lines: Sequence[str]) -> bool:
    blob = " ".join(lines).lower()
    return any(k in blob for k in _ERR_KEYWORDS)


def _detect_powershell() -> Optional[List[Device]]:
    rc, lines = run_powershell(_PS_DETECT, timeout=30)
    text = "".join(lines).strip()
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        raw = json.loads(text[start:end + 1])
    except Exception:
        return None
    if isinstance(raw, dict):
        raw = [raw]
    sysletters = _system_letters()
    devices: List[Device] = []
    for item in raw:
        letter = str(item.get("Letter") or "").strip().upper()
        if len(letter) != 1:
            continue
        dtype = _int(item.get("DriveType"))
        bus = str(item.get("Bus") or "").strip()
        is_sys = (bool(item.get("IsSystem")) or bool(item.get("IsBoot"))
                  or letter in sysletters)
        if is_sys:
            continue
        removable = dtype == 2 or bus.upper() in ("USB", "SD", "MMC")
        if not removable:
            continue
        num = item.get("DiskNumber")
        devices.append(Device(
            letter=letter,
            label=str(item.get("Label") or "").strip(),
            fstype=str(item.get("FileSystem") or "").strip(),
            size=_int(item.get("Size")),
            free=_int(item.get("Free")),
            drive_type=dtype,
            removable=True,
            verified=True,
            disk_number=_int(num) if num is not None else None,
            model=str(item.get("Model") or "").strip(),
            bus=bus,
            health=str(item.get("Health") or "").strip(),
            readonly=bool(item.get("ReadOnly")),
            is_system=is_sys,
        ))
    devices.sort(key=lambda d: d.letter)
    return devices


def _parse_wmic_list(text: str) -> List[dict]:
    entries: List[dict] = []
    cur: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if cur:
                entries.append(cur)
                cur = {}
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            cur[key.strip()] = value.strip()
    if cur:
        entries.append(cur)
    return entries


def _wmic_partition_map() -> dict:
    try:
        rc, lines = run_process(
            ["wmic", "partition", "get", "DiskIndex,DriveLetter", "/format:csv"],
            timeout=20)
        mapping = {}
        for row in (l for l in (x.strip() for x in lines) if l):
            parts = row.split(",")
            if len(parts) >= 3 and parts[-2].isdigit() and parts[-1]:
                letter = parts[-1].replace(":", "").strip().upper()
                if len(letter) == 1:
                    mapping[letter] = int(parts[-2])
        return mapping
    except Exception:
        return {}


def _detect_wmic() -> Optional[List[Device]]:
    rc, lines = run_process(
        ["wmic", "logicaldisk", "get",
         "DeviceID,DriveType,FileSystem,FreeSpace,Size,VolumeName", "/format:list"],
        timeout=20)
    entries = [e for e in _parse_wmic_list("".join(lines)) if e.get("DeviceID")]
    if not entries:
        return None  # wmic kullanılamıyor olabilir → sonraki strateji
    diskmap = _wmic_partition_map()
    sysletters = _system_letters()
    devices: List[Device] = []
    for e in entries:
        letter = e["DeviceID"].replace("\\", "").replace(":", "").strip().upper()
        if len(letter) != 1:
            continue
        dtype = _int(e.get("DriveType"))
        if dtype != 2 or letter in sysletters:  # wmic yolunda yalnızca takeılabilirler
            continue
        devices.append(Device(
            letter=letter,
            label=e.get("VolumeName", ""),
            fstype=e.get("FileSystem", ""),
            size=_int(e.get("Size")),
            free=_int(e.get("FreeSpace")),
            drive_type=dtype,
            removable=True,
            verified=False,
            disk_number=diskmap.get(letter),
        ))
    devices.sort(key=lambda d: d.letter)
    return devices


def _detect_psutil() -> Optional[List[Device]]:
    try:
        import psutil
    except ImportError:
        return _detect_ctypes_only()
    sysletters = _system_letters()
    devices: List[Device] = []
    for part in psutil.disk_partitions(all=False):
        mp = part.mountpoint or ""
        if len(mp) < 2:
            continue
        letter = mp[0].upper()
        if letter in sysletters or _drive_type(letter) != 2:
            continue
        size = free = 0
        try:
            usage = shutil.disk_usage(mp)
            size, free = usage.total, usage.free
        except Exception:
            pass
        devices.append(Device(letter=letter, fstype=part.fstype or "", size=size,
                              free=free, drive_type=2, removable=True))
    devices.sort(key=lambda d: d.letter)
    return devices


def _detect_ctypes_only() -> Optional[List[Device]]:
    """psutil yoksa yalnızca GetDriveTypeW ile takeılabilir harfleri tarar."""
    sysletters = _system_letters()
    devices: List[Device] = []
    for code in range(ord("C"), ord("Z") + 1):
        letter = chr(code)
        if letter in sysletters or _drive_type(letter) != 2:
            continue
        size = free = 0
        try:
            usage = shutil.disk_usage(f"{letter}:\\")
            size, free = usage.total, usage.free
        except Exception:
            continue
        devices.append(Device(letter=letter, size=size, free=free,
                              drive_type=2, removable=True))
    return devices


def detect_devices(logger: Optional[Emitter] = None) -> List[Device]:
    """Takılı aday cihazları listeler. PowerShell → wmic → psutil sırasıyla denenir."""
    for fn in (_detect_powershell, _detect_wmic, _detect_psutil):
        try:
            result = fn()
        except FileNotFoundError:
            continue
        except Exception as exc:
            if logger:
                logger.debug(f"{fn.__name__} başarısız: {exc}")
            continue
        if result is not None:
            return result
    return []


def fresh_device(letter: str) -> Optional[Device]:
    letter = letter.strip().upper()
    for dev in detect_devices():
        if dev.letter == letter:
            return dev
    return None


def get_disk_number(letter: str) -> Optional[int]:
    letter = letter.strip().upper()
    try:
        rc, lines = run_powershell(
            f"try {{ (Get-Partition -DriveLetter '{letter}' -EA Stop).DiskNumber }} catch {{ 'X' }}",
            timeout=15)
        text = "".join(lines).strip()
        if text.isdigit():
            return int(text)
    except Exception:
        pass
    return _wmic_partition_map().get(letter)


# -------------------------------------------------------- biçimlendirme -----

def run_format(logger: Emitter, letter: str, fs_key: str, label: str,
               quick: bool, size_hint: int = 0,
               cancel: Optional[threading.Event] = None) -> bool:
    """diskpart ile biçimlendirir. Önce volume odaklı, olmazsa clean + bölümleme."""
    letter = letter.strip().upper()
    if fs_key.upper().startswith("EXT4"):
        logger.error(tr("fmt.ext4_err"))
        return False
    fs_part = {"FAT32": "fat32", "NTFS": "ntfs", "exFAT": "exfat"}.get(fs_key)
    if not fs_part:
        logger.error(tr("fmt.bad_fs", fs=fs_key))
        return False
    # Windows, 32 GB uzerinde FAT32 olusturamaz. Eger yine de denerseniz
    # diskpart basarisiz olur ve yedek "clean" yolu diski tamamen SILER →
    # veri kaybi. Bu yuzden HIC BASLATMADAN DURDURUYORUZ.
    if fs_key == "FAT32" and size_hint > 32 * GB:
        logger.error(tr("fmt.fat32_block", s=human_bytes(size_hint)))
        return False
    if cancel is not None and cancel.is_set():
        logger.warn(tr("ui.cancelled"))
        return False
    label = (label or "").replace('"', "").strip()
    fmt = (f"format fs={fs_part} override" + (" quick" if quick else "")
           + (f' label="{label}"' if label else ""))

    mode = tr("dlg.mode.quick") if quick else tr("dlg.mode.full")
    logger.info(tr("fmt.start", mode=mode, l=letter, fs=fs_key))
    timeout = DP_TIMEOUT_QUICK if quick else DP_TIMEOUT_FULL

    script = [f"select volume {letter}", fmt]
    logger.cmd("diskpart » " + " ; ".join(script))
    code, lines = run_diskpart(script, on_line=logger.cmd, timeout=timeout,
                               cancel=cancel)
    if not _has_error(lines) and code == 0:
        if label:
            logger.ok(tr("fmt.ok_l", l=letter, fs=fs_key, ad=label))
        else:
            logger.ok(tr("fmt.ok", l=letter, fs=fs_key))
        return True
    if cancel is not None and cancel.is_set():
        logger.warn(tr("ui.cancelled"))
        return False

    logger.warn(tr("fmt.fallback_warn"))
    dev = fresh_device(letter)
    disk_number = dev.disk_number if dev and dev.disk_number is not None else get_disk_number(letter)
    if disk_number is None:
        logger.error(tr("fmt.disknum_err"))
        return False
    script2 = [f"select disk {disk_number}", "clean", "create partition primary",
               fmt, f"assign letter={letter}"]
    logger.cmd("diskpart » " + " ; ".join(script2))
    code, lines = run_diskpart(script2, on_line=logger.cmd, timeout=timeout,
                               cancel=cancel)
    run_diskpart(["rescan"], on_line=logger.cmd, timeout=60)
    if not _has_error(lines) and code == 0:
        logger.ok(tr("fmt.clean_ok", l=letter, fs=fs_key))
        return True
    logger.error(tr("fmt.fail", c=code))
    return False


# ------------------------------------------------------------- onarım -------

def run_repair(logger: Emitter, letter: str,
               cancel: Optional[threading.Event] = None) -> bool:
    """Yazma korumasını temizler, chkdsk /f /r çalıştırır; RAW ise bölümü yeniler."""
    letter = letter.strip().upper()
    dev = fresh_device(letter)
    if dev is None:
        logger.error(tr("rep.not_found", l=letter))
        return False
    logger.info(tr("rep.start", l=letter, n=dev.name, f=dev.fstype_display))
    if dev.readonly:
        logger.warn(tr("rep.readonly_warn"))

    if dev.disk_number is not None:
        script = [f"select disk {dev.disk_number}",
                  "attributes disk clear readonly",
                  f"select volume {letter}",
                  "attributes volume clear readonly"]
    else:
        script = [f"select volume {letter}", "attributes volume clear readonly"]
    logger.cmd("diskpart » " + " ; ".join(script))
    code, lines = run_diskpart(script, on_line=logger.cmd, timeout=120,
                               cancel=cancel)
    if not _has_error(lines) and code == 0:
        logger.ok(tr("rep.readonly_ok"))
    else:
        logger.warn(tr("rep.readonly_fail"))

    logger.info(tr("rep.chkdsk_start"))
    code, lines = run_shell(f"echo Y| chkdsk {letter}: /f /r",
                            on_line=logger.cmd, timeout=6 * 3600, cancel=cancel)
    if cancel is not None and cancel.is_set():
        logger.warn(tr("ui.cancelled"))
        return False
    if code == 0:
        logger.ok(tr("rep.chkdsk_ok"))
    else:
        logger.warn(tr("rep.chkdsk_warn", c=code))

    dev2 = fresh_device(letter)
    if dev2 is not None and dev2.is_raw:
        fs = dev2.suggested_fs()
        logger.warn(tr("rep.raw_warn"))
        logger.info(tr("rep.raw_fs", fs=fs))
        if not run_format(logger, letter, fs, "", quick=True,
                          size_hint=dev2.size, cancel=cancel):
            return False

    run_diskpart(["rescan"], on_line=logger.cmd, timeout=60)
    logger.ok(tr("rep.done"))
    return True


# ----------------------------------------------------- izleme iş parçacığı --

class DeviceMonitor(threading.Thread):
    """Arka planda cihazları tarar; tak/çıkar olaylarını ve listeyi yayınlar.

    Hizli yol: her turda yalnizca ``GetLogicalDrives`` bitmask'i okunur
    (subprocess yok, ~0 ms). Harf kumasi DEGISMEDIGI surece PowerShell'e
    hiç basvurulmaz; boyut/bos alan bilgisi ucuz ``shutil.disk_usage`` ile
    tazelenir. Boylece arka planda surekli PowerShell prosesi dogmaz ve
    arayuz hep guncel kalir.
    """

    def __init__(self, emit: Callable, interval: float = 3.0) -> None:
        super().__init__(daemon=True, name="lunaci-monitor")
        self.emit = emit
        self.interval = max(1.0, float(interval or 3.0))
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._logger = Emitter(emit, task="monitor")
        self._letters: set = set()
        self._known: set = set()          # en son gorulen TUM harfler
        self._devices: List[Device] = []  # onbellek
        self._force = True                # ilk turda hep tam tarama

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def request_poll(self, force: bool = True) -> None:
        """Bir turu hemen calistir; ``force`` tam PowerShell taramasi zorlar."""
        if force:
            self._force = True
        self._wake.set()

    def _full_detect(self) -> List[Device]:
        try:
            devices = detect_devices(self._logger)
        except Exception as exc:
            self._logger.error(tr("mon.error", e=exc))
            devices = []
        self._devices = devices
        return devices

    @staticmethod
    def _refresh_usage(devices: List[Device]) -> List[Device]:
        """Bilinen cihazlarin boyut/bos alanini subprocess'siz tazeler."""
        out: List[Device] = []
        for dev in devices:
            try:
                u = shutil.disk_usage(f"{dev.letter}:\\")
            except OSError:
                continue  # cikti
            out.append(replace(dev, size=u.total, free=u.free))
        return out

    def run(self) -> None:
        while not self._stop.is_set():
            # Bu dongu ASLA olmemeli: herhangi bir beklenmeyen hata olsa bile
            # bir sonraki turda cihaz algilama devam eder (arayuz donmaz).
            try:
                self._tick()
            except Exception as exc:
                try:
                    self._logger.error(tr("mon.error", e=exc))
                except Exception:
                    pass
            self._wake.wait(self.interval)
            self._wake.clear()

    def _tick(self) -> None:
        letters = fast_drive_letters()
        need_full = (self._force or letters != self._known
                     or not self._devices)
        if need_full:
            devices = self._full_detect()
            # PowerShell hicbir sey bulamadiysa ama surucu harfi varsa
            # sonraki turda tekrar dene (algilama gecici olarak basarisiz olabilir).
            if not devices and letters:
                self._known = set()
            else:
                self._known = letters
            self._force = False
        else:
            devices = self._refresh_usage(self._devices)
            if len(devices) != len(self._devices):
                # bu sirada bir cihaz kaybolmus → tam tarama
                devices = self._full_detect()
                self._known = fast_drive_letters()
            else:
                self._devices = devices

        dev_letters = {d.letter for d in devices}
        for dev in devices:
            if dev.letter not in self._letters:
                self._logger.ok(tr("mon.added", d=dev.display,
                                   f=dev.fstype_display))
        for letter in sorted(self._letters - dev_letters):
            self._logger.warn(tr("mon.removed", l=letter))
        self._letters = dev_letters
        try:
            self.emit(("devices", devices))
        except Exception:
            pass
