"""Lunaci — kapsamli otomatik test (guvenli: gercek disk FORMATLANMAZ).

Calistir:  python tools/selftest.py
Kapsam:
  1) Tum modullerin derlenmesi (py_compile)
  2) TR/EN i18n anahtar esitligi
  3) Tema JSON anahtarlarinin blue.json ile uyumu
  4) ConfigManager: arka plan (bloklamayan) yazma
  5) run_format FAT32 >32GB korumasi (diskpart CAGIRILMAZ)
  6) utils.run_process: hizli satir ayirma + iptal (cancel)
  7) file_ops: subst sanal surucuye kopyalama + ZIP (1200 dosya)
  8) UI: LunaciApp olusumu, bozuk olayda _poll dayanikliligi, toplu log performansi
  9) AST: gorev (task) bloklari Tk widget'larina dokunmuyor
"""
from __future__ import annotations

import ast
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Turkce konsol kod sayfasi (cp1254) bazi unicode karakterleri yazamaz;
# ciktiyi UTF-8'e cevir ki test raporu yarida kesilmesin.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASSED = []
FAILED = []


def check(name: str, cond: bool, detail="") -> bool:
    (PASSED if cond else FAILED).append(name)
    tag = "PASS" if cond else "FAIL"
    line = f"[{tag}] {name}"
    if detail and not cond:
        line += f"  ::  {detail}"
    print(line, flush=True)
    return bool(cond)


# ------------------------------------------------------------------ 1) derle
MODULES = ["main.py", "app.py", "i18n.py", "utils.py", "disk_manager.py",
           "file_ops.py", "health.py", "config_manager.py"]
print("\n== 1. Derleme ==")
for f in MODULES:
    path = os.path.join(ROOT, f)
    try:
        py_compile.compile(path, doraise=True, cfile=os.path.join(tempfile.gettempdir(),
                                                                  f + "c"))
        check(f"compile {f}", True)
    except Exception as exc:  # noqa: BLE001
        check(f"compile {f}", False, exc)

# ------------------------------------------------------------------ 2) i18n
print("\n== 2. i18n ==")
import i18n  # noqa: E402

tr_keys, en_keys = set(i18n.TR), set(i18n.EN)
check("i18n anahtar esitligi", tr_keys == en_keys,
      f"sadece TR={sorted(tr_keys - en_keys)} sadece EN={sorted(en_keys - tr_keys)}")

# ------------------------------------------------------------------ 3) tema
print("\n== 3. Tema ==")
BLUE = os.path.normpath(os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "Lib",
    "site-packages", "customtkinter", "assets", "themes", "blue.json"))
THEME = os.path.join(ROOT, "assets", "theme_lunaci.json")
try:
    with open(THEME, "r", encoding="utf-8") as fh:
        theme = json.load(fh)
    check("tema JSON okunur", True)
    if os.path.isfile(BLUE):
        with open(BLUE, "r", encoding="utf-8") as fh:
            blue = json.load(fh)
        missing = set(blue) - set(theme)
        check("tema blue.json anahtarlarini kapsiyor", not missing, f"eksik={missing}")
    else:
        check("blue.json bulundu (atlandi)", True)
except Exception as exc:  # noqa: BLE001
    check("tema JSON gecerli", False, exc)

# CTk'nin temayi yukleyip TUM widget anahtarlariyla sorunsuz kurdugunu dogrula.
try:
    import customtkinter as _ctk

    _ctk.set_default_color_theme(THEME)
    _root = _ctk.CTk()
    try:
        _ctk.CTkFrame(_root)
        _ctk.CTkButton(_root)
        _ctk.CTkLabel(_root)
        _ctk.CTkEntry(_root)
        _ctk.CTkCheckBox(_root)
        _ctk.CTkSwitch(_root)
        _ctk.CTkRadioButton(_root)
        _ctk.CTkProgressBar(_root)
        _ctk.CTkSlider(_root)
        _ctk.CTkOptionMenu(_root, values=["a", "b"])
        _ctk.CTkComboBox(_root, values=["a", "b"])
        _ctk.CTkScrollbar(_root)
        _ctk.CTkSegmentedButton(_root, values=["a", "b"])
        _ctk.CTkTextbox(_root)
        _ctk.CTkScrollableFrame(_root)
        check("CTk tema ile tum widget'lar olusturuldu", True)
    finally:
        _root.destroy()
