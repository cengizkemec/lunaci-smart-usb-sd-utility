# -*- mode: python ; coding: utf-8 -*-
"""Lunaci Smart USB & SD Card Utility — PyInstaller spec.

Tek dosya (onefile) exe; assets/logo.ico pencere ikonu, assets/logo.jpg
Hakkında penceresi görseli olarak paketlenir.
"""
import os

block_cipher = None
ROOT = os.path.abspath(".")

a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "assets", "logo.ico"), "assets"),
        (os.path.join(ROOT, "assets", "logo.jpg"), "assets"),
        (os.path.join(ROOT, "assets", "theme_lunaci.json"), "assets"),
    ],
    hiddenimports=["psutil"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "PIL.ImageQt", "tkinter.test"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="LunaciSmartUSBCardUtility",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI uygulaması: konsol penceresi açılmasın
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "logo.ico"),
)
