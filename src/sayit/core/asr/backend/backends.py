"""Concrete ASR backends (Phase 1).

ParakeetCPUBackend is the ONLY production-registered backend. It delegates to the
existing, validated ``TranscriptionEngine`` (sherpa-onnx 1.12.21, Parakeet int8,
CPU, greedy) so output is byte-identical to today. No ASR logic is reimplemented.

The future backends (DirectML/CUDA/Vulkan/Metal) are represented ONLY as honest,
unavailable/experimental descriptors so diagnostics can show them without
implying support. They raise nothing and never run in production.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..transcriber import TranscriptionEngine
from .base import (
    ASRBackend,
    BackendCapabilities,
    BackendState,
    TranscriptionOutput,
    ValidationLevel,
)


class ParakeetCPUBackend(ASRBackend):
    """Production CPU backend. Thin wrapper over the existing engine.

    Behaviorally identical to calling TranscriptionEngine directly: the app can
    keep using the engine today, and this wrapper exists so the BackendManager
    has a uniform object to register/select/diagnose.
    """

    NAME = "parakeet-cpu"

    def __init__(
        self,
        model_name: str = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8",
        whisper_num_threads: int = 4,
        engine: Optional[TranscriptionEngine] = None,
    ):
        self._model_name = model_name
        self._whisper_num_threads = whisper_num_threads
        # Allow injecting an already-constructed engine so the app can wrap the
        # exact warm engine it already owns (no second model load).
        self._engine = engine
        self._state = BackendState.UNINITIALIZED

    # -- lifecycle ---------------------------------------------------------
    def attach_engine(self, engine: TranscriptionEngine) -> None:
        """Wrap an existing (possibly already-loaded) engine without reloading."""
        self._engine = engine
        if engine is not None and engine.is_ready:
            self._state = BackendState.READY

    def initialize(self) -> bool:
        try:
            if self._engine is None:
                self._engine = TranscriptionEngine(
                    model_name=self._model_name,
                    whisper_num_threads=self._whisper_num_threads,
                )
            if not self._engine.is_ready:
                self._engine.load_model()
            self._state = BackendState.READY
            return True
        except Exception:
            self._state = BackendState.ERROR
            return False

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        if self._engine is None:
            return None
        # Delegate to the EXACT production path (chunking + offline decode).
        return self._engine.transcribe_chunked(audio_data, sample_rate)

    def transcribe_detailed(self, audio_data: np.ndarray, sample_rate: int = 16000) -> TranscriptionOutput:
        text = self.transcribe(audio_data, sample_rate) or ""
        return TranscriptionOutput(
            text=text,
            chunk_count=getattr(self._engine, "last_chunk_count", 1) or 1,
            invocation_count=getattr(self._engine, "last_invocation_count", 1) or 1,
        )

    def cancel(self) -> None:
        # The native offline decode cannot be force-interrupted; cooperative
        # cancellation is owned by the worker/job-id layer (unchanged). No-op
        # here keeps the contract explicit.
        return None

    def shutdown(self) -> None:
        try:
            if self._engine is not None:
                self._engine.unload()
        finally:
            self._state = BackendState.SHUTDOWN

    # -- introspection -----------------------------------------------------
    def is_available(self) -> bool:
        """CPU backend is available whenever the model is cached/loadable."""
        try:
            if self._engine is not None and self._engine.is_ready:
                return True
            probe = self._engine or TranscriptionEngine(model_name=self._model_name)
            return probe.is_model_cached()
        except Exception:
            return False

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name=self.NAME,
            display_name="Parakeet CPU",
            device_kind="cpu",
            validation=ValidationLevel.VALIDATED,  # the only validated backend
            experimental=False,
            accelerated=False,
            vendors=("CPU",),
            notes="Production path: sherpa-onnx 1.12.21, Parakeet TDT 0.6B v2 int8, greedy.",
        )

    def diagnostics(self) -> dict:
        return {
            "backend": self.NAME,
            "display_name": "Parakeet CPU",
            "device": "cpu",
            "validation": ValidationLevel.VALIDATED.value,
            "state": self.state.value,
            "model": self._model_name,
            "accelerated": False,
        }


# --------------------------------------------------------------------------
# Honest placeholders for future backends. These are NOT registered for
# selection in production; they exist so diagnostics can show the roadmap
# truthfully (detected hardware != supported != validated).
# --------------------------------------------------------------------------
class UnavailableBackend(ASRBackend):
    """A not-yet-available backend descriptor. Never runs; always unavailable."""

    def __init__(self, name: str, display_name: str, device_kind: str,
                 vendors: tuple, validation: ValidationLevel, note: str):
        self._name = name
        self._display = display_name
        self._device_kind = device_kind
        self._vendors = vendors
        self._validation = validation
        self._note = note
        self._state = BackendState.UNINITIALIZED

    def initialize(self) -> bool:
        return False

    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        return None

    def cancel(self) -> None:
        return None

    def shutdown(self) -> None:
        self._state = BackendState.SHUTDOWN

    def is_available(self) -> bool:
        return False

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name=self._name,
            display_name=self._display,
            device_kind=self._device_kind,
            validation=self._validation,
            experimental=True,
            accelerated=False,
            vendors=self._vendors,
            notes=self._note,
        )

    def diagnostics(self) -> dict:
        return {
            "backend": self._name,
            "display_name": self._display,
            "device": self._device_kind,
            "validation": self._validation.value,
            "state": "unavailable",
            "experimental": True,
            "accelerated": False,
            "note": self._note,
        }
