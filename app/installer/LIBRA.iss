; Inno Setup script for LIBRA – Crossover Randomizer (Windows). Run by build.py after PyInstaller:
;     ISCC /DAppVersion=1.0.0 /DSourceDir=<folder made by PyInstaller> LIBRA.iss

#define AppName "LIBRA"
#define AppTitle "LIBRA – Crossover Randomizer"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "build\dist\LIBRA"
#endif
#define AppExe "LIBRA.exe"

[Setup]
AppId={{B3A6F0D2-7C41-4E58-9D2A-1F6E8C0B5A47}
AppName={#AppTitle}
AppVersion={#AppVersion}
AppVerName={#AppTitle} {#AppVersion}
AppPublisher=NUDZ
; per-user install: no administrator rights needed
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
OutputDir=output
OutputBaseFilename=LIBRA-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppTitle}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Shortcuts:"

[InstallDelete]
; old libraries of a previous version, so nothing stale is left after an update
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "{#AppTitle}: balanced randomization of treatment schedules"; Tasks: desktopicon
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Comment: "{#AppTitle}: balanced randomization of treatment schedules"

[Registry]
; double-click a .libra project file to open it in the app
Root: HKCU; Subkey: "Software\Classes\.libra"; ValueType: string; ValueName: ""; ValueData: "LIBRA.Project"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\LIBRA.Project"; ValueType: string; ValueName: ""; ValueData: "LIBRA project"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\LIBRA.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKCU; Subkey: "Software\Classes\LIBRA.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
