# Phase 8 Validation — SayIt Local Intelligence Layer (8A–8H)

This document records exactly what was built in Phase 8, how it was verified, and
what still requires manual/physical validation. It strictly separates
**AUTOMATED VERIFIED**, **INSTALLED-APPLICATION VERIFIED**, and **USER PHYSICAL
VALIDATION REQUIRED**.

Phase 8 adds a deterministic, local-only, explainable intelligence layer on top
of the existing ASR pipeline. It does **not** modify the ASR model architecture,
recording state machine, cancellation, shutdown, model catalog, core privacy
defaults, or the existing 6G/6I/6J correction behavior.

---

## 1. Runtime pipeline (actual)

```
hotkey press
  → Safe Zone gate (8E) — BEFORE any audio; blocks recording in protected apps
  → AudioRecorder (record)
hotkey release
  → context resolved once (8A), snapshot passed to the worker
  → ASR (transcribe_chunked) → raw_text          [background worker]
  → Intelligence Orchestrator (8H) on raw_text:
        Voice Edit (8B) → Snippet (8C) → Structure (8G) → Developer (8D) → Dictate
        (first match wins; single pass; sets skip_correction for literal output)
  → 6G technical correction + 6I structured formatting   (skipped if skip_correction)
        (profile from 8A narrows which flags run)
  → 6J user vocabulary                                    (skipped if skip_correction)
  → optional LLM enhancement (off by default)
  → finished signal (adds intelligence metadata)
  → TextOutputController.output_text (clipboard + paste)  [existing safe path]
  → recent-output buffer updated (8B) for the next utterance's edits
```

The orchestrator **orchestrates** existing engines; it contains no second copy
of context, correction, or vocabulary logic.

---

## 2. Features

| Sub-phase | Feature | Module |
|-----------|---------|--------|
| 8A | Context Engine + Profiles (pre-existing, reused) | `core/context` |
| 8B | Voice Edit / Backtrack + bounded output buffer | `core/voice_commands` |
| 8C | Snippets (text-only expansion) | `core/snippets` |
| 8D | Developer Mode (casing + code block) | `core/developer` |
| 8E | Safe Zones (recording gate) | `core/safezones` |
| 8F | Remember Correction (explicit learning) | `core/learning` |
| 8G | Smart Structure / dictation commands | `core/structure` |
| 8H | Intelligence Orchestrator + contracts | `core/intelligence` |

---

## 3. Settings added

`intelligence_enabled`, `voice_edit_enabled`, `snippets_enabled`,
`structure_enabled`, `developer_mode_enabled`, `snippets` (list),
`safe_zones_enabled`, `protected_apps` (list), `correction_never_list` (list),
`remember_corrections_enabled`, plus the 8A fields
(`context_detection_enabled`, `context_override`, `context_app_mappings`).
All default to safe values and round-trip through the existing JSON settings with
malformed-value fallback.

---

## 4. UI changes

- **New Snippets tab** (navigation), modeled on the Vocabulary tab.
- **Configuration tab**: Context & Profiles section (8A), Local Intelligence
  toggles (8B–8G master + per-feature), Safe Zones section (enable + protected
  app list with Add/Remove/Clear).
- **Remember-correction dialog** (Remember / Not now / Never).
- **Home indicators**: context chip (`Context: …`), protected state
  ("SayIt paused — protected application"), and a brief voice-edit note.
- All reuse the existing motion system and honour reduced motion.

---

## 5. Tests — AUTOMATED VERIFIED

Command: `uv run pytest -m "not slow"` → **546 passed, 0 failed, 5 deselected.**
(390 pre-Phase-8B baseline + 156 new.)

New test files:
- `test_voice_edit_phase8b.py` — within/cross-utterance edits, negatives, buffer, determinism
- `test_snippets_phase8c.py` — matching, inline, conflicts, persistence, **AST security (no exec/subprocess)**
- `test_developer_phase8d.py` — casing (4 styles), code block, strong negatives
- `test_safezones_phase8e.py` — matching, transitions, fail-safe, privacy, **app recording-gate**
- `test_learning_phase8f.py` — candidate diff, suppression, entry creation, **privacy (no passive-learning imports)**
- `test_structure_phase8g.py` — breaks, ordinal lists, strong negatives
- `test_orchestrator_phase8h.py` — priority, disabled features, context modifier, **cross-feature matrix**, **loop prevention**, determinism
- `test_phase8_integration.py` — **E2E scenarios A–H** through the real worker + orchestrator (stub transcriber)
- `test_phase8_ui.py` — Snippets tab, Remember dialog, Config toggles
- `test_phase8_settings.py` — defaults, round-trip, malformed fallback

