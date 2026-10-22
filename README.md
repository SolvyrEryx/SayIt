<div align="center">

# SayIt

**Local-first voice typing for your desktop.**

**Authors:** Rahul J, Noah J, and Pranav H

Hold a hotkey, speak, release — your words are transcribed on-device and
inserted at your cursor in any application.

[![License: MIT](https://img.shields.io/badge/License-MIT-informational.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%20x64-0a7bbb.svg)](#supported-platforms)
[![ASR: Parakeet TDT 0.6B v2](https://img.shields.io/badge/ASR-Parakeet%20TDT%200.6B%20v2-5a4fcf.svg)](#models)
[![Local-first](https://img.shields.io/badge/privacy-local--first-2e7d32.svg)](#privacy)

### [⬇ Download for Windows](https://github.com/VptrCipher/SayIt/releases/latest) · [⬇ Download for Linux](https://github.com/VptrCipher/SayIt/releases/latest) · [🌐 Website](https://vptrcipher.github.io/SayIt/) · [📦 Releases](https://github.com/VptrCipher/SayIt/releases)

<img src="docs/assets/sayit-home-idle.png" alt="SayIt — ready to speak" width="420">

</div>

> **Release status:** `v0.1.2` has been **built and released**. The official
> website is **https://vptrcipher.github.io/SayIt/**. See [Release status](#release-status)
> for details.

---

## What is SayIt?

SayIt is a lightweight push-to-talk voice-typing utility for the desktop. You
hold a global hotkey (default **Ctrl + Space**), speak, and release — the
complete utterance is transcribed **on your own machine** by a local
speech-recognition model and the resulting text is inserted at your active
cursor via the clipboard.

It is **not** a cloud dictation service. Core speech recognition runs locally;
network access is only involved for the one-time model download and for an
**optional, off-by-default** cloud text-enhancement feature.

## Why SayIt?

- **Local-first speech recognition** — transcription runs on-device via
  [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx); your audio does not leave
  your computer for recognition.
- **Technical terminology handling** — a deterministic, on-device correction
  layer normalizes developer terms ("git hub" → GitHub, "ci slash cd" → CI/CD)
  and clearly-dictated structured values (URLs, paths, versions), conservatively.
- **Explicit personalization** — user-controlled vocabulary and snippets;
  nothing is learned silently.
- **Transparent correction with safe abstention** — ordinary prose is left
  unchanged; the correction layer is explainable and can be turned off.
- **Desktop-wide insertion** — works across applications through the system
  clipboard + paste.
- **Explicit privacy controls** — cloud enhancement and transcript history are
  both **off by default**.

## Core features

- Push-to-talk recording with a configurable global hotkey.
- On-device transcription for **English, Hindi, and Kannada**. English uses Parakeet TDT 0.6B v2 INT8 by default (with optional Whisper models); Hindi and Kannada use their respective IndicConformer INT8 models.
- Explicit dictation-language selection and language-compatible model routing. Hindi/Kannada sessions never silently fall back to an English-only recognizer.
- Deterministic local technical-term correction and structured formatting.
- User vocabulary, snippets, and context-aware formatting profiles.
- Esc cancellation of an in-progress recording/transcription.
- First-run setup wizard (microphone, model, hotkey).
- System-tray workflow with Ready / Recording / Processing / Error states.
- Optional, opt-in transcript enhancement via a local (Ollama) or cloud LLM.

<div align="center">
<img src="docs/assets/sayit-recording.png" alt="SayIt listening overlay" width="260">
&nbsp;&nbsp;
<img src="docs/assets/sayit-result.png" alt="SayIt transcription result" width="360">
</div>

## How it works

```mermaid
flowchart LR
    A["Hold hotkey · speak · release"] --> B[Audio Recorder]
    B --> C[Backend Manager]
    C --> D["Parakeet CPU Backend<br/>(sherpa-onnx, on-device)"]
    D --> E[Transcript Intelligence]
    E --> F[Clipboard / Text Insertion]
    F --> G[Your active application]
   subgraph TI [Transcript Intelligence]
      E1[terminology retrieval] --> E2[correction]
      E2 --> E3[ranking]
      E3 --> E4[explicit personalization]
    end
```

Dictation is **one-shot**: the full utterance is decoded by the local offline
recognizer when you release the hotkey, then the correction layer runs, then the
text is inserted. It is not a streaming/real-time system.

## Architecture

SayIt uses a hardware-adaptive backend abstraction. Only the **CPU backend is
production-validated** today; GPU paths are experimental research and are **not**
active.

```mermaid
flowchart TB
    U[User] --> HK[Global Hotkey]
    HK --> REC[Audio Recorder]
    REC --> BM[ASR Backend Manager]
    BM --> CPU["ParakeetCPUBackend — VALIDATED (default)"]
    BM -. experimental .-> DML[DirectML]
    BM -. experimental .-> CUDA[CUDA]
    BM -. experimental .-> VK[Vulkan]
    CPU --> TI[Transcript Intelligence]
    TI --> INS[Clipboard / Insertion]
    INS --> APP[Target Application]
```

> **Experimental:** DirectML/CUDA/Vulkan are research tracks. DirectML
> encoder/joiner GPU execution has been verified in isolation, but complete
> end-to-end Parakeet TDT GPU transcription is **not** validated. `AUTO`
> resolves to **CPU**.

## Privacy

- **Core speech recognition runs locally** on your computer.
- **Cloud enhancement is optional and off by default.** It only sends transcript
  text when you explicitly enable it and configure a remote provider. Audio is
  never sent for enhancement.
- **Transcript history is off by default.** When enabled, completed transcripts
  are stored in a local file.
- **Model download** requires network access and is separate from speech
  recognition — downloading a model is not cloud transcription.
- No analytics or telemetry are added by the project.

SayIt does **not** claim to be "100% private" or "fully offline in every
configuration", because model downloads and optional cloud enhancement involve
the network. See the in-app **Privacy & Data** settings.

## Intelligence / correction

The on-device correction layer is deterministic and explainable: the same input,
context, and settings always produce the same output, and each change is
attributable to a specific rule. It normalizes common technical terms and
clearly-structured values, leaves ordinary prose untouched, abstains when
evidence is weak, and can be disabled. It does not use an LLM, the network, the
clipboard, or screen contents.

## Performance

Measured on one development machine under a warm steady-state benchmark — a
**reference point, not a guarantee** for other hardware.

| Metric | p50 | p95 |
|---|---:|---:|
| ASR (Parakeet int8, warm) | ≈ 739 ms | ≈ 1795 ms |
| Stop → text (ASR + intelligence, excluding insertion and GUI) | ≈ 836 ms | ≈ 2049 ms |

- **Environment:** AMD Ryzen 5 4600G (6c/12t), Windows, CPU inference,
  Parakeet TDT 0.6B v2 INT8, warm (model already loaded).
- **Methodology:** 60 warm runs over fixed benchmark clips. The stop → text
  figure covers ASR plus the on-device intelligence/correction stage; cold model
  initialization (~a few seconds) and the clipboard/paste insertion + GUI
  rendering are measured separately and excluded here.

No "fastest", "best", or "zero-latency" claims are made. Your results will
differ by CPU and utterance length.

## Models

| Language | Role | Model | Notes |
|---|---|---|---|
| English | **Default** | Parakeet TDT 0.6B v2 INT8 | On-device transducer; downloaded on first use. |
| English | Optional | Whisper Small | Alternative recognizer; slower end-to-end. |
| Hindi | Optional | IndicConformer Hindi INT8 | Language-specific CTC recognizer; downloaded on demand. |
| Kannada | Optional | IndicConformer Kannada INT8 | Language-specific CTC recognizer; downloaded on demand. |

Choose the dictation language and its matching model in Settings. SayIt checks
language/model compatibility during selection and startup so a Hindi or Kannada
session cannot silently run through an English-only model.

Model weights are **downloaded on demand** into your local app-data folder and
are **not** bundled with the installer. Download size depends on the selected
model. No relative accuracy/speed claim is made between models beyond what has
been measured.

## Installation

### Normal users

The `v0.1.2` release is built and released. Download it from the
[Releases page](https://github.com/VptrCipher/SayIt/releases/latest) or visit
[https://vptrcipher.github.io/SayIt/](https://vptrcipher.github.io/SayIt/). The
release artifacts are built by CI and named:

- **Windows:** `SayIt-Setup-x64.exe` (Inno Setup installer). Unsigned; see
  [Release status](#release-status) for the expected SmartScreen notice.
- **Linux:** `SayIt-0.1.2-Linux-x86_64.AppImage`. Mark it executable
  (`chmod +x`) and run.

Verify your download against the published checksums (`checksums.txt` and the
per-file `.sha256`) on the release page.

Normal users do **not** need Python, a compiler, CUDA, or any SDK.

### From source

```bash
git clone https://github.com/VptrCipher/SayIt.git
cd SayIt
uv sync --frozen
uv run python -m sayit
```

## Supported platforms

| Platform | Status |
|---|---|
| Windows x64 | Supported. Packaged install + live dictation validated; both installers built and checksummed. |
| macOS 12+ (Apple Silicon / Intel) | Cross-platform engineering implemented (native per-arch `.app`/DMG config, Cmd+V insertion, mic + Accessibility permission diagnostics). **Build + live validation pending a macOS runner; DMGs are UNSIGNED until Apple Developer credentials are supplied.** |
| Linux x86_64 (X11) | Supported. AppImage build target; pynput global hotkey + `xclip`/`xsel` clipboard. |
| Linux x86_64 (Wayland) | Implemented via the GlobalShortcuts portal with `wl-clipboard`; when the compositor lacks portal/synthetic-input support, SayIt leaves the transcript on the clipboard and tells you to paste. **Per-compositor live validation pending.** |
| Linux ARM64 | Experimental; not validated this milestone. |

macOS global hotkey and desktop-wide text insertion require **Accessibility /
Input Monitoring** permission; microphone capture requires the microphone
permission. SayIt surfaces actionable guidance when a permission is missing and
never claims to be listening when the OS has denied access.

GPU acceleration (NVIDIA/AMD/Intel) is **experimental research only** and not a
supported production backend.

## Release status

`v0.1.2` is the current **bugfix release**. What is verified:

- ✅ Automated test suite: 916 passed, 5 deselected.
- ✅ Warm performance measured (see [Performance](#performance)).
- ✅ Privacy defaults verified (cloud enhancement + history off by default).
- ✅ Dependencies pinned and reproducible (`uv sync --frozen`).
- ✅ Packaged application and live desktop usage have been tested.
- ✅ SayIt has been launched at **https://vptrcipher.github.io/SayIt/**.
- ✅ Custom hotkeys persist across restarts and are re-registered immediately when changed.
- ℹ️ The Windows installer is unsigned; Windows SmartScreen may show a
  "Windows protected your PC" notice on first run (choose *More info →
  Run anyway*).

## Development

```bash
uv sync --frozen            # install the exact validated environment
uv run pytest -m "not slow" # run the test suite (headless)
uv run python -m sayit      # run the app
```

The validated runtime is **sherpa-onnx 1.13.8 + sherpa-onnx-core 1.13.8**
(pinned together). Do not upgrade either without re-validation.

## Project structure

```
SayIt/
├── src/sayit/            # application package (ASR, intelligence, UI, settings)
├── tests/                # test suite
├── scripts/build.py      # Briefcase build driver
├── website/              # product website (GitHub Pages)
├── installer.iss         # Windows Inno Setup script
└── pyproject.toml        # project + Briefcase configuration
```

## Roadmap

- Hardware-adaptive GPU backends (DirectML first) — pending end-to-end
  validation.
- Further ASR latency optimization.
- Broader platform validation.

These are research directions, not dated commitments; experimental work is not
production-ready.

## Contributing

Contributions are welcome. Please fork, create a feature branch, run
`uv run pytest -m "not slow"`, and open a pull request. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) if present.

## License

SayIt is released under the **MIT License** — see [`LICENSE`](LICENSE).
Model weights and runtime dependencies are governed by their own licenses; see
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).

## Acknowledgements

- [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx) (Apache-2.0) — on-device
  ASR inference.
- [NVIDIA Parakeet TDT 0.6B v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
  (CC-BY-4.0) — default speech model (downloaded, not bundled).
- [OpenAI Whisper](https://github.com/openai/whisper) (MIT) — optional models.
- [PySide6 / Qt](https://www.qt.io/) (LGPLv3) — desktop UI.
