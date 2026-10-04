# Third-Party Licenses — Phase 9 (Recognition Intelligence)

This records the external sources and dependencies touched by the Phase 9
experimental recognition-intelligence stack. All of it is **experimental** and
**not wired into the production application**; the production ASR path (sherpa-onnx
1.12.21, greedy decoder, Parakeet TDT v2 int8) is unchanged. No runtime network,
no API keys, no new runtime Python dependency was added.

## Code dependencies
- **No new Python dependency** was introduced by Phase 9. Fuzzy matching uses the
  standard library (`difflib`). RapidFuzz was benchmarked (MIT) and deliberately
  NOT added. `wordfreq` was considered (optional, 9F-J) and NOT added. No
  embeddings/vector libraries were added.
- `sherpa-onnx` **1.13.8** was installed into an ISOLATED experiment venv
  (`tools/phase9a1/.venv-upstream`) for the 9A.1 compatibility experiment only.
  It is Apache-2.0 licensed. It is NOT a production dependency; the production
  pin remains 1.12.21 and `uv.lock`/`pyproject.toml` dependency pins are unchanged.

## Data sources (build-time only; no runtime network)
| Source | Used data | License | Ingested | Notes |
|---|---|---|---|---|
| github-linguist/linguist | `lib/linguist/languages.yml` (name/aliases/interpreters) | MIT | 634 language terms (build-time download) | Only structured fields; bundled grammars NOT ingested |
| nice-registry/all-the-package-names | npm package names | MIT | **bounded curated real subset (15)** | Full 117 MB git-LFS `names.json` NOT loaded (rules 9C-12/32) |
| sethmlarson/pypi-data | PyPI package names/metadata | Apache-2.0 | **bounded curated real subset (20)** | Full dataset NOT loaded |
| SayIt curated technical pack | databases/protocols/tools + real ASR mis-hearings | project MIT | 11 (9C) | canonical = official published casings |
| SayIt domain packs (9D) | 7 domains, 62 terms | project MIT | 62 | official canonical casings, evidence-driven |
| SayIt entity packs (9E) | orgs/products/langs/standards/locations | project MIT | ~24 | OSMNames documented as a FUTURE build-time source; full gazetteer NOT imported |
| SayIt personalization (9G) | the user's own explicit 6J vocabulary | n/a (user data, local) | per-user | explicit only; no passive learning; never transmitted |

## Attribution / redistribution
- Linguist `languages.yml` is MIT; attribution preserved via this manifest and
  the per-phase source manifests (`artifacts/phase9d/DOMAIN_SOURCE_MANIFEST.md`,
  `artifacts/phase9e/ENTITY_SOURCE_MANIFEST.md`).
- npm/PyPI package NAMES used are factual identifiers from the public registries;
  only a small curated real subset is embedded. If full-dataset ingestion is
  pursued later, the dataset repositories' licenses (MIT / Apache-2.0) and any
  attribution requirements must be re-reviewed at that time.
- No dataset's data license was assumed from its code license; the exact files
  used are listed above.

## Runtime posture
No runtime network, telemetry, API keys, clipboard/screen scraping, keylogging,
passive learning, subprocess, eval, or exec in any Phase 9 intelligence module
(verified by AST audit — `artifacts/phase9h/privacy_security_audit.json`).
