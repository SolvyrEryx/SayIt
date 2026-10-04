# Phase 9A.2 / 9A.2R Validation — Real Recording Ingest + Hotword Benchmark

**Evaluation-only. Production unchanged. Gate: `C. HOTWORDS DO NOT HELP`** (and
the required beam decoder actively harms recognition on this real corpus).

Backed by `artifacts/phase9/9A2R/`: `source_inventory.json`,
`conversion_report.json`, `mapping_review.json`, `commit_report.json`,
`recording_status.json`, `benchmark_raw.json`, `hard_negatives.json`,
`sweeps.json`, `performance.json`, `performance_rss.json`, `final_report.json`.

## 1. Ingest
- 18 `.m4a` recordings from `C:\Users\user\OneDrive\Documents\Sound Recordings`.
- Converted with **ffmpeg** to WAV / 16000 Hz / mono / PCM s16le into a staging
  dir, then validated (spec + non-silence + peak/RMS). All 18 valid. Originals
  never modified.

## 2. Mapping correction (content-verified, not assumed)
The source files are named `Pair1..Pair8` + `Multi-word` + `Mixed`. I did **not**
assume filename order. Each staged clip was transcribed with the production
greedy recognizer and matched to a discriminator by content. This caught a real
discrepancy: the recordings do **not** match the prior `labels.json` pair order.
Their true discriminators are:

`FASTAPI, PG, OPENAI, NEXTJS, SQLALCHEMY, TENSORFLOW, WEBAUTHN, KUBECTL`
(+ `MULTI01`, `MIXED01`) — i.e. the master-prompt §8 list. **PYTHON and RUST
were not recorded** and remain `needs_recording` (reported, not hidden).

Labels were remapped to the content-confirmed discriminators; references were
set to the content-confirmed intended sentences (NOT rewritten to flatter
results); target/negative terms follow the discriminator.

## 3. Corpus completion
23 real clips scored (5 A–E + 18 ingested). 8 complete hard-negative pairs +
MULTI01 + MIXED01. 4 clips (PYTHON/RUST pairs) still pending.

## 4. Raw-ASR results (3 arms, identical audio)

| Metric | A greedy | B beam | C beam+hotwords |
|---|---:|---:|---:|
| WER | **0.213** | 0.237 | 0.237 |
| Technical-term recall | **0.538** | 0.462 | 0.462 |
| Exact-entity accuracy | **0.462** | 0.154 | 0.154 |
| False substitutions | 1 | 1 | 1 |
| Determinism (×3) | yes | yes | yes |

Process RSS (psutil): baseline 36 → greedy 749 → beam 766 → hotword 764 MiB.
Per-utterance latency: beam/hotword ~10–20% higher than greedy. (performance.json
reports tracemalloc; performance_rss.json reports true RSS.)

## 5. Decisive findings
- **Hotwords = beam, byte-for-byte, on every clip** and across the full score
  sweep {0.5–2.5} and count sweep {0,1,5,10,25}. Hotwords recovered **zero**
  technical terms that beam missed.
- **The decoder switch harmed recognition**: WER ↑ (0.213→0.237), recall ↓
  (0.538→0.462), exact-entity ↓ (0.462→0.154).
- **Concrete regression**: `OPENAI` technical was "OpenAI" under greedy but
  regressed to "open AI" under beam/hotword.
- Exact-entity collapse = beam **lowercasing** entities ("github"/"python").
- Acoustically mis-heard terms (PostGrey/PostDreSQL, SQL Alchemy, WebANT,
  Ubitil, "fast API") were recovered by **no** arm at **any** score/count —
  hotword biasing cannot create a token path the acoustic model never scored.
- Ordinary halves preserved identically across arms (hotwords did not force
  technical terms onto ordinary speech). The one flagged false-sub (NEXTJS
  ordinary "next js" vs negative "Next.js") is a case-insensitive labeling
  ambiguity present equally in all arms — not hotword-caused.

## 6. Interpretation (per master-prompt §25)
The question was not "did a number move" but "do hotwords improve technical
recognition while preserving ordinary language." Answer on real audio: **no**
— hotwords were inert, and the decoder they require is a net regression. The
honest classification is **C**, with a documented harm from the required
decoder change (not a pure D, because hotwords themselves did not introduce
false substitutions — they simply did nothing).

## 7. Gate decision → C, and the pivot it implies
Abandon the **decoder-hotword** architecture for SayIt's Parakeet int8 model.
This does not end Phase 9's goal; it redirects it to the documented alternative:
**post-ASR contextual rescoring/correction** (raw greedy transcript + bounded
context candidates + deterministic, ordinary-word-protected scoring), which
keeps the fast, higher-accuracy production greedy decoder untouched. That is a
separate future phase requiring explicit approval.

## 8. Tests / regression
`tests/test_contextual_biasing_phase9a2r.py` updated for the post-ingest reality
(real recordings present, PYTHON/RUST pending). phase9a2 + phase9a2r: 34 passed.
Full suite: **598 passed, 5 deselected**. No regression.

## 9. Flags
- PRODUCTION CHANGED: **NO**
- API KEYS ADDED: **NO**
- EXTERNAL NETWORK AT RUNTIME: **NO**
- PRODUCTION DEPENDENCY CHANGED: **NO**
- MODEL FILES CHANGED: **NO**
- REAL RECORDINGS INGESTED: **YES**
- ALL 18 RECORDINGS VALID: **YES**
- HARD-NEGATIVE PAIRS COMPLETE: **YES** (8 recorded; PYTHON/RUST not recorded)

## 10. Validation status
AUTOMATED VERIFIED (ingest/convert/validate/map/metrics/isolation);
REAL-ASR VERIFIED (23 real human clips, 3 arms, isolated 1.13.8);
USER PHYSICAL VALIDATION: live-mic in-app hotword path not tested (and now moot
given gate C); PYTHON/RUST pairs still unrecorded.
