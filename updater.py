"""GitHub tabanlı güncelleme denetimi ve otomatik güncelleme.

Akış:
  1) ``check_for_update``  → GitHub Releases API'sinden en son sürümü okur.
  2) ``download_update``   → yeni EXE'yi ``<program>\\update`` klasörüne indirir
                             ve UTF-8 bir ``update.cmd`` betiği yazar.
  3) ``launch_updater``    → mevcut EXE kapanır; betik yeni EXE'yi bekleyip
                             yerine kopyalar, programı yeniden başlatır ve
                             kendini siler.

Hiçbir adım arayüz iş parçacığını bloklamaz; yalnızca standart kütüphane
(``urllib``, ``ctypes``) kullanılır — ek bağımlılık yoktur.
"""
from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from config_manager import (APP_VERSION, BASE_DIR, FROZEN, GITHUB_OWNER,
                            GITHUB_REPO, UPDATE_ASSET_NAME)

API_LATEST = (f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
              "/releases/latest")
RELEASES_PAGE = (f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
                 "/releases/latest")

USER_AGENT = f"LunaciUpdater/{APP_VERSION}"
TIMEOUT = 15

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


@dataclass
class UpdateInfo:
    version: str = ""
    tag: str = ""
    notes: str = ""
    page_url: str = RELEASES_PAGE
    asset_url: str = ""
    asset_name: str = ""
    asset_size: int = 0
    assets: List[dict] = field(default_factory=list)

    @property
    def has_asset(self) -> bool:
        return bool(self.asset_url)


def _version_tuple(text: str) -> tuple:
    """'v1.2.10' → (1, 2, 10). Sayısal olmayan parçalar güvenle atlanır."""
    clean = (text or "").strip().lstrip("vV").split("+")[0].split("-")[0]
    parts = []
    for piece in clean.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def is_newer(remote: str, current: str = APP_VERSION) -> bool:
    return _version_tuple(remote) > _version_tuple(current)


def _ssl_context() -> ssl.SSLContext:
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()  # pragma: no cover


def _api_request(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT,
                                context=_ssl_context()) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("beklenmeyen API yanıtı")
    return data


def check_for_update() -> Optional[UpdateInfo]:
    """En son sürümü döndürür. Hata durumunda ``None``.

    Not: çağıran taraf ``check_for_update`` sonucunu ``is_newer`` ile
    karşılaştırmalıdır; bu fonksiyon her zaman en güncel sürümü döndürür.
    """
    data = _api_request(API_LATEST)
    info = UpdateInfo(
        tag=str(data.get("tag_name") or ""),
        notes=str(data.get("body") or ""),
        page_url=str(data.get("html_url") or RELEASES_PAGE),
    )
    info.version = info.tag.lstrip("vV")
    assets = data.get("assets") or []
    if isinstance(assets, list):
        info.assets = [a for a in assets if isinstance(a, dict)]
    for asset in info.assets:
        name = str(asset.get("name") or "")
        if name.lower() == UPDATE_ASSET_NAME.lower():
            info.asset_name = name
            info.asset_url = str(asset.get("browser_download_url") or "")
            try:
                info.asset_size = int(asset.get("size") or 0)
            except (TypeError, ValueError):
                info.asset_size = 0
            break
    if not info.asset_url:
        for asset in info.assets:
            name = str(asset.get("name") or "")
            if name.lower().endswith(".exe") and "setup" not in name.lower():
                info.asset_name = name
                info.asset_url = str(asset.get("browser_download_url") or "")
                info.asset_size = int(asset.get("size") or 0)
                break
    return info


def _update_dir() -> str:
    return os.path.join(BASE_DIR, "update")


def update_available() -> bool:
    """Ucuz on kontrol: yalnızca true/false (hata → False)."""
    try:
        info = check_for_update()
    except Exception:
        return False
    return bool(info and info.version and is_newer(info.version))


def download_update(info: UpdateInfo, logger=None,
                    progress: Optional[Callable[[float, str], None]] = None
                    ) -> str:
    """Yeni EXE'yi indirir ve güncelleme betiğini hazırlar; betik yolunu döner."""
    if not info.asset_url:
        raise ValueError("sürümde indirilebilir EXE bulunamadı")

    folder = _update_dir()
    os.makedirs(folder, exist_ok=True)
    new_exe = os.path.join(folder, info.asset_name or UPDATE_ASSET_NAME)
    part = new_exe + ".part"

    def _log(level: str, msg: str) -> None:
        if logger:
            try:
                getattr(logger, level, logger.info)(msg)
            except Exception:
                pass

    _log("info", f"İndiriliyor: {info.asset_name} ({info.asset_size} bayt) → {new_exe}")
    req = urllib.request.Request(info.asset_url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp:
        total = int(resp.headers.get("Content-Length") or info.asset_size or 0)
        read = 0
        started = time.time()
        with open(part, "wb") as f:
            while True:
                block = resp.read(256 * 1024)
                if not block:
                    break
                f.write(block)
                read += len(block)
                if progress and total:
                    pct = read * 100.0 / total
                    sp = (read / max(time.time() - started, 1e-6)) / (1024 * 1024)
                    progress(pct, f"%{pct:.0f}  ·  {sp:.1f} MB/s")
    os.replace(part, new_exe)
    _log("ok", f"İndirme tamamlandı: {new_exe}")

    script = _write_update_script(new_exe)
    return script


def _write_update_script(new_exe: str) -> str:
    """Mevcut EXE'yi yeni sürümle değiştiren ve programı yeniden başlatan betik."""
    script_path = os.path.join(tempfile.gettempdir(), "lunaci_update.cmd")
    # Betik ASCII olmalı: cmd.exe kod sayfalarıyla uğraşmamak için yollar
    # yalnızca yerel kodlamada yazılır.
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "ping 127.0.0.1 -n 3 >nul",
        f'set "NEW={new_exe}"',
        f'set "OLD={sys.executable}"',
        'copy /y "%NEW%" "%OLD%" >nul',
        'if errorlevel 1 (',
        '  ping 127.0.0.1 -n 3 >nul',
        '  copy /y "%NEW%" "%OLD%" >nul',
        ')',
        'start "" "%OLD%"',
        'ping 127.0.0.1 -n 3 >nul',
        'del /f /q "%NEW%" >nul 2>&1',
        'rd /s /q "%NEW%\\.." >nul 2>&1',
        'del /f /q "%~f0" >nul 2>&1',
    ]
    with open(script_path, "w", encoding="utf-8", errors="replace",
              newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return script_path


def launch_updater(script_path: str) -> bool:
    """Güncelleme betiğini bağımsız (detached) başlatır."""
    try:
        subprocess.Popen(["cmd", "/c", script_path],
                         creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
                         close_fds=True, cwd=tempfile.gettempdir())
        return True
    except Exception:
        return False


def updater_supported() -> bool:
    """Otomatik güncelleme yalnızca paketlenmiş (EXE) sürümde desteklenir."""
    return bool(FROZEN)
