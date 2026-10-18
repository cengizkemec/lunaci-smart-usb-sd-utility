# Lunaci Smart USB & SD Card Utility

Windows 10/11 için Python + CustomTkinter ile geliştirilmiş modern USB / SD kart
biçimlendirme, dosya aktarımı, imaj yazma ve disk onarım aracı.

## Özellikler

- **Canlı cihaz algılama** — PowerShell / wmic / psutil sıralamasıyla arka planda
  tak-çıkar olayları, cihaz adı, harf, kapasite, dosya sistemi, veri yolu (USB/SD),
  disk numarası ve yazma koruması bilgisi.
- **Sağlık LED'i** — yazma/okuma + SHA-256 doğrulama testi; Yeşil (İYİ), Sarı
  (UYARI), Kırmızı (KRİTİK). Yeni cihaz takılınca otomatik test edilir.
- **Akıllı biçimlendirme** — mevcut dosya sistemi algılanır ve listede varsayılan
  seçilir. FAT32 / NTFS / exFAT (diskpart). Hızlı ve detaylı (sektör taramalı)
  biçimlendirme; gerekirse otomatik `clean + create partition` yedeği.
- **Klasörü Diske Yaz** — seçilen klasörün içeriğini diskin köküne kopyalar
  (shutil motoru veya `robocopy`); canlı log + ilerleme yüzdesi. Aynı adlı,
  boyut/zamanı değişmemiş dosyalar atlanır.
- **Klasörü ZIP Yaz** — seçilen klasörü diskin kökünde `<Klasor>.zip` olarak
  paketler (ZIP_DEFLATED, %6 sıkıştırma).
- **ISO Yazdır** — `.iso` dosyasını ham (DD) modda diske yazar
  (`\\.\X:` üzerinden CreateFile/WriteFile).
- **ZIP Yazdır** — bir `.zip` arşivinin içeriğini diskin köküne güvenle açar
  (path traversal koruması ile).
- **Bozuk Diski Onar** — `attributes disk/volume clear readonly` + `chkdsk /f /r`;
  RAW diskte otomatik bölüm yenileme.
- **Tema** — Koyu / Aydınlık / Sistem teması (Windows temasına otomatik uyum).
- **Canlı log konsolu** — diskpart çıktıları, kopyalama yüzdeları, zaman
  damgaları; renkli seviyeler; "Temizle" ve "Kaydet".
- **Raporlar** — biçimlendirme/onarım/kopyalama raporları hedef klasörün
  `LunaciReports` alt klasörüne kaydedilebilir.

## Kurulum

```powershell
cd "SD-USB Formatter"
py -m pip install -r requirements.txt
py main.py
```

> **Not:** Uygulama başlarken yönetici (UAC) izni ister. "Hayır" derseniz sınırlı
> modda açılır: algılama ve kopyalama çalışır, diskpart/chkdsk/ISO işlemleri
> çalışmaz.

## VS Code ile geliştirme

1. Python uzantısını kurun, yorumlayıcı olarak `py` / Python 3.11+ seçin.
2. `Ctrl+Shift+P` → *Python: Select Interpreter* → proje klasörü.
3. `F5` ile "Lunaci: Uygulamayı Çalıştır" yapılandırmasını kullanın
   (`.vscode/launch.json` hazır).

## Dosya yapısı

```
main.py            Giriş: DPI ayarı + UAC yükseltilmesi + uygulama
app.py             CustomTkinter arayüzü (tüm paneller, konsol, görev motoru)
disk_manager.py    Cihaz algılama, diskpart biçimlendirme/onarım, DeviceMonitor
file_ops.py        Kopyalama (shutil/robocopy), ham ISO yazımı, ZIP işlemleri
health.py          Okuma/yazma + SHA-256 doğrulama sağlık testi
config_manager.py  config.json atomik okuma/yazma
utils.py           Yetki, süreç çalıştırma (diskpart/powershell), log kayıtları
config.json        Kullanıcı ayarları (tema, hedef klasör, motor, raporlar…)
```

## Güvenlik notları

- Sistem diski (boot/system) asla hedef listede görünmez; biçimlendirme/onarım
  öncesi cihaz yeniden doğrulanır, disk numarası PowerShell ile tespit edilir.
- "Detaylı biçimlendirme" tüm sektörleri sıfırlar; büyük kartlarda saatler sürebilir.
- ISO yazımı ham moddur: hedef diskteki her şey silinir, işlem sonrasında
  cihazı çıkarıp takmak gerekir.
