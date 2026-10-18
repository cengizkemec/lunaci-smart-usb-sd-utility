"""Lunaci Smart USB & SD Card Utility — giriş noktası.

Yönetici yetkisi gerektiren disk işlemleri (diskpart, chkdsk, ham ISO yazımı)
için uygulama başlangıcında UAC ile yükseltilir.
"""
import ctypes
import os
import sys
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


def main() -> None:
    _install_excepthook()
    _dpi_aware()
    _ensure_admin()
    import customtkinter as ctk
    ctk.set_default_color_theme("blue")
    from app import LunaciApp
    app = LunaciApp()
    # Pencere/taskbar ikonu (paket içi assets/logo.ico)
    try:
        import os
        from config_manager import resource_path
        icon_path = resource_path("assets/logo.ico")
        if os.path.isfile(icon_path):
            app.iconbitmap(icon_path)
    except Exception:
        pass
    app.mainloop()


if __name__ == "__main__":
    main()
