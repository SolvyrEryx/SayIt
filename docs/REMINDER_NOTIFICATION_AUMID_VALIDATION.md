# Reminder Notification Fix — Windows Shortcut AUMID Validation

This document records the fix for "the reminder scheduler fires but no Windows
notification appears" in the **packaged** app, and how to verify it on a real
machine. It keeps automated (ran here) evidence strictly separate from the
manual validation that still requires a real install.

## Resolution summary (two layers)

The bug had **two** layers; fixing only the first was necessary but NOT
sufficient:

1. **Missing shortcut AUMID (necessary fix).** The installer-created shortcuts
   had no `System.AppUserModel.ID`, so Windows could not attribute a
   notification to SayIt. Fixed by stamping the AUMID on every app-launching
   shortcut (details below).
2. **Legacy balloon delivery path (the actual reason nothing showed).** Even
   with the AUMID, `QSystemTrayIcon.showMessage()` only raises a legacy
   `Shell_NotifyIcon` *balloon*. On Windows 10/11 that balloon is handed to the
   shell but is frequently **not rendered** and does **not** persist to the
   Action Center. Fixed by adding `WindowsToastNotifier`, which raises a real
   **WinRT `ToastNotification`** under the AUMID via the `winsdk` package;
   `build_notifier` now prefers it on Windows and falls back to the tray.

### Verified evidence (observed on a real Windows install)

An isolated QA build (`SayIt QA`, its own AppId so it never touches the
production install) was installed, and launched **from its AUMID-stamped Start
Menu shortcut** with `SAYIT_TEST_REMINDER_SECONDS=20`:

- Installed shortcut AUMID read back via Shell COM = `VptrCipher.SayIt` (match).
- App log: `build_notifier: using WindowsToastNotifier (WinRT toast, persists
  to Action Center)` and, at fire time,
  `WindowsToastNotifier.notify delivered to WinRT platform (title='SayIt test
  reminder', aumid=VptrCipher.SayIt)`.
- **Windows notification database (`wpndatabase.db`) persisted the toast**
  under `PrimaryId=VptrCipher.SayIt`, `Type=toast`, `ArrivalTime` equal to the
  log fire time, with payload text `SayIt test reminder` / `Scheduled for ...`.

Contrast captured in the same environment:

| Delivery path | Handler registered | Row persisted to Action Center |
|---|---|---|
| `QSystemTrayIcon.showMessage` balloon | yes (AUMID `LastNotificationAddedTime` updated) | **no (0 rows)** |
| WinRT `ToastNotification` (winsdk) | yes | **yes (toast row with title/time)** |

Notification settings were confirmed not suppressing (toasts enabled globally,
per-AUMID, balloon tips enabled; no Focus Assist override set).

### Visible-banner status: CONFIRMED by the user (with DND off)

The on-screen pop-up banner was **observed by the user**: with Windows Do Not
Disturb / Focus Assist turned OFF, the installed QA app displayed its
"SayIt test reminder" banner when the scheduler fired. This closes the
acceptance test.

Earlier in the investigation the banner did not appear; that was conclusively
traced to an **external Windows setting — Focus Assist set to "Priority only"**,
which suppresses on-screen banners for non-priority apps while still delivering
them to the Action Center. This was proven independently of SayIt: a control
toast raised under the built-in Windows PowerShell AUMID was *also* suppressed
under the same setting, and `ToastNotifier.setting` reported `ENABLED` for
SayIt (i.e. not blocked for the app). It was not a SayIt defect.

Two distinct, verifiable facts therefore hold and are NOT in tension:
- **Platform delivery** (automated, reproducible): the WinRT toast is accepted
  and persisted to the Action Center under `VptrCipher.SayIt` at the fire time
  — captured from `wpndatabase.db` on this host.
- **On-screen banner** (human visual): confirmed by the user once Focus Assist
  was off. When Focus Assist/DND is active, Windows intentionally routes the
  toast to the Action Center without a banner — expected OS behavior, not a bug.

No reopening of the notifier implementation is warranted; there is no evidence
of a SayIt defect.

---

## Root cause

Windows routes a toast/balloon notification to an app identity only when the
**shortcut that launched the process** carries a `System.AppUserModel.ID`
(AUMID) matching the AUMID the process sets at runtime.

- The process sets its AUMID via `SetCurrentProcessExplicitAppUserModelID`
  (see `WINDOWS_APP_USER_MODEL_ID = "VptrCipher.SayIt"` in
  `src/sayit/app.py`).
- The installer-created Start Menu / desktop / startup shortcuts had **no**
  AUMID at all.

With a missing shortcut AUMID, the shell cannot resolve a consistent identity,
so it **silently suppresses** the toast even though
`QSystemTrayIcon.showMessage()` returns without error. That is exactly the
observed symptom: `TrayNotifier` is reached, `showMessage()` succeeds, the
scheduler fires, but nothing is displayed.