except Exception as exc:  # noqa: BLE001
    check("CTk tema ile widget olusumu", False, exc)

# --------------------------------------------------------------- 4) config
print("\n== 4. ConfigManager (arka plan yazma) ==")
import config_manager as cm  # noqa: E402

tmp_root = tempfile.mkdtemp(prefix="lunaci_test_")
try:
    cfg = cm.ConfigManager(os.path.join(tmp_root, "config.json"))
    t0 = time.time()
    for i in range(300):
        cfg.set("volume_label", f"LBL{i}")
    dt = time.time() - t0
    check("300x set() ana thread'i bloklamiyor (<1s)", dt < 1.0, f"{dt:.3f}s")
    cfg.flush()
    with open(os.path.join(tmp_root, "config.json"), "r", encoding="utf-8") as fh:
        saved = json.load(fh)
    check("config.json'a yazildi (son deger)", saved.get("volume_label") == "LBL299",
          saved.get("volume_label"))
except Exception as exc:  # noqa: BLE001
    check("ConfigManager", False, exc)

# ------------------------------------------------------- 5) FAT32 >32GB koruma
print("\n== 5. FAT32 >32GB korumasi (diskpart cagrilmamali) ==")
import disk_manager as dm  # noqa: E402
from utils import Emitter  # noqa: E402

dp_calls = []
_orig_dp = dm.run_diskpart


def _fake_dp(*a, **k):
    dp_calls.append(a)
    return 0, []


dm.run_diskpart = _fake_dp
try:
    _none = []
    lg = Emitter(lambda item: _none.append(item), task="test")
    res = dm.run_format(lg, "F", "FAT32", "TEST", quick=True, size_hint=64 * dm.GB)
    check("64GB FAT32 -> False dondurur", res is False, res)
    check("64GB FAT32 -> diskpart HIC cagrilmadi", dp_calls == [], dp_calls)
    # 31GB FAT32 -> diskpart cagrilir (guvenli sahte)
    dp_calls.clear()
    dm.run_format(lg, "F", "FAT32", "TEST", quick=True, size_hint=31 * dm.GB)
    check("31GB FAT32 -> diskpart cagrildi (sinir alti)", len(dp_calls) >= 1, dp_calls)
finally:
    dm.run_diskpart = _orig_dp

# ------------------------------------------- 5b) DeviceMonitor dayaniklilik
print("\n== 5b. DeviceMonitor dayaniklilik ==")
try:
    check("fast_drive_letters C: iceriyor", "C" in dm.fast_drive_letters(),
          dm.fast_drive_letters())
    events = []
    mon = dm.DeviceMonitor(lambda ev: events.append(ev), interval=0.15)

    def _boom(_logger):
        raise RuntimeError("algilama patladi (test)")

    _orig_detect = dm.detect_devices
    dm.detect_devices = _boom
    mon.start()
    time.sleep(0.9)
    alive = mon.is_alive()
    mon.stop()
    dm.detect_devices = _orig_detect
    time.sleep(0.2)
    check("DeviceMonitor hatalara ragmen calismaya devam etti",
          alive and len(events) >= 1, f"alive={alive} events={len(events)}")
    check("DeviceMonitor hata durumunda bos liste yayinladi",
          any(ev[0] == "devices" and ev[1] == [] for ev in events), events[:2])
except Exception as exc:  # noqa: BLE001
    check("DeviceMonitor dayaniklilik", False, exc)

# --------------------------------------------------- 6) run_process hiz/cancel
print("\n== 6. run_process ==")
from utils import run_process  # noqa: E402

try:
    code, lines = run_process('echo lunaci_hello & echo lunaci_world')
    joined = " ".join(lines)
    check("satir ayirma (echo)", "lunaci_hello" in joined and "lunaci_world" in joined,
          lines)
except Exception as exc:  # noqa: BLE001
    check("run_process echo", False, exc)

