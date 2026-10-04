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

## Speech models (downloaded, not bundled)

Model weights are downloaded on demand from the upstream Sherpa-ONNX model
releases and are **not** redistributed by this repository. The following reflect
the upstream model cards as of the research date and **must be reconfirmed with
upstream before any bundling or redistribution**:

| Model | Upstream license (to reconfirm) | Notes |
|-------|---------------------------------|-------|
| NVIDIA Parakeet TDT 0.6B v2 (default) | CC-BY-4.0 | Commercial use permitted; **attribution required**. |
| OpenAI Whisper (tiny / small / distil-large / large-v3) | MIT | Permissive. |
| Sherpa-ONNX model conversions | Redistributed by k2-fsa (Apache-2.0 project) | Confirm the conversion/redistribution terms for each specific model artifact. |

> **Owner/legal review required before redistribution:**
> - If model weights are ever bundled with an installer, confirm CC-BY-4.0
>   attribution requirements for Parakeet are satisfied and that the specific
>   Sherpa-ONNX artifacts may be redistributed.
> - Do not assume a model's license matches the application (MIT).

## Product name

The working product name **SayIt** is provisional. No trademark, domain,
package, app-store, or social-handle availability has been checked or claimed.
Final branding requires owner review before public launch. Repository and
technical identifiers currently remain **SayIt**.
