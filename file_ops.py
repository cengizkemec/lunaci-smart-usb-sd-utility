"""Dosya kopyalama (shutil / robocopy), ISO yazma, ZIP paketleme/açma ve raporlama."""
from __future__ import annotations

import ctypes
import os
import re
import time
import zipfile
from typing import Callable, List, Optional, Tuple

from i18n import tr
from utils import human_bytes, run_diskpart, run_process, run_shell

MB = 1024 * 1024
GB = 1024 * MB
CHUNK = 4 * MB          # buyuk tampon = daha az sistem cagrisi = daha hizli
ProgressCb = Optional[Callable[[float, Optional[str]], None]]
# Canli aktarim bildirimi: (dosya, boyut, durum, MB/s, tamamlanan, toplam, ozet)
FileCb = Optional[Callable[[str, int, str, float, int, int, str], None]]

# Cok dosyali klasorlerde satir basina log basmak arayuzu bogar; esik uzerinde
# ozet satiri uretilir (rapor yine de tum dosyalari tutar).
_FILELOG_LIMIT = 200

# Windows çekirdek API'leri (ham disk yazımı için)
_k32 = ctypes.windll.kernel32
_CreateFileW = _k32.CreateFileW
_CreateFileW.restype = ctypes.c_void_p
_CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint,
                         ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
_WriteFile = _k32.WriteFile
_WriteFile.restype = ctypes.c_bool
_WriteFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint,
                       ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
_FlushFileBuffers = _k32.FlushFileBuffers
_FlushFileBuffers.restype = ctypes.c_bool
_FlushFileBuffers.argtypes = [ctypes.c_void_p]
_CloseHandle = _k32.CloseHandle
_CloseHandle.argtypes = [ctypes.c_void_p]

GENERIC_RW = 0x80000000 | 0x40000000
FILE_SHARE_RW = 0x00000003
OPEN_EXISTING = 3


# ------------------------------------------------------------ yardımcılar ---

def _walk_files(src: str) -> Tuple[List[Tuple[str, Optional[os.stat_result]]], int]:
    files: List[Tuple[str, Optional[os.stat_result]]] = []
    total = 0
    for root, _dirs, names in os.walk(src):
        for name in names:
            path = os.path.join(root, name)
            try:
                st = os.stat(path)
            except OSError:
                st = None
            files.append((path, st))
            if st:
                total += st.st_size
    return files, total


def save_report(text: str, folder: str, name: str) -> str:
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# ------------------------------------------------------------- kopyalama ----

def copy_folder(src: str, letter: str, logger, cancel,
                engine: str = "shutil", progress: ProgressCb = None,
                file_cb: FileCb = None) -> bool:
    """Hedef klasörün içeriğini diskin köküne güvenle aktarır."""
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        logger.error(tr("copy.missing_src", p=src))
        return False
    dst = f"{letter}:\\"
    if not os.path.isdir(dst):
        logger.error(tr("copy.dst_error", d=dst))
        return False
    if engine == "robocopy":
        return _robocopy_copy(src, dst, logger, progress, file_cb)
    return _shutil_copy(src, dst, logger, cancel, progress, file_cb)


