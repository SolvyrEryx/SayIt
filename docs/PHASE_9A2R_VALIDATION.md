# Phase 9A.2R Validation — Human Recording Completion (Ingest Loop)

**Evaluation-only. Production unchanged. Gate: `HOLD / EXPAND DATA` — blocked on
USER PHYSICAL VALIDATION (human recording).**

## 1. The hard constraint (stated honestly)
9A.2R's objective is to obtain the **real human recordings** of the 18
hard-negative/extended clips defined in `artifacts/phase9/9A2/labels.json`. This
automated environment has **no microphone, no human speaker, and no local
offline TTS** (verified: pyttsx3/piper/TTS/espeak/gtts all absent). The master
prompt forbids fabricating speech (§9) and fabricating data/results (§57).
Therefore 9A.2R **cannot be completed here** — it can only be made turnkey and
left blocked on a human.

## 2. What was delivered instead (so completion is one step away)
- **`tools/phase9a2/ingest_status.py`** — scans `labels.json`, finds which clips
  now have audio (in `artifacts/phase9/9A2/corpus/` or the Phase 6F eval dir),
  validates each against SayIt's capture spec (**mono / 16000 Hz / 16-bit PCM**),
  and reports `missing` / `present` / `invalid` / `blocking`. With `--apply` it
  flips `needs_recording -> false` for every entry whose **valid** audio has
  appeared, so re-running the benchmark immediately includes them.
- **`tools/phase9a2/plumbing_selftest.py`** — proves the full
  record→ingest→rerun loop WITHOUT fabricating speech: it writes throwaway
  **silence** placeholder WAVs (correct spec) into a temp dir, runs the ingest +
  auto-flip logic, asserts a valid clip becomes non-blocking while a wrong-spec
  clip and a missing clip stay blocking, then auto-deletes the temp dir. The
  silence files are plumbing-only and never transcribed or scored.

## 3. Current recording status (measured)
`artifacts/phase9/9A2R/recording_status.json`:
- valid real clips: **A, B, C, D, E** (5)
- missing/blocking: **18**
- `recording_complete`: **false**
- corpus audio files fabricated by this phase: **0** (test-asserted)

## 4. Benchmark re-run (real A–E only)
Re-running `tools/phase9a2/benchmark.py` with only the real clips reproduces the
9A.2 numbers exactly (WER 0.189 all arms; tech recall 0.75; exact-entity greedy
0.75 vs beam/hotword 0.25; false-sub 0) — confirming the pipeline is stable and
that **no new evidence exists** because no new audio exists.

## 5. How a human completes 9A.2R (turnkey)
1. Record the 18 clips per `docs/PHASE_9A2_RECORDING_GUIDE.md` into
   `artifacts/phase9/9A2/corpus/` using the exact `<id>.wav` names.
2. `uv run python tools/phase9a2/ingest_status.py --apply`
   (auto-flips `needs_recording` for valid clips; reports any spec problems).
3. Re-run the 9A.2 benchmark; it auto-includes the new clips and refreshes the
   hard-negative analysis, sweeps, and gate inputs for a 9A.3 decision.

## 6. Tests / regression
`tests/test_contextual_biasing_phase9a2r.py` — 12 passed (wav-spec validation,
ingest status counts, auto-flip-only-valid, plumbing self-test, no-fabrication
guard, production isolation). Full suite: **596 passed, 5 deselected** (was 584;
+12). No regression.

## 7. Flags
- PRODUCTION CHANGED: **NO**
- API KEYS ADDED: **NO**
- EXTERNAL NETWORK AT RUNTIME: **NO**
- PRODUCTION DEPENDENCY CHANGED: **NO**
- MODEL FILES CHANGED: **NO**

## 8. Validation status
- AUTOMATED VERIFIED: ingest logic, spec validation, auto-flip, plumbing loop.
- ISOLATED EXPERIMENT VERIFIED: benchmark re-run on real A–E (sherpa 1.13.8).
- **USER PHYSICAL VALIDATION REQUIRED**: the 18 real recordings — this is the
  blocking item and cannot be satisfied without a human + microphone.