Cross-feature matrix covered: 8A+8D, 8A+8C, 8A+8B, 8C+6J, loop prevention,
disabled-feature pass-through, master-switch pass-through.

---

## 6. Performance — AUTOMATED VERIFIED

Measured locally (5,000 iterations each; temporary benchmark, not committed):

| Engine | median | p95 |
|--------|--------|-----|
| 8B voice edit (cross) | 0.0064 ms | 0.0092 ms |
| 8C snippet match | 0.0017 ms | 0.0026 ms |
| 8D casing | 0.0042 ms | 0.0062 ms |
| 8D code block | 0.0024 ms | 0.0035 ms |
| 8E safe zone | 0.0016 ms | 0.0025 ms |
| 8F learn candidate | 0.0057 ms | 0.0086 ms |
| 8G structure | 0.0009 ms | 0.0013 ms |
| 8H orchestrator (dictate) | 0.0106 ms | 0.0161 ms |
| 8H orchestrator (snippet) | 0.0050 ms | 0.0076 ms |

The whole intelligence layer is negligible compared with ASR (hundreds of ms).
Context detection (8A) real-OS path measured ~0.06 ms/op, once per dictation,
off the recording hot path.

---

## 7. Memory — AUTOMATED VERIFIED

50 mixed cycles (orchestrator + voice edit + snippet + structure + casing +
safe-zone + buffer updates) under `tracemalloc`: **5.7 KiB** growth. No leak; the
output buffer retains a single unit (not a growing history).

---

## 8. Privacy — AUTOMATED VERIFIED

- AST tests assert `core/context`, `core/safezones`, and `core/learning` import
  **no** screenshot/clipboard/screen-capture/keyboard-observer libraries
  (`mss`, `PIL`, `pyautogui`, `pyperclip`, `pynput`, `keyboard`).
- Context/Safe Zone read only foreground app/window **metadata**.
- Learning acts only on explicitly provided raw+corrected text; no passive
  observation. "Never" suppression is deterministic.
- No telemetry, no network calls in the new layer.

---

## 9. Security — AUTOMATED VERIFIED

- Snippets: AST test asserts the snippet modules contain no `eval`/`exec`/
  `system`/`popen`/`run`/`spawn` calls and import no `subprocess`/`pty`/`ctypes`.
  Command-like content ("git pull && rm -rf /") is returned as a literal string.
- Voice edit / developer / structure engines produce text only.
- Safe Zones demonstrably block `recorder.start()` in a protected app
  (`TestAppRecordingGate`).
- No feature provides a code/command execution surface.

---

## 10. Regression — AUTOMATED VERIFIED

- All pre-Phase-8 tests pass unchanged (6G technical correction, 6I structured
  formatting, 6J vocabulary, 8A context, 6H timing/cancellation, Phase 7
  settings/privacy). The worker's `finished` signal gained one optional
  trailing `object` (intelligence metadata); existing callers are unaffected
  (the app handler's new parameter defaults to `None`).
- With the orchestrator producing a `DICTATE` result, the pipeline output is
  byte-identical to the pre-8H behavior (verified by integration tests).

---

## 11. Real ASR — REAL ASR VERIFIED (core path)

`uv run pytest -m "slow"` → **4 passed, 1 skipped** using models cached in
`%LOCALAPPDATA%\SayIt\models`. This verifies the real Sherpa-ONNX inference
path still runs end-to-end. It does **not** exercise Phase 8 commands through
live microphone speech — see §13.

---

## 12. INSTALLED-APPLICATION VERIFIED

- Packaging-safety reviewed: no new Phase 8 module uses `__file__`- or
  source-tree-relative data paths (only pre-existing ASR/LLM bundled-JSON
  loaders do, which already work when packaged). New state is stored via the
  existing `platformdirs` settings.
- Not independently re-validated inside a freshly built installer in this effort
  (the installer is compiled by CI; see `docs/PHASE_7_RELEASE_VALIDATION.md`).

---

## 13. USER PHYSICAL VALIDATION REQUIRED

- Real foreground-window detection across actual apps on a live Windows desktop
  (CI is headless).
- Live voice-edit / snippet / casing / structure commands recognized from actual
  microphone speech (depends on ASR recognizing the command words).
- Safe Zone blocking verified against real password managers / banking apps.
- Paste behavior in specific target applications.
- Linux/X11 `xdotool` detection on real hardware; Wayland remains limited.

---

## 14. Known limitations

- Context/Safe Zone detection relies on process/window metadata; some apps may
  not expose ideal names, and Linux detection is limited by the display server.
- Voice-edit grammar is deterministic and intentionally small.
- Snippets are text-only (by design).
- Developer Mode is conservative (explicit commands only).
- Remember Correction requires explicit confirmation; it never learns passively.
- ASR remains non-streaming (unchanged from prior phases).