def _shutil_copy(src, dst, logger, cancel, progress: ProgressCb,
                 file_cb: FileCb = None) -> bool:
    """Klasör içeriğini diske kopyalar; her dosya için canlı aktarım bildirimi yayar."""
    files, total = _walk_files(src)
    verbose = len(files) <= _FILELOG_LIMIT
    logger.info(tr("copy.start", n=len(files), s=human_bytes(total), d=dst))
    copied = skipped = errors = written = done_bytes = 0
    started = time.time()
    last_pct = -10
    last_emit = 0.0

    def emit(file: str, size: int, state: str, speed: float,
             done: int, count: int) -> None:
        if not file_cb:
            return
        try:
            file_cb(file, size, state, speed, done, count, human_bytes(total))
        except Exception:
            pass

    def emit_progress(force: bool = False) -> None:
        """Yüzde + anlık yazma hızını UI'a iletir (~0.25 sn'de bir)."""
        nonlocal last_emit
        if not progress:
            return
        now = time.time()
        if not force and now - last_emit < 0.25:
            return
        last_emit = now
        pct = int(done_bytes * 100 / total) if total else 100
        speed = (done_bytes / max(now - started, 1e-6)) / MB  # MB/s
        progress(float(pct), tr("copy.progress_speed", p=pct, sp=f"{speed:.1f}"))

    count = len(files)
    for path, st in files:
        if cancel.is_set():
            logger.warn(tr("copy.cancelled"))
            return False
        rel = os.path.relpath(path, src)
        target = os.path.join(dst, rel)
        size = st.st_size if st else 0
        try:
            if st and os.path.exists(target):
                tst = os.stat(target)
                if tst.st_size == st.st_size and abs(tst.st_mtime - st.st_mtime) < 2:
                    skipped += 1
                    done_bytes += st.st_size
                    emit(rel, size, "skip", 0.0, copied + skipped, count)
                    continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            emit(rel, size, "active", 0.0, copied + skipped + 1, count)
            f_start = time.time()
            f_done = 0
            with open(path, "rb") as fi, open(target, "wb") as fo:
                while True:
                    if cancel.is_set():
                        fo.close()
                        try:
                            os.remove(target)
                        except OSError:
                            pass
                        emit(rel, size, "cancel", 0.0, copied + skipped, count)
                        logger.warn(tr("copy.partial_removed"))
                        return False
                    block = fi.read(CHUNK)
                    if not block:
                        break
                    fo.write(block)
                    written += len(block)
                    done_bytes += len(block)
                    f_done += len(block)
                    emit_progress()
            if st:
                try:
                    os.utime(target, (st.st_atime, st.st_mtime))
                except OSError:
                    pass
            copied += 1
            f_elapsed = max(time.time() - f_start, 1e-6)
            speed = (f_done / f_elapsed) / MB
            emit(rel, size, "done", speed, copied + skipped, count)
            if verbose:
                logger.info(f"  {rel}  ({human_bytes(size)})")
        except OSError as exc:
            errors += 1
            emit(rel, size, "error", 0.0, copied + skipped + errors, count)
            logger.error(tr("copy.file_error", rel=rel, e=exc))
        # done_bytes artışı chunk döngüsünde yapıldı; burada tekrarlanmıyor.
        pct = int(done_bytes * 100 / total) if total else 100
        if pct >= last_pct + 5:
            last_pct = (pct // 5) * 5
            emit_progress(force=True)

    elapsed = max(time.time() - started, 1e-6)
    if not verbose:
        logger.info(tr("copy.file_log_skipped", n=len(files)))
    logger.ok(tr("copy.done", c=copied, s=skipped, e=errors,
                 w=human_bytes(written), t=f"{elapsed:.1f}",
                 sp=f"{written / elapsed / MB:.1f}"))
    if progress:
        progress(100.0, tr("copy.progress", p=100))
    return errors == 0


def _robocopy_copy(src, dst, logger, progress: ProgressCb,
                   file_cb: FileCb = None) -> bool:
    cmd = f'robocopy "{src}" "{dst}" /E /COPY:DAT /DCOPY:T /R:1 /W:1 /NP'
    logger.cmd("» " + cmd)
    percent_re = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)%")
    # robocopy satiri:  "           1234\tYol\\dosya.txt"
    file_re = re.compile(r"^\s*(\d[\d,\.]*)\t(.+?)\s*$")
    state = {"pct": -20, "count": 0}

    def on_line(line: str) -> None:
        m = percent_re.match(line)
        if m:
            pct = float(m.group(1))
            if pct - state["pct"] >= 10:
                state["pct"] = (int(pct) // 10) * 10
                if progress:
                    progress(pct, f"Robocopy %{pct:.0f}")
            return
        text = line.strip()
        if not text:
            return
        fm = file_re.match(line)
        if fm:
            try:
                size = int(fm.group(1).replace(",", "").replace(".", ""))
            except ValueError:
                size = 0
            if file_cb:
                state["count"] += 1
                try:
                    file_cb(fm.group(2).strip(), size, "done", 0.0,
                            state["count"], state["count"], "")
                except Exception:
                    pass
        low = text.upper()
        if low.startswith("ERROR") or " ERROR " in low:
            logger.error("  " + text)
        else:
            logger.cmd("  " + text)

    code, _lines = run_process(cmd, on_line=on_line)
    if 0 <= code < 8:
        logger.ok(tr("robocopy.done", c=code))
        if progress:
            progress(100.0, tr("copy.progress", p=100))
        return True
    logger.error(tr("robocopy.fail", c=code))
    return False


# ------------------------------------------------------------- ISO yazma ----

def write_iso_raw(iso_path: str, letter: str, logger, cancel,
                  progress: ProgressCb = None) -> bool:
    """Seçili .iso dosyasını diske ham (DD) modda yazar. Yönetici yetkisi gerekir."""
    iso_path = os.path.abspath(iso_path)
    if not os.path.isfile(iso_path) or not iso_path.lower().endswith(".iso"):
        logger.error(tr("iso.invalid", p=iso_path))
        return False
    size = os.path.getsize(iso_path)
    dev_path = rf"\\.\{letter}:"
    logger.info(tr("iso.start", name=os.path.basename(iso_path),
                   size=human_bytes(size), l=letter))
    logger.warn(tr("iso.warn"))

    code, _ = run_shell(f"fsutil volume dismount {letter}: /y", timeout=20)
    if code != 0:
        logger.warn(tr("iso.dismount_warn"))

    handle = _CreateFileW(dev_path, GENERIC_RW, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
    if not handle:
        logger.error(tr("iso.open_err", e=ctypes.WinError()))
        return False

    written = 0
    started = time.time()
    ok = True
    last_emit = 0.0
    try:
        with open(iso_path, "rb") as img:
            while True:
                if cancel.is_set():
                    logger.error(tr("iso.cancel", w=human_bytes(written)))
                    ok = False
                    break
                block = img.read(CHUNK)
                if not block:
                    break
                done = ctypes.c_uint32(0)
                if not _WriteFile(handle, block, len(block), ctypes.byref(done), None):
                    logger.error(tr("iso.write_err", e=ctypes.WinError()))
                    ok = False
                    break
                written += done.value
                if progress:
                    now = time.time()
                    if now - last_emit >= 0.25:
                        last_emit = now
                        pct = written * 100.0 / size
                        sp = (written / max(now - started, 1e-6)) / MB
                        progress(pct, tr("copy.progress_speed", p=f"{pct:.0f}",
                                         sp=f"{sp:.1f}"))
        if ok:
            if not _FlushFileBuffers(handle):
                logger.warn(f"Önbellek boşaltılamadı: {ctypes.WinError()}")
            elapsed = max(time.time() - started, 1e-6)
            logger.ok(tr("iso.done", w=human_bytes(written), s=human_bytes(size),
                         t=f"{elapsed:.1f}",
                         sp=f"{written / elapsed / MB:.1f}"))
    finally:
        _CloseHandle(handle)

    run_diskpart(["rescan"], on_line=logger.cmd, timeout=60)
    logger.info(tr("iso.rescan"))
    if ok and progress:
        elapsed = max(time.time() - started, 1e-6)
        progress(100.0, tr("copy.progress_speed", p=100,
                           sp=f"{written / elapsed / MB:.1f}"))
    return ok


# ------------------------------------------- önyüklenebilir ISO yazma -------

# ISO9660 birincil birim tanimlayicisi (PVD) — "CD001" imzasi.
_ISO_PVD_OFFSET = 16 * 2048
_MOUNT_WAIT = 25.0


def _iso_kind(iso_path: str) -> str:
    """ISO'nun turunu belirler: 'windows' | 'other' | 'unknown'.

    ISO9660 PVD'sindeki "CD001" imzasi okunur; imaj icinde
    ``sources/install.wim`` veya ``sources/install.esd`` aranirsa Windows
    kurulum medyasi sayilir. Aranacak dosya adlari yalnizca ASCII oldugundan
    ham bayt arama guvenlidir.
    """
    try:
        with open(iso_path, "rb") as f:
            f.seek(_ISO_PVD_OFFSET)
            if f.read(5) != b"CD001":
                return "unknown"
            f.seek(0)
            head = f.read(8 * MB)
            if (b"INSTALL.WIM" in head.upper() or b"INSTALL.ESD" in head.upper()
                    or b"SOURCES/BOOT.WIM" in head.upper()):
                return "windows"
            f.seek(max(0, os.path.getsize(iso_path) // 2))
            mid = f.read(8 * MB).upper()
            if b"INSTALL.WIM" in mid or b"INSTALL.ESD" in mid:
                return "windows"
            return "other"
    except OSError:
        return "unknown"


def _mount_iso(iso_path: str) -> str:
    """ISO'yu bir surucu harfine baglar ve harfi dondurur ('' = basarisiz).

    ``Mount-DiskImage`` + ``Get-Volume`` kullanilir (Win8+ yerel destek).
    """
    ps = (
        "$ErrorActionPreference='Stop';"
        f"$img = Mount-DiskImage -ImagePath '{iso_path}' -PassThru;"
        "$v = $img | Get-Volume;"
        "if ($v.DriveLetter) { $v.DriveLetter } else { 'X' }"
    )
    rc, lines = run_powershell(ps, timeout=45)
    text = "".join(lines).strip()
    for token in reversed(text.split()):
        token = token.strip().strip(":")
        if len(token) == 1 and token.isalpha():
            return token.upper()
    return ""


def _unmount_iso(iso_path: str) -> None:
    try:
        run_powershell(
            f"Dismount-DiskImage -ImagePath '{iso_path}' "
            "$ErrorActionPreference='SilentlyContinue'", timeout=30)
    except Exception:
        pass


def _wait_volume_ready(letter: str, logger, timeout: float = 20.0) -> bool:
    root = f"{letter}:\\"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if os.path.isdir(root):
                os.listdir(root)
                return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def _copy_iso_tree(src: str, letter: str, logger, cancel, progress: ProgressCb,
                   file_cb: FileCb) -> tuple:
    """ISO içeriğini diske kopyalar. (ok, install_wim_var_mi, toplam_bayt) döner."""
    files, total = _walk_files(src)
    total = total or 1
    dst = f"{letter}:\\"
    logger.info(tr("iso.copy_start", n=len(files), s=human_bytes(total), l=letter))
    copied = errors = done_bytes = 0
    started = time.time()
    last_emit = 0.0
    wim_present = False
    count = len(files)

    for path, st in files:
        if cancel.is_set():
            return False, False, copied, done_bytes
        rel = os.path.relpath(path, src)
        low = rel.replace("/", "\\").lower()
        if low in ("sources\\install.wim", "sources\\install.esd"):
            wim_present = True
            if st and st.st_size > (4 * GB - (64 * MB)):
                # FAT32 tek dosya siniri: .wim bolunmezse kopyalanamaz.
                logger.warn(tr("iso.skip_wim"))
                done_bytes += st.st_size
                continue
        target = os.path.join(dst, rel)
        size = st.st_size if st else 0
        if file_cb:
            try:
                file_cb(rel, size, "active", 0.0, copied + 1, count,
                        human_bytes(total))
            except Exception:
                pass
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            f_start = time.time()
            f_done = 0
            with open(path, "rb") as fi, open(target, "wb") as fo:
                while True:
                    if cancel.is_set():
                        fo.close()
                        try:
                            os.remove(target)
                        except OSError:
                            pass
                        return False, wim_present, copied, done_bytes
                    block = fi.read(CHUNK)
                    if not block:
                        break
                    fo.write(block)
                    done_bytes += len(block)
                    f_done += len(block)
                    if progress:
                        now = time.time()
                        if now - last_emit >= 0.25:
                            last_emit = now
                            pct = done_bytes * 100.0 / total
                            sp = (done_bytes / max(now - started, 1e-6)) / MB
                            progress(min(pct, 99.0),
                                     tr("copy.progress_speed", p=f"{pct:.0f}",
                                        sp=f"{sp:.1f}"))
            if st:
                try:
                    os.utime(target, (st.st_atime, st.st_mtime))
                except OSError:
                    pass
            copied += 1
            f_elapsed = max(time.time() - f_start, 1e-6)
            if file_cb:
                try:
                    file_cb(rel, size, "done", (f_done / f_elapsed) / MB,
                            copied, count, human_bytes(total))
                except Exception:
                    pass
        except OSError as exc:
            errors += 1
            if file_cb:
                try:
                    file_cb(rel, size, "error", 0.0, copied + errors, count, "")
                except Exception:
                    pass
            logger.error(tr("copy.file_error", rel=rel, e=exc))
    return errors == 0, wim_present, copied, done_bytes


def _split_wim(src_letter: str, dst_letter: str, logger, cancel) -> bool:
    """FAT32 için install.wim dosyasini ISO kaynagindan install.swm olarak böler.

    Kaynak: bagli ISO'nun ``sources\\install.wim`` dosyasi (4 GB ustunde
    oldugu icin hedefe kopyalanmamisti). Hedef: diskin ``sources\\`` klasoru.
    """
    wim = f"{src_letter}:\\sources\\install.wim"
    swm = f"{dst_letter}:\\sources\\install.swm"
    if not os.path.isfile(wim):
        return False
    logger.info(tr("iso.split_start", swm=human_bytes(3800 * MB)))
    code, lines = run_process(
        ["dism", "/English", "/Split-Image", f"/ImageFile:{wim}",
         f"/SWMFile:{swm}", "/FileSize:3800"],
        on_line=logger.cmd, timeout=6 * 3600, cancel=cancel)
    if code == 0 and os.path.isfile(swm):
        logger.ok(tr("iso.split_done"))
        return True
    logger.warn(tr("iso.split_fail", e="dism " + str(code)))
    return False


def _write_boot_code(letter: str, logger, cancel, is_fat32: bool = False) -> bool:
    """BIOS + UEFI önyükleme kaydını yazar (Rufus'un DD-dışı yöntemi).

    ``bootsect`` yalnızca Windows kurulum medyasinda anlamlidir; bulunamazsa
    veya basarisiz olursa UEFI dosyalari zaten kopyalandigi icin yazim yine de
    onyuklenebilir kalir (sadece eski BIOS donaniminda sorun cikabilir).
    """
    logger.info(tr("iso.boot_start"))
    ok_any = False
    targets = [
        (["bootsect", "/nt60", f"{letter}:", "/mbr", "/force"], "MBR"),
        (["bootsect", "/nt60", f"{letter}:", "/force"], "PBR"),
    ]
    for cmd, what in targets:
        try:
            code, _ = run_process(cmd, on_line=logger.cmd, timeout=120,
                                  cancel=cancel)
            if code == 0:
                ok_any = True
            else:
                logger.debug(f"bootsect {what} çıkış kodu: {code}")
        except FileNotFoundError:
            logger.debug("bootsect bulunamadi")
        except Exception as exc:
            logger.debug(f"bootsect {what} hatasi: {exc}")
    # UEFI: \EFI\BOOT\BOOTX64.EFI ISO içinden kopyalandi; ek dosya gerekmez.
    if ok_any:
        logger.ok(tr("iso.boot_ok"))
    else:
        logger.warn(tr("iso.boot_skip"))
    return ok_any


def write_iso_bootable(iso_path: str, letter: str, logger, cancel,
                       progress: ProgressCb = None, file_cb: FileCb = None) -> bool:
    """ISO içeriğini diske kopyalayarak önyüklenebilir (FAT32/NTFS) medya yazar.

    Windows kurulum imajları FAT32'yi zorunlu kılar (UEFI). install.wim 4 GB
    üzerindeyse ``dism /Split-Image`` ile bölünür; ardından önyükleme kaydı
    yazılır. Bu yol imajı birebir kopyalamaz (ham DD'den farkı budur) ama
    BIOS + UEFI önyükleme destekli medya üretir.
    """
    iso_path = os.path.abspath(iso_path)
    if not os.path.isfile(iso_path):
        logger.error(tr("iso.invalid", p=iso_path))
        return False

    # Bootable (ISO) modda dosyalarin kopyalanabilmesi icin hedefin bir
    # dosya sistemi olmali. "Yazmadan once bicimlendir" kapaliyken RAW disk
    # uzerine kopyalamak anlamsizdir; burada net bir mesaj verilir.
    root = f"{letter}:\\"
    try:
        if not os.path.isdir(root):
            os.listdir(root)
    except OSError:
        logger.error(tr("iso.fs_required"))
        return False

    drive = _mount_iso(iso_path)
    if not drive:
        logger.error(tr("iso.mount_fail", e="Mount-DiskImage"))
        return False
    if not _wait_volume_ready(drive, logger):
        logger.error(tr("iso.mount_fail", e=drive))
        _unmount_iso(iso_path)
        return False
    logger.ok(tr("iso.mount_ok", l=drive, name=os.path.basename(iso_path)))
    logger.info(tr("iso.iso_selected"))

    ok = False
    started = time.time()
    try:
        ok, wim_present, copied, written = _copy_iso_tree(
            drive, letter, logger, cancel, progress, file_cb)
        if not ok or cancel.is_set():
            return ok
        # FAT32'de 4 GB üzeri install.wim kopyalanamadiysa bol (kaynak ISO'dan).
        if wim_present:
            try:
                need_split = not os.path.isfile(f"{letter}:\\sources\\install.wim")
            except OSError:
                need_split = False
            if need_split:
                _split_wim(drive, letter, logger, cancel)
        _write_boot_code(letter, logger, cancel)
        elapsed = max(time.time() - started, 1e-6)
        logger.ok(tr("iso.iso_done", n=copied, s=human_bytes(written),
                     t=f"{elapsed:.1f}"))
        return True
    finally:
        _unmount_iso(iso_path)
        logger.info(tr("iso.umount"))
        if progress:
            progress(100.0, tr("copy.progress", p=100))


def write_image(iso_path: str, letter: str, logger, cancel,
                mode: str = "auto", progress: ProgressCb = None,
                file_cb: FileCb = None) -> bool:
    """ISO yazimini moda gore yonlendirir: auto | raw | iso (onyuklenebilir)."""
    if mode == "raw":
        logger.info(tr("iso.raw_selected"))
        return write_iso_raw(iso_path, letter, logger, cancel, progress)
    if mode == "iso":
        logger.info(tr("iso.iso_selected"))
        return write_iso_bootable(iso_path, letter, logger, cancel, progress, file_cb)
    # auto: Windows kurulum imaji ise onyuklenebilir, degilse ham
    kind = _iso_kind(iso_path)
    if kind == "windows":
        logger.info(tr("iso.kind.windows"))
        ok = write_iso_bootable(iso_path, letter, logger, cancel, progress, file_cb)
        if not ok and not cancel.is_set():
            logger.warn(tr("iso.not_bootable"))
            return write_iso_raw(iso_path, letter, logger, cancel, progress)
        return ok
    logger.info(tr("iso.kind.other"))
    return write_iso_raw(iso_path, letter, logger, cancel, progress)


# ---------------------------------------------------------- ZIP işlemleri ---

def zip_folder_to_device(src: str, letter: str, logger, cancel,
                         progress: ProgressCb = None) -> bool:
    """Seçili klasörü diskin köküne <KlasorAdi>.zip olarak paketler."""
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        logger.error(tr("copy.missing_src", p=src))
        return False
    name = os.path.basename(src.rstrip("\\/")) or "klasor"
    out = os.path.join(f"{letter}:", f"{name}.zip")
    files, total = _walk_files(src)
    verbose = len(files) <= _FILELOG_LIMIT
    logger.info(tr("zip.folder_start", n=len(files), s=human_bytes(total), d=out))
    started = time.time()
    packed = errors = done = 0
    last_pct = -10
    cancelled = False

    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for path, st in files:
                if cancel.is_set():
                    cancelled = True
                    logger.warn(tr("zip.folder_cancelled"))
                    break
                rel = os.path.relpath(path, src)
                try:
                    zf.write(path, rel.replace("\\", "/"))
                    packed += 1
                    if verbose:
                        logger.info(f"  + {rel}  ({human_bytes(st.st_size if st else 0)})")
                except Exception as exc:
                    errors += 1
                    logger.error(tr("zip.folder_error", rel=rel, e=exc))
                done += st.st_size if st else 0
                pct = int(done * 100 / total) if total else 100
                if pct >= last_pct + 10:
                    last_pct = (pct // 10) * 10
                    if progress:
                        progress(float(pct), tr("zip.progress", p=pct))
    except Exception as exc:
        logger.error(tr("zip.folder_error_top", e=exc))
        try:
            os.remove(out)
        except OSError:
            pass
        return False

    if cancelled:
        try:
            os.remove(out)
            logger.info(tr("zip.folder_removed"))
        except OSError:
            pass
        return False

    out_size = os.path.getsize(out)
    elapsed = max(time.time() - started, 1e-6)
    ratio = (100.0 * (1 - out_size / total)) if total else 0.0
    if not verbose:
        logger.info(tr("copy.file_log_skipped", n=len(files)))
    logger.ok(tr("zip.folder_done", d=out, s=human_bytes(out_size), r=f"{ratio:.0f}",
                 n=packed, e=errors, t=f"{elapsed:.1f}"))
    if progress:
        progress(100.0, tr("zip.progress", p=100))
    return errors == 0


def write_zip_to_device(zip_path: str, letter: str, logger, cancel,
                        progress: ProgressCb = None, file_cb: FileCb = None) -> bool:
    """Bir .zip arşivinin içeriğini diskin köküne güvenle açar (yazdırır)."""
    zip_path = os.path.abspath(zip_path)
    if not os.path.isfile(zip_path) or not zipfile.is_zipfile(zip_path):
        logger.error(tr("zip.invalid", p=zip_path))
        return False
    dst_root = os.path.abspath(f"{letter}:\\")
    logger.info(tr("zip.extract_start", name=os.path.basename(zip_path), d=dst_root))
    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir()]
            verbose = len(infos) <= _FILELOG_LIMIT
            total = sum(i.file_size for i in infos) or 1
            logger.info(tr("zip.extract_count", n=len(infos), s=human_bytes(total)))
            written = errors = 0
            started = time.time()
            last_pct = -10
            total_n = len(infos)

            def emit(name: str, size: int, state: str, speed: float, idx: int) -> None:
                if not file_cb:
                    return
                try:
                    file_cb(name, size, state, speed, idx, total_n,
                            human_bytes(total))
                except Exception:
                    pass

            for info in infos:
                if cancel.is_set():
                    logger.warn(tr("zip.extract_cancelled"))
                    return False
                target = os.path.normpath(os.path.join(dst_root, info.filename))
                low, root_low = target.lower(), dst_root.lower()
                if not (low == root_low or low.startswith(root_low + os.sep)):
                    logger.error(tr("zip.traversal", name=info.filename))
                    errors += 1
                    emit(info.filename, info.file_size, "error", 0.0,
                         written * 0 + 1)
                    continue
                emit(info.filename, info.file_size, "active", 0.0, 1)
                try:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    f_start = time.time()
                    f_done = 0
                    with zf.open(info) as srcf, open(target, "wb") as outf:
                        while True:
                            block = srcf.read(CHUNK)
                            if not block:
                                break
                            outf.write(block)
                            written += len(block)
                            f_done += len(block)
                    f_elapsed = max(time.time() - f_start, 1e-6)
                    emit(info.filename, info.file_size, "done",
                         (f_done / f_elapsed) / MB, 1)
                    if verbose:
                        logger.info(f"  {info.filename}  ({human_bytes(info.file_size)})")
                except Exception as exc:
                    errors += 1
                    emit(info.filename, info.file_size, "error", 0.0, 1)
                    logger.error(tr("zip.extract_error", name=info.filename, e=exc))
                pct = int(written * 100 / total)
                if pct >= last_pct + 10:
                    last_pct = (pct // 10) * 10
                    if progress:
                        progress(float(pct), tr("zip.extract_progress", p=pct))
            elapsed = max(time.time() - started, 1e-6)
    except Exception as exc:
        logger.error(tr("zip.read_error", e=exc))
        return False

    if not verbose:
        logger.info(tr("copy.file_log_skipped", n=len(infos)))
    if errors:
        logger.warn(tr("zip.extract_warn", e=errors))
    else:
        logger.ok(tr("zip.extract_done", n=len(infos), s=human_bytes(written),
                     t=f"{elapsed:.1f}"))
    if progress:
        progress(100.0, tr("zip.extract_progress", p=100))
    return errors == 0
