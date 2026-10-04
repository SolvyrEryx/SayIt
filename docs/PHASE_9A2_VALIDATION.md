# Phase 9A.2 Validation — Recognition Challenge Corpus & Hard-Negative Analysis

**Evaluation-only. Production unchanged. Gate: `B. INSUFFICIENT EVIDENCE`.**

Backed by `artifacts/phase9/9A2/` (`labels.json`, `corpus_manifest.json`,
`benchmark_raw.json`, `hard_negatives.json`, `sweeps.json`, `performance.json`,
`final_report.json`) and the isolated upstream venv (sherpa_onnx 1.13.8).

## 1. Objective
Build a trustworthy, labeled instrument to decide whether upstream decoder
hotwords improve SayIt's recognition of technical terms **without** harming
ordinary speech — distinguishing "hotwords don't help" from "our corpus is too
weak to tell." Separate raw ASR from post-processing.

## 2. What was built
- `tools/phase9a2/metrics.py` — pure raw-ASR metrics: WER, technical-term recall
  (normalized), exact-entity accuracy (case/punct-exact), phrase recall, false
  technical substitution, ordinary-language preservation, aggregation.
- `tools/phase9a2/corpus_validator.py` — labels schema + validator + scorable
  filter.
- `tools/phase9a2/benchmark.py` — isolated 3-arm harness (greedy / beam /
  beam+hotwords) on identical audio, hard-negative pair analysis, score sweep
  {0.5..2.5}, count sweep {0,1,5,10,25}, determinism ×3, latency/RTF/memory.
- `artifacts/phase9/9A2/labels.json` — 23 labeled entries (5 real A–E scored;
  18 marked `needs_recording` with full target/negative labels, incl. 8
  hard-negative pairs).
- `docs/PHASE_9A2_RECORDING_GUIDE.md` — exact spec/template for the human
  recordings required to complete the evaluation.

## 3. Audio reality (honest)
This environment has **no microphone** and **no local offline TTS** (checked:
pyttsx3/piper/TTS/espeak/gtts all absent). Therefore:
- Scored now: the **5 real** Phase 6F clips A–E (human speech), with 4 technical
  target terms (GitHub, Python, PostgreSQL in D; TLS in E).
- Not scored: 18 entries (8 hard-negative pairs + multiword + mixed) are
  specified and labeled but require human recording. **0 synthetic clips were
  created** (no fabricated audio).

## 4. Results on the real clips (raw ASR, 3 arms)

| Metric | greedy (1.13.8 control-equiv) | beam | beam + hotwords |
|---|---:|---:|---:|
| WER | 0.189 | 0.189 | 0.189 |
| Technical-term recall (norm) | 0.75 | 0.75 | 0.75 |
| Exact-entity accuracy | **0.75** | **0.25** | **0.25** |
| False substitutions | 0 | 0 | 0 |
| Determinism (×3) | yes | yes | yes |
| Load time (s) | 2.94 | 3.32 | 3.53 |
| Memory (tracemalloc peak) | ~31 KiB | — | — |

Production control (from 9A.1, greedy on 1.12.21): WER 0.24 on A–E with the
earlier metric; the 9A.2 harness uses a stricter target-labelled scoring, hence
the different absolute WER. The three 9A.2 arms are mutually comparable (same
interpreter, same audio, same preprocessing).

## 5. Key observations
- **No hotword benefit** on the available technical clips: identical output
  across the full score sweep {0.5–2.5} and count sweep {0,1,5,10,25}.
  "PostgreSQL" remained "postjsql" in every beam/hotword configuration — the
  motivating error was never recovered.
- **Beam decoder slightly *reduced* exact-entity accuracy** (0.75→0.25): it
  emits lowercase "github"/"python" where greedy emits "GitHub"/"Python". This
  is a decoder surface-casing artifact (a real integration caution), not a
  hotword effect, and hotwords did not fix it.
- **False substitutions = 0**, but this is uninformative: there are **no
  ordinary hard-negative recordings** to stress it. The single most important
  question (do hotwords force "FastAPI" onto "fast API"?) is **unmeasured**.
- Determinism preserved; memory negligible; modest load/latency cost for
  beam/hotword.

## 6. Gate decision — B (INSUFFICIENT EVIDENCE)
The instrument is sound and reusable, but real spoken coverage (5 clips, 4
target terms, 0 hard-negative pairs) is far too small to conclude A/C/D, and the
false-substitution question cannot be answered at all without the ordinary
hard-negative recordings. The honest classification is B.

## 7. Recommended next step (NOT actioned)
Record the 18 `needs_recording` clips per the recording guide (especially the 8
hard-negative pairs), flip `needs_recording` to false, and re-run
`tools/phase9a2/benchmark.py`. Only then can the hotword benefit/harm question
be decided. Do **not** build 9B knowledge packs and do **not** change production
on current evidence. The observed beam casing change is an additional reason to
require post-processing review before any future integration.

## 8. Flags
- PRODUCTION CHANGED: **NO**
- API KEYS ADDED: **NO**
- EXTERNAL NETWORK AT RUNTIME: **NO**
- PRODUCTION DEPENDENCY CHANGED: **NO**
- MODEL FILES CHANGED: **NO**

## 9. Tests / regression
`tests/test_contextual_biasing_phase9a2.py` — 20 passed (metrics, validation,
artifact schema, production-isolation guards incl. eval-reference immutability).
Full suite: **584 passed, 5 deselected** (was 564; +20). No regression.

## 10. Validation status
- AUTOMATED VERIFIED: metrics, validation, isolation, artifact schema.
- ISOLATED UPSTREAM VERIFIED: 3-arm benchmark on real clips A–E (sherpa 1.13.8).
- REAL-ASR VERIFIED: on A–E only (limited coverage).
- USER PHYSICAL VALIDATION REQUIRED: the 18 hard-negative/extended recordings,
  and any live-microphone evaluation of the hotword path.