Note: a from-source run (`uv run python -m sayit`) is launched from a console,
not from an AUMID-stamped shortcut, so it exhibits the same suppression. The
fix targets the installed shortcut, which is the supported launch path.

## The fix

### Delivery backend (the decisive fix)

- Added `WindowsToastNotifier` in `src/sayit/core/reminders/notifier.py`: a
  Windows-only backend that raises a WinRT `ToastNotification` under
  `WINDOWS_APP_USER_MODEL_ID` using `winsdk`. It reports `delivered=True,
  visibility_unconfirmed=True` on platform acceptance (honest: still no
  eyeball-level API), and an honest NOT-delivered result if `winsdk` is missing
  or the call fails.
- `build_notifier` now prefers `WindowsToastNotifier` on Windows when `winsdk`
  is importable, and otherwise falls back to the existing `TrayNotifier`
  (unchanged macOS/Linux behaviour).
- Added `winsdk` as a Windows-only dependency in `pyproject.toml`
  (`[project].dependencies` and the Briefcase `requires`, both with
  `; sys_platform == 'win32'`), so the packaged Windows app bundles it.
- The scheduler and the `Notifier`/`NotificationResult` abstraction were **not**
  changed.

### Shortcut AUMID (necessary pre-requisite)

In both `installer.iss` and `installer-offline.iss`:

1. Added a shared define:
   ```
   #define MyAppUserModelID "VptrCipher.SayIt"
   ```
   This value **must stay identical** to `WINDOWS_APP_USER_MODEL_ID` in
   `src/sayit/app.py`.
2. Added `AppUserModelID: "{#MyAppUserModelID}"` to every app-launching
   shortcut in `[Icons]`:
   - `{group}\SayIt` (Start Menu)
   - `{autodesktop}\SayIt` (optional desktop icon)
   - `{userstartup}\SayIt` (optional run-at-startup)

   The uninstaller shortcut is intentionally left without an AUMID — it does
   not launch the app.

Inno Setup's `[Icons]` `AppUserModelID` parameter writes the
`System.AppUserModel.ID` shell property onto the generated `.lnk`.

The scheduler and notifier were **not** redesigned. `TrayNotifier` still
honestly reports `delivered=True, visibility_unconfirmed=True`, because no
cross-platform API can confirm on-screen visibility.

## Automated verification (ran in this environment)

```
uv run pytest tests/test_installer_aumid.py tests/test_icon_packaging.py \
  tests/test_reminders_notifier_tray.py tests/test_v020_release.py -q
# => 35 passed
```

`tests/test_installer_aumid.py` asserts, at the source level (no Inno Setup or
Windows required):

- Each installer's `#define MyAppUserModelID` equals the process AUMID
  (`WINDOWS_APP_USER_MODEL_ID`) parsed from `src/sayit/app.py` — exactly.
- Every app-launching shortcut (`{group}`, `{autodesktop}`, `{userstartup}`)
  carries `AppUserModelID: "{#MyAppUserModelID}"`.
- The uninstaller shortcut does **not** carry an AUMID.

## Building the QA installer (does NOT overwrite validated installers)

`installer.iss` now accepts `/D` overrides so a QA build lands in a separate
location — and, for a fully isolated side-by-side QA install, under a **distinct
AppId / name / install dir / Start Menu group** — leaving the preserved,
validated installers in `installer-output/` (and
`installer-output/validated-2026-10-17/`) byte-for-byte untouched AND never
disturbing a real production install or its registration.

```powershell
# 1) Build the app bundle (ondemand = smaller; no model staging).
#    This also bundles winsdk (required by WindowsToastNotifier) on Windows.
uv run python scripts/build.py --variant ondemand
#    -> build\sayit\windows\app\src\SayIt.exe  (and app_packages\winsdk\)

# 2) Compile an ISOLATED QA installer: distinct output name + AppId + name so
#    it installs SIDE-BY-SIDE and cannot overwrite the production install,
#    its shortcut, or its uninstall registry key.
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" `
    /DMyOutputBaseFilename=SayIt-Setup-x64-QA `
    "/DMyOutputDir=installer-output\qa" `
    "/DMyAppIdOverride={{B2C3D4E5-6F70-4812-9A3B-C0FFEE115AF1}" `
    "/DMyInstallName=SayIt QA" `
    installer.iss
