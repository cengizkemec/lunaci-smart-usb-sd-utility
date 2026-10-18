"""Okuma/yazma tabanlı disk sağlık testi → Yeşil / Sarı / Kırmızı durum."""
from __future__ import annotations

import hashlib
import os
import time
from typing import Tuple

from disk_manager import Device
from i18n import tr
from utils import Emitter, human_bytes

GOOD = "good"
WARN = "warn"
CRIT = "crit"

CHUNK = 1024 * 1024


def run_health_test(device: Device, logger: Emitter, cancel,
                    size_mb: int = 8) -> Tuple[str, dict]:
    """Geçici bir dosya yazıp okuyarak doğrular; hız ve tutarlılık ölçer.

    Not: Bazı USB kartlar ``FlushFileBuffers`` (os.fsync) sırasında takılı
    kalıyor; bu yüzden fsync KULLANILMIYOR. Çıkarılabilir medya Windows'ta
    varsayılan olarak write-through önbellekleme polityası kullanır; okuma
    testi yine de medyadan gelir.
    """
    letter = device.letter
    root = f"{letter}:\\"
    info = {"write_mb_s": None, "read_mb_s": None, "checked_mb": 0}
    started = time.time()

    if not os.path.isdir(root):
        logger.error(tr("h.access_err", r=root))
        return CRIT, info
    if device.readonly:
        logger.error(tr("h.readonly_err"))
        return CRIT, info
    if device.is_raw:
        logger.error(tr("h.raw_err"))
        return CRIT, info

    tmp = os.path.join(root, "_lunaci_health.bin")
    mb = max(1, int(size_mb or 8))
    if device.free and device.free < (mb + 8) * CHUNK:
        mb = 1
        logger.warn(tr("h.small_space"))

    write_hash = hashlib.sha256()
    read_hash = hashlib.sha256()
    status = GOOD

    try:
        blocks = [os.urandom(CHUNK) for _ in range(mb)]
        logger.info(tr("h.write_start", p=tmp, m=mb))
        w_start = time.time()
        with open(tmp, "wb") as f:
            for i, block in enumerate(blocks):
                if cancel.is_set():
                    logger.warn(tr("h.cancelled"))
                    status = WARN
                    break
                f.write(block)
                write_hash.update(block)
                if (i + 1) % 4 == 0:
                    logger.info(tr("h.write_progress", i=i + 1, m=mb))
            f.flush()
            # os.fsync() YOK: bazı kartlarda takılıyor ve görevi bitmiyordu.
        w_time = max(time.time() - w_start, 1e-6)
        info["write_mb_s"] = round(mb / w_time, 2)
        logger.info(tr("h.write_speed", v=info["write_mb_s"]))

        logger.info(tr("h.read_start"))
        r_start = time.time()
        read = 0
        with open(tmp, "rb") as f:
            while True:
                if cancel.is_set():
                    status = WARN
                    break
                block = f.read(CHUNK)
                if not block:
                    break
                read_hash.update(block)
                read += len(block)
        r_time = max(time.time() - r_start, 1e-6)
        info["read_mb_s"] = round((read / CHUNK) / r_time, 2)
        info["checked_mb"] = mb
        logger.info(tr("h.read_speed", v=info["read_mb_s"]))

        if read_hash.hexdigest() != write_hash.hexdigest():
            logger.error(tr("h.mismatch"))
            status = CRIT
        elif status != WARN:
            logger.ok(tr("h.verify_ok"))
    except OSError as exc:
        logger.error(tr("h.io_err", e=exc))
        status = CRIT
    finally:
        try:
            os.remove(tmp)
            logger.info(tr("h.cleanup_ok"))
        except Exception as exc:
            logger.warn(tr("h.cleanup_warn", e=exc))
            if status == GOOD:
                status = WARN

    if status != CRIT:
        ws = info.get("write_mb_s") or 0
        rs = info.get("read_mb_s") or 0
        if ws and ws < 1.0:
            logger.warn(tr("h.slow_write"))
            if status == GOOD:
                status = WARN
        if rs and rs < 1.5:
            logger.warn(tr("h.slow_read"))
            if status == GOOD:
                status = WARN

    logger.info(tr("h.duration", t=f"{time.time() - started:.1f}",
                   w=human_bytes(mb * CHUNK)))
    return status, info
