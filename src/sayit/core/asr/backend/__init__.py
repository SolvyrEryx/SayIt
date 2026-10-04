"""Hardware-adaptive ASR backend foundation (Phase 1-4).

Public API. In production only the CPU/Parakeet backend is registered and
selectable; everything else is honest roadmap metadata for diagnostics.
"""
from .base import (
    ASRBackend,
    BackendCapabilities,
    BackendState,
    TranscriptionOutput,
    ValidationLevel,
)
from .backends import ParakeetCPUBackend, UnavailableBackend
from .capability import CapabilityReport, GPUInfo, detect_capabilities
from .manager import AccelerationMode, BackendManager

__all__ = [
    "ASRBackend",
    "BackendCapabilities",
    "BackendState",
    "TranscriptionOutput",
    "ValidationLevel",
    "ParakeetCPUBackend",
    "UnavailableBackend",
    "CapabilityReport",
    "GPUInfo",
    "detect_capabilities",
    "AccelerationMode",
    "BackendManager",
]