#    -> installer-output\qa\SayIt-Setup-x64-QA.exe  (installs as "SayIt QA")
```

Without `/DMyAppIdOverride` / `/DMyInstallName`, the script emits the EXACT
production defaults (AppId `{{13AD1DC3-...}}`, name `SayIt`), so production
builds are unaffected.

Verified in this environment: the isolated QA installer compiled to
`installer-output\qa\SayIt-Setup-x64-QA.exe`, installed to
`%LOCALAPPDATA%\Programs\SayIt QA` under its own AppId, and the preserved
installers in `installer-output\` and `installer-output\validated-2026-10-17\`
kept their original timestamps/sizes. `installer-output/` is gitignored.


## MANUAL VALIDATION REQUIRED (real Windows machine)

Compiling the `.exe` requires Inno Setup (`ISCC.exe`). The automated,
reproducible delivery proof below (Action Center DB) was performed here; the
one remaining purely-visual step (watching the transient toast) is a human
glance.

### 0. Verify the toast persisted to the Action Center (automated, reproducible)

This is the strongest automated proof that the notification was delivered and
is user-reachable. After the reminder fires, read the Windows notification DB:

```powershell
# Copy the live DB (+WAL) so SQLite can read it while the service holds it.
$db = "$env:LOCALAPPDATA\Microsoft\Windows\Notifications\wpndatabase.db"
$tmp = "$env:TEMP\wpn"; New-Item -Force -ItemType Directory $tmp | Out-Null
Copy-Item "$db*" $tmp -Force
# Any SQLite reader works; expect a row with Type='toast',
# PrimaryId='VptrCipher.SayIt', and payload text 'SayIt test reminder'.
```

Also check `HKCU:\Software\Microsoft\Windows\CurrentVersion\Notifications\
Settings\VptrCipher.SayIt` → `LastNotificationAddedTime` should equal the fire
time.

### 1. Verify the installed shortcut's AUMID (PowerShell)

After installing the QA build and launching once, inspect the Start Menu
shortcut's stored `System.AppUserModel.ID` property:

```powershell
$lnk = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\SayIt\SayIt.lnk'
Test-Path $lnk   # expect: True

# Read the System.AppUserModel.ID property (PKEY_AppUserModel_ID) from the .lnk
$shell  = New-Object -ComObject Shell.Application
$folder = $shell.Namespace((Split-Path $lnk))
$item   = $folder.ParseName((Split-Path $lnk -Leaf))
# Property index 0 with the canonical name differs per OS; enumerate to find it:
$item.ExtendedProperty('System.AppUserModel.ID')
# expect: VptrCipher.SayIt
```

If `ExtendedProperty('System.AppUserModel.ID')` returns empty on your OS build,
use the property store via the `Windows.ApplicationModel`/`propsys` route, or
simply confirm the define is present in the compiled script. The authoritative
check is the end-to-end toast test below.

> If the installer was created per-machine (admin install), the shortcut is
> under `%ProgramData%\Microsoft\Windows\Start Menu\Programs\SayIt` instead of
> `%APPDATA%`. This project installs per-user by default
> (`PrivilegesRequired=lowest`), so `%APPDATA%` is the expected location.

### 2. End-to-end toast test (the real acceptance test)

1. Install the QA build (`SayIt-Setup-x64-QA.exe`, see the build doc) — do
   **not** overwrite any preserved validated installer.
2. Launch SayIt **from its Start Menu shortcut** (not from a console). This is
   what stamps the process with the shortcut AUMID.
3. Open **CMD** and set the manual QA hook, then launch from the shortcut in
   the same session is not required — the env var must be visible to the app
   process. Easiest reliable method:
   ```cmd
   set SAYIT_TEST_REMINDER_SECONDS=20
   "%LOCALAPPDATA%\Programs\SayIt\SayIt.exe"
   ```
   (Launching the installed `.exe` from a CMD that has the env var set still
   uses the installed binary; for the strict shortcut-launch path, instead set
   the variable as a user environment variable via
   `setx SAYIT_TEST_REMINDER_SECONDS 20`, open a new session, then launch from
   the Start Menu shortcut.)
4. Wait ~20 seconds. **Expected:** a Windows notification titled like a SayIt
   test reminder appears (action center / bottom-right toast).

### 3. If no toast appears

Before any architectural change, check the Windows notification path:

- **Settings → System → Notifications**: notifications are On globally and for
  SayIt specifically (SayIt should appear in the per-app list once it has
  attempted at least one notification under its AUMID).
- **Focus Assist / Do Not Disturb**: turn off; it silently suppresses toasts.
- **Balloon tips**: on some policies legacy balloon tips are disabled; confirm
  `HKCU\...\Advanced\EnableBalloonTips` is not `0`.
- Confirm the process AUMID at runtime matches: the app logs
  `Set Windows AppUserModelID=VptrCipher.SayIt` on startup. If this log line is
  missing, the ctypes call failed and toasts will be suppressed regardless of
  the shortcut.
- Re-check step 1: the shortcut AUMID must read back as `VptrCipher.SayIt`.

Only after these are ruled out should the notification API path (e.g. moving
from `QSystemTrayIcon.showMessage` to the WinRT ToastNotification API) be
considered.
