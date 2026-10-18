"""Uygulama ayarlarını JSON dosyasında saklar.

Ayar dosyası; frozen (exe) modunda exe'nin yanındaki ``config.json``,
kaynak modda proje kökündedir. Raporlar her iki modda da programın
yanındaki ``reports`` klasörüne yazılır.
"""
from __future__ import annotations

import json
import os
import sys

APP_NAME = "Lunaci Smart USB & SD Card Utility"
APP_VERSION = "1.0.0"
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
}


class ConfigManager:
    """Basit JSON ayar yonetici; okuma/yazma hatalarinda DEFAULTS'e duser."""

    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update(stored)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def get(self, key: str, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value) -> None:
        self.data[key] = value
        self.save()