try:
    ev = threading.Event()

    def _setter():
        time.sleep(0.5)
        ev.set()

    threading.Thread(target=_setter, daemon=True).start()
    t0 = time.time()
    code, _lines = run_process("ping 127.0.0.1 -n 20 >nul", cancel=ev)
    dt = time.time() - t0
    check("cancel → proses erken olduruldu (<3s)", dt < 3.0, f"{dt:.2f}s")
except Exception as exc:  # noqa: BLE001
    check("run_process cancel", False, exc)

# --------------------------------------------- 7) file_ops (subst sanal surucu)
print("\n== 7. file_ops (subst sanal surucu Z:) ==")
import file_ops  # noqa: E402

subst_target = os.path.join(tmp_root, "target")
src = os.path.join(tmp_root, "src")
os.makedirs(subst_target, exist_ok=True)
os.makedirs(src, exist_ok=True)
for i in range(1200):
    with open(os.path.join(src, f"foto_{i:04d}.txt"), "w", encoding="utf-8") as fh:
        fh.write("x" * 400)

subst_ok = False
try:
    r = subprocess.run(["subst", "Z:", subst_target], capture_output=True, text=True)
    subst_ok = r.returncode == 0
except Exception:  # noqa: BLE001
    subst_ok = False
check("subst Z: olusturuldu", subst_ok)

if subst_ok:
    try:
        cancel = threading.Event()
        log_items = []
        plog = Emitter(lambda it: log_items.append(it), task="copy")
        progress_calls = []
        t0 = time.time()
        ok = file_ops.copy_folder(src, "Z", plog, cancel,
                                  progress=lambda p, t: progress_calls.append(p))
        dt = time.time() - t0
        copied = sum(1 for _r, _d, fs in os.walk(subst_target) for _ in fs)
        check("copy_folder basarili", ok, f"ok={ok}")
        check("copy_folder 1200 dosya kopyalandi", copied >= 1200, copied)
        check("copy_folder < 30s", dt < 30.0, f"{dt:.1f}s")
        check("copy_folder ilerleme bildirimi alindi", len(progress_calls) > 0,
              len(progress_calls))
        check("copy_folder log tasmasi yok (<300 UI olayi)", len(log_items) < 300,
              len(log_items))
    except Exception as exc:  # noqa: BLE001
        check("copy_folder", False, exc)

    try:
        zdir = os.path.join(tmp_root, "zsrc")
        os.makedirs(zdir, exist_ok=True)
        for i in range(50):
            with open(os.path.join(zdir, f"a{i}.txt"), "w") as fh:
                fh.write("hello" * 100)
        ok = file_ops.zip_folder_to_device(zdir, "Z", plog, cancel,
                                           progress=lambda p, t: None)
        zpath = os.path.join("Z:\\", os.path.basename(zdir) + ".zip")
        check("zip_folder_to_device basarili", ok and os.path.isfile(zpath), zpath)
        # geri cikarma testi
        back = os.path.join(tmp_root, "back")
        os.makedirs(back, exist_ok=True)
        if os.path.isfile(zpath):
            file_ops.write_zip_to_device(zpath, "Z", plog, cancel,
                                         progress=lambda p, t: None)
            check("write_zip_to_device calisti", True)
    except Exception as exc:  # noqa: BLE001
        check("zip islemleri", False, exc)
    finally:
        subprocess.run(["subst", "Z:", "/D"], capture_output=True, text=True)

# ------------------------------------------------------------------ 9) AST
print("\n== 9. AST: gorev bloklari Tk'ya dokunmuyor ==")
TK_ATTRS = {"fs_var", "label_var", "target_var", "autofmt_switch", "reports_switch",
            "log_box", "device_menu", "prog", "status_label", "theme_menu",
            "lang_menu", "cap_bar", "led", "info_label", "fs_box", "autofmt_switch"}
