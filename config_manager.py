"""Uygulama ayarlarını JSON dosyasında saklar.

Ayar dosyası; frozen (exe) modunda exe'nin yanındaki ``config.json``,
kaynak modda proje kökündedir. Raporlar her iki modda da programın
yanındaki ``reports`` klasörüne yazılır.
"""
from __future__ import annotations

import json
import os
import sys
import threading

APP_NAME = "Lunaci Smart USB & SD Card Utility"
APP_VERSION = "1.3.2"
GITHUB_URL = "https://github.com/cengizkemec/lunaci-smart-usb-sd-utility"
WEBSITE_URL = "https://cengizkemec.com.tr/"

FROZEN = bool(getattr(sys, "frozen", False))
# Kaynaklar (logo vb.) paket içinde; ayar/raporlar exe yaninda kalici olmali.
BASE_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(
    os.path.abspath(__file__))


def resource_path(relative: str) -> str:
    """Paket içi (assets) bir dosyanin mutlak yolunu dondurur."""
    if FROZEN:
        base = getattr(sys, "_MEIPASS", BASE_DIR)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# GitHub deposu (guncelleme denetimi ve surum sayfasi icin)
GITHUB_OWNER = "cengizkemec"
GITHUB_REPO = "lunaci-smart-usb-sd-utility"
UPDATE_ASSET_NAME = "LunaciSmartUSBCardUtility.exe"

DEFAULTS = {
    "theme": "system",                 # system | dark | light
    "language": "tr",                  # tr | en
    "target_folder": "",
    "last_device": None,
    "volume_label": "LUNACI",
    "preferred_filesystem": None,      # None => cihazin mevcut FS'i
    "copy_engine": "shutil",           # shutil | robocopy
    "save_reports": True,
    "auto_format_before_write": True,   # yazmadan once hizli bicimlendir
    "reports_folder_name": "reports",  # program klasorundeki rapor klasoru
    "poll_interval": 3.0,              # saniye
    # istege bagli acilista otomatik saglik testi (varsayilan: kapali)
    "auto_health_check": False,
    "health_test_mb": 8,
    "sound_on_complete": True,          # islem bitince kisa bildirim sesi
    "auto_update_check": True,          # acilista GitHub'dan guncelleme denetle
}


class ConfigManager:
    """Basit JSON ayar yonetici; okuma/yazma hatalarinda DEFAULTS'e duser.

    Yazma islemi arka planda (debounce) yapilir; boylece ana arayuz
    thread'i OneDrive/disk kilitleri nedeniyle ASLA takilmez.
    """

    SAVE_DELAY = 0.4  # saniye — hizli degisiklik serisini tek yazimda birlestirir

    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self.data = dict(DEFAULTS)
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()
        self._dirty = False
        self._wake = threading.Event()
        self._closed = False
        self.load()
        self._writer = threading.Thread(target=self._writer_loop, daemon=True,
                                        name="lunaci-config-writer")
        self._writer.start()

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update(stored)
        except (OSError, ValueError):
            pass

    # ---- arka plan yazici ----
    def _writer_loop(self) -> None:
        while True:
            self._wake.wait(self.SAVE_DELAY)
            self._wake.clear()
            if self._closed:
                return
            with self._lock:
                if not self._dirty:
                    continue
                self._dirty = False
            self.save()

    def flush(self) -> None:
        """Bekleyen (veya devam eden) yazimi senkron olarak tamamla."""
        self._closed = True
        self._wake.set()
        try:
            self._writer.join(timeout=5.0)
        except Exception:
            pass
        with self._lock:
            pending = self._dirty
            self._dirty = False
        if pending:
            self.save()

    def save(self) -> None:
        """Ayarlari diske yaz. Ayni anda tek yazici olur (kilitli)."""
        with self._save_lock:
            try:
                payload = json.dumps(self.data, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp, self.path)
            except OSError:
                try:
                    with open(self.path, "w", encoding="utf-8") as f:
                        f.write(payload)
                except OSError:
                    pass

    def get(self, key: str, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        """Ana thread'i asla bloklamayan, arka plana ertelenen guncelleme."""
        with self._lock:
            if self.data.get(key) == value:
                return
            self.data[key] = value
            self._dirty = True
        self._wake.set()
