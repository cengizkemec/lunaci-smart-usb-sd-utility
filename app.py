"""Lunaci Smart USB & SD Card Utility — CustomTkinter arayüzü."""
from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

import i18n
from i18n import tr
from config_manager import (APP_NAME, APP_VERSION, BASE_DIR, GITHUB_URL,
                            WEBSITE_URL, ConfigManager, resource_path)
from disk_manager import (Device, DeviceMonitor, fstype_to_option, run_format,
                          run_repair)
from file_ops import (copy_folder, save_report, write_image, write_iso_bootable,
                      write_iso_raw, write_zip_to_device, zip_folder_to_device)
from health import CRIT, GOOD, WARN, run_health_test
from utils import (LEVEL_COLORS, Emitter, human_bytes, is_admin,
                   play_notification)
import updater

THEME_TO_MODE = {"system": "System", "dark": "Dark", "light": "Light"}
THEME_KEYS = ("system", "dark", "light")

# Aktarim paneli durum renkleri ve ilgili ceviri anahtarlari — (acik, koyu)
XF_COLORS = {"active": ("#9A6700", "#d29922"), "done": ("#1A7F37", "#3fb950"),
             "skip": ("#5F6B76", "#8b949e"), "error": ("#CF222E", "#f85149"),
             "cancel": ("#CF222E", "#f85149")}
XF_STATE_KEY = {"active": "xf.state.active", "done": "xf.state.done",
                "skip": "xf.state.skip", "error": "xf.state.error",
                "cancel": "xf.state.cancel"}
XF_ICON = {"active": "▶", "done": "✔", "skip": "»", "error": "✖", "cancel": "✖"}

ISO_MODE_KEYS = ("iso.mode.auto", "iso.mode.raw", "iso.mode.iso")
ISO_MODE_VALUES = {"iso.mode.auto": "auto", "iso.mode.raw": "raw",
                   "iso.mode.iso": "iso"}

# Telegram esintili yardimci renkler — (acik, koyu) ciftleri seklinde verilir,
# boylece koyu/aci temalari arasinda geciste otomatik uyum saglanir.
# Renkler WCAG kontrast oranina gore secildi (koyu temada soluk metinler
# okunmazdi; acik temada kirmizi butonlarin beyaz yazisi zayif kalmisti).
MUTED = ("#5A626B", "#9AA7B4")          # soluk/bilgi metinleri
LINK = ("#0B6FBF", "#52A9F2")           # baglanti metinleri
SEC_BTN = ("#E7EBF0", "#2B5278")        # ikincil buton
SEC_BTN_H = ("#D5DBE0", "#3A6594")
SEC_BTN_T = ("#17212B", "#E9EDF2")
DANGER_BTN = ("#C62828", "#8B1E1E")     # tehlikeli buton
DANGER_BTN_H = ("#B71C1C", "#A62727")
CANCEL_BTN = ("#C62828", "#B91C1C")     # iptal butonu
CANCEL_BTN_H = ("#B71C1C", "#991B1B")
WHITE = ("#FFFFFF", "#FFFFFF")
# Segment dugmelerde secili parcayi vurgulayan vurgu rengi. Koyu/acik
# eslesmesi, beyaz yazi ile 4.5:1 kontrastin uzerinde kalir.
SEL_COLOR = ("#3B6FA8", "#3F76B0")
SEL_COLOR_H = ("#33608F", "#5589C4")
ACCENT = ("#3B6FA8", "#3F76B0")         # ana (vurgu) butonlar
ACCENT_H = ("#33608F", "#5589C4")

LED_COLORS = {"unknown": "#6b7280", GOOD: "#22c55e", WARN: "#eab308", CRIT: "#ef4444"}
HEALTH_KEY = {"unknown": "health.unknown", GOOD: "health.good",
              WARN: "health.warn", CRIT: "health.crit"}

FS_OPTIONS = ["FAT32", "NTFS", "exFAT", "EXT4 (Linux)"]
NEED_ADMIN = {"format", "repair", "iso"}

# Gunluk (log) konsolu icin tema farkli renkler — (acik, koyu) ciftleri.
# Koyu tema renkleri acik temada okunmazdi; ikisi de ayri ayri verilir.
LOG_COLORS = {
    "DEBUG": ("#5f6b76", "#8b949e"),
    "INFO":  ("#1f6feb", "#58a6ff"),
    "OK":    ("#1a7f37", "#3fb950"),
    "WARN":  ("#9a6700", "#d29922"),
    "ERROR": ("#cf222e", "#f85149"),
    "CMD":   ("#8250df", "#bc8cff"),
}

# Dosya-bazli yazma islemleri: canli aktarim panelini temizler
XF_TASKS = {"copy", "zip", "iso"}
# Islem bitisinde kisa bildirim sesi calan gorevler
SOUND_TASKS = {"format", "repair", "iso", "zip", "copy", "zipfolder", "health"}


class LunaciApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = ConfigManager()
        i18n.set_language(self.cfg.get("language") or "tr")

        self.q: "queue.Queue" = queue.Queue()
        self.devices: list = []
        self.active_letter: str | None = None
        self.known_letters: set = set()
        self.health: dict = {}
        self.busy: str | None = None
        self.cancel_event = threading.Event()
        self._device_map: dict = {}
        self._fs_synced_letter: str | None = None
        self._log_tags: set = set()
        self._indeterminate = False
        self._about = None
        # performans/onluklar: degismedikce Tk widget'larina dokunulmaz
        self._menu_values: list = []
        self._menu_current: str = ""
        self._target_cache: tuple = (None, False, 0.0)
        self._target_checking = False
        # Birlesik konsol: dosya aktarim satirlari + gunluk kayitlari ayni
        # metin kutusunda tutulur (satirlar dogrudan guncellenir).
        self._xf_rows: dict = {}
        self._xf_count = 0
        self._xf_max = 3000
        self._xf_head = (0, 0, "")
        self._update_dialog = None
        self._update_running = False

        ctk.set_appearance_mode(THEME_TO_MODE.get(self.cfg.get("theme"), "System"))
        # Telegram esintili varsayilan tema (assets/theme_lunaci.json)
        try:
            _theme_path = resource_path(os.path.join("assets", "theme_lunaci.json"))
            if os.path.isfile(_theme_path):
                ctk.set_default_color_theme(_theme_path)
        except Exception:
            pass

        self.title(APP_NAME)
        self.geometry("1180x940")
        self.minsize(1040, 820)

        self.font_ui = ctk.CTkFont(family="Segoe UI", size=13)
        self.font_small = ctk.CTkFont(family="Segoe UI", size=12)
        self.font_title = ctk.CTkFont(family="Segoe UI", size=21, weight="bold")
        self.font_mono = ctk.CTkFont(family="Consolas", size=13)

        self._build_ui()
        self._refresh_all_text()

        self._ui_emitter = Emitter(self.q.put, task="ui")
        self._refresh_actions()

        self.monitor = DeviceMonitor(self.q.put, self.cfg.get("poll_interval") or 3.0)
        self.monitor.start()

        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Beklenmedik Tk geri cagrisi hatalarini sessizce yutma, error.log'a yaz.
        self.report_callback_exception = lambda *a: self._report_callback_error(a[1])

        # Acilista sessiz guncelleme denetimi (arka planda; arayuzu bloklamaz)
        if self.cfg.get("auto_update_check"):
            self.after(2500, lambda: self._check_updates(silent=True))

    # ----------------------------------------------------------- yardımcı --

    def reports_dir(self) -> str:
        """Raporlar programın yanındaki reports klasörüne yazılır."""
        name = self.cfg.get("reports_folder_name") or "reports"
        path = os.path.join(BASE_DIR, name)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass
        return path

    # ----------------------------------------------------------- arayüz ----

    def _build_ui(self) -> None:
        for w in self.winfo_children():
            w.destroy()

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        # Konsol tek panel oldugu icin kalan tum dikey alani kaplar; boylece
        # iki panel arasindaki dikey kaydirma cakismasi ortadan kalkar.
        self.grid_rowconfigure(3, weight=1)

        # üst başlık
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text=APP_NAME,
                     font=self.font_title).grid(row=0, column=0, sticky="w")
        self.subtitle_label = ctk.CTkLabel(
            header, text=tr("app.subtitle"), text_color=MUTED, font=self.font_small)
        self.subtitle_label.grid(row=1, column=0, sticky="w")
        admin = is_admin()
        self.admin_badge = ctk.CTkLabel(
            header, text=tr("badge.admin") if admin else tr("badge.limited"),
            text_color="#22c55e" if admin else "#ef4444",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
        self.admin_badge.grid(row=0, column=1, rowspan=2, padx=(8, 14))
        self.theme_menu = ctk.CTkSegmentedButton(
            header, values=[tr("theme.system"), tr("theme.dark"), tr("theme.light")],
            command=self._on_theme, font=self.font_small, width=220,
            selected_color=SEL_COLOR, selected_hover_color=SEL_COLOR_H)
        self.theme_menu.grid(row=0, column=2, rowspan=2, padx=(0, 8))
        self.lang_menu = ctk.CTkSegmentedButton(
            header, values=["TR", "EN"], command=self._on_language,
            font=self.font_small, width=90,
            selected_color=SEL_COLOR, selected_hover_color=SEL_COLOR_H)
        self.lang_menu.grid(row=0, column=3, rowspan=2, padx=(0, 8))
        self.btn_update = ctk.CTkButton(header, text=tr("btn.update"), width=140,
                                        fg_color=SEC_BTN, hover_color=SEC_BTN_H,
                                        text_color=SEC_BTN_T,
                                        command=self._check_updates)
        self.btn_update.grid(row=0, column=4, rowspan=2, padx=(0, 8))
        self.btn_about = ctk.CTkButton(header, text=tr("btn.about"), width=90,
                                       fg_color=SEC_BTN, hover_color=SEC_BTN_H,
                                       text_color=SEC_BTN_T,
                                       command=self._show_about)
        self.btn_about.grid(row=0, column=5, rowspan=2)

        # cihaz kartı
        dev_frame = ctk.CTkFrame(self)
        dev_frame.grid(row=1, column=0, sticky="nsew", padx=(18, 6), pady=6)
        dev_frame.grid_columnconfigure(1, weight=1)
        self.dev_section = ctk.CTkLabel(dev_frame, text=tr("dev.section"),
                                        font=self.font_small, text_color=MUTED)
        self.dev_section.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.device_menu = ctk.CTkOptionMenu(dev_frame, width=340,
                                             fg_color=ACCENT,
                                             button_color=ACCENT_H,
                                             button_hover_color=ACCENT_H,
                                             text_color=WHITE,
                                             command=self._on_device_pick)
        self.device_menu.grid(row=0, column=1, columnspan=2, sticky="ew",
                              padx=12, pady=(10, 2))
        self.led = ctk.CTkLabel(dev_frame, text="●", text_color=LED_COLORS["unknown"],
                                font=ctk.CTkFont(size=26))
        self.led.grid(row=0, column=3, rowspan=2, padx=(6, 12), pady=(8, 0))
        self.health_label = ctk.CTkLabel(dev_frame, text=tr("health.status", s="—"),
                                         font=self.font_small, text_color=MUTED)
        self.health_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=12)
        self.info_label = ctk.CTkLabel(dev_frame, text=tr("dev.waiting"),
                                       font=self.font_ui, anchor="w", justify="left")
        self.info_label.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(8, 2))
        self.cap_bar = ctk.CTkProgressBar(dev_frame)
        self.cap_bar.set(0)
        self.cap_bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 2))
        self.cap_label = ctk.CTkLabel(dev_frame, text="", font=self.font_small,
                                      text_color=MUTED)
        self.cap_label.grid(row=4, column=0, columnspan=3, sticky="w", padx=12)
        self.tech_label = ctk.CTkLabel(dev_frame, text="", font=self.font_small,
                                       text_color=MUTED)
        self.tech_label.grid(row=5, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))
        self.btn_health = ctk.CTkButton(dev_frame, text=tr("btn.health"),
                                        fg_color=ACCENT, hover_color=ACCENT_H,
                                        text_color=WHITE,
                                        command=lambda: self._do_health())
        self.btn_health.grid(row=6, column=0, columnspan=3, sticky="ew", padx=12, pady=(2, 12))

        # yazdırılacak klasör kartı (sağ üst)
        tgt_frame = ctk.CTkFrame(self)
        tgt_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 18), pady=6)
        tgt_frame.grid_columnconfigure(0, weight=1)
        self.folder_section = ctk.CTkLabel(tgt_frame, text=tr("folder.section"),
                                           font=self.font_small, text_color=MUTED)
        self.folder_section.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        row = ctk.CTkFrame(tgt_frame, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=12)
        row.grid_columnconfigure(0, weight=1)
        self.target_var = tk.StringVar(value=self.cfg.get("target_folder") or "")
        self.target_entry = ctk.CTkEntry(row, textvariable=self.target_var,
                                         placeholder_text=tr("folder.placeholder"),
                                         state="readonly")
        self.target_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.btn_browse = ctk.CTkButton(row, text=tr("btn.browse"), width=70,
                                        fg_color=ACCENT, hover_color=ACCENT_H,
                                        text_color=WHITE,
                                        command=self._pick_folder)
        self.btn_browse.grid(row=0, column=1)
        self.btn_copy = ctk.CTkButton(tgt_frame, text=tr("btn.write_folder"),
                                      fg_color=ACCENT, hover_color=ACCENT_H,
                                      text_color=WHITE,
                                      command=self._do_copy)
        self.btn_copy.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 2))
        self.btn_zipfolder = ctk.CTkButton(tgt_frame, text=tr("btn.zip_folder"),
                                           fg_color=SEC_BTN, hover_color=SEC_BTN_H,
                                           text_color=SEC_BTN_T,
                                           command=self._do_zipfolder)
        self.btn_zipfolder.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 4))
        self.autofmt_switch = ctk.CTkSwitch(
            tgt_frame, text=tr("switch.autofmt"),
            command=self._toggle_autofmt, font=self.font_small)
        if self.cfg.get("auto_format_before_write"):
            self.autofmt_switch.select()
        self.autofmt_switch.grid(row=4, column=0, sticky="w", padx=12, pady=(2, 2))
        options_row = ctk.CTkFrame(tgt_frame, fg_color="transparent")
        options_row.grid(row=5, column=0, sticky="ew", padx=12, pady=(2, 2))
        self.reports_switch = ctk.CTkSwitch(
            options_row, text=tr("switch.reports"),
            command=self._toggle_reports, font=self.font_small)
        if self.cfg.get("save_reports"):
            self.reports_switch.select()
        self.reports_switch.grid(row=0, column=0, sticky="w")
        self.sound_switch = ctk.CTkSwitch(
            options_row, text=tr("switch.sound"),
            command=self._toggle_sound, font=self.font_small)
        if self.cfg.get("sound_on_complete"):
            self.sound_switch.select()
        self.sound_switch.grid(row=0, column=1, sticky="w", padx=(18, 0))
        self.btn_reports = ctk.CTkButton(tgt_frame, text=tr("btn.reports"),
                                         fg_color=SEC_BTN,
                                         hover_color=SEC_BTN_H,
                                         text_color=SEC_BTN_T,
                                         command=self._open_reports)
        self.btn_reports.grid(row=6, column=0, sticky="ew", padx=12, pady=(2, 12))

        # biçimlendirme
        fmt_frame = ctk.CTkFrame(self)
        fmt_frame.grid(row=2, column=0, sticky="nsew", padx=(18, 6), pady=6)
        fmt_frame.grid_columnconfigure(1, weight=1)
        self.fmt_section = ctk.CTkLabel(fmt_frame, text=tr("fmt.section"),
                                        font=self.font_small, text_color=MUTED)
        self.fmt_section.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.fs_var = tk.StringVar(value="FAT32")
        self.fs_box = ctk.CTkComboBox(fmt_frame, values=FS_OPTIONS, state="readonly",
                                      variable=self.fs_var, width=180)
        self.fs_box.grid(row=0, column=1, sticky="w", padx=6)
        self.label_caption = ctk.CTkLabel(fmt_frame, text=tr("fmt.label"),
                                          font=self.font_small, text_color=MUTED)
        self.label_caption.grid(row=0, column=2, sticky="w", padx=12)
        self.label_var = tk.StringVar(value=self.cfg.get("volume_label") or "LUNACI")
        ctk.CTkEntry(fmt_frame, textvariable=self.label_var, width=160).grid(
            row=0, column=3, sticky="e", padx=(6, 12))
        self.btn_quick = ctk.CTkButton(fmt_frame, text=tr("btn.quick_format"),
                                       fg_color=ACCENT, hover_color=ACCENT_H,
                                       text_color=WHITE,
                                       command=lambda: self._do_format(True))
        self.btn_quick.grid(row=1, column=0, columnspan=2, sticky="ew",
                            padx=12, pady=(8, 2))
        self.btn_full = ctk.CTkButton(fmt_frame, text=tr("btn.full_format"),
                                      fg_color=SEC_BTN, hover_color=SEC_BTN_H,
                                      text_color=SEC_BTN_T,
                                      command=lambda: self._do_format(False))
        self.btn_full.grid(row=1, column=2, columnspan=2, sticky="ew",
                           padx=12, pady=(8, 2))
        self.fmt_hint = ctk.CTkLabel(fmt_frame, text=tr("fmt.hint"),
                                     font=self.font_small, text_color=MUTED)
        self.fmt_hint.grid(row=2, column=0, columnspan=4, sticky="w", padx=12,
                           pady=(2, 10))

        # araçlar: ISO / ZIP / onarım
        tools_frame = ctk.CTkFrame(self)
        tools_frame.grid(row=2, column=1, sticky="nsew", padx=(6, 18), pady=6)
        tools_frame.grid_columnconfigure((0, 1), weight=1)
        self.tools_section = ctk.CTkLabel(tools_frame, text=tr("tools.section"),
                                          font=self.font_small, text_color=MUTED)
        self.tools_section.grid(row=0, column=0, columnspan=2, sticky="w",
                                padx=12, pady=(10, 2))
        self.btn_iso = ctk.CTkButton(tools_frame, text=tr("btn.iso"),
                                     fg_color=ACCENT, hover_color=ACCENT_H,
                                     text_color=WHITE,
                                     command=self._do_iso)
        self.btn_iso.grid(row=1, column=0, sticky="ew", padx=(12, 3), pady=(6, 2))
        self.btn_zip = ctk.CTkButton(tools_frame, text=tr("btn.zip"),
                                     fg_color=SEC_BTN, hover_color=SEC_BTN_H,
                                     text_color=SEC_BTN_T,
                                     command=self._do_zip)
        self.btn_zip.grid(row=1, column=1, sticky="ew", padx=(3, 12), pady=(6, 2))
        self.btn_repair = ctk.CTkButton(tools_frame, text=tr("btn.repair"),
                                        fg_color=DANGER_BTN, hover_color=DANGER_BTN_H,
                                        text_color=WHITE,
                                        command=self._do_repair)
        self.btn_repair.grid(row=2, column=0, columnspan=2, sticky="ew",
                             padx=12, pady=(2, 4))
        self.tools_hint = ctk.CTkLabel(tools_frame, text=tr("tools.hint"),
                                       font=self.font_small, text_color=MUTED,
                                       justify="left")
        self.tools_hint.grid(row=3, column=0, columnspan=2, sticky="w", padx=12,
                             pady=(2, 10))

        # birlesik konsol: canli aktarim satirlari + gunluk kayitlari tek panelde
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, columnspan=2, sticky="nsew",
                       padx=18, pady=(6, 12))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(3, weight=1)
        self.log_section = ctk.CTkLabel(log_frame, text=tr("log.section"),
                                        font=self.font_small, text_color=MUTED)
        self.log_section.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))
        self.btn_clear = ctk.CTkButton(log_frame, text=tr("btn.clear"), width=80,
                                       fg_color=SEC_BTN, hover_color=SEC_BTN_H,
                                       text_color=SEC_BTN_T,
                                       command=self._clear_log)
        self.btn_clear.grid(row=0, column=1, padx=(4, 6))
        self.btn_save_log = ctk.CTkButton(log_frame, text=tr("btn.save"), width=80,
                                          fg_color=SEC_BTN, hover_color=SEC_BTN_H,
                                          text_color=SEC_BTN_T,
                                          command=self._save_console)
        self.btn_save_log.grid(row=0, column=2, padx=(0, 12))
        # Aktarim ozeti (yalnizca aktarim islerinde dolar). Ilerleme cubugu
        # BURADA degil, alttaki tek durum cubugunda gosterilir; boylece
        # ekranda iki ayri ilerleme cubugu karisikligi olmaz.
        self.xf_summary = ctk.CTkLabel(log_frame, text=tr("xf.empty"),
                                       font=self.font_small, text_color=MUTED,
                                       anchor="w")
        self.xf_summary.grid(row=2, column=0, columnspan=3, sticky="ew",
                             padx=12, pady=(0, 2))
        self.log_box = ctk.CTkTextbox(log_frame, font=self.font_mono, wrap="none",
                                      activate_scrollbars=True)
        self.log_box.grid(row=3, column=0, columnspan=3, sticky="nsew",
                          padx=12, pady=(0, 12))
        self._init_xf_tags()

        # durum çubuğu
        status = ctk.CTkFrame(self, fg_color="transparent")
        status.grid(row=4, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 12))
        status.grid_columnconfigure(1, weight=1)
        self.status_label = ctk.CTkLabel(status, text=tr("status.ready"), anchor="w",
                                         font=self.font_small)
        self.status_label.grid(row=0, column=0, sticky="w")
        self.prog = ctk.CTkProgressBar(status, mode="determinate")
        self.prog.set(0)
        self.prog.grid(row=0, column=1, sticky="ew", padx=10)
        self.cancel_btn = ctk.CTkButton(status, text=tr("btn.cancel"), width=90,
                                        fg_color=CANCEL_BTN, hover_color=CANCEL_BTN_H,
                                        text_color=WHITE,
                                        state="disabled", command=self._cancel_task)
        self.cancel_btn.grid(row=0, column=2)

        self.log_box.insert("end", tr("app.starting") + "\n")

    def _refresh_all_text(self) -> None:
        """Dil değişince tüm sabit metinleri yeniler."""
        admin = is_admin()
        self.subtitle_label.configure(text=tr("app.subtitle"))
        self.admin_badge.configure(text=tr("badge.admin") if admin
                                   else tr("badge.limited"))
        self.theme_menu.configure(values=[tr("theme.system"), tr("theme.dark"),
                                          tr("theme.light")])
        self.theme_map = {tr("theme.system"): "system",
                          tr("theme.dark"): "dark",
                          tr("theme.light"): "light"}
        self.theme_menu.set(self.theme_map.get(self.cfg.get("theme"), tr("theme.system")))
        self.lang_menu.set((self.cfg.get("language") or "tr").upper())
        self.btn_about.configure(text=tr("btn.about"))
        self.btn_update.configure(text=tr("btn.update"))
        self.dev_section.configure(text=tr("dev.section"))
        self.folder_section.configure(text=tr("folder.section"))
        self.btn_browse.configure(text=tr("btn.browse"))
        self.btn_copy.configure(text=tr("btn.write_folder"))
        self.btn_zipfolder.configure(text=tr("btn.zip_folder"))
        self.autofmt_switch.configure(text=tr("switch.autofmt"))
        self.reports_switch.configure(text=tr("switch.reports"))
        self.sound_switch.configure(text=tr("switch.sound"))
        self.btn_reports.configure(text=tr("btn.reports"))
        self.fmt_section.configure(text=tr("fmt.section"))
        self.label_caption.configure(text=tr("fmt.label"))
        self.btn_quick.configure(text=tr("btn.quick_format"))
        self.btn_full.configure(text=tr("btn.full_format"))
        self.fmt_hint.configure(text=tr("fmt.hint"))
        self.tools_section.configure(text=tr("tools.section"))
        self.btn_iso.configure(text=tr("btn.iso"))
        self.btn_zip.configure(text=tr("btn.zip"))
        self.btn_repair.configure(text=tr("btn.repair"))
        self.tools_hint.configure(text=tr("tools.hint"))
        self.log_section.configure(text=tr("log.section"))
        self.btn_clear.configure(text=tr("btn.clear"))
        self.btn_save_log.configure(text=tr("btn.save"))
        if not self._xf_count:
            self.xf_summary.configure(text=tr("xf.empty"))
        self.btn_health.configure(text=tr("btn.health"))
        self.cancel_btn.configure(text=tr("btn.cancel"))
        if not self.busy:
            self.status_label.configure(text=tr("status.ready"))
        self._menu_values = []          # dil degisince cihaz menusu yeniden kurulur
        self._menu_current = ""
        self._update_device_card()

    # --------------------------------------------------------- durum UI -----

    def active_device(self) -> Device | None:
        for dev in self.devices:
            if dev.letter == self.active_letter:
                return dev
        return None

    def _target_exists(self) -> bool:
        """Hedef klasor gecerliligi.

        Dosya sistemi sorgusu (``os.path.isdir``) ana thread'de ASLA yapilmaz:
        hedef klasor OneDrive/ag uzerinde olabileceginden sorgu arka planda
        calisir, sonuc kuyruk uzerinden ``_on_target_ok`` ile geri gelir.
        Buradan yalnizca onbellekteki sonuc dondurulur.
        """
        target = (self.target_var.get() or "").strip()
        cached_target, cached_ok, cached_at = self._target_cache
        if cached_target == target and (time.time() - cached_at) < 5.0:
            return cached_ok
        if not self._target_checking:
            self._target_checking = True

            def _probe(probe_target: str = target) -> None:
                try:
                    found = bool(probe_target) and os.path.isdir(probe_target)
                except OSError:
                    found = False
                try:
                    self.q.put(("target_ok", probe_target, found))
                except Exception:
                    pass

            threading.Thread(target=_probe, daemon=True,
                             name="lunaci-target-check").start()
        return cached_ok if cached_target == target else False

    def _on_target_ok(self, target: str, ok: bool) -> None:
        """Arka plan hedef sorgusunun sonucu (ana thread'de calisir)."""
        self._target_checking = False
        if (self.target_var.get() or "").strip() != target:
            return
        self._target_cache = (target, ok, time.time())
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        has_dev = self.active_device() is not None
        busy = self.busy is not None
        has_target = self._target_exists()

        def st(ok: bool) -> str:
            return "normal" if (ok and has_dev and not busy) else "disabled"

        self.btn_quick.configure(state=st(True))
        self.btn_full.configure(state=st(True))
        self.btn_iso.configure(state=st(True))
        self.btn_zip.configure(state=st(True))
        self.btn_repair.configure(state=st(True))
        self.btn_health.configure(state=st(True))
        self.btn_copy.configure(state=st(has_target))
        self.btn_zipfolder.configure(state=st(has_target))
        self.device_menu.configure(state="disabled" if (busy or not has_dev) else "normal")

    def _update_device_card(self) -> None:
        dev = self.active_device()
        if dev is None:
            self.info_label.configure(text=tr("dev.waiting"))
            self.cap_label.configure(text="")
            self.tech_label.configure(text="")
            self.cap_bar.set(0)
            self._update_health_ui(None)
            return
        self.info_label.configure(
            text=f"{dev.name}\n{dev.letter}:  ·  {dev.fstype_display}  ·  "
                 f"{human_bytes(dev.size)}  (boş: {human_bytes(dev.free)})")
        self.cap_bar.set(max(0.0, min(1.0, dev.used_ratio)))
        self.cap_label.configure(
            text=tr("dev.usage", p=f"{dev.used_ratio * 100:.1f}",
                    u=human_bytes(dev.used), t=human_bytes(dev.size)))
        extra = []
        if dev.bus:
            extra.append(f"{tr('dev.bus')}: {dev.bus}")
        if dev.disk_number is not None:
            extra.append(f"Disk #{dev.disk_number}")
        if dev.readonly:
            extra.append(tr("dev.readonly"))
        self.tech_label.configure(text="  ·  ".join(extra))
        self._update_health_ui(dev.letter)

    def _update_health_ui(self, letter) -> None:
        status, _info = self.health.get(letter, ("unknown", {}))
        self.led.configure(text_color=LED_COLORS.get(status, LED_COLORS["unknown"]))
        key = HEALTH_KEY.get(status)
        text = tr(key) if key else "—"
        self.health_label.configure(text=tr("health.status", s=text))

    def _sync_fs_for(self, dev: Device) -> None:
        """Cihaz değişince dosya sistemini ve birim adını mevcut değerlerle doldur."""
        opt = (fstype_to_option(dev.fstype) or dev.suggested_fs() or "FAT32")
        if opt not in FS_OPTIONS:
            opt = "FAT32"
        self.fs_var.set(opt)
        # Birim adı: cihazın mevcut etiketi varsayılan olsun
        self.label_var.set(dev.label or (self.cfg.get("volume_label") or "LUNACI"))
        self._fs_synced_letter = dev.letter

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    # --------------------------------------------------------- olaylar ------

    def _poll(self) -> None:
        """Kuyrugu bosaltir. Hangi olay gelirse gelsin DONMAZ: tum dongu
        try/except ile korunur ve ``after`` her durumda yeniden kurulur.
        Log kayitlari tek tek degil, TEK seferde toplu yazilir (UI tikanmaz)."""
        logs = []
        try:
            for _ in range(2000):
                try:
                    kind, *payload = self.q.get_nowait()
                except queue.Empty:
                    break
                try:
                    if kind == "log":
                        logs.append(payload[0])
                    elif kind == "devices":
                        self._on_devices(payload[0])
                    elif kind == "health":
                        letter, status, info = payload
                        self.health[letter] = (status, info)
                        if letter == self.active_letter:
                            self._update_health_ui(letter)
                    elif kind == "progress":
                        self._on_progress(payload[0],
                                          payload[1] if len(payload) > 1 else None)
                    elif kind == "file":
                        self._on_file(*payload)
                    elif kind == "target_ok":
                        self._on_target_ok(payload[0], payload[1])
                    elif kind == "update_check":
                        self._on_update_check(*payload)
                    elif kind == "task_done":
                        self._on_task_done(*payload)
                except Exception as exc:
                    self._report_callback_error(exc)
            if logs:
                self._insert_logs(logs)
        except Exception as exc:
            self._report_callback_error(exc)
        finally:
            try:
                self.after(80, self._poll)
            except Exception:
                pass

    def _report_callback_error(self, exc: BaseException) -> None:
        """Arayuz geri cagrisindaki hatayi yutar ama error.log'a yazar."""
        try:
            import traceback
            with open(os.path.join(BASE_DIR, "error.log"), "a", encoding="utf-8") as f:
                f.write(f"[ui-callback] {type(exc).__name__}: {exc}\n")
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass

    def _on_devices(self, devices: list) -> None:
        self.devices = devices
        letters = [d.letter for d in devices]
        if self.active_letter not in letters:
            preferred = self.cfg.get("last_device")
            self.active_letter = (preferred if preferred in letters
                                  else (letters[0] if letters else None))
        self._device_map = {d.display: d.letter for d in devices}
        if devices:
            cur = next((d.display for d in devices if d.letter == self.active_letter),
                       devices[0].display)
            values = [d.display for d in devices]
        else:
            cur = tr("dev.empty")
            values = [tr("dev.empty")]
        # Menu yalnizca gerçekten degistiysa yeniden kurulur (her 3 sn'de
        # yeniden olusturmak gereksiz CPU/çizim yükü yapiyordu).
        if values != self._menu_values:
            self._menu_values = values
            self.device_menu.configure(values=values)
        if cur != self._menu_current:
            self._menu_current = cur
            self.device_menu.set(cur)
        self._update_device_card()

        dev = self.active_device()
        if dev and dev.letter != self._fs_synced_letter:
            self._sync_fs_for(dev)
        if (self.cfg.get("last_device") or "") != (self.active_letter or ""):
            self.cfg.set("last_device", self.active_letter or "")

        new_letters = set(letters) - self.known_letters
        self.known_letters = set(letters)
        for letter in list(self.health):
            if letter not in self.known_letters:
                del self.health[letter]
        # Otomatik sağlık testi yalnızca açıkça etkinse (isteğe bağlı)
        for letter in sorted(new_letters):
            if self.cfg.get("auto_health_check") and not self.busy:
                self._do_health(letter)
                break
        self._refresh_actions()

    def _on_device_pick(self, display: str) -> None:
        letter = self._device_map.get(display)
        if not letter or letter == self.active_letter:
            return
        self.active_letter = letter
        self.cfg.set("last_device", letter)
        dev = self.active_device()
        if dev:
            self._sync_fs_for(dev)
        self._update_device_card()
        self._refresh_actions()

    # --------------------------------------------------- canlı aktarım ------

    def _xf_color(self, state: str) -> str:
        light, dark = XF_COLORS.get(state, ("#33383d", "#c9d1d9"))
        return dark if ctk.get_appearance_mode() == "Dark" else light

    def _init_xf_tags(self) -> None:
        inner = getattr(self.log_box, "_textbox", None)
        if inner is None:
            return
        for state in XF_COLORS:
            try:
                inner.tag_config(f"xf_{state}", foreground=self._xf_color(state))
            except Exception:
                pass

    def _xf_reset(self) -> None:
        """Birlesik konsolu temizler (yeni gorev basinda cagrilir)."""
        self._xf_rows = {}
        self._xf_count = 0
        self._xf_head = (0, 0, "")
        try:
            self.log_box.delete("1.0", "end")
        except Exception:
            pass
        try:
            self.log_box.mark_unset(self.XF_MARK)
        except Exception:
            pass
        self._log_tags.clear()
        try:
            self.xf_summary.configure(text=tr("xf.empty"))
        except Exception:
            pass

    def _on_file(self, name, size, state, speed, done, total, summary) -> None:
        """Dosya aktarim olayi (ana thread'de calisir).

        Aktarim satirlari konsolun sonundaki bitisik blogu olusturur; ayni
        dosyanin satiri yerinde guncellenir, boylece liste uzayip karmaşa
        olusturmaz. Index'ler widget'in kendi satir numaralarindan turetilir
        (elle tutulan sayac zamanla kayabilirdi).
        """
        key = str(name)
        line = self._xf_line(key, size, state, speed)
        try:
            if key in self._xf_rows:
                self._replace_xf_row(self._xf_rows[key], line, state)
            else:
                if self._xf_count >= self._xf_max:
                    self._trim_xf_rows()
                first_row = self._xf_count == 0
                # Aktarim satirlari her zaman blogun sonuna eklenir.
                self.log_box.insert("end", line + "\n", f"xf_{state}")
                self._xf_rows[key] = self._log_end()
                self._xf_count += 1
                if first_row:
                    # Blok tepesi: az once eklenen ilk satirin baslangici.
                    self._ensure_mark(f"{self._xf_rows[key]}.0")
            if state in ("active", "done", "error"):
                self.log_box.see("end")
        except Exception as exc:
            self._report_callback_error(exc)
        self._xf_head = (done, total, summary)
        self._xf_update_summary()

    def _xf_line(self, name, size, state, speed) -> str:
        icon = XF_ICON.get(state, "·")
        label = tr(XF_STATE_KEY.get(state, "xf.state.done"))
        text = name if len(name) <= 64 else "…" + name[-63:]
        sp = f"{speed:.1f} MB/s" if speed else ""
        return f"{icon}  {text:<64}  {label:<11} {human_bytes(size):>10}  {sp:>12}"

    def _xf_update_summary(self) -> None:
        done, total, summary = self._xf_head
        if not total:
            return
        text = tr("xf.summary", d=done, t=total, s=summary or "")
        try:
            self.xf_summary.configure(text=text.strip())
        except Exception:
            pass

    # ------------------------------------------- konsol satir yonetimi ------

    # Aktarim blogunun tepesini isaretleyen Tk mark adi. Mark, onune metin
    # eklendiginde kendiliginden kayar; boylece satir index'lerini elle
    # saymak zorunda kalmayiz (eski sayac yaklasimi zamanla kayiyordu).
    XF_MARK = "xf_block_start"

    def _log_end(self) -> int:
        """Konsolun son DOLU satir numarasi (bos konsol icin 0)."""
        try:
            content = self.log_box.get("1.0", "end")
            if not content or content == "\n":
                return 0
            # get() sonuna bir "\n" ekler; satir sayisini ona gore hesapla.
            return max(0, len(content.rstrip("\n").split("\n")))
        except Exception:
            return 0

    def _ensure_mark(self, index: str = "end-1c") -> None:
        """Aktarim blogu baslangic mark'ini (yoksa) verilen konuma kurar.

        Gravity ``right`` (Tk varsayilani) kritik: mark'a metin eklendiginde
        mark eklenen metnin ARDINA kayar. Gunlukler hep mark'a eklendigi icin
        mark blokla birlikte asagi iner ve blogun gercek baslangicini gosterir.
        """
        try:
            if self.XF_MARK not in self.log_box.mark_names():
                self.log_box.mark_set(self.XF_MARK, index)
            self.log_box.mark_gravity(self.XF_MARK, "right")
        except Exception:
            pass

    def _block_start(self) -> int:
        """Aktarim blogunun ilk satir numarasi (blok yoksa 0)."""
        if not self._xf_count:
            return 0
        try:
            if self.XF_MARK not in self.log_box.mark_names():
                return 0
            idx = self.log_box.index(self.XF_MARK)   # "satir.kolon"
            return int(str(idx).split(".")[0])
        except Exception:
            return 0

    def _reindex_xf_rows(self) -> None:
        """Mark'tan baslayarak aktarim blogunun satir index'lerini tazeler."""
        if not self._xf_rows:
            return
        base = self._block_start()
        if base <= 0:
            return
        for i, key in enumerate(list(self._xf_rows)):
            self._xf_rows[key] = base + i

    def _append_xf_row(self, key: str, line: str, state: str) -> None:
        """Aktarim satirini blogun SONUNA ekler."""
        try:
            self.log_box.insert("end", line + "\n", f"xf_{state}")
        except Exception:
            self.log_box.insert("end", line + "\n")
        self._xf_rows[key] = self._log_end()

    def _replace_xf_row(self, idx: int, line: str, state: str) -> None:
        """Mevcut aktarim satirini yerinde gunceller (satir sayisi degismez)."""
        try:
            self.log_box.delete(f"{idx}.0", f"{idx}.end")
            self.log_box.insert(f"{idx}.0", line, f"xf_{state}")
        except Exception:
            pass

    def _trim_xf_rows(self) -> None:
        """Blok 3000 satiri gecince en eski aktarim satirlarini siler."""
        excess = self._xf_count - self._xf_max
        if excess <= 0:
            return
        keys = list(self._xf_rows)[:excess]
        first = self._xf_rows[keys[0]]
        try:
            self.log_box.delete(f"{first}.0", f"{first + excess}.0")
        except Exception:
            return
        for key in keys:
            self._xf_rows.pop(key, None)
        self._xf_count = len(self._xf_rows)
        # Silinen satirlardan sonra mark dogru yerde mi? Blok basi artik
        # "first" satirinda; mark'i oraya tasi.
        try:
            self.log_box.mark_set(self.XF_MARK, f"{first}.0")
        except Exception:
            pass
        self._reindex_xf_rows()

    def _on_progress(self, pct, text: str | None = None) -> None:
        """Ilerleme cubugunu gunceller. Bozuk/eksik deger gelse bile arayuz
        ASLA hata vermemeli (beklenmeyen tur degerleri sessizce yutulur)."""
        try:
            if pct is None:
                # Olculemeyen asama (or. diskpart): belirsiz mod
                if not self._indeterminate:
                    self.prog.configure(mode="indeterminate")
                    self.prog.start()          # CTk: start() argümansiz
                    self._indeterminate = True
            else:
                if self._indeterminate:
                    self.prog.stop()
                    self.prog.configure(mode="determinate")
                    self._indeterminate = False
                self.prog.set(max(0.0, min(1.0, float(pct) / 100.0)))
        except (TypeError, ValueError, tk.TclError):
            pass
        if text:
            self._set_status(text)

    def _insert_logs(self, records) -> None:
        """Bir grup log kaydini TEK seferde yazar.

        Birlesik konsolda dosya aktarim satirlari her zaman en alttaki bitisik
        blogu olusturur; gunluk kayitlari bu blogun USTUNE yazilir. Boylece tek
        panelde hem zaman damgali gunlukler hem de canli dosya listesi ayri
        ayri, birbirine karismadan gorunur.

        Eski sürüm her satiri ayri ayri ekleyip her seferinde ``see("end")``
        cagiriyordu; binlerce dosyada bu ana thread'i doyurup arayuzu kilitliyordu.
        Burada ardisik ayni seviyedeki satirlar birlestirilip tek ``insert`` ile
        yazilir ve yalnizca sonda bir kez kaydirilir.
        """
        total = len(records)
        if not total:
            return
        # Aktarim blogunun baslangici: gunlukler bu satirin USTUNE girer.
        # Mark tabanli index her zaman dogrudur; elle sayilan end-count+1
        # yontemi blogun ilk satiri log'lardan sonra eklendiginde kayiyordu.
        base = self._block_start()
        insert_at = f"{base}.0" if base > 0 else "end"
        inner = getattr(self.log_box, "_textbox", None)
        if inner is None:
            chunk = "".join(
                f"[{r.time_str}] [{r.level:<5}] {r.message}\n" for r in records)
            try:
                self.log_box.insert(insert_at, chunk)
            except Exception:
                pass
        else:
            i = 0
            while i < total:
                level = records[i].level
                j = i
                parts = []
                while j < total and records[j].level == level:
                    r = records[j]
                    parts.append(f"[{r.time_str}] [{r.level:<5}] {r.message}\n")
                    j += 1
                chunk = "".join(parts)
                self._ensure_log_tag(level, inner)
                try:
                    inner.insert(insert_at, chunk, level)
                except Exception:
                    try:
                        self.log_box.insert(insert_at, chunk)
                    except Exception:
                        pass
                i = j
        # Aktarim blogu asagi kaydi; index'leri yeniden hesapla.
        if self._xf_count:
            self._reindex_xf_rows()
        # Gunluk gecmisi cok uzarsa en eskileri at (aktarim blogu korunur).
        try:
            limit = 5000 + self._xf_count
            live = self._log_end()
            if live > limit:
                drop = live - limit
                self.log_box.delete("1.0", f"{drop + 1}.0")
                if self._xf_count:
                    self._reindex_xf_rows()
        except Exception:
            pass
        try:
            self.log_box.see("end")
        except Exception:
            pass

    def _ensure_log_tag(self, level: str, inner) -> None:
        """Gunluk etiketini (tag) mevcut temaya gore ayarlar."""
        if level in self._log_tags:
            return
        try:
            inner.tag_config(level, foreground=self._log_color(level))
        except Exception:
            pass
        self._log_tags.add(level)

    def _log_color(self, level: str) -> str:
        light, dark = LOG_COLORS.get(level, ("#33383d", "#c9d1d9"))
        return dark if ctk.get_appearance_mode() == "Dark" else light

    def _refresh_log_tags(self) -> None:
        """Tema degisince mevcut gunluk etiket renklerini yeniler."""
        inner = getattr(self.log_box, "_textbox", None)
        if inner is None:
            return
        for level in list(self._log_tags):
            try:
                inner.tag_config(level, foreground=self._log_color(level))
            except Exception:
                pass

    def _insert_log(self, rec) -> None:
        """Geriye dönük uyumluluk için tek kayıt ekler."""
        self._insert_logs([rec])

    def _log(self, level: str, msg: str) -> None:
        fn = getattr(self._ui_emitter, level.lower(), self._ui_emitter.info)
        fn(msg)

    # ------------------------------------------------------- görev motoru ---

    def _start_task(self, key: str, status_text: str, fn, cancellable=True) -> None:
        if self.busy:
            self._log("WARN", tr("ui.busy", k=self.busy))
            return
        if key in NEED_ADMIN and not is_admin():
            self._log("ERROR", tr("ui.admin_needed"))
            self._set_status(tr("status.failed"))
            return
        self.busy = key
        self.cancel_event.clear()
        logger = Emitter(self.q.put, task=key)
        self._set_status(status_text)
        try:
            self.prog.stop()
            self.prog.configure(mode="determinate")
            self._indeterminate = False
            self.prog.set(0)
        except Exception:
            pass
        if key in XF_TASKS:
            self._xf_reset()
        self.cancel_btn.configure(state="normal" if cancellable else "disabled")
        self._refresh_actions()

        def runner() -> None:
            ok, extra = False, None
            try:
                res = fn(logger)
                if isinstance(res, tuple):
                    ok, extra = bool(res[0]), res[1]
                else:
                    ok = bool(res)
            except Exception as exc:
                logger.error(f"Beklenmeyen hata: {exc}")
            finally:
                self.q.put(("task_done", key, ok, logger, extra))

        threading.Thread(target=runner, daemon=True, name=f"lunaci-{key}").start()

    def _on_task_done(self, key: str, ok: bool, logger: Emitter, extra) -> None:
        self.busy = None
        if self._indeterminate:
            self.prog.stop()
            self.prog.configure(mode="determinate")
            self._indeterminate = False
        self.prog.set(0.0)
        self.cancel_btn.configure(state="disabled")
        self._set_status(tr("status.ready") if ok else tr("status.failed"))
        self._refresh_actions()

        if ok and key == "format" and isinstance(extra, str) and extra in FS_OPTIONS:
            self.fs_var.set(extra)
            if self.active_letter:
                self._fs_synced_letter = self.active_letter
            self.cfg.set("preferred_filesystem", extra)

        # Raporlar her zaman programın yanındaki reports klasörüne.
        # Yazma arka planda yapilir: rapor klasoru de OneDrive içinde
        # olabildiginden ana arayuz thread'i asla bloklanmaz.
        if ok and self.cfg.get("save_reports"):
            folder = self.reports_dir()
            ts = time.strftime("%Y%m%d_%H%M%S")
            header = (f"{APP_NAME} — {key}\n"
                      f"Tarih / Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                      f"Cihaz / Device: {self.active_letter or '-'}:\n"
                      f"Sonuç / Result: OK\n" + "=" * 64 + "\n")
            text = header + "\n".join(logger.capture) + "\n"
            name = f"{key}_{ts}.txt"

            def _save() -> None:
                try:
                    path = save_report(text, folder, name)
                    self._ui_emitter.ok(tr("ui.report_saved", p=path))
                except Exception as exc:
                    self._ui_emitter.error(tr("ui.report_error", e=exc))

            threading.Thread(target=_save, daemon=True,
                             name="lunaci-report").start()

        if ok and key in ("format", "repair", "iso", "zip", "copy", "zipfolder"):
            self.monitor.request_poll(force=True)
        if self.cfg.get("sound_on_complete") and key in SOUND_TASKS:
            play_notification(ok)
        if key == "update_download":
            self._complete_update_download(ok, extra)

    def _cancel_task(self) -> None:
        if self.busy:
            self.cancel_event.set()
            self._log("WARN", tr("ui.cancel_req"))

    def _progress_emit(self, pct, text=None) -> None:
        self.q.put(("progress", pct, text))

    # --------------------------------------------------------- eylemler -----

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(title=tr("pick.folder_title"))
        if path:
            self.target_var.set(path)
            self._target_cache = (None, False, 0.0)   # hedef degisti
            self.cfg.set("target_folder", path)
            self._refresh_actions()

    def _toggle_reports(self) -> None:
        self.cfg.set("save_reports", bool(self.reports_switch.get()))

    def _toggle_autofmt(self) -> None:
        self.cfg.set("auto_format_before_write", bool(self.autofmt_switch.get()))

    def _toggle_sound(self) -> None:
        self.cfg.set("sound_on_complete", bool(self.sound_switch.get()))

    def autofmt_enabled(self) -> bool:
        return bool(self.autofmt_switch.get())

    def _fmt_opts_snapshot(self) -> "dict | None":
        """ANA iş parçacığında biçimlendirme seçeneklerini anlık okur.

        Görev iş parçacığı asla Tk widget/variable'ına dokunmamalı: Tcl bu
        erişimleri ana döngüye kilitler ve arayüz kalıcı donar (yaşanan hata).
        """
        if not self.autofmt_switch.get():
            return None
        return {"fs": self.fs_var.get(),
                "label": self.label_var.get().strip() or "LUNACI"}

    def _preflight_format(self, logger, dev, fmt_opts) -> bool:
        """Yazma işleminden önce açıksa hızlı biçimlendirme yapar.

        ``fmt_opts`` ana iş parçacığından gelir (None = kapalı). Bu metot
        görev iş parçacığında koşar ve Tk'ya dokunmaz. Biçimlendirme sonrası
        diskin yeniden erişilebilir olması beklenir; aksi halde yazım hemen
        başlayınca "disk bulunamadı" hatası alınırdı.
        """
        if not fmt_opts:
            self._log("INFO", tr("ui.autofmt_skip"))
            return True
        if not is_admin():
            logger.error(tr("ui.admin_needed"))
            return False
        fs = fmt_opts.get("fs") or "FAT32"
        if fs.startswith("EXT4"):
            logger.error(tr("fmt.ext4_err"))
            return False
        label = fmt_opts.get("label") or "LUNACI"
        letter = dev.letter
        size_hint = dev.size
        logger.info(tr("ui.autofmt_start"))
        if not run_format(logger, letter, fs, label, quick=True,
                          size_hint=size_hint, cancel=self.cancel_event):
            return False
        # Format sonrası diskin geri gelmesini bekle (en fazla 30 sn)
        if not self._wait_drive_ready(letter, logger, timeout=30.0):
            return False
        self.monitor.request_poll(force=True)
        return True

    def _wait_drive_ready(self, letter: str, logger: Emitter,
                          timeout: float = 30.0) -> bool:
        """diskpart sonrası diskin yeniden erişilebilir olmasını bekler."""
        root = f"{letter}:\\"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.cancel_event.is_set():
                return False
            if os.path.isdir(root):
                try:
                    os.listdir(root)
                    logger.ok(tr("ui.autofmt_ready", l=letter))
                    return True
                except OSError:
                    pass
            time.sleep(0.5)
        logger.error(tr("ui.autofmt_not_ready", l=letter))
        return False

    def _open_reports(self) -> None:
        folder = self.reports_dir()
        self._log("INFO", tr("ui.reports_open", p=folder))
        try:
            os.startfile(folder)
        except OSError as exc:
            self._log("ERROR", tr("ui.report_error", e=exc))

    def _on_theme(self, choice: str) -> None:
        key = self.theme_map.get(choice, "system")
        ctk.set_appearance_mode(THEME_TO_MODE.get(key, "System"))
        self.cfg.set("theme", key)
        # Konsol satirlari eski temanin rengini korur; ikisini de yenile
        # (gunluk etiketleri + aktarim durum renkleri).
        self.after(50, self._refresh_log_tags)
        self.after(50, self._init_xf_tags)

    def _on_language(self, choice: str) -> None:
        lang = "en" if choice == "EN" else "tr"
        if lang == (self.cfg.get("language") or "tr"):
            return
        i18n.set_language(lang)
        self.cfg.set("language", lang)
        self._refresh_all_text()
        self._log("INFO", "Language changed / Dil değiştirildi → " + lang.upper())

    def _do_copy(self) -> None:
        dev = self.active_device()
        src = (self.target_var.get() or "").strip()
        if not dev or not src or not os.path.isdir(src):
            return
        engine = self.cfg.get("copy_engine") or "shutil"
        # GUVENLIK: otomatik bicimlendirme acikken diske yazmak TUM veriyi
        # silebilir; bu yuzden yazmadan once mutlaka onay istenir.
        if not messagebox.askyesno(
                tr("dlg.copy.title"),
                tr("dlg.copy.body", name=os.path.basename(src), l=dev.letter,
                   dev=dev.name)
                + ("\n\n" + tr("dlg.will_format") if self.autofmt_enabled() else ""),
                icon="warning"):
            return
        self._log("INFO", tr("ui.copy_engine", l=dev.letter, e=engine))
        fmt_opts = self._fmt_opts_snapshot()   # ANA iş parçacığında oku

        def file_emit(name, size, state, speed, done, total, summary):
            self.q.put(("file", name, size, state, speed, done, total, summary))

        def task(logger):
            if not self._preflight_format(logger, dev, fmt_opts):
                return False, None
            return copy_folder(src, dev.letter, logger, self.cancel_event,
                               engine=engine, progress=self._progress_emit,
                               file_cb=file_emit), None

        self._start_task("copy", tr("task.copy", l=dev.letter), task, cancellable=True)
    def _do_zipfolder(self) -> None:
        dev = self.active_device()
        src = (self.target_var.get() or "").strip()
        if not dev or not src or not os.path.isdir(src):
            return
        if not messagebox.askyesno(
                tr("dlg.zipfolder.title"),
                tr("dlg.zipfolder.body", name=os.path.basename(src), l=dev.letter)
                + ("\n\n" + tr("dlg.will_format") if self.autofmt_enabled() else "")):
            return

        fmt_opts = self._fmt_opts_snapshot()   # ANA iş parçacığında oku

        def task(logger):
            if not self._preflight_format(logger, dev, fmt_opts):
                return False, None
            return zip_folder_to_device(src, dev.letter, logger, self.cancel_event,
                                        progress=self._progress_emit), None

        self._start_task("zipfolder", tr("task.zipfolder", l=dev.letter), task,
                         cancellable=True)

    def _do_format(self, quick: bool) -> None:
        dev = self.active_device()
        if not dev:
            return
        fs = self.fs_var.get()
        label = self.label_var.get().strip() or "LUNACI"
        if fs.startswith("EXT4"):
            messagebox.showwarning(tr("dlg.ext4.title"), tr("dlg.ext4.body"))
            return
        mode = tr("dlg.mode.quick") if quick else tr("dlg.mode.full")
        if not messagebox.askyesno(
                tr("dlg.fmt.title"),
                tr("dlg.fmt.body", l=dev.letter, name=dev.name,
                   size=human_bytes(dev.size), fs=fs, mode=mode),
                icon="warning"):
            return

        def task(logger):
            ok = run_format(logger, dev.letter, fs, label, quick=quick,
                            size_hint=dev.size, cancel=self.cancel_event)
            return (ok, fs if ok else None)

        self._start_task("format", tr("task.format", l=dev.letter), task,
                         cancellable=False)

    def _do_repair(self) -> None:
        dev = self.active_device()
        if not dev:
            return
        if not messagebox.askyesno(tr("dlg.repair.title"),
                                   tr("dlg.repair.body", l=dev.letter),
                                   icon="warning"):
            return

        def task(logger):
            return run_repair(logger, dev.letter, cancel=self.cancel_event), None

        self._start_task("repair", tr("task.repair", l=dev.letter), task,
                         cancellable=False)

    def _choose_iso_mode(self, path: str, size: int, dev: Device) -> str | None:
        """ISO yazım modunu seçtiren pencere. ``None`` = iptal."""
        win = ctk.CTkToplevel(self)
        win.title(tr("iso.dlg.title"))
        win.geometry("480x340")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        ctk.CTkLabel(win, text=os.path.basename(path),
                     font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                     wraplength=420).pack(pady=(18, 2))
        ctk.CTkLabel(win, text=f"{human_bytes(size)}  ·  {dev.letter}: ({dev.name})",
                     text_color=MUTED, font=self.font_small).pack()

        values = [tr(k) for k in ISO_MODE_KEYS]
        mode_map = {tr(k): ISO_MODE_VALUES[k] for k in ISO_MODE_KEYS}
        seg = ctk.CTkSegmentedButton(win, values=values, width=420,
                                     font=self.font_small,
                                     selected_color=SEL_COLOR,
                                     selected_hover_color=SEL_COLOR_H)
        seg.set(values[0])
        seg.pack(pady=(18, 6))
        ctk.CTkLabel(win, text=tr("iso.mode.hint"), text_color=MUTED,
                     font=self.font_small, wraplength=420, justify="left").pack(
            padx=18, anchor="w")
        if self.autofmt_enabled():
            ctk.CTkLabel(win, text=tr("dlg.will_format"), text_color="#d29922",
                         font=self.font_small, wraplength=420,
                         justify="left").pack(padx=18, pady=(8, 0), anchor="w")

        chosen = {}

        def ok():
            chosen["mode"] = mode_map.get(seg.get(), "auto")
            win.destroy()

        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(side="bottom", pady=14)
        ctk.CTkButton(row, text=tr("iso.btn.write"), width=110,
                      fg_color=ACCENT, hover_color=ACCENT_H, text_color=WHITE,
                      command=ok).pack(side="left", padx=6)
        ctk.CTkButton(row, text=tr("btn.cancel"), width=90,
                      fg_color=CANCEL_BTN, hover_color=CANCEL_BTN_H,
                      text_color=WHITE,
                      command=win.destroy).pack(side="left", padx=6)
        win.wait_window()
        return chosen.get("mode")

    def _do_iso(self) -> None:
        dev = self.active_device()
        if not dev:
            return
        path = filedialog.askopenfilename(
            title=tr("pick.iso_title"),
            filetypes=[(tr("file.iso"), "*.iso"), (tr("file.all"), "*.*")])
        if not path:
            return
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        mode = self._choose_iso_mode(path, size, dev)
        if not mode:
            return
        if not messagebox.askyesno(
                tr("dlg.iso.title"),
                tr("dlg.iso.body", name=os.path.basename(path),
                   size=human_bytes(size), l=dev.letter, dev=dev.name)
                + ("\n\n" + tr("dlg.will_format") if self.autofmt_enabled() else ""),
                icon="warning"):
            return

        fmt_opts = self._fmt_opts_snapshot()   # ANA iş parçacığında oku

        def file_emit(name, size_bytes, state, speed, done, total, summary):
            self.q.put(("file", name, size_bytes, state, speed, done, total, summary))

        def task(logger):
            if not self._preflight_format(logger, dev, fmt_opts):
                return False, None
            return write_image(path, dev.letter, logger, self.cancel_event,
                               mode=mode, progress=self._progress_emit,
                               file_cb=file_emit), None

        self._start_task("iso", tr("task.iso", l=dev.letter), task, cancellable=True)

    def _do_zip(self) -> None:
        dev = self.active_device()
        if not dev:
            return
        path = filedialog.askopenfilename(
            title=tr("pick.zip_title"),
            filetypes=[(tr("file.zip"), "*.zip"), (tr("file.all"), "*.*")])
        if not path:
            return
        if not messagebox.askyesno(
                tr("dlg.zip.title"),
                tr("dlg.zip.body", name=os.path.basename(path),
                   l=dev.letter, dev=dev.name)
                + ("\n\n" + tr("dlg.will_format") if self.autofmt_enabled() else ""),
                icon="warning"):
            return

        fmt_opts = self._fmt_opts_snapshot()   # ANA iş parçacığında oku

        def file_emit(name, size, state, speed, done, total, summary):
            self.q.put(("file", name, size, state, speed, done, total, summary))

        def task(logger):
            if not self._preflight_format(logger, dev, fmt_opts):
                return False, None
            return write_zip_to_device(path, dev.letter, logger, self.cancel_event,
                                       progress=self._progress_emit,
                                       file_cb=file_emit), None

        self._start_task("zip", tr("task.zip", l=dev.letter), task, cancellable=True)

    def _do_health(self, letter: str | None = None) -> None:
        if letter is None:
            dev = self.active_device()
            if not dev:
                return
            letter = dev.letter
        dev = next((d for d in self.devices if d.letter == letter), None)
        if not dev:
            return

        def task(logger):
            status, info = run_health_test(
                dev, logger, self.cancel_event,
                int(self.cfg.get("health_test_mb") or 8))
            self.q.put(("health", letter, status, info))
            return (status != CRIT, None)

        self._start_task("health", tr("task.health", l=dev.letter), task,
                         cancellable=True)

    # ------------------------------------------------------- hakkında -------

    def _show_about(self) -> None:
        if self._about is not None and self._about.winfo_exists():
            self._about.focus()
            return
        win = ctk.CTkToplevel(self)
        win.title(tr("dlg.about.title"))
        win.geometry("460x430")
        win.resizable(False, False)
        win.transient(self)
        self._about = win

        try:
            from PIL import Image
            logo_img = ctk.CTkImage(
                light_image=Image.open(resource_path("assets/logo.jpg")),
                dark_image=Image.open(resource_path("assets/logo.jpg")),
                size=(110, 110))
            ctk.CTkLabel(win, image=logo_img, text="").pack(pady=(22, 6))
        except Exception:
            pass

        ctk.CTkLabel(win, text=APP_NAME,
                     font=ctk.CTkFont(family="Segoe UI", size=17,
                                      weight="bold")).pack(pady=(4, 2))
        ctk.CTkLabel(win, text=f"{tr('about.version')} {APP_VERSION}",
                     text_color=MUTED, font=self.font_small).pack()

        def link(text: str, url: str) -> None:
            lbl = ctk.CTkLabel(win, text=text, text_color=LINK,
                               font=ctk.CTkFont(family="Segoe UI", size=13,
                                                underline=True),
                               cursor="hand2")
            lbl.pack(pady=3)
            lbl.bind("<Button-1>", lambda e, u=url: _open_url(u))

        def _open_url(url: str) -> None:
            import webbrowser
            webbrowser.open(url)

        ctk.CTkLabel(win, text=f"{tr('about.maker')}: Cengiz Kemeç",
                     font=self.font_ui).pack(pady=(14, 2))
        link(WEBSITE_URL, WEBSITE_URL)
        link(f"GitHub → {GITHUB_URL}", GITHUB_URL)

        ctk.CTkButton(win, text=tr("btn.update"),
                      fg_color=SEC_BTN, hover_color=SEC_BTN_H,
                      text_color=SEC_BTN_T,
                      command=lambda: (win.destroy(), self._check_updates())).pack(
            side="bottom", pady=(2, 14))
        ctk.CTkButton(win, text="✕", width=40, fg_color=DANGER_BTN,
                      hover_color=DANGER_BTN_H, text_color=WHITE,
                      command=win.destroy).pack(
            side="bottom", pady=14)

    # ------------------------------------------------------- güncelleme -----

    def _check_updates(self, silent: bool = False) -> None:
        """GitHub'daki en son sürümü arka planda denetler (arayüzü bloklamaz)."""
        if self._update_running:
            return
        self._update_running = True
        self._set_status(tr("update.checking"))
        if not silent:
            self._log("INFO", tr("update.checking"))

        def worker() -> None:
            info, err = None, ""
            try:
                info = updater.check_for_update()
            except Exception as exc:
                err = str(exc)
            try:
                self.q.put(("update_check", info, err, silent))
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True, name="lunaci-update").start()

    def _on_update_check(self, info, err: str, silent: bool) -> None:
        """Guncelleme denetimi sonucu (ana thread'de calisir)."""
        self._update_running = False
        if self.busy is None:
            self._set_status(tr("status.ready"))
        if err:
            if not silent:
                self._log("ERROR", tr("update.error", e=err))
            return
        if not info or not updater.is_newer(info.version):
            if not silent:
                self._log("OK", tr("update.latest", cur=APP_VERSION))
            return
        self._log("OK", tr("update.found", new=info.version, cur=APP_VERSION,
                           notes=tr("update.notes_empty")))
        if not updater.updater_supported() or not info.has_asset:
            self._log("WARN", tr("update.source_only"))
            try:
                import webbrowser
                webbrowser.open(info.page_url)
            except Exception:
                pass
            return
        if not messagebox.askyesno(
                tr("btn.update"),
                tr("update.found", new=info.version, cur=APP_VERSION,
                   notes=(info.notes or "").strip() or tr("update.notes_empty"))):
            return
        self._start_update_download(info)

    def _start_update_download(self, info) -> None:
        if self.busy:
            self._log("WARN", tr("ui.busy", k=self.busy))
            return
        self._log("INFO", tr("update.downloading", p=info.asset_name))

        def task(logger):
            script = updater.download_update(info, logger,
                                             progress=self._progress_emit)
            return True, script

        self._start_task("update_download", tr("update.downloading", p=""),
                         task, cancellable=True)

    def _complete_update_download(self, ok: bool, script) -> None:
        if not ok or not script:
            return
        self._log("OK", tr("update.downloaded"))
        if not messagebox.askyesno(tr("btn.update"), tr("update.downloaded")):
            return
        if updater.launch_updater(script):
            self._log("OK", tr("update.applied"))
            self.after(600, self._on_close)
        else:
            self._log("ERROR", tr("update.error", e="launch"))

    # ------------------------------------------------------- konsol UI ------

    def _clear_log(self) -> None:
        self._xf_reset()

    def _save_console(self) -> None:
        text = self.log_box.get("1.0", "end")
        try:
            path = save_report(text, self.reports_dir(),
                               f"lunaci_log_{time.strftime('%Y%m%d_%H%M%S')}.txt")
            self._log("OK", tr("ui.console_saved", p=path))
        except Exception as exc:
            self._log("ERROR", tr("ui.console_error", e=exc))

    # ------------------------------------------------------------- kapat ---

    def _on_close(self) -> None:
        try:
            self.monitor.stop()
        except Exception:
            pass
        self.cancel_event.set()
        try:
            self.cfg.set("volume_label", self.label_var.get().strip() or "LUNACI")
            theme = self.theme_map.get(self.theme_menu.get(), "system")
            self.cfg.set("theme", theme)
        except Exception:
            pass
        # Bekleyen ayar yazimini kapatmadan once diske isle (OneDrive kilidi
        # olsa bile UI donmadan, kapanis sirasinda senkron tamamlanir).
        try:
            self.cfg.flush()
        except Exception:
            pass
        self.destroy()