try:
    with open(os.path.join(ROOT, "app.py"), "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    violations = []

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if node.name in ("task", "runner", "_save"):
                for sub in ast.walk(node):
                    if (isinstance(sub, ast.Attribute)
                            and isinstance(sub.value, ast.Name)
                            and sub.value.id == "self"
                            and sub.attr in TK_ATTRS):
                        violations.append((node.name, sub.attr, sub.lineno))
            self.generic_visit(node)

    V().visit(tree)
    check("task/runner bloklari Tk widget'i okumuyor", not violations, violations)
except Exception as exc:  # noqa: BLE001
    check("AST analizi", False, exc)

# ------------------------------------------------------------------ 8) UI
print("\n== 8. UI (LunaciApp) ==")
cfg_backup = None
cfg_path = os.path.join(ROOT, "config.json")
if os.path.isfile(cfg_path):
    with open(cfg_path, "rb") as fh:
        cfg_backup = fh.read()

app = None
try:
    import customtkinter as ctk  # noqa: E402

    from app import LunaciApp  # noqa: E402

    app = LunaciApp()
    check("LunaciApp olusturuldu", True)

    # bozuk olay enjekte et: _poll DIE olmamali + gercek 3 sn'lik canli GUI oturumu
    from datetime import datetime  # noqa: E402

    from utils import LogRecord  # noqa: E402

    results = {}

    def _poison() -> None:
        app.q.put(("progress", "bu-bir-sayi-degil"))
        app.q.put(("progress", None))
        app.q.put(("log", LogRecord(datetime.now(), "INFO", "poll-dayaniklilik")))
        app.q.put(("bilinmeyen-olay", 1, 2, 3))
        app.q.put(("log", LogRecord(datetime.now(), "OK", "bozuk olaydan sonra yasadi")))

    def _batch() -> None:
        records = [LogRecord(datetime.now(), "INFO", f"poll-log-{i}")
                   for i in range(3000)]
        t0 = time.time()
        app._insert_logs(records)
        results["batch"] = time.time() - t0

    def _wrap_up() -> None:
        results["menu_values"] = hasattr(app, "_menu_values")
        try:
            results["target_bool"] = isinstance(app._target_exists(), bool)
        except Exception as exc:  # noqa: BLE001
            results["target_bool"] = False
            results["target_err"] = str(exc)
        # arka plan hedef sorgusu gercekten calisti mi? (zaman damgasi > 0)
        results["target_probed"] = app._target_cache[2] > 0
        try:
            results["log_text"] = app.log_box.get("1.0", "end")
        except Exception as exc:  # noqa: BLE001
            results["log_text"] = ""
            results["log_err"] = str(exc)
        results["target_cache_ts"] = app._target_cache[2] > 0
        app.destroy()

    app.after(300, _poison)
    app.after(800, _batch)
    app.after(3000, _wrap_up)
    app.mainloop()          # gercek GUI dongusu — donma olursa burada kalir

    check("canli GUI oturumu (3 sn mainloop) sorunsuz tamamlandi", True)
    check("bozuk olaylardan sonra _poll hayatta kaldi (log yazildi)",
          "bozuk olaydan sonra yasadi" in results.get("log_text", ""),
          results.get("log_err"))
    check("3000 kayit toplu yazimda hizli (<1s)",
          results.get("batch", 99) < 1.0, f"{results.get('batch', 99):.3f}s")
    check("_menu_values ilklendi", results.get("menu_values") is True)
    check("_target_cache calisiyor", results.get("target_bool") is True)
    check("hedef klasor sorgusu arka planda tamamlandi",
          results.get("target_cache_ts") is True,
          results.get("target_cache_ts"))
    app = None
except Exception as exc:  # noqa: BLE001
    import traceback
    check("LunaciApp UI testi", False, exc)
    print(traceback.format_exc())
finally:
    if app is not None:
        try:
            app.monitor.stop()
        except Exception:
            pass
        try:
            app.destroy()
        except Exception:
            pass
    if cfg_backup is not None:
        try:
            with open(cfg_path, "wb") as fh:
                fh.write(cfg_backup)
        except Exception:
            pass

# ------------------------------------------------------------------ ozet
print("\n" + "=" * 60)
print(f"SONUC: {len(PASSED)} basarili, {len(FAILED)} basarisiz")
if FAILED:
    print("BASARISIZ TESTLER:")
    for name in FAILED:
        print("  -", name)
sys.exit(1 if FAILED else 0)
