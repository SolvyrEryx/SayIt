# Phase 6 — Real-Device Validation

This document is the procedure and record for validating SayIt's real dictation
pipeline on a physical Windows machine. It separates what has been
**automatically verified** from what must be **manually verified** by a human
with a real microphone and display.

## What is automatically verified (in this environment)

- Real local Whisper Tiny inference runs through the actual Sherpa-ONNX path
  (not mocked, no cloud): `tests/test_real_asr.py` passes with the model
  installed.
- Pipeline timing instrumentation emits per-job diagnostics (see Logging).
- Workflow safety (cancellation, stale-result rejection, overlapping jobs,
  empty/short audio, microphone-start failure, shutdown) is covered by the fast
  test suite.

## What still requires manual verification

Everything involving a real microphone, holding Ctrl + Space, real foreground
applications, and real speech accuracy. Those cannot be automated here.

---

## Environment (captured on the test machine)

- OS: Windows 11 Pro (build 10.0.26300)
- CPU: AMD Ryzen 5 4600G (6-core APU)
- RAM: 15.9 GB
- GPU: NVIDIA GeForce RTX 3060 — note: the ASR backend runs on **CPU**
  (`provider="cpu"`), so the GPU is not used for inference.
- Python 3.12.10, uv 0.10.7
- App commit at validation: `34d740d` (plus uncommitted Phase 1–6B work)

## Model configuration

- Model: `sherpa-onnx-whisper-tiny` (installed locally; downloaded on demand,
  not bundled).
- Enhancement: **None** (cloud enhancement off by default).
- Cache: `%LOCALAPPDATA%\SayIt\models\sherpa-onnx-whisper-tiny`.

## Measured ASR timing (engineering baseline, this machine)

Measured with synthetic audio (silence) — real speech of the same length may
differ. Use these only as an order-of-magnitude baseline, not a published claim.

| Audio length | Inference time (CPU) |
|--------------|----------------------|
| model load (one-time, warm) | ~0.61 s |
| 1 s | ~0.12 s |
| 3 s | ~0.16 s |
| 5 s | ~0.22 s |
| 10 s | ~0.37 s |

Implication: for short dictations the `TRANSCRIBING` state typically lasts
~100–250 ms, which is why it is hard to see. This is expected; no artificial
delay was added. Capture real-speech numbers below.

---

## Manual test procedure

For each test, record the actual observed result. Do not assume a transcript.

Launch: `uv run python -m sayit` (default hotkey `Ctrl + Space`, Esc cancels).
Tip: with `config.py` `LOG_LEVEL=DEBUG`, per-job timing lines appear in the logs.

### Normal dictation
Reference: "Let's meet tomorrow afternoon to review the plan."
- Observed transcript:
- Inserted correctly (y/n):
- Release→visible text (approx):

### Numbers / date
Reference: "Version 3.2 shipped on March 14th with 95 percent coverage."
- Observed transcript:
- Number/date formatting notes:

### Names
Reference: "Please email Aarav, Priya, and Rohan before noon."
- Observed transcript:
- Proper-noun errors:

### Technical sentence
Reference: "Push the code to GitHub, then run the Python script against PostgreSQL."
- Observed transcript:
- Technical-term errors:

### Cyber / DevOps sentence
Reference: "The CI/CD pipeline rotates the TLS certificate and checks the firewall rules."
- Observed transcript:
- Term errors:

### Natural speech (your normal accent)
Speak naturally (not a scripted sentence). This is a limited sample and must not
be generalized.
- Spoken (summary):
- Observed transcript:

### Silence
Activate recording and do not speak.
- Observed result (expect: no crash, no fabricated transcript, no stale text):

### Short input
Speak one or two words.
- Observed transcript:
- Any stale/garbage result:

### Long input (~30–60 s)
- Responsive during transcription (y/n):
- Transcript complete / omissions / duplicates:
- Insertion result:

### Recording cancellation
Ctrl + Space → speak → Esc (before release).
- Recording stopped (y/n):
- Anything inserted (should be no):
- Returned to Ready (y/n):
- Next dictation works (y/n):

### Transcription cancellation
Start a longer dictation, release, then press Esc while transcribing.
- Cancellation immediate or cooperative:
- Anything inserted (should be no):
- Final state / next dictation works:

### Focus change
Dictate into Notepad, release, switch to VS Code/browser before completion.
- Where text landed:
- Notes:

### Insertion targets
- Notepad — inserted / punctuation / caps / delay / retry:
- VS Code — inserted / punctuation / caps / delay / retry:
- Browser text field — inserted / notes:
- Browser address bar — inserted / notes:

### Clipboard
`Set-Clipboard "SENTINEL-123"`, dictate once, then `Get-Clipboard`.
- Sentinel preserved or overwritten:
- Dictated text on clipboard afterward:
- Notes (restoration is NOT promised by design):

### Repeated dictation (×10)
- Missed starts/stops:
- Transcription/insertion failures:
- Stale/incorrect results:
- Latency growth:
- Any stuck state:
- Returns to IDLE each time (y/n):

### Resource observation (Task Manager, python process, one 30–60 s dictation)
- Idle CPU/RAM:
- Recording CPU/RAM:
- Transcribing CPU/RAM:
- After repeated dictations CPU/RAM:
- RAM climbing (y/n):

### Microphone failure
Disable/unplug the mic, then try a dictation; also try with no focused field.
- Behavior (expect: no crash, no stuck RECORDING, can retry):

### Privacy verification
- Cloud enhancement off (y/n):
- API key configured (should be none):
- Any network during dictation beyond the one-time model download (y/n):
- Logs contain no audio / transcript / keys (spot check):

---

## Logging (per-job trace)

With debug logging, each dictation emits lines tagged `[job N]`:
recording captured (samples, audio seconds, held duration) → transcription
complete (release→transcript time, char count) → text inserted. Logs record
lengths and durations only — never audio, transcript text, clipboard contents,
or secrets.
