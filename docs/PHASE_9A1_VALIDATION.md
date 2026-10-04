# Phase 9A.1 Validation — Upstream Sherpa-ONNX / Parakeet Hotword Reassessment

**Evaluation-only. Production was not changed. Gate decision: `B. TECHNICALLY
VERIFIED BUT BENEFIT NOT YET PROVEN`.**

All findings are backed by executable artifacts in `artifacts/phase9/9A1/`
(`environment.json`, `upstream_report.json`, `final_report.json`) produced by
the isolated tooling under `tools/phase9a1/`.

---

## 1. Question

Phase 9A found decoder hotwords UNSAFE/INCOMPATIBLE on the production stack
(sherpa_onnx 1.12.21 aborts on `modified_beam_search` for the NeMo transducer).
9A.1 asks the narrower question: does a **current upstream** sherpa-onnx allow
the **exact same** Parakeet TDT v2 int8 model to use contextual hotwords
safely, and does it provide **measurable benefit**?

## 2. Isolation (production frozen)

- Production interpreter remains on **sherpa_onnx 1.12.21**; `uv.lock` and the
  dependency pins in `pyproject.toml` were not changed. (`pyproject.toml` shows
  a pre-existing Phase 7 Briefcase rebrand diff only — no dependency change.)
- The experiment ran in an isolated venv `tools/phase9a1/.venv-upstream`
  (`sherpa_onnx==1.13.8`, numpy), created with `uv venv` + `uv pip install`.
- `bpe.vocab` was derived into `artifacts/phase9/9A1/temp_bpe_vocab/`; the model
  directory was **never modified** (`bpe.vocab`/`bpe.model` still absent there).
- All recognizer construction ran via subprocess so any native abort is
  contained.

## 3. Environment inventory (measured)

sherpa_onnx 1.12.21 (prod), Python 3.12.10, Parakeet int8 (nemo_transducer),
tokens.txt = 1025 BPE tokens, no bpe.vocab, baseline load ≈ 3.37 s, baseline
inference ≈ 0.64 s. See `environment.json`.

## 4. Version selected and why

**1.13.8** — the latest upstream release on PyPI at test time. It is the current
upstream that (per the Parakeet hotword example) adds `modified_beam_search`
support to the NeMo transducer path. Only the current pin (1.12.21) and this
current upstream were compared, as instructed (no scattershot version testing).

## 5. API / model compatibility findings

| Config | 1.12.21 (prod) | 1.13.8 (isolated) |
|---|---|---|
| greedy_search | loaded | loaded |
| modified_beam_search (bpe, no hotwords) | **process abort** | **LOADED + decoded** |
| modified_beam_search (bpe) + hotwords | **process abort** | **LOADED + decoded** |

The Phase 9A hard incompatibility is **resolved in upstream 1.13.8** for the
exact SayIt model. Note: the 1.12.21 abort persists even with
`modeling_unit=bpe` + a derived `bpe.vocab`, confirming the limitation was the
version, not the modeling unit.

## 6. BPE vocabulary findings

`tokens.txt` (1025 lines, `<token> <id>`) was transformed into a
SentencePiece-style `bpe.vocab` (`<token> 0` per line). The upstream recognizer
accepted it and decoded normally, reproducing the upstream "derive bpe.vocab
from tokens.txt" approach without shipping or modifying any model file.

## 7. Decoder vs hotword effect (controlled corpus A–E)

Raw ASR, identical audio, 3 runs each:

| Metric | greedy | beam (bpe) | beam + hotwords |
|---|---|---|---|
| aggregate WER | 0.24 | 0.24 | 0.24 |
| raw technical-term recall | 0.833 | 0.833 | 0.833 |
| false technical substitutions | 0 | 0 | 0 |
| determinism (×3) | yes | yes | yes |
| load time (s) | 2.89 | 2.87 | 3.66 |
| per-utterance RTF | ~0.11 | ~0.12–0.13 | ~0.12–0.13 |

Neither the decoder change nor the hotwords changed WER or recall on this
corpus.

## 8. The motivating case (and the decisive negative)

Clip D: spoken "PostgreSQL" → ASR "**postjsql**" (the error that motivated
Phase 9). Result in every configuration:

- greedy → `postjsql`
- beam, no hotword → `postjsql`
- beam + hotword `PostgreSQL` → `postjsql`
- **score sweep** {0.5, 1.0, 1.5, 2.0, 2.5} → `postjsql` at every score
- **count sweep** {0, 1, 5, 10} → `postjsql` at every count

The hotword did **not** recover the term. Decoder hotword biasing boosts
plausible alternative decoding paths; it did not overturn the acoustic model's
confident wrong hypothesis for this utterance. This is a measured negative, not
an assumption.

## 9. Hard negatives / ordinary language

No false substitutions were produced in any configuration on A–E (ordinary
clips A/B/C unchanged). Dedicated hard-negative *recordings* ("I need a fast
API" vs "FastAPI", etc.) are NOT in the current corpus (only A–E exist); the
false-substitution risk could therefore not be exercised directly and is listed
as a known gap requiring crafted audio.

## 10. Performance / memory / determinism

Beam/hotword add ~10–15% per-utterance latency and ~0.8 s extra load; peak
tracemalloc ≈ 1.8 MiB (flat). All configurations fully deterministic across
3 runs. No leak or instability observed in the isolated runs.

## 11. Native crash/abort behavior

1.12.21 aborts hard (contained in subprocess). 1.13.8 did not abort in any
tested configuration.

## 12. Production regression

`uv run pytest -m "not slow"` → **555 passed, 5 deselected** (unchanged).
`tests/test_contextual_biasing_phase9a1.py` → 9 passed (isolation guards,
artifact findings, bpe.vocab derivation, live upstream construction).

## 13. Privacy / security / licenses

Fully local; no network at runtime; no API keys; transcripts only in artifacts.
No external knowledge datasets used. Only sherpa-onnx (open source) exercised in
an isolated venv; no upstream source copied into SayIt, so
`THIRD_PARTY_LICENSES.md` needs no change.

## 14. Gate decision

**B. TECHNICALLY VERIFIED BUT BENEFIT NOT YET PROVEN.**

Capability on the exact model is verified under current upstream; the benefit on
the controlled corpus is not demonstrated (the motivating error was not
recovered; WER/recall unchanged).

## 15. Next recommendation (NOT actioned)

Expand the controlled audio corpus — including real hard-negative recordings —
and re-measure in the isolated upstream env before considering any controlled
production evaluation. Do **not** bump the production sherpa-onnx pin, change the
decoder, or replace the model on the basis of 9A.1 alone.
