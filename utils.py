"""Lunaci yardımcıları: yetki yönetimi, süreç çalıştırma ve log kayıtları."""
from __future__ import annotations

import ctypes
import locale
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Sequence, Tuple, Union

CREATE_NO_WINDOW = 0x08000000

LEVEL_COLORS = {
    "DEBUG": "#8b949e",
    "INFO": "#58a6ff",
    "OK": "#3fb950",
    "WARN": "#d29922",
    "ERROR": "#f85149",
    "CMD": "#bc8cff",
}

Command = Union[str, Sequence[str]]


@dataclass
class LogRecord:
    ts: datetime
    level: str
    message: str
    task: str = ""

    @property
    def time_str(self) -> str:
        return self.ts.strftime("%H:%M:%S")

    @property
    def line(self) -> str:
        return f"[{self.time_str}] [{self.level:<5}] {self.message}"

    @property
    def color(self) -> str:
        return LEVEL_COLORS.get(self.level, "#c9d1d9")


class Emitter:
    """İş parçacığı güvenli log yayını. Kayıtları kuyruğa atar ve rapor için saklar."""

    def __init__(self, put: Callable, task: str = "") -> None:
        self._put = put
        self.task = task
        self._lock = threading.Lock()
        self.capture: List[str] = []

    def log(self, level: str, message: str) -> LogRecord:
        rec = LogRecord(datetime.now(), level, str(message), self.task)
        with self._lock:
            self.capture.append(rec.line)
            if len(self.capture) > 2000:
                del self.capture[:1000]
        try:
            self._put(("log", rec))
        except Exception:
            pass
        return rec

    def debug(self, msg: str) -> LogRecord:
        return self.log("DEBUG", msg)

    def info(self, msg: str) -> LogRecord:
        return self.log("INFO", msg)

    def ok(self, msg: str) -> LogRecord:
        return self.log("OK", msg)

    def warn(self, msg: str) -> LogRecord:
        return self.log("WARN", msg)

    def error(self, msg: str) -> LogRecord:
        return self.log("ERROR", msg)

    def cmd(self, msg: str) -> LogRecord:
        return self.log("CMD", msg)


# ---------------------------------------------------------------- yetki ----

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_current_process() -> bool:
    """Uygulamayı yönetici olarak yeniden başlatır. UAC iptal edilirse False döner."""
    try:
        frozen = bool(getattr(sys, "frozen", False))
        if frozen:
            # PyInstaller exe: kendimizi yeniden başlat (argüman yok)
            executable, param_line = sys.executable, ""
        else:
            script = os.path.abspath(sys.argv[0])
            rest = " ".join(f'"{a}"' for a in sys.argv[1:])
            param_line = f'"{script}"' + (" " + rest if rest else "")
            executable = sys.executable
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, param_line,
            os.path.dirname(sys.executable if frozen else script), 1
        )
        return rc > 32
    except Exception:
        return False


# ------------------------------------------------------------- biçim -------

def human_bytes(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    if n < 0:
        n = 0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "cp857", "cp1254"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("cp1254", errors="replace")


# ------------------------------------------------------ süreç çalıştırma ----

def run_process(
    cmd: Command,
    *,
    on_line: Optional[Callable[[str], None]] = None,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[int, List[str]]:
    """Komutu gizli pencerede çalıştırır; hem \\n hem \\r ayracıyla satır akışı sağlar."""
    cmd_list: List[str] = ["cmd", "/c", cmd] if isinstance(cmd, str) else list(cmd)
    lines: List[str] = []
    proc = subprocess.Popen(
        cmd_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        cwd=cwd,
        creationflags=CREATE_NO_WINDOW,
        bufsize=0,
    )
    killed = threading.Event()

    def _watch() -> None:
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            killed.set()
            try:
                proc.kill()
            except Exception:
                pass

    if timeout:
        threading.Thread(target=_watch, daemon=True).start()

    def _flush(buf: bytearray) -> None:
        if not buf:
            return
        text = _decode(bytes(buf))
        buf.clear()
        lines.append(text)
        if on_line:
            try:
                on_line(text)
            except Exception:
                pass

    buf = bytearray()
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            for b in chunk:
                if b in (10, 13):
                    _flush(buf)
                else:
                    buf.append(b)
    finally:
        _flush(buf)
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            proc.wait(10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    rc = proc.returncode if proc.returncode is not None else -1
    return (-1 if killed.is_set() else rc), lines


def run_shell(cmd: str, on_line: Optional[Callable[[str], None]] = None,
              timeout: Optional[float] = None) -> Tuple[int, List[str]]:
    """cmd.exe içinde, UTF-8 konsol kod sayfasıyla çalıştırır."""
    return run_process(f"chcp 65001>nul & {cmd}", on_line=on_line, timeout=timeout)


def run_diskpart(script_lines: Sequence[str],
                 on_line: Optional[Callable[[str], None]] = None,
                 timeout: Optional[float] = None) -> Tuple[int, List[str]]:
    """diskpart'a satırları dosya üzerinden verir; satırları canlı iletir."""
    fd, path = tempfile.mkstemp(prefix="lunaci_dp_", suffix=".txt")
    try:
        enc = locale.getpreferredencoding(False) or "cp1254"
        with os.fdopen(fd, "w", encoding=enc, errors="replace", newline="\r\n") as f:
            for line in script_lines:
                f.write(line + "\n")
        return run_process(["diskpart", "/s", path], on_line=on_line, timeout=timeout)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def run_powershell(script: str, timeout: float = 25.0) -> Tuple[int, List[str]]:
    return run_process(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        timeout=timeout,
    )
