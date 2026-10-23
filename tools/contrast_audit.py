# -*- coding: utf-8 -*-
"""Lunaci tema kontrast denetimi (WCAG 2.1 AA).

Kontrol eder:
  * assets/theme_lunaci.json icindeki metin/zemin ciftleri
  * app.py renk sabitleri (accent, ikincil, tehlike, log renkleri)
  * canli widget'larin cozulmus renkleri (segment secili zemin dahil)

Kullanim:  python tools/contrast_audit.py
Cikis kodu: 0 = tum kontroller AA (>= 4.5:1) veya AA-large (>= 3:1).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("LUNACI_SMOKE_TEST", "0")

THEME_PATH = os.path.join(ROOT, "assets", "theme_lunaci.json")
WHITE = "#FFFFFF"
# Konsolun gercek arka planlari (CTkTextbox: acik, koyu)
CONSOLE_BG = ("#F4F6F7", "#0E1621")

failures: list[str] = []


def _lum(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"gecersiz renk: {hex_color!r}")
    rgb = [int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
           for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(fg: str, bg: str) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def check(label: str, fg: str, bg: str, minimum: float = 4.5) -> None:
    value = ratio(fg, bg)
    ok = value >= minimum
    print(f"  [{'PASS' if ok else 'FAIL'}] {label:<46} "
          f"{fg} / {bg} = {value:.2f}:1")
    if not ok:
        failures.append(label)


def check_pair(label: str, pair, bg_pair, minimum: float = 4.5) -> None:
    """(acik, koyu) metin/zemin ciftlerini iki temada da denetler."""
    for mode, idx in (("light", 0), ("dark", 1)):
        check(f"{label} ({mode})", pair[idx], bg_pair[idx], minimum)


with open(THEME_PATH, "r", encoding="utf-8") as fh:
    theme = json.load(fh)

print("== Tema JSON: metin/zemin ciftleri ==")
check_pair("CTkButton yazi", theme["CTkButton"]["text_color"],
           theme["CTkButton"]["fg_color"])
check_pair("CTkButton hover yazi", theme["CTkButton"]["text_color"],
           theme["CTkButton"]["hover_color"])
check_pair("CTkOptionMenu yazi", theme["CTkOptionMenu"]["text_color"],
           theme["CTkOptionMenu"]["fg_color"])
check_pair("CTkOptionMenu hover yazi", theme["CTkOptionMenu"]["text_color"],
           theme["CTkOptionMenu"]["button_hover_color"])
check_pair("CTkSegmentedButton secili", theme["CTkSegmentedButton"]["text_color"],
           theme["CTkSegmentedButton"]["selected_color"])
check_pair("CTkSegmentedButton secili hover",
           theme["CTkSegmentedButton"]["text_color"],
           theme["CTkSegmentedButton"]["selected_hover_color"])
check_pair("CTkSegmentedButton secisiz",
           theme["CTkSegmentedButton"]["text_color"],
           theme["CTkSegmentedButton"]["unselected_color"])
check_pair("CTkSegmentedButton secisiz hover",
           theme["CTkSegmentedButton"]["text_color"],
           theme["CTkSegmentedButton"]["unselected_hover_color"])
check_pair("CTkEntry yazi", theme["CTkEntry"]["text_color"],
           theme["CTkEntry"]["fg_color"])
check_pair("CTkEntry placeholder", theme["CTkEntry"]["placeholder_text_color"],
           theme["CTkEntry"]["fg_color"])
check_pair("CTkComboBox yazi", theme["CTkComboBox"]["text_color"],
           theme["CTkComboBox"]["fg_color"])
check_pair("CTkLabel yazi", theme["CTkLabel"]["text_color"],
           theme["CTk"]["fg_color"])
check_pair("DropdownMenu yazi", theme["DropdownMenu"]["text_color"],
           theme["DropdownMenu"]["fg_color"])
check_pair("DropdownMenu hover yazi", theme["DropdownMenu"]["text_color"],
           theme["DropdownMenu"]["hover_color"])

# Metin icermeyen bilesenler: WCAG AA non-text esigi 3:1.
print("\n== Tema JSON: bilesen renkleri (non-text, >= 3:1) ==")
for key, field, bg_key, bg_field in (
    ("CTkCheckBox", "fg_color", "CTkFrame", "fg_color"),
    ("CTkRadioButton", "fg_color", "CTkFrame", "fg_color"),
    ("CTkProgressBar", "progress_color", "CTkFrame", "fg_color"),
    ("CTkSwitch", "progress_color", "CTkFrame", "fg_color"),
):
    check_pair(f"{key}.{field}", theme[key][field], theme[bg_key][bg_field], 3.0)

print("\n== app.py renk sabitleri ==")
import app as appmod  # noqa: E402

check_pair("MUTED", appmod.MUTED, theme["CTkFrame"]["fg_color"])
check_pair("LINK", appmod.LINK, theme["CTkFrame"]["fg_color"])
check_pair("SEC_BTN yazi", appmod.SEC_BTN_T, appmod.SEC_BTN)
check_pair("SEC_BTN hover yazi", appmod.SEC_BTN_T, appmod.SEC_BTN_H)
check_pair("ACCENT (beyaz yazi)", appmod.WHITE, appmod.ACCENT)
check_pair("ACCENT hover (beyaz yazi)", appmod.WHITE, appmod.ACCENT_H)
check_pair("SEL_COLOR (segment secili)", theme["CTkSegmentedButton"]["text_color"],
           appmod.SEL_COLOR)
check_pair("SEL_COLOR_H (segment secili hover)",
           theme["CTkSegmentedButton"]["text_color"], appmod.SEL_COLOR_H)
check_pair("DANGER_BTN (beyaz yazi)", appmod.WHITE, appmod.DANGER_BTN)
check_pair("DANGER_BTN hover (beyaz yazi)", appmod.WHITE, appmod.DANGER_BTN_H)
check_pair("CANCEL_BTN (beyaz yazi)", appmod.WHITE, appmod.CANCEL_BTN)
check_pair("CANCEL_BTN hover (beyaz yazi)", appmod.WHITE, appmod.CANCEL_BTN_H)

print("\n== Konsol gunluk renkleri (gercek metin kutusu zemini) ==")
for level, pair in appmod.LOG_COLORS.items():
    check_pair(f"LOG {level}", pair, CONSOLE_BG)

print("\n== Canli widget'lar ==")
import customtkinter as ctk  # noqa: E402

a = appmod.LunaciApp()
a.update_idletasks()
try:
    widgets = [
        ("tema segmenti", a.theme_menu),
        ("dil segmenti", a.lang_menu),
        ("guncelle butonu", a.btn_update),
        ("hakkinda butonu", a.btn_about),
        ("gozat butonu", a.btn_browse),
        ("raporlar butonu", a.btn_reports),
        ("gecmis butonu", a.btn_clear),
        ("kaydet butonu", a.btn_save_log),
        ("iptal butonu", a.cancel_btn),
        ("tam bicim butonu", a.btn_full),
        ("hizli bicim butonu", a.btn_quick),
        ("onar butonu", a.btn_repair),
        ("ses anahtari", a.sound_switch),
        ("cihaz menusu", a.device_menu),
    ]
    for mode in ("Light", "Dark"):
        idx = 0 if mode == "Light" else 1
        ctk.set_appearance_mode(mode)
        a.update_idletasks()
        print(f"  -- {mode} --")
        for label, w in widgets:
            text = w.cget("text_color")
            text = text[idx] if isinstance(text, (list, tuple)) else text
            if isinstance(w, ctk.CTkSegmentedButton):
                bg = w.cget("selected_color")
                bg = bg[idx] if isinstance(bg, (list, tuple)) else bg
            else:
                bg = w.cget("fg_color")
                if isinstance(bg, (list, tuple)):
                    bg = bg[idx]
            if not isinstance(bg, str) or not bg.startswith("#"):
                continue
            check(label, text, bg)
finally:
    a.monitor.stop()
    a.destroy()

print("\n" + "=" * 60)
if failures:
    print(f"SONUC: {len(failures)} kontrast sorunu bulundu")
    for item in failures:
        print("  - " + item)
    sys.exit(1)
print("SONUC: tum kontrast kontrolleri AA uyumlu")
