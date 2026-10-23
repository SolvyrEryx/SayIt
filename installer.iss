; Inno Setup script for SayIt (Windows installer)
; Produces SayIt-Setup-x64.exe with Start Menu / optional Desktop shortcuts and
; an uninstaller. The product presents to users as "SayIt". Internal technical
; identifiers (the executable name, package, and the %LOCALAPPDATA%\SayIt
; data directory) are "SayIt".

#define MyAppName "SayIt"
#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif
#define MyAppPublisher "SayIt"
#define MyAppURL "https://github.com/VptrCipher/SayIt"
; The Briefcase-built executable is named SayIt.exe (technical identifier).
#define MyAppExeName "SayIt.exe"
#define MyAppIcon "icons\sayit.ico"
; Windows Application User Model ID. This MUST match the AUMID the running
; process sets via SetCurrentProcessExplicitAppUserModelID (see
; WINDOWS_APP_USER_MODEL_ID in src/sayit/app.py). Windows only routes
; toast/balloon notifications (used by reminders) to the app when the LAUNCHING
; shortcut carries the same System.AppUserModel.ID as the process. Without it,
; QSystemTrayIcon.showMessage() succeeds silently but no notification appears.
#define MyAppUserModelID "VptrCipher.SayIt"

[Setup]
; Unique application identifier - NEVER change this after first release.
; Production emits the EXACT original literal. An isolated QA build passes
; /DMyAppIdOverride={{<guid>} so it registers under a DIFFERENT uninstall key
; and never disturbs the production registration. The override value must
; already include Inno's leading escaped brace, e.g. {{B2C3...}.
#ifdef MyAppIdOverride
AppId={#MyAppIdOverride}
#else
AppId={{13AD1DC3-955C-4618-86E0-36B01ABF13EF}}
#endif
; A QA build can relabel the user-facing name / install dir / Start Menu group
; so it installs SIDE-BY-SIDE with the real app and never overwrites its
; shortcut, files, or data. Production defaults below are unchanged.
#ifndef MyInstallName
  #define MyInstallName MyAppName
#endif
AppName={#MyInstallName}
AppVersion={#MyAppVersion}
AppVerName={#MyInstallName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyInstallName}
DefaultGroupName={#MyInstallName}
AllowNoIcons=yes
UninstallDisplayName={#MyInstallName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; Output settings - the installer is created in installer-output/.
; OutputDir and OutputBaseFilename can be overridden on the ISCC command line
; (e.g. a QA build) via /D defines, without editing the validated defaults:
;   ISCC.exe /DMyOutputBaseFilename=SayIt-Setup-x64-QA /DMyOutputDir=installer-output\qa installer.iss
#ifndef MyOutputDir
  #define MyOutputDir "installer-output"
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "SayIt-Setup-x64"
#endif
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
; Compression settings
Compression=lzma2
SolidCompression=yes
; Windows version requirements
MinVersion=10.0
; Installer appearance
SetupIconFile={#MyAppIcon}
WizardStyle=modern
; Privilege requirements - install for current user by default (no UAC prompt).
; App installs to: C:\Users\<User>\AppData\Local\Programs\SayIt
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; 64-bit architecture settings
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start SayIt when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Install all files from the Briefcase build folder. Briefcase places the app
; (executable + bundled Python runtime + resources) under app\src.
Source: "build\sayit\windows\app\src\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyInstallName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{group}\{cm:UninstallProgram,{#MyInstallName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyInstallName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; Tasks: desktopicon
Name: "{userstartup}\{#MyInstallName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyInstallName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; NOTE: User data (settings, downloaded models, vocabulary, logs, history) lives
; in %LOCALAPPDATA%\SayIt and is intentionally NOT removed automatically on
; uninstall, so reinstalling preserves the user's setup and ~100MB-1GB models.
; The user is offered an explicit choice at uninstall time (see [Code]). SayIt
; also provides an in-app "Clear Data" action for users who want a full wipe.

[Code]
// Kill the running process before uninstalling to release file locks.
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM {#MyAppExeName} /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
  Result := True;
end;

// On uninstall, ASK before deleting user data (settings + downloaded models).
// Default is to KEEP it, so an accidental uninstall never destroys a user's
// multi-hundred-MB model cache or their configuration.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\SayIt');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete SayIt user data (settings and downloaded speech models) in'
                + #13#10 + DataDir + '?' + #13#10 + #13#10
                + 'Choose No to keep your settings and models for a future reinstall.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;

