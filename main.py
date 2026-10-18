"""Lunaci Smart USB & SD Card Utility — giriş noktası.

Yönetici yetkisi gerektiren disk işlemleri (diskpart, chkdsk, ham ISO yazımı)
için uygulama başlangıcında UAC ile yükseltilir.
"""
import ctypes
import os
import sys
import tempfile
import tkinter as tk
import tkinter.messagebox as messagebox


def _install_excepthook() -> None:
    """Beklenmeyen çökmeleri program yanındaki error.log dosyasına yazar."""
    import traceback

    def _hook(exc_type, exc, tb):
        try:
            from config_manager import BASE_DIR
            path = os.path.join(BASE_DIR, "error.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(exc_type, exc, tb)))
                f.write("\n" + "=" * 60 + "\n")
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook


def _dpi_aware() -> None:
    """Yüksek çözünürlüklü ekranlarda net görüntü."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _ensure_admin() -> None:
    from utils import elevate_current_process, is_admin
    if is_admin():
        return
    root = tk.Tk()
    root.withdraw()
    try:
        answer = messagebox.askyesno(
            "Yönetici Yetkisi Gerekli",
            "Lunaci; biçimlendirme (diskpart), onarım (chkdsk), ISO/ZIP yazma ve RAW "
            "erişimi için yönetici yetkisi gerektirir.\n\n"
            "Uygulama yönetici olarak yeniden başlatılsın mı?",
            icon="warning")
    finally:
        root.destroy()
    if answer:
        if elevate_current_process():
            sys.exit(0)
        messagebox.showwarning(
            "Yükseltme Başarısız",
            "Yönetici yetkisi alınamadı (UAC iptal edilmiş olabilir).\n"
            "Uygulama sınırlı modda devam edecek: biçimlendirme, onarım ve ISO/ZIP "
            "yazma işlemleri çalışmayacaktır.")


def _load_theme() -> None:
    """Telegram esintili varsayilan renk temasi (assets/theme_lunaci.json)."""
    import customtkinter as ctk
    try:
        from config_manager import resource_path
        path = resource_path(os.path.join("assets", "theme_lunaci.json"))
        if os.path.isfile(path):
            ctk.set_default_color_theme(path)
            return
    except Exception:
        pass
    ctk.set_default_color_theme("blue")


def _smoke_seconds() -> int:
    """Tanilama: LUNACI_SMOKE_TEST=<saniye> ayarliysa yonetici istemeden kisa
    bir GUI oturumu calistirilir (paketin eksiksiz kuruldugunu dogrulamak icin).
    Normal kullanimda bu ortam degiskeni tanimli olmadigindan hicbir etkisi yoktur.
    """
    try:
        raw = os.environ.get("LUNACI_SMOKE_TEST", "").strip()
        return max(1, min(int(raw), 120)) if raw else 0
    except Exception:
        return 0


def main() -> None:
    _install_excepthook()
    _dpi_aware()
    smoke = _smoke_seconds()
    if smoke:
        marker = os.path.join(tempfile.gettempdir(), "lunaci_smoke_ok.txt")
        try:
            os.remove(marker)
        except OSError:
            pass
        _load_theme()
        from app import LunaciApp
        app = LunaciApp()
        app.after(smoke * 1000, app.destroy)
        app.mainloop()
        with open(marker, "w", encoding="utf-8") as f:
            f.write("ok\n")
        return
    _ensure_admin()
    _load_theme()
    from app import LunaciApp
    app = LunaciApp()
    # Pencere/taskbar ikonu (paket içi assets/logo.ico)
    try:
        from config_manager import resource_path
        icon_path = resource_path("assets/logo.ico")
        if os.path.isfile(icon_path):
            app.iconbitmap(icon_path)
    except Exception:
        pass
    app.mainloop()


if __name__ == "__main__":
    main()
