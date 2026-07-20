; Inno Setup script for the M110 Windows installer.
; Build (after the PyInstaller onedir build) with:
;   iscc /DMyAppVersion=0.1.0 packaging\windows\M110.iss
; build_windows.ps1 does this for you. Requires Inno Setup 6.3+.

#define MyAppName "M110"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "Michael Merideth"
#define MyAppExeName "M110.exe"
#define MyAppURL "https://github.com/mjm1138/m110"

[Setup]
; AppId uniquely identifies M110 for upgrade/uninstall — keep it STABLE across releases.
AppId={{254AD386-F2A6-4DAB-800F-DDC4E12F5EFB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install by default — no admin/UAC prompt for a beta hobbyist. Users can
; still choose all-users via the dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=M110-{#MyAppVersion}-setup
SetupIconFile=M110.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; A onedir app must fully replace on upgrade — wipe the install dir first so a stale
; older `m110-*.dist-info` (or any module dropped between versions) can't linger. Left
; behind, `importlib.metadata` read the OLD dist-info and the About box reported an
; older beta (#74). Runs at the start of the install step, before [Files]. {app} holds
; only program files — the user's data lives in ~\Documents\M110 and ~\.m110.
Type: filesandordirs; Name: "{app}\*"

[Files]
Source: "..\..\dist\M110\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
