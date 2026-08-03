; Script Inno Setup pour Lumio.
; Génère un installeur unique (Lumio-Setup.exe) à partir du build PyInstaller
; (dist/Lumio/). Compiler avec : iscc lumio.iss

#define MyAppName "Lumio"
#define MyAppVersion "1.0.4"
#define MyAppExeName "Lumio.exe"

[Setup]
AppId={{7B6E9C2A-4F1D-4E8B-9A3C-1D2E3F4A5B6C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Lumio
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=Lumio-Setup
SetupIconFile=desktop\frontend\lumio_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "dist\Lumio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer Lumio"; Flags: nowait postinstall skipifsilent
