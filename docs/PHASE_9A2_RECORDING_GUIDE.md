# Phase 9A.2 Recording Guide (USER PHYSICAL VALIDATION)

This environment has **no microphone and no local offline TTS**, so the
hard-negative and extended-category clips in `artifacts/phase9/9A2/labels.json`
that are marked `"needs_recording": true` must be recorded by a human. Until
they exist, the 9A.2 benchmark scores only the real Phase 6F clips **A–E** and
the gate decision is bounded by that limited coverage.

Nothing you record is uploaded or committed; it stays local.

## Format (match SayIt capture)
- **Mono, 16000 Hz, 16-bit PCM WAV.**
- Quiet room, normal pace, natural pronunciation.
- Do **not** over-enunciate the technical terms — the point is to test whether
  the recognizer handles natural speech, and whether hotwords wrongly force a
  technical word onto an ordinary phrase.
- One utterance per file; name each file exactly `<id>.wav` using the `id`
  from `labels.json` (e.g. `PAIR_PG_ORDINARY.wav`).
- Put the files in `artifacts/phase9/9A2/corpus/`.

## What to record (from labels.json)
Record the exact `reference` for every entry with `"needs_recording": true`.
The set is organized as **hard-negative pairs** — for each pair, record BOTH
the ordinary-meaning sentence and the technical-meaning sentence, in the same
voice and environment:

| pair_id | ordinary (negative term must NOT appear) | technical (target must be recognized) |
|---|---|---|
| PG | "The postgres database is slow this morning." | "Connect the backend to PostgreSQL and use SQLAlchemy for the ORM." |
| FASTAPI | "I need a fast API for the internal service." | "Build the endpoint with FastAPI and Pydantic." |
| OPENAI | "The office is open AI will not change that." | "We call the OpenAI API from the worker." |
| NEXTJS | "The next JS file is in the folder." | "The frontend is built with Next.js and React." |
| TENSORFLOW | "Watch the tensor flow through the network graph." | "Train the model in TensorFlow and export to ONNX." |
| KUBECTL | "Please take the cube control panel to the lab." | "Run kubectl to restart the Kubernetes deployment." |
| PYTHON | "The python slithered across the warm rock." | "Python is installed on the build server." |
| RUST | "There is rust on the old iron gate." | "We rewrote the parser in Rust for speed." |

Plus:
- `MULTI01` — "Configure GitHub Actions and Docker Compose for the pipeline."
- `MIXED01` — "I used Python yesterday, but today I need a fast API for the internal service."

## After recording
1. Place the WAVs in `artifacts/phase9/9A2/corpus/`.
2. Set `"needs_recording": false` on those entries in `labels.json` (references
   must stay exactly as written — they are the ground truth).
3. Re-run `tools/phase9a2/benchmark.py`. The harness will automatically include
   the newly available clips, recompute all raw-ASR metrics, and refresh the
   hard-negative analysis and the gate decision.

## Why pairs matter
The single most important question in Phase 9A.2 is whether contextual hotwords
**raise false technical substitutions** on ordinary speech. That can only be
measured with the *ordinary* half of each pair (e.g. "fast API" must NOT become
"FastAPI" just because "FastAPI" is in the hotword list). Recording both halves
in one voice isolates the hotword effect from speaker/acoustic variation.
