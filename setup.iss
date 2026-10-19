; Lunaci Smart USB & SD Card Utility — Inno Setup kurulum betiği
; Derlemek için: ISCC.exe setup.iss

#define MyAppName "Lunaci Smart USB & SD Card Utility"
#define MyAppVersion "1.3.2"
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

[CustomMessages]
turkish.CreateDesktopIcon=Masaüstü kısayolu oluştur
english.CreateDesktopIcon=Create a desktop shortcut
turkish.AdditionalIcons=Ek kısayollar:
english.AdditionalIcons=Additional icons:
turkish.LaunchApp=Uygulamayı başlat
english.LaunchApp=Launch the application

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\LunaciSmartUSBCardUtility.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; Raporlar programın yanına yazılır; ilk kurulumda klasörü hazırla
Name: "{app}\reports"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent
