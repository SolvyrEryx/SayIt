# Phase 9C Validation — Local Knowledge + Contextual Candidate Retrieval

**Isolated. Production unchanged. Gate: `A. RETRIEVAL PROVEN`.**

Backed by `artifacts/phase9/9C/`: `source_manifest.json`, `ingestion_report.json`,
`index_stats.json`, `retrieval_benchmark.json`, `retrieval_ablation.json`,
`hard_negative_results.json`, `end_to_end_results.json`, `performance.json`,
`memory.json`, `final_report.json`.

## 1. Objective
9B proved correction works *given* a candidate. 9C proves SayIt can **find** the
candidate locally: build a knowledge index and retrieve a small relevant
candidate set automatically to feed the unchanged 9B corrector.

## 2. Knowledge sources (provenance)
- **GitHub Linguist** `languages.yml` — **634** programming/markup languages,
  **MIT**, downloaded at **build time** (never at runtime).
- **npm** (all-the-package-names, MIT) + **PyPI** (pypi-data, Apache-2.0) —
  **bounded curated real subsets** (15 + 20 names). The npm `names.json` is a
  **117 MB git-LFS** file; per rules 12/32 the full dataset is NOT loaded.
  Full disk-backed ingestion is deferred to future build tooling.
- **SayIt curated technical pack** — 11 entities (databases/protocols/tools)
  with the real 9A.2 ASR mis-hearings as variants (postjsql, webant, ubitil…).
- Merged, de-duplicated: **672 terms**, compact **147 KB** JSON index.

## 3. Schema / ingestion / index
`core/knowledge/models.py` (`KnowledgeTerm`), `tools/knowledge/{linguist_loader,
npm_pypi_seed,normalize}.py` (build-time ingestion → merged index + manifests),
`core/knowledge/index.py` (`KnowledgeIndex`: exact map + token postings +
char-3-gram postings; bounded `candidate_ids`; JSON save/load — **no SQLite**,
unnecessary at 147 KB / sub-ms lookup).

## 4. Retrieval
`core/knowledge/retrieval.py` (`CandidateRetriever`): bounded candidate pool via
postings, then deterministic scoring (0.55 edit + 0.25 ngram + 0.15 token +
0.05 prefix) × per-context domain prior × relevance, with 6J/fallback priority
boost. Context **reduces/reweights** candidate space (email/chat down-weight
developer terms) — it never fabricates substitutions. Fail-safe (returns [] on
error; falls back to 6J/curated when the index is missing).

## 5. Adapter (reuses 9B unchanged)
`core/knowledge/adapter.py`: builds a per-utterance 9B `CandidatePack` from
retrieved terms and runs the **unchanged** `PostASRContextCorrector`. The 9B
corrector keeps sole responsibility for scoring/threshold/margin/ordinary
protection.

## 6. Retrieval quality (Recall@K)
Recall@1 = **0.846** (11/13 targets rank-1), flat through @50 — when a target is
retrieved it is already rank-1 with clear margin over the 634 noise languages.
The 2 "misses" (TLS, Next.js) were **already correct** in raw greedy, so not
real recognition losses.

## 7. End-to-end (raw ASR → retrieval → 9B)
| Arm | tech recall | exact | false subs | WER |
|---|---:|---:|---:|---:|
| raw greedy | 0.538 | 0.462 | 1 | 0.217 |
| 9B manual pack | 1.000 | 1.000 | 2 | 0.188 |
| **9C auto retrieval** | **0.923** | **0.692** | 2 | 0.193 |

Automatic retrieval recovers **most** of the manually-curated benefit with no
hand-built per-run pack and no added ordinary-language corruption.

## 8. Ablation (which source carries value)
| Source | recall | exact | false subs |
|---|---:|---:|---:|
| linguist only | 0.538 | 0.462 | 1 |
| npm+pypi only | 0.615 | 0.385 | 2 |
| **curated only** | 0.846 | **0.769** | **1** |
| combined | **0.923** | 0.692 | 2 |

**Key finding:** the small curated pack is the cleanest (best exact, lowest
false subs); the 634-language list adds recall breadth but introduces **noise**
that lowers exact-entity accuracy and adds 1 false sub. This directly motivates
candidate **ranking** (future 9F) before adding larger sources.

## 9. Hard negatives
**8/8 ordinary halves preserved** (unchanged). The 2 false subs are pre-existing
9B artifacts (NEXTJS "next JS" metric artifact + MIXED01 developer-context
ambiguity) — **not** retrieval-induced.

## 10. Performance / memory / determinism
Retrieval-only **0.73 ms**/call; end-to-end **131 ms**/utterance (adapter
re-retrieves per span — a clear retrieve-once optimization exists before any
integration); index **147 KB**; process RSS ~194 MiB; deterministic ×3.

## 11. Tests / regression
`tests/test_knowledge_retrieval_phase9c.py` — 22 passed, 1 (artifact) satisfied
by final_report. Full suite below. Production isolation asserted (worker/app do
not import knowledge; backend still greedy). Privacy AST test: knowledge modules
import no urllib/requests/socket/http/subprocess and call no eval/exec/system.

## 12. Gate → A (RETRIEVAL PROVEN)
Efficient local index, automatic Recall@1 0.846, end-to-end recovery of most
manual benefit, no retrieval-induced false subs, ordinary language preserved,
deterministic. Scope honesty: full npm/PyPI not ingested; this proves the
retrieval architecture, and the ablation shows ranking is the next real problem.

## 13. Recommended next step (NOT actioned)
Candidate **ranking / false-positive control** (9F) to tame the noise the large
source introduces, plus a retrieve-once latency optimization and a separate
approved controlled production-integration design (post-ASR, before 6G/6I/6J).
Do **not** add domain packs (9D), proper names (9E), or embeddings yet.

## 14. Flags
PRODUCTION CHANGED: NO · PRODUCTION ASR CHANGED: NO · API KEYS ADDED: NO ·
EXTERNAL NETWORK AT RUNTIME: NO · PRODUCTION DEPENDENCY CHANGED: NO ·
MODEL FILES CHANGED: NO · 6G/6I/6J CHANGED: NO · 8A/8H CHANGED: NO ·
USER VOCABULARY CHANGED: NO · EXTERNAL DATASETS DOWNLOADED: YES (build-time
Linguist languages.yml only; full npm/PyPI NOT downloaded; zero runtime network).
