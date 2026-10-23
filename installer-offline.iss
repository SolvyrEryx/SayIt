; Inno Setup script for SayIt — FULL OFFLINE installer variant.
;
; Identical to installer.iss except it ships the four validated INT8 ASR models
; (English Fast = Parakeet INT8, English Higher Accuracy = Whisper Small INT8,
; Hindi = IndicConformer INT8, Kannada = IndicConformer INT8) inside the app so
; dictation works with no model download. The models are staged into the
; Briefcase app tree under src/app/sayit/resources/bundled_models (the app's own
; package; third-party dependencies live under src/app_packages/) by
; scripts/build.py --variant offline (which runs the integrity gate first).
;
; Output: SayIt-Setup-x64-Offline.exe
; The smaller download-on-demand installer is still produced by installer.iss.

#define MyAppName "SayIt"
#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif
#define MyAppPublisher "SayIt"
#define MyAppURL "https://github.com/VptrCipher/SayIt"
#define MyAppExeName "SayIt.exe"
#define MyAppIcon "icons\sayit.ico"
; Windows Application User Model ID. MUST match the process AUMID set by
; SetCurrentProcessExplicitAppUserModelID (WINDOWS_APP_USER_MODEL_ID in
; src/sayit/app.py) so Windows routes reminder toast/balloon notifications to
; SayIt. Set on every app-launching shortcut below.
#define MyAppUserModelID "VptrCipher.SayIt"

[Setup]
; Same AppId as the on-demand installer: Offline and on-demand are the SAME
; product (one must upgrade/replace the other in place), they differ only in
; whether model weights ship inside the installer.
; Production emits the EXACT original literal. An isolated QA build passes
; /DMyAppIdOverride={{<guid>} so it registers under a DIFFERENT uninstall key
; and never disturbs the production registration.
#ifdef MyAppIdOverride
AppId={#MyAppIdOverride}
#else
AppId={{13AD1DC3-955C-4618-86E0-36B01ABF13EF}}
#endif
; A QA build can relabel the user-facing name / install dir / Start Menu group
; (via /DMyInstallName=...) so it installs SIDE-BY-SIDE with the real app.
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
; OutputDir / OutputBaseFilename are overridable for an isolated QA build via
; /D defines, without editing the validated production defaults.
#ifndef MyOutputDir
  #define MyOutputDir "installer-output"
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "SayIt-Setup-x64-Offline"
#endif
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma2
SolidCompression=yes
MinVersion=10.0
SetupIconFile={#MyAppIcon}
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start SayIt when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Install the full Briefcase build folder. For the offline variant this already
; contains the staged + integrity-verified model weights under
; app_packages\sayit\resources\bundled_models (placed there by the build step).
Source: "build\sayit\windows\app\src\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyInstallName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"
Name: "{group}\{cm:UninstallProgram,{#MyInstallName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyInstallName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; Tasks: desktopicon
Name: "{userstartup}\{#MyInstallName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelID}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyInstallName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; User data (settings, any downloaded models, vocabulary, logs, history) lives
; in %LOCALAPPDATA%\SayIt and is NOT removed automatically on uninstall. The
; bundled offline models live under {app} and are removed with the app.

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM {#MyAppExeName} /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(500);
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\SayIt');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete SayIt user data (settings and any downloaded speech models) in'
                + #13#10 + DataDir + '?' + #13#10 + #13#10
                + 'Choose No to keep your settings for a future reinstall.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
