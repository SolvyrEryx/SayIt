"""Language-aware model routing (Phase: Bharat).

Keeps the user-facing *dictation language* decoupled from the concrete ASR
model id. The core guarantees enforced here:

- A non-English language (hi/kn) is NEVER routed to an English-only model
  (e.g. Parakeet). ``is_compatible`` and ``resolve_model_for_language`` both
  refuse that pairing.
- Switching language resolves to a compatible model; if an installed one
  exists it is preferred, otherwise the canonical default for that language is
  returned so the UI can offer a download.
- Incompatibilities are reported explicitly (never silently "fixed" by
  swapping to a wrong-language model behind the user's back).

This module is pure/deterministic and does not perform any network or disk
writes; it only reads the registry + installed-model status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models.registry import (
    get_model_by_id,
    get_models_for_language,
    is_model_downloaded,
)

# Canonical default model id per language. English keeps the existing shipped
# Parakeet int8 default; hi/kn use the IndicConformer CTC exports.
DEFAULT_MODEL_BY_LANGUAGE = {
    "en": "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
    "hi": "indicconformer-hi-int8",
    "kn": "indicconformer-kn-int8",
}


@dataclass
class RouteResult:
    language: str
    model_id: Optional[str]
    installed: bool
    compatible: bool
    reason: str


def get_model_language(model_id: str) -> Optional[str]:
    model = get_model_by_id(model_id)
    return model.language if model else None


def is_compatible(language: str, model_id: str) -> bool:
    """True only if ``model_id`` exists and declares the requested language."""
    model = get_model_by_id(model_id)
    if model is None:
        return False
    return model.language == language


def resolve_model_for_language(
    language: str, current_model_id: Optional[str] = None
) -> RouteResult:
    """Pick a compatible model for ``language``.

    Preference order:
      1. ``current_model_id`` if it is already compatible (don't churn).
      2. An installed model for the language.
      3. The canonical default model for the language (may need downloading).

    Never returns a model of a different language. If no model is registered
    for the language, ``model_id`` is None with an explanatory reason.
    """
    candidates = get_models_for_language(language)
    if not candidates:
        return RouteResult(
            language=language,
            model_id=None,
            installed=False,
            compatible=False,
            reason=f"No model is registered for language '{language}'.",
        )

    # 1. Keep the current model if it is already compatible.
    if current_model_id and is_compatible(language, current_model_id):
        return RouteResult(
            language=language,
            model_id=current_model_id,
            installed=is_model_downloaded(current_model_id),
            compatible=True,
            reason="Current model already matches the selected language.",
        )

    # 2. Prefer an installed compatible model.
    for model in candidates:
        if is_model_downloaded(model.id):
            return RouteResult(
                language=language,
                model_id=model.id,
                installed=True,
                compatible=True,
                reason="Using an installed model for the selected language.",
            )

    # 3. Fall back to the canonical default (needs download).
    default_id = DEFAULT_MODEL_BY_LANGUAGE.get(language, candidates[0].id)
    return RouteResult(
        language=language,
        model_id=default_id,
        installed=is_model_downloaded(default_id),
        compatible=True,
        reason="No compatible model installed yet; download required.",
    )


def resolve_fallback_model(
    language: str, failed_model_id: str, english_fallback_id: str
) -> Optional[str]:
    """Pick a startup fallback model that NEVER crosses languages.

    Release-gate rule: a Hindi/Kannada selection must never silently fall back
    to the English-only Parakeet model. So:

    - For English, the historical behaviour is preserved: fall back to
      ``english_fallback_id`` only if it is actually an English-tagged model
      and is not the one that just failed.
    - For a non-English language, only a model *of that same language* may be
      used as a fallback, and never the one that just failed. If no other
      compatible model exists, return ``None`` so the caller surfaces an honest
      error instead of switching the user to English.
    """
    if language == "en":
        if (
            is_compatible("en", english_fallback_id)
            and english_fallback_id != failed_model_id
        ):
            return english_fallback_id
        return None

    for model in get_models_for_language(language):
        if model.id != failed_model_id:
            return model.id
    return None


def check_language_model_pairing(language: str, model_id: str) -> RouteResult:
    """Diagnose a (language, model) pair for the UI/startup.

    Returns a RouteResult describing whether the pairing is compatible and
    installed. Used to surface clear errors like 'Hindi selected but the
    English Parakeet model is active'.
    """
    model = get_model_by_id(model_id)
    if model is None:
        return RouteResult(
            language=language,
            model_id=model_id,
            installed=False,
            compatible=False,
            reason=f"Model '{model_id}' is not registered.",
        )
    compatible = model.language == language
    reason = (
        "Compatible."
        if compatible
        else (
            f"Model '{model_id}' is for language '{model.language}', "
            f"but '{language}' is selected."
        )
    )
    return RouteResult(
        language=language,
        model_id=model_id,
        installed=is_model_downloaded(model_id),
        compatible=compatible,
        reason=reason,
    )
