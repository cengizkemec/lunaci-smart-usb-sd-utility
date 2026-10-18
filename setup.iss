; Lunaci Smart USB & SD Card Utility — Inno Setup kurulum betiği
; Derlemek için: ISCC.exe setup.iss

#define MyAppName "Lunaci Smart USB & SD Card Utility"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Cengiz Kemeç"
#define MyAppURL "https://cengizkemec.com.tr/"
#define MyAppExeName "LunaciSmartUSBCardUtility.exe"

[Setup]
AppId={{458E6791-1FAE-473F-8F12-5F7CF6C34869}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\Lunaci
DefaultGroupName={#MyAppName}
OutputDir=dist
OutputBaseFilename=LunaciSetup
SetupIconFile=assets\logo.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstü kısayolu oluştur"; GroupDescription: "Ek kısayollar:"
Name: "quicklaunchicon"; Description: "Hızlı başlat çubuğuna ekle"; GroupDescription: "Ek kısayollar:"; Flags: unchecked

[Files]
Source: "dist\LunaciSmartUSBCardUtility.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Raporlar programın yanına yazılır; ilk kurulumda klasörü hazırla
Name: "{app}\reports"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} uygulamasını başlat"; Flags: nowait postinstall skipifsilent
