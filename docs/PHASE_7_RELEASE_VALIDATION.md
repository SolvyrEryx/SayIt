# Phase 7 — Release Validation (SayIt Windows)

This document separates what was actually verified in the development
environment from what still requires a real installed-application run and a
human on real hardware. The three categories below are kept strictly distinct.
Nothing in "USER PHYSICAL VALIDATION REQUIRED" has been performed by the
developer tooling.

Environment of record: Windows, Python 3.12, uv, Briefcase 0.3.26. Inno Setup
(`iscc`) was **not available** in this environment, so the final `.exe`
installer could not be compiled locally; it is produced by the
`windows-latest` GitHub Actions job (which has Inno Setup) and the clean-install
flow must be validated there or on a real machine.

---

## AUTOMATED VERIFIED (ran here, reproducible)

- Full unit/integration suite: **338 passed, 0 failed, 5 deselected**
  (`uv run pytest -m "not slow"`).
- Slow real-ASR tests: **2 passed** (`tests/test_real_asr.py -m slow`) — real
  Sherpa-ONNX inference path on an installed model.
- Slow streaming-capability + model-gated tests: pass / skip cleanly.
- Benchmarks reproduce:
  - Phase 6G: raw WER 11.0% → processed 4.7% (A–E referenced set).
  - Phase 6H: model load ~4.3 s, median RTF ~0.10, 0 nondeterministic clips.
  - Phase 6J vocabulary latency: ~0.06 ms (10 entries), ~0.59 ms (100),
    ~3.7 ms (500), ~53 ms (1000) median.
- Packaging config: `briefcase create windows app` and
  `briefcase build windows app` both succeed and produce
  `build\sayit\windows\app\src\SayIt.exe` (138,752 bytes).
- Executable metadata (via `rcedit`): ProductName=SayIt, FileDescription=SayIt,
  CompanyName=SayIt, ProductVersion/FileVersion=0.1.0, OriginalFilename=SayIt.exe
  — no "SayIt" developer branding on the user-facing executable.
- Bundle self-containment: the sayit package, PySide6, sherpa_onnx (incl.
  native `sherpa-onnx-c-api.dll`), and all declared dependencies are bundled.
  Bundle size ≈ 480 MB (no ASR model weights bundled — correct).
- Packaging security scan: no `.env`, `.log`, private key, or SayIt
  test/benchmark fixtures in the bundle. Files matching "credential/secret/
  token" are legitimate dependency source modules (litellm/botocore/openai), not
  secret values. Standard CA bundles (`cacert.pem`) only.
- Version consistency: single version 0.1.0 across `__init__.py`,
  `pyproject.toml`, Briefcase config, exe metadata, and the `.iss` default; the
  build script injects the git-tag version into pyproject + `__init__`.
- `.iss` hardened: product "SayIt", output `SayIt-Setup-x64.exe`, Start Menu +
  optional Desktop/startup shortcuts, uninstaller, and a prompt (default: keep)
  before deleting user data in `%LOCALAPPDATA%\SayIt`.
- Model/data path resolution is install-location independent:
  `platformdirs.user_data_dir("SayIt")` → `%LOCALAPPDATA%\SayIt\models`.
- Autostart resolves the exe dynamically (`sys.executable` when frozen), so it is
  correct regardless of the `SayIt.exe` name.

## INSTALLED-APPLICATION VERIFIED (requires Inno Setup build + install)

> Not performed in this environment (no `iscc`). Must be done on the CI
> `windows-latest` runner artifact or a real Windows machine.

- [ ] `iscc installer.iss` compiles `installer-output\SayIt-Setup-x64.exe`.
- [ ] Installer is double-clickable and installs without a dev environment.
- [ ] Start Menu entry "SayIt" created; optional Desktop/startup shortcuts work.
- [ ] Installed `SayIt.exe` launches, shows the tray, no stray console window.
- [ ] Uninstaller present; uninstall removes app files; user-data prompt behaves
      (default keep).
- [ ] Reinstall preserves settings + downloaded models.
- [ ] SHA-256 and size recorded for the actual artifact.

## USER PHYSICAL VALIDATION REQUIRED (human on real hardware)

> Requires a real microphone, speakers, display, and target apps. Not observed.

- [ ] First-run wizard: welcome/privacy, mic test, model step, hotkey, try-it.
- [ ] Model download from the installed app into `%LOCALAPPDATA%\SayIt\models`.
- [ ] Hold hotkey → speak → release → text inserted at cursor exactly once.
- [ ] Phase 6G/6I/6J effects visible on dictated technical speech.
- [ ] Insertion into a real text editor AND a browser field.
- [ ] Esc cancellation; repeated utterances; shutdown during transcription.
- [ ] Missing/unavailable microphone handled gracefully.
- [ ] Interrupted model download handled gracefully.
- [ ] Settings/model state persist across restart.
- [ ] Memory stable over a long session on the target machine.

Procedures for the installed-app and physical steps are the sequences in the
Phase 7 instructions (§8, §22, §25) and the earlier phase manual-validation docs
(`docs/PHASE_6H_MANUAL_VALIDATION.md`, `_6I_`, `_6J_`).
