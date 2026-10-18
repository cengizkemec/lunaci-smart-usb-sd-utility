"""Lunaci Smart USB & SD Card Utility — CustomTkinter arayüzü."""
from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

import i18n
from i18n import tr
from config_manager import (APP_NAME, APP_VERSION, BASE_DIR, GITHUB_URL,
                            WEBSITE_URL, ConfigManager, resource_path)
from disk_manager import (Device, DeviceMonitor, fstype_to_option, run_format,
                          run_repair)
from file_ops import (copy_folder, save_report, write_iso_raw,
                      write_zip_to_device, zip_folder_to_device)
from health import CRIT, GOOD, WARN, run_health_test
from utils import Emitter, human_bytes, is_admin

THEME_TO_MODE = {"system": "System", "dark": "Dark", "light": "Light"}
THEME_KEYS = ("system", "dark", "light")

LED_COLORS = {"unknown": "#6b7280", GOOD: "#22c55e", WARN: "#eab308", CRIT: "#ef4444"}
HEALTH_KEY = {"unknown": "health.unknown", GOOD: "health.good",
              WARN: "health.warn", CRIT: "health.crit"}

FS_OPTIONS = ["FAT32", "NTFS", "exFAT", "EXT4 (Linux)"]
NEED_ADMIN = {"format", "repair", "iso"}


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
        self._log_lines = 0
        self._indeterminate = False
        self._about = None

        ctk.set_appearance_mode(THEME_TO_MODE.get(self.cfg.get("theme"), "System"))
        ctk.set_default_color_theme("blue")

        self.title(APP_NAME)
        self.geometry("1120x880")
        self.minsize(980, 780)

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
        self.grid_rowconfigure(3, weight=1)

        # üst başlık
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text=APP_NAME,
                     font=self.font_title).grid(row=0, column=0, sticky="w")
        self.subtitle_label = ctk.CTkLabel(
            header, text=tr("app.subtitle"), text_color="gray", font=self.font_small)
        self.subtitle_label.grid(row=1, column=0, sticky="w")
        admin = is_admin()
        self.admin_badge = ctk.CTkLabel(
            header, text=tr("badge.admin") if admin else tr("badge.limited"),
            text_color="#22c55e" if admin else "#ef4444",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"))
        self.admin_badge.grid(row=0, column=1, rowspan=2, padx=(8, 14))
        self.theme_menu = ctk.CTkSegmentedButton(
            header, values=[tr("theme.system"), tr("theme.dark"), tr("theme.light")],
            command=self._on_theme, font=self.font_small, width=220)
        self.theme_menu.grid(row=0, column=2, rowspan=2, padx=(0, 8))
        self.lang_menu = ctk.CTkSegmentedButton(
            header, values=["TR", "EN"], command=self._on_language,
            font=self.font_small, width=90)
        self.lang_menu.grid(row=0, column=3, rowspan=2, padx=(0, 8))
        self.btn_about = ctk.CTkButton(header, text=tr("btn.about"), width=90,
                                       fg_color="#334155", hover_color="#1e293b",
                                       command=self._show_about)
        self.btn_about.grid(row=0, column=4, rowspan=2)

        # cihaz kartı
        dev_frame = ctk.CTkFrame(self)
        dev_frame.grid(row=1, column=0, sticky="nsew", padx=(18, 6), pady=6)
        dev_frame.grid_columnconfigure(1, weight=1)
        self.dev_section = ctk.CTkLabel(dev_frame, text=tr("dev.section"),
                                        font=self.font_small, text_color="gray")
        self.dev_section.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.device_menu = ctk.CTkOptionMenu(dev_frame, width=340,
                                             command=self._on_device_pick)
        self.device_menu.grid(row=0, column=1, columnspan=2, sticky="ew",
                              padx=12, pady=(10, 2))
        self.led = ctk.CTkLabel(dev_frame, text="●", text_color=LED_COLORS["unknown"],
                                font=ctk.CTkFont(size=26))
        self.led.grid(row=0, column=3, rowspan=2, padx=(6, 12), pady=(8, 0))
        self.health_label = ctk.CTkLabel(dev_frame, text=tr("health.status", s="—"),
                                         font=self.font_small, text_color="gray")
        self.health_label.grid(row=1, column=0, columnspan=3, sticky="w", padx=12)
        self.info_label = ctk.CTkLabel(dev_frame, text=tr("dev.waiting"),
                                       font=self.font_ui, anchor="w", justify="left")
        self.info_label.grid(row=2, column=0, columnspan=3, sticky="ew", padx=12, pady=(8, 2))
        self.cap_bar = ctk.CTkProgressBar(dev_frame)
        self.cap_bar.set(0)
        self.cap_bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=12, pady=(4, 2))
        self.cap_label = ctk.CTkLabel(dev_frame, text="", font=self.font_small,
                                      text_color="gray")
        self.cap_label.grid(row=4, column=0, columnspan=3, sticky="w", padx=12)
        self.tech_label = ctk.CTkLabel(dev_frame, text="", font=self.font_small,
                                       text_color="gray")
        self.tech_label.grid(row=5, column=0, columnspan=3, sticky="w", padx=12, pady=(0, 6))
        self.btn_health = ctk.CTkButton(dev_frame, text=tr("btn.health"),
                                        command=lambda: self._do_health())
        self.btn_health.grid(row=6, column=0, columnspan=3, sticky="ew", padx=12, pady=(2, 12))

        # yazdırılacak klasör kartı (sağ üst)
        tgt_frame = ctk.CTkFrame(self)
        tgt_frame.grid(row=1, column=1, sticky="nsew", padx=(6, 18), pady=6)
        tgt_frame.grid_columnconfigure(0, weight=1)
        self.folder_section = ctk.CTkLabel(tgt_frame, text=tr("folder.section"),
                                           font=self.font_small, text_color="gray")
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
                                        command=self._pick_folder)
        self.btn_browse.grid(row=0, column=1)
        self.btn_copy = ctk.CTkButton(tgt_frame, text=tr("btn.write_folder"),
                                      command=self._do_copy)
        self.btn_copy.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 2))
        self.btn_zipfolder = ctk.CTkButton(tgt_frame, text=tr("btn.zip_folder"),
                                           fg_color="#334155", hover_color="#1e293b",
                                           command=self._do_zipfolder)
        self.btn_zipfolder.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 4))
        self.autofmt_switch = ctk.CTkSwitch(
            tgt_frame, text=tr("switch.autofmt"),
            command=self._toggle_autofmt, font=self.font_small)
        if self.cfg.get("auto_format_before_write"):
            self.autofmt_switch.select()
        self.autofmt_switch.grid(row=4, column=0, sticky="w", padx=12, pady=(2, 2))
        reports_row = ctk.CTkFrame(tgt_frame, fg_color="transparent")
        reports_row.grid(row=5, column=0, sticky="ew", padx=12, pady=(2, 12))
        reports_row.grid_columnconfigure(0, weight=1)
        self.reports_switch = ctk.CTkSwitch(
            reports_row, text=tr("switch.reports"),
            command=self._toggle_reports, font=self.font_small)
        if self.cfg.get("save_reports"):
            self.reports_switch.select()
        self.reports_switch.grid(row=0, column=0, sticky="w")
        self.btn_reports = ctk.CTkButton(reports_row, text=tr("btn.reports"),
                                         width=150, fg_color="#334155",
                                         hover_color="#1e293b",
                                         command=self._open_reports)
        self.btn_reports.grid(row=0, column=1, sticky="e")

        # biçimlendirme
        fmt_frame = ctk.CTkFrame(self)
        fmt_frame.grid(row=2, column=0, sticky="nsew", padx=(18, 6), pady=6)
        fmt_frame.grid_columnconfigure(1, weight=1)
        self.fmt_section = ctk.CTkLabel(fmt_frame, text=tr("fmt.section"),
                                        font=self.font_small, text_color="gray")
        self.fmt_section.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        self.fs_var = tk.StringVar(value="FAT32")
        self.fs_box = ctk.CTkComboBox(fmt_frame, values=FS_OPTIONS, state="readonly",
                                      variable=self.fs_var, width=180)
        self.fs_box.grid(row=0, column=1, sticky="w", padx=6)
        self.label_caption = ctk.CTkLabel(fmt_frame, text=tr("fmt.label"),
                                          font=self.font_small, text_color="gray")
        self.label_caption.grid(row=0, column=2, sticky="w", padx=12)
        self.label_var = tk.StringVar(value=self.cfg.get("volume_label") or "LUNACI")
        ctk.CTkEntry(fmt_frame, textvariable=self.label_var, width=160).grid(
            row=0, column=3, sticky="e", padx=(6, 12))
        self.btn_quick = ctk.CTkButton(fmt_frame, text=tr("btn.quick_format"),
                                       command=lambda: self._do_format(True))
        self.btn_quick.grid(row=1, column=0, columnspan=2, sticky="ew",
                            padx=12, pady=(8, 2))
        self.btn_full = ctk.CTkButton(fmt_frame, text=tr("btn.full_format"),
                                      fg_color="#334155", hover_color="#1e293b",
                                      command=lambda: self._do_format(False))
        self.btn_full.grid(row=1, column=2, columnspan=2, sticky="ew",
                           padx=12, pady=(8, 2))
        self.fmt_hint = ctk.CTkLabel(fmt_frame, text=tr("fmt.hint"),
                                     font=self.font_small, text_color="gray")
        self.fmt_hint.grid(row=2, column=0, columnspan=4, sticky="w", padx=12,
                           pady=(2, 10))

        # araçlar: ISO / ZIP / onarım
        tools_frame = ctk.CTkFrame(self)
        tools_frame.grid(row=2, column=1, sticky="nsew", padx=(6, 18), pady=6)
        tools_frame.grid_columnconfigure((0, 1), weight=1)
        self.tools_section = ctk.CTkLabel(tools_frame, text=tr("tools.section"),
                                          font=self.font_small, text_color="gray")
        self.tools_section.grid(row=0, column=0, columnspan=2, sticky="w",
                                padx=12, pady=(10, 2))
        self.btn_iso = ctk.CTkButton(tools_frame, text=tr("btn.iso"),
                                     command=self._do_iso)
        self.btn_iso.grid(row=1, column=0, sticky="ew", padx=(12, 3), pady=(6, 2))
        self.btn_zip = ctk.CTkButton(tools_frame, text=tr("btn.zip"),
                                     fg_color="#334155", hover_color="#1e293b",
                                     command=self._do_zip)
        self.btn_zip.grid(row=1, column=1, sticky="ew", padx=(3, 12), pady=(6, 2))
        self.btn_repair = ctk.CTkButton(tools_frame, text=tr("btn.repair"),
                                        fg_color="#7f1d1d", hover_color="#6b1414",
                                        command=self._do_repair)
        self.btn_repair.grid(row=2, column=0, columnspan=2, sticky="ew",
                             padx=12, pady=(2, 4))
        self.tools_hint = ctk.CTkLabel(tools_frame, text=tr("tools.hint"),
                                       font=self.font_small, text_color="gray",
                                       justify="left")
        self.tools_hint.grid(row=3, column=0, columnspan=2, sticky="w", padx=12,
                             pady=(2, 10))

        # log konsolu
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, columnspan=2, sticky="nsew",
                       padx=18, pady=(6, 6))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)
        self.log_section = ctk.CTkLabel(log_frame, text=tr("log.section"),
                                        font=self.font_small, text_color="gray")
        self.log_section.grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))
        self.btn_clear = ctk.CTkButton(log_frame, text=tr("btn.clear"), width=80,
                                       fg_color="#334155", hover_color="#1e293b",
                                       command=self._clear_log)
        self.btn_clear.grid(row=0, column=1, padx=(4, 6))
        self.btn_save_log = ctk.CTkButton(log_frame, text=tr("btn.save"), width=80,
                                          fg_color="#334155", hover_color="#1e293b",
                                          command=self._save_console)
        self.btn_save_log.grid(row=0, column=2, padx=(0, 12))
        self.log_box = ctk.CTkTextbox(log_frame, font=self.font_mono, wrap="word")
        self.log_box.grid(row=1, column=0, columnspan=3, sticky="nsew",
                          padx=12, pady=(0, 12))

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
                                        fg_color="#b91c1c", hover_color="#991b1b",
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
        self.dev_section.configure(text=tr("dev.section"))
        self.folder_section.configure(text=tr("folder.section"))
        self.btn_browse.configure(text=tr("btn.browse"))
        self.btn_copy.configure(text=tr("btn.write_folder"))
        self.btn_zipfolder.configure(text=tr("btn.zip_folder"))
        self.autofmt_switch.configure(text=tr("switch.autofmt"))
        self.reports_switch.configure(text=tr("switch.reports"))
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
        self.btn_health.configure(text=tr("btn.health"))
        self.cancel_btn.configure(text=tr("btn.cancel"))
        if not self.busy:
            self.status_label.configure(text=tr("status.ready"))
        self._update_device_card()

    # --------------------------------------------------------- durum UI -----

    def active_device(self) -> Device | None:
        for dev in self.devices:
            if dev.letter == self.active_letter:
                return dev
        return None

    def _refresh_actions(self) -> None:
        has_dev = self.active_device() is not None
        busy = self.busy is not None
        target = (self.target_var.get() or "").strip()
        has_target = bool(target) and os.path.isdir(target)

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
        try:
            for _ in range(400):
                kind, *payload = self.q.get_nowait()
                if kind == "log":
                    self._insert_log(payload[0])
                elif kind == "devices":
                    self._on_devices(payload[0])
                elif kind == "health":
                    letter, status, info = payload
                    self.health[letter] = (status, info)
                    if letter == self.active_letter:
                        self._update_health_ui(letter)
                elif kind == "progress":
                    self._on_progress(payload[0], payload[1] if len(payload) > 1 else None)
                elif kind == "task_done":
                    self._on_task_done(*payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

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
            self.device_menu.configure(values=[d.display for d in devices])
            self.device_menu.set(cur)
        else:
            self.device_menu.configure(values=[tr("dev.empty")])
            self.device_menu.set(tr("dev.empty"))
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

    def _on_progress(self, pct, text: str | None = None) -> None:
        if pct is None:
            if not self._indeterminate:
                self.prog.configure(mode="indeterminate")
                self.prog.start(12)
                self._indeterminate = True
        else:
            if self._indeterminate:
                self.prog.stop()
                self.prog.configure(mode="determinate")
                self._indeterminate = False
            self.prog.set(max(0.0, min(1.0, float(pct) / 100.0)))
        if text:
            self._set_status(text)

    def _insert_log(self, rec) -> None:
        line = f"[{rec.time_str}] [{rec.level:<5}] {rec.message}\n"
        inner = getattr(self.log_box, "_textbox", None)
        if inner is not None:
            try:
                if rec.level not in self._log_tags:
                    inner.tag_config(rec.level, foreground=rec.color)
                    self._log_tags.add(rec.level)
                inner.insert("end", line, rec.level)
            except Exception:
                self.log_box.insert("end", line)
        else:
            self.log_box.insert("end", line)
        self._log_lines += 1
        if self._log_lines > 5000:
            try:
                self.log_box.delete("1.0", "1001.0")
            except Exception:
                pass
            self._log_lines -= 1000
        try:
            self.log_box.see("end")
        except Exception:
            pass

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
        self._on_progress(None, status_text)
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

        # Raporlar her zaman programın yanındaki reports klasörüne
        if ok and self.cfg.get("save_reports"):
            folder = self.reports_dir()
            ts = time.strftime("%Y%m%d_%H%M%S")
            header = (f"{APP_NAME} — {key}\n"
                      f"Tarih / Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                      f"Cihaz / Device: {self.active_letter or '-'}:\n"
                      f"Sonuç / Result: OK\n" + "=" * 64 + "\n")
            try:
                path = save_report(header + "\n".join(logger.capture) + "\n",
                                   folder, f"{key}_{ts}.txt")
                self._log("OK", tr("ui.report_saved", p=path))
            except Exception as exc:
                self._log("ERROR", tr("ui.report_error", e=exc))

        if ok and key in ("format", "repair", "iso", "zip", "copy", "zipfolder"):
            self.monitor.request_poll()

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
            self.cfg.set("target_folder", path)
            self._refresh_actions()

    def _toggle_reports(self) -> None:
        self.cfg.set("save_reports", bool(self.reports_switch.get()))

    def _toggle_autofmt(self) -> None:
        self.cfg.set("auto_format_before_write", bool(self.autofmt_switch.get()))

    def autofmt_enabled(self) -> bool:
        return bool(self.autofmt_switch.get())

    def _preflight_format(self, logger, dev) -> bool:
        """Yazma işleminden önce açıksa hızlı biçimlendirme yapar.

        * fs/label ANA iş parçacığında okunur (Tk değişkenleri arka plandan
          güvenle okunmaz). Görev iş parçacığı yalnızca bu değerleri kullanır.
        * Biçimlendirme sonrası diskin yeniden erişilebilir olması BEKLENİR;
          aksi halde yazım hemen başlayınca "disk bulunamadı" hatası alınırdı.
        """
        if not self.autofmt_enabled():
            self._log("INFO", tr("ui.autofmt_skip"))
            return True
        if not is_admin():
            logger.error(tr("ui.admin_needed"))
            return False
        fs = self.fs_var.get()
        if fs.startswith("EXT4"):
            logger.error(tr("fmt.ext4_err"))
            return False
        label = self.label_var.get().strip() or "LUNACI"
        letter = dev.letter
        size_hint = dev.size
        logger.info(tr("ui.autofmt_start"))
        if not run_format(logger, letter, fs, label, quick=True,
                          size_hint=size_hint):
            return False
        # Format sonrası diskin geri gelmesini bekle (en fazla 30 sn)
        if not self._wait_drive_ready(letter, logger, timeout=30.0):
            return False
        self.monitor.request_poll()
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
        self._log("INFO", tr("ui.copy_engine", l=dev.letter, e=engine))

        def task(logger):
            if not self._preflight_format(logger, dev):
                return False, None
            return copy_folder(src, dev.letter, logger, self.cancel_event,
                               engine=engine, progress=self._progress_emit), None

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

        def task(logger):
            if not self._preflight_format(logger, dev):
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
                            size_hint=dev.size)
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
            return run_repair(logger, dev.letter), None

        self._start_task("repair", tr("task.repair", l=dev.letter), task,
                         cancellable=False)

    def _do_iso(self) -> None:
        dev = self.active_device()
        if not dev:
            return
        path = filedialog.askopenfilename(
            title=tr("pick.iso_title"),
            filetypes=[(tr("file.iso"), "*.iso"), (tr("file.all"), "*.*")])
        if not path:
            return
        size = os.path.getsize(path)
        if not messagebox.askyesno(
                tr("dlg.iso.title"),
                tr("dlg.iso.body", name=os.path.basename(path),
                   size=human_bytes(size), l=dev.letter, dev=dev.name)
                + ("\n\n" + tr("dlg.will_format") if self.autofmt_enabled() else ""),
                icon="warning"):
            return

        def task(logger):
            if not self._preflight_format(logger, dev):
                return False, None
            return write_iso_raw(path, dev.letter, logger, self.cancel_event,
                                 progress=self._progress_emit), None

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

        def task(logger):
            if not self._preflight_format(logger, dev):
                return False, None
            return write_zip_to_device(path, dev.letter, logger, self.cancel_event,
                                       progress=self._progress_emit), None

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
                     text_color="gray", font=self.font_small).pack()

        def link(text: str, url: str) -> None:
            lbl = ctk.CTkLabel(win, text=text, text_color="#3b82f6",
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

        ctk.CTkButton(win, text="✕", width=40, fg_color="#7f1d1d",
                      hover_color="#6b1414", command=win.destroy).pack(
            side="bottom", pady=14)

    # ------------------------------------------------------- konsol UI ------

    def _clear_log(self) -> None:
        self.log_box.delete("1.0", "end")
        self._log_lines = 0

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
        self.cfg.set("volume_label", self.label_var.get().strip() or "LUNACI")
        theme = self.theme_map.get(self.theme_menu.get(), "system")
        self.cfg.set("theme", theme)
        self.destroy()
