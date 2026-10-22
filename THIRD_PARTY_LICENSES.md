# Third-Party & Model Licensing Notes

This file records licensing information that is useful for a release review. It
distinguishes the application license, runtime dependency licenses, and speech
model licenses. It does **not** change any license and does **not** bundle any
model weights.

Where a value could not be fully verified from repository files alone, it is
flagged for owner/legal review rather than asserted.

## Application

- **License:** MIT (see `LICENSE`). Unchanged.

## Runtime dependencies

Declared in `pyproject.toml`. The licenses below are the commonly published
licenses for these packages and should be confirmed against the exact installed
versions before release (e.g. via a license scan of the resolved environment).
This list has not been machine-verified against the lockfile in this effort.

| Package | Purpose | License (to confirm) |
|---------|---------|----------------------|
| PySide6-Essentials | Qt GUI framework | LGPLv3 / commercial (Qt) — review Qt/LGPL obligations for distribution |
| pynput | Global hotkey capture | LGPLv3 |
| sounddevice | Audio capture | MIT |
| sherpa-onnx / sherpa-onnx-core | ASR inference engine | Apache-2.0 (k2-fsa) |
| litellm | LLM client (optional enhancement) | MIT |
| pydantic | Settings validation | MIT |
| platformdirs | Platform paths | MIT |
| numpy | Numerical operations | BSD-3-Clause |
| pyperclip | Clipboard access | BSD-3-Clause |

> **Owner/legal review:** Qt (PySide6) distribution has LGPL obligations that
> should be reviewed for a packaged release. Confirm all dependency licenses
> against the resolved `uv.lock` versions.

## Speech models (download-on-demand installer)

For the default download-on-demand installer, model weights are downloaded on
demand from the upstream Sherpa-ONNX / Hugging Face model releases and are
**not** redistributed by this repository. Per-file provenance, source URLs, and
SHA-256 hashes are recorded in `src/sayit/core/asr/models/models.json`.

| Model | Upstream license | Notes |
|-------|------------------|-------|
| NVIDIA Parakeet TDT 0.6B v2 (default) | CC-BY-4.0 | Commercial use permitted; **attribution required**. |
| OpenAI Whisper (tiny / small / distil-large / large-v3) | MIT | Permissive. |
| AI4Bharat IndicConformer (Hindi, Kannada) | MIT (AI4Bharat IndicConformer weights) | ONNX/INT8 export packaging by `parismitaglobalsolutions/indicconformer-sherpa-onnx` (Apache-2.0). |
| Sherpa-ONNX model conversions | Redistributed by k2-fsa (Apache-2.0 project) | Confirm the conversion/redistribution terms for each specific model artifact. |

## Speech models bundled by the Full Offline Installer (v0.2.0+)

The **Full Offline Installer** variant redistributes four validated INT8 model
artifacts inside the application. Each bundled file is pinned by SHA-256 in the
version-controlled integrity manifest
`src/sayit/core/asr/models/bundled_models.json`; a build-time gate
(`model_integrity.verify_staged_models`) fails the build on any missing file or
hash/size mismatch, so a swapped or corrupted artifact can never be packaged
silently. The attributions below mirror that manifest exactly and are shipped
with the application. These terms permit redistribution; the attribution
obligations below are satisfied by including this notice and the manifest.

| Role | Model | Weight license | Packaging | Attribution |
|------|-------|----------------|-----------|-------------|
| English Fast (default) | NVIDIA Parakeet TDT 0.6B v2 (INT8) | CC-BY-4.0 | ONNX INT8 export by k2-fsa/sherpa-onnx (Apache-2.0 tooling) | NVIDIA Parakeet TDT 0.6B v2, CC-BY-4.0. **Attribution required and provided here.** |
| English Higher Accuracy | OpenAI Whisper Small (INT8) | MIT | ONNX INT8 export by k2-fsa/sherpa-onnx (Apache-2.0 tooling) | OpenAI Whisper Small, MIT License. |
| Hindi | AI4Bharat IndicConformer Hindi (INT8) | MIT (AI4Bharat IndicConformer weights) | ONNX/INT8 export by `parismitaglobalsolutions/indicconformer-sherpa-onnx` (Apache-2.0) | AI4Bharat IndicConformer (MIT). Export packaging Apache-2.0. |
| Kannada | AI4Bharat IndicConformer Kannada (INT8) | MIT (AI4Bharat IndicConformer weights) | ONNX/INT8 export by `parismitaglobalsolutions/indicconformer-sherpa-onnx` (Apache-2.0) | AI4Bharat IndicConformer (MIT). Export packaging Apache-2.0. |

The IndicConformer licensing notice (MIT weights + Apache-2.0 export packaging)
in `bundled_models.json` is **consistent** with the documented weight license
`"MIT (AI4Bharat IndicConformer)"` in `models.json`; the manifest only adds the
export-tooling license. The per-file SHA-256 hashes in both files are identical
(enforced by `tests/test_model_integrity.py::test_indic_manifest_hashes_match_models_json`).

> **Owner/legal review before publication:**
> - Confirm CC-BY-4.0 attribution for Parakeet is satisfied by this notice in
>   the installed application (it is included verbatim from the manifest).
> - Reconfirm redistribution terms for each specific Sherpa-ONNX / Hugging Face
>   artifact with upstream before publishing the offline installer.
> - Do not assume a model's license matches the application (MIT).

## Product name

The working product name **SayIt** is provisional. No trademark, domain,
package, app-store, or social-handle availability has been checked or claimed.
Final branding requires owner review before public launch. Repository and
technical identifiers currently remain **SayIt**.
