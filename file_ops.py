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

CHUNK = 1024 * 1024
ProgressCb = Optional[Callable[[float, Optional[str]], None]]

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
                engine: str = "shutil", progress: ProgressCb = None) -> bool:
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
        return _robocopy_copy(src, dst, logger, progress)
    return _shutil_copy(src, dst, logger, cancel, progress)


def _shutil_copy(src, dst, logger, cancel, progress: ProgressCb) -> bool:
    files, total = _walk_files(src)
    logger.info(tr("copy.start", n=len(files), s=human_bytes(total), d=dst))
    copied = skipped = errors = written = done_bytes = 0
    started = time.time()
    last_pct = -10
    last_emit = 0.0

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
        speed = (done_bytes / max(now - started, 1e-6)) / CHUNK  # MB/s
        progress(float(pct), tr("copy.progress_speed", p=pct, sp=f"{speed:.1f}"))

    for path, st in files:
        if cancel.is_set():
            logger.warn(tr("copy.cancelled"))
            return False
        rel = os.path.relpath(path, src)
        target = os.path.join(dst, rel)
        try:
            if st and os.path.exists(target):
                tst = os.stat(target)
                if tst.st_size == st.st_size and abs(tst.st_mtime - st.st_mtime) < 2:
                    skipped += 1
                    done_bytes += st.st_size
                    continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(path, "rb") as fi, open(target, "wb") as fo:
                while True:
                    if cancel.is_set():
                        fo.close()
                        try:
                            os.remove(target)
                        except OSError:
                            pass
                        logger.warn(tr("copy.partial_removed"))
                        return False
                    block = fi.read(CHUNK)
                    if not block:
                        break
                    fo.write(block)
                    written += len(block)
                    done_bytes += len(block)
                    emit_progress()
            if st:
                try:
                    os.utime(target, (st.st_atime, st.st_mtime))
                except OSError:
                    pass
            copied += 1
            logger.info(f"  {rel}  ({human_bytes(st.st_size if st else 0)})")
        except OSError as exc:
            errors += 1
            logger.error(tr("copy.file_error", rel=rel, e=exc))
        # done_bytes artışı chunk döngüsünde yapıldı; burada tekrarlanmıyor.
        pct = int(done_bytes * 100 / total) if total else 100
        if pct >= last_pct + 5:
            last_pct = (pct // 5) * 5
            emit_progress(force=True)

    elapsed = max(time.time() - started, 1e-6)
    logger.ok(tr("copy.done", c=copied, s=skipped, e=errors,
                 w=human_bytes(written), t=f"{elapsed:.1f}",
                 sp=f"{written / elapsed / CHUNK:.1f}"))
    if progress:
        progress(100.0, tr("copy.progress", p=100))
    return errors == 0


def _robocopy_copy(src, dst, logger, progress: ProgressCb) -> bool:
    cmd = f'robocopy "{src}" "{dst}" /E /COPY:DAT /DCOPY:T /R:1 /W:1 /NFL /NDL'
    logger.cmd("» " + cmd)
    percent_re = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)%")
    state = {"pct": -20}

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
        if "ERROR" in text.upper()[:10]:
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
                if progress and written % (CHUNK * 16) < CHUNK:
                    pct = written * 100.0 / size
                    progress(pct, tr("copy.progress", p=f"{pct:.0f}"))
        if ok:
            if not _FlushFileBuffers(handle):
                logger.warn(f"Önbellek boşaltılamadı: {ctypes.WinError()}")
            elapsed = max(time.time() - started, 1e-6)
            logger.ok(tr("iso.done", w=human_bytes(written), s=human_bytes(size),
                         t=f"{elapsed:.1f}",
                         sp=f"{written / elapsed / CHUNK:.1f}"))
    finally:
        _CloseHandle(handle)

    run_diskpart(["rescan"], on_line=logger.cmd)
    logger.info(tr("iso.rescan"))
    if ok and progress:
        progress(100.0, tr("iso.done", w=human_bytes(written), s=human_bytes(size),
                           t="0", sp="0"))
    return ok


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
    logger.ok(tr("zip.folder_done", d=out, s=human_bytes(out_size), r=f"{ratio:.0f}",
                 n=packed, e=errors, t=f"{elapsed:.1f}"))
    if progress:
        progress(100.0, tr("zip.progress", p=100))
    return errors == 0


def write_zip_to_device(zip_path: str, letter: str, logger, cancel,
                        progress: ProgressCb = None) -> bool:
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
            total = sum(i.file_size for i in infos) or 1
            logger.info(tr("zip.extract_count", n=len(infos), s=human_bytes(total)))
            written = errors = 0
            started = time.time()
            last_pct = -10
            for info in infos:
                if cancel.is_set():
                    logger.warn(tr("zip.extract_cancelled"))
                    return False
                target = os.path.normpath(os.path.join(dst_root, info.filename))
                low, root_low = target.lower(), dst_root.lower()
                if not (low == root_low or low.startswith(root_low + os.sep)):
                    logger.error(tr("zip.traversal", name=info.filename))
                    errors += 1
                    continue
                try:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(info) as srcf, open(target, "wb") as outf:
                        while True:
                            block = srcf.read(CHUNK)
                            if not block:
                                break
                            outf.write(block)
                            written += len(block)
                    logger.info(f"  {info.filename}  ({human_bytes(info.file_size)})")
                except Exception as exc:
                    errors += 1
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

    if errors:
        logger.warn(tr("zip.extract_warn", e=errors))
    else:
        logger.ok(tr("zip.extract_done", n=len(infos), s=human_bytes(written),
                     t=f"{elapsed:.1f}"))
    if progress:
        progress(100.0, tr("zip.extract_progress", p=100))
    return errors == 0
