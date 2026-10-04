# SayIt Icon & OS Branding

## Canonical source

The canonical packaged application icon is icons/sayit.svg. It is intentionally
identical to website/src/app/icon.svg and is not redrawn per platform.

## Build-time derivatives

scripts/generate_icons.py derives the Windows and Linux assets from the SVG.
Generated binaries are gitignored so there is one authoritative artwork source.

Windows ICO:
- 16, 32, 48, 64, 128, 256

Linux PNG:
- 16, 32, 48, 64, 128, 256, 512

The official package build (uv run python scripts/build.py) generates these
assets before invoking Briefcase.

## Packaging

Briefcase uses icon = "icons/sayit", which lets the platform template select
the platform-specific extension from the same prefix.

Inno Setup uses the generated icons/sayit.ico for the installer and the installed
SayIt.exe for application shortcut/uninstaller identity.

## Expected Windows surfaces

After a fresh installation the approved SayIt icon should appear in:

- SayIt.exe in Explorer
- installer
- Desktop shortcut
- Start Menu
- Windows Search
- taskbar
- pinned taskbar
- Alt+Tab
- window/title bar
- Settings/setup windows
- system tray
- Installed Apps/uninstaller where Windows exposes an icon

The old BeeWare bee must not appear on normal user-facing surfaces.

## Linux

The same canonical SVG is rasterized into Briefcase-compatible PNG derivatives.
Verify the launcher, dock, app switcher and window identity only on environments
that are actually tested.

## Validation

AUTOMATED VERIFIED:
- canonical source and configuration
- installer directives
- generator structure
- build ordering

PACKAGED ARTIFACT VERIFIED:
- actual SayIt.exe/icon resource after a fresh build

USER PHYSICAL VALIDATION REQUIRED:
- Windows shell surfaces
- installer
- Linux launcher/dock where applicable

Do not use icon-cache clearing as the implementation; it is only a diagnostic
for stale OS presentation.
