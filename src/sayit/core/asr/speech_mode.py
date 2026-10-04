"""Speech-mode abstraction — Fast (Parakeet) vs Higher Accuracy (Whisper Small).

A thin PRODUCT-level layer over the existing ASR model registry/backend. It does
NOT introduce a second architecture: both modes resolve to a concrete model id
consumed by the SAME ``TranscriptionEngine`` / ``SherpaOnnxBackend`` and the SAME
downstream SayIt intelligence. Only the ASR model changes.

- FAST = Parakeet TDT v2 INT8 (production default; always the fallback).
- HIGHER_ACCURACY = Whisper Small (OPT-IN; measured +25 pts UNSEEN technical
  recall on the TIE held-out set, at ~4x compute and a small hallucination risk).

Selection is persisted via the existing ``Settings.model_id`` (so legacy saved
selections keep working). This module only maps modes <-> model ids and reports
availability; it reads/writes nothing on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .models.registry import is_model_downloaded

# Concrete model ids (must match models.json / registry).
FAST_MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
HIGHER_ACCURACY_MODEL_ID = "sherpa-onnx-whisper-small"

FAST = "fast"
HIGHER_ACCURACY = "higher_accuracy"
DEFAULT_MODE = FAST


@dataclass(frozen=True)
class SpeechMode:
    mode: str                 # "fast" | "higher_accuracy"
    model_id: str
    label: str                # user-facing short label
    tagline: str              # one-line trade-off description
    tradeoff: str             # longer trade-off note
    status_prefix: str        # subtle status, e.g. "Fast" / "Higher Accuracy"
    optional: bool            # requires explicit opt-in + possible download


_MODES: Dict[str, SpeechMode] = {
    FAST: SpeechMode(
        mode=FAST, model_id=FAST_MODEL_ID, label="Fast",
        tagline="Fast local dictation",
        tradeoff="Fastest response. The default for everyday dictation.",
        status_prefix="Fast", optional=False,
    ),
    HIGHER_ACCURACY: SpeechMode(
        mode=HIGHER_ACCURACY, model_id=HIGHER_ACCURACY_MODEL_ID,
        label="Higher Accuracy",
        tagline="Higher technical recall in SayIt's measured evaluation",
        tradeoff=("Stronger technical-term recognition in SayIt's measured TIE "
                  "evaluation, but noticeably slower transcription (~4x). Optional."),
        status_prefix="Higher Accuracy", optional=True,
    ),
}


def all_modes() -> List[SpeechMode]:
    # Fast first, then Higher Accuracy (stable product order).
    return [_MODES[FAST], _MODES[HIGHER_ACCURACY]]


def mode_for_model_id(model_id: Optional[str]) -> str:
    """Resolve a persisted model id to a product mode. Unknown/legacy ids map to
    FAST only if they equal the fast model; otherwise they are reported as their
    own custom selection via ``is_known_mode`` (kept FAST for the toggle default
    but never silently rewritten)."""
    if model_id == HIGHER_ACCURACY_MODEL_ID:
        return HIGHER_ACCURACY
    return FAST


def is_known_mode_model(model_id: Optional[str]) -> bool:
    return model_id in (FAST_MODEL_ID, HIGHER_ACCURACY_MODEL_ID)


def model_id_for_mode(mode: str) -> str:
    return _MODES.get(mode, _MODES[FAST]).model_id


def get_mode(mode: str) -> SpeechMode:
    return _MODES.get(mode, _MODES[FAST])


def is_mode_available(mode: str) -> bool:
    """Whether the mode's model is downloaded/ready locally."""
    try:
        return is_model_downloaded(model_id_for_mode(mode))
    except Exception:
        return False


def mode_status(mode: str) -> str:
    """UI status token: 'Installed'/'Ready'/'Not installed'."""
    m = get_mode(mode)
    if is_mode_available(mode):
        return "Ready" if m.optional else "Installed"
    return "Not installed"


def status_line(model_id: Optional[str]) -> str:
    """Subtle current-model status for the Home surface, e.g.
    'Fast · Parakeet INT8' or 'Higher Accuracy · Whisper Small'. Never exposes
    internal backend class names."""
    mode = mode_for_model_id(model_id)
    m = get_mode(mode)
    friendly = "Parakeet INT8" if mode == FAST else "Whisper Small"
    return f"{m.status_prefix} · {friendly}"
