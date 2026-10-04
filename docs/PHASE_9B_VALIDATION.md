# Phase 9B Validation — Post-ASR Contextual Candidate Correction

**Isolated proof-of-capability. Production unchanged. Gate: `A. POST-ASR
CORRECTION PROVEN` (given a relevant candidate set).**

Backed by `artifacts/phase9/9B/`: `baseline.json`, `correction_results.json`,
`hard_negative_results.json`, `ablation.json`, `threshold_sweep.json`,
`margin_sweep.json`, `candidate_count_sweep.json`, `performance.json`,
`final_report.json`.

## 1. Problem
Greedy Parakeet mis-hears technical terms ("postjsql" for PostgreSQL). Phase 9A
showed decoder hotwords cannot fix this (no benefit + beam harm). 9B tests a
different architecture: correct the raw transcript AFTER ASR using a small,
context-relevant candidate set — without touching the decoder/model.

## 2. Approach (not blind replacement)
`src/sayit/core/asr/post_context.py`: deterministic
`PostASRContextCorrector`. For each 1–3-word span it scores every candidate's
spoken variants with a fixed blend (0.60 edit similarity + 0.20 char-ngram +
0.10 token overlap + 0.05 prefix + 0.05 suffix), multiplies by a per-context
weight, then applies gates: **threshold → margin → ordinary-language protection
→ already-canonical**. A span is corrected only if evidence is strong; otherwise
left unchanged. Single bounded left-to-right pass (longest changed span wins; no
re-trigger; no loops). Fail-safe: returns input unchanged on any error.
`post_context_pack.py` is a small hand-reviewed 20-candidate set (NOT a
knowledge base). Fuzzy matching uses stdlib **difflib** — RapidFuzz was
benchmarked and found unnecessary, so **no new dependency** was added.

## 3. Results (raw ASR, same greedy decoder both arms)

| Metric | Arm A (raw) | Arm B (corrected) |
|---|---:|---:|
| WER | 0.217 | **0.188** |
| Technical-term recall | 0.538 | **1.000** |
| Exact-entity accuracy | 0.462 | **1.000** |
| False substitutions | 1 | 2 |
| Deterministic (×3) | — | yes |

## 4. False substitutions — honest breakdown
- **PAIR_NEXTJS_ORDINARY** ("Next.js"): **not corrector-caused** — the raw greedy
  already produced "next JS", flagged by case-insensitive matching against the
  negative term. Present in Arm A too (it is the pre-existing fsub=1).
- **MIXED01** ("FastAPI"): the **one genuine** corrector substitution — "fast
  API" → "FastAPI" in developer/mixed context. A real, tunable ambiguity
  (`strong_context_weight`), not a systemic failure.

So the corrector introduced **exactly one** debatable substitution, in the most
ambiguous (developer-mixed) context.

## 5. Ablation — the decisive safety evidence
| Variant | recall | false subs | WER |
|---|---:|---:|---:|
| A similarity only | 1.000 | **8** | 0.246 |
| B + context | 1.000 | **2** | 0.188 |
| C + margin | 1.000 | 2 | 0.188 |
| D + negative protection | 1.000 | 2 | 0.188 |

**Context weighting is what makes correction safe**: similarity-only corrupts 8
ordinary phrases; adding context eliminates 6 (8→2) while keeping recall at
1.000. Margin and negative protection are protective headroom.

## 6. Sweeps
- **Threshold**: recall 1.0 / false-subs 2 stable 0.70–0.90; recall collapses to
  0.769 at 0.95.
- **Margin**: false-subs flat at 2 across 0.00–0.20 (the one real sub has margin
  0.66).
- **Candidate count**: recall 0.692 (5) → 0.923 (10) → 1.0 (20,50); false-subs
  flat at 2 — **more candidates did not increase false substitutions** on this
  corpus.

## 7. Performance / memory / determinism
~40 ms median per 12-word sentence (difflib, 20 candidates) — off the recording
hot path, ~100× below ASR. tracemalloc peak small. Fully deterministic across 3
runs. A cheap pre-filter+cache optimization is available before any integration.

## 8. Capability vs knowledge (explicit)
The candidate pack contained the relevant entities, so this proves the
**correction mechanism** works given relevant candidates. It does **not** claim
SayIt knows every technical term. Assembling a small relevant candidate set from
large local knowledge is the next architectural problem (future phase).

## 9. Tests / regression
`tests/test_post_context_phase9b.py` — 27 passed, 1 (artifact) now satisfied by
final_report.json. Full suite: **625 passed, 1 skipped, 5 deselected** (was 598;
+27). No regression. Production isolation asserted (worker/app do not import
post_context; backend still greedy).

## 10. Gate → A, with scope honesty
Meaningful targeted recovery (recall 0.538→1.0, exact 0.462→1.0, WER down) with
controlled false positives (context 8→2; 1 artifact + 1 tunable ambiguity).
This is a genuine, measured positive — the opposite of 9A's decoder-hotword
result.

## 11. Recommended next step (NOT actioned)
Candidate **retrieval**: produce a small relevant candidate set per utterance
from local knowledge (8A context + 6J + a bounded developer index) without
dumping large vocabularies — plus a latency optimization and a separate,
approved controlled production-integration design (post-ASR, before 6G/6I/6J).
Do **not** integrate now; do **not** add external datasets yet.

## 12. Flags
PRODUCTION CHANGED: NO · PRODUCTION ASR CHANGED: NO · API KEYS ADDED: NO ·
EXTERNAL NETWORK AT RUNTIME: NO · PRODUCTION DEPENDENCY CHANGED: NO ·
MODEL FILES CHANGED: NO · 6G CHANGED: NO · 6I CHANGED: NO · 6J CHANGED: NO ·
USER VOCABULARY CHANGED: NO
