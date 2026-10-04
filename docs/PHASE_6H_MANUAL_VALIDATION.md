# Phase 6H — Manual Validation Procedure (dictation latency / responsiveness)

This procedure is for a human running SayIt on real hardware with a real
microphone and a model installed. The automated test suite and benchmark verify
the mechanics (timing instrumentation, duplicate prevention, determinism, state
machine), but they **cannot** verify perceived responsiveness or insertion into
real applications. Those require you.

> **Important:** Record only what you actually observe. Do not fill in outcomes
> you did not test. Blank is better than guessed.

## Preconditions

- A speech model is installed (default: Parakeet TDT 0.6B v2 int8).
- A working microphone is selected in Settings → Configuration.
- The hotkey is known (default: `Ctrl + Space`).

## What the implementation does (so expectations are correct)

SayIt is **one-shot offline**, not streaming. You hold the hotkey and speak;
when you **release**, the whole utterance is transcribed, corrected, and
inserted. You will **not** see words appear while you are still speaking. The
goal of this check is that the time between release and inserted text feels
acceptable, and that text is inserted exactly once, correctly.

## Test matrix

For each row, perform the action and write down only what you observed.

| # | Scenario | What to do | Observed outcome |
|---|----------|-----------|------------------|
| 1 | Short sentence | Dictate: "Let's meet tomorrow afternoon." | |
| 2 | Long sentence | Dictate ~2–3 sentences without stopping. | |
| 3 | Technical sentence | Dictate: "Push the code to GitHub then run the CI/CD pipeline." | |
| 4 | Pause mid-speech | Dictate, pause ~1s mid-sentence, continue, then release. | |
| 5 | Rapid dictation | Speak quickly; release promptly. | |
| 6 | Cancellation | Start dictating, press **Esc** before releasing. Confirm nothing is inserted. | |
| 7 | Repeated utterances | Do 10 dictate→release cycles back-to-back. Confirm each inserts once. | |
| 8 | Insert into text editor | Focus Notepad / VS Code, dictate, confirm text lands at the cursor. | |
| 9 | Insert into browser field | Focus a browser text box, dictate, confirm insertion. | |
| 10 | Switch model (optional) | In Settings, switch to another installed model, repeat #1 and #3. | |

## Specific things to watch for (failure modes)

- **Duplicate text** — e.g. "Push the code to GitHub Push the code to GitHub".
  Report immediately if seen; this is a correctness failure.
- **Missing/clipped words**, especially the first or last word.
- **Cursor jumps** or text landing in the wrong place.
- **A result arriving after you pressed Esc** (should never happen).
- **App hang** on quit while a transcription is in flight.

## Latency note

If you want a rough local latency reading, run:

```
uv run python tools/benchmark_models.py --phase6h sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8
```

This writes `artifacts/phase6/model-benchmark/phase6h-<model>.json` with
per-clip decode time, RTF, and a determinism check. These are machine numbers,
not a perceived-responsiveness claim.

## Sign-off

- Tester:
- Machine / CPU:
- Model used:
- Date:
- Overall: PASS / FAIL / MIXED (explain):
