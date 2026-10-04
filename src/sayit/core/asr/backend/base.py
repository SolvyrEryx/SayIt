"""ASRBackend abstraction (Phase 1).

A thin, additive interface that lets SayIt support multiple inference backends
in the future (CPU, DirectML, CUDA, Vulkan, Metal) WITHOUT changing today's
behavior. The ONLY production-registered backend is ``ParakeetCPUBackend``,
which simply delegates to the existing, validated ``TranscriptionEngine`` so
transcripts are byte-identical to the current implementation.

Design rules honored:
- No ASR logic is reimplemented here. The CPU backend wraps the existing engine.
- ``validated`` is reserved for backends with PROVEN end-to-end parity. Only CPU
  is validated today.
- Every method is safe to call; backends report availability instead of raising.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class BackendState(Enum):
    UNINITIALIZED = "uninitialized"
    READY = "ready"
    ERROR = "error"
    SHUTDOWN = "shutdown"


class ValidationLevel(Enum):
    """How much we trust a backend. Keep this honest.

    DETECTED   -> hardware/runtime present, nothing proven
    SUPPORTED  -> code exists that could target it
    VALIDATED  -> proven end-to-end parity + stability (production-eligible)
    """

    DETECTED = "detected"
    SUPPORTED = "supported"
    VALIDATED = "validated"


@dataclass
class BackendCapabilities:
    """What a backend claims about itself. Never overstates GPU acceleration."""

    name: str                       # e.g. "parakeet-cpu"
    display_name: str               # e.g. "Parakeet CPU"
    device_kind: str                # "cpu" | "directml" | "cuda" | "vulkan" | "metal"
    validation: ValidationLevel     # honesty gate
    experimental: bool = False
    accelerated: bool = False       # True ONLY if proven real HW acceleration
    vendors: tuple = ()             # e.g. ("NVIDIA","AMD","Intel") or ("CPU",)
    notes: str = ""


@dataclass
class TranscriptionOutput:
    """Backend transcription result. ``text`` must match the production engine
    for the CPU backend (byte-identical)."""

    text: str
    chunk_count: int = 1
    invocation_count: int = 1
    extra: dict = field(default_factory=dict)


class ASRBackend(abc.ABC):
    """Abstract inference backend. Implementations must be fail-safe."""

    @abc.abstractmethod
    def initialize(self) -> bool:
        """Load/warm the backend. Returns True on success, False on failure.
        Must not raise for ordinary failure modes."""

    @abc.abstractmethod
    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        """Transcribe mono audio. Returns text or None. Byte-identical to the
        production engine for the CPU backend."""

    @abc.abstractmethod
    def cancel(self) -> None:
        """Cooperative cancel request. ASR native calls cannot be force-killed;
        this signals intent only (parity with the existing worker contract)."""

    @abc.abstractmethod
    def shutdown(self) -> None:
        """Release the model/resources. Idempotent."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Can this backend run on THIS machine right now (model + runtime)?"""

    @abc.abstractmethod
    def capabilities(self) -> BackendCapabilities:
        """Static capability/honesty descriptor."""

    @abc.abstractmethod
    def diagnostics(self) -> dict:
        """Human-facing status dict (no transcript content). Must distinguish
        detected vs supported vs validated vs active."""

    @property
    def state(self) -> BackendState:
        return getattr(self, "_state", BackendState.UNINITIALIZED)
