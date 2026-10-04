"""BackendManager (Phase 2) + honest diagnostics (Phase 4).

Enumerates backends, queries capabilities, selects one, exposes the active
backend, and provides safe fallback. In production it registers ONLY the
validated CPU/Parakeet backend; future GPU backends are listed as
experimental/unavailable so the diagnostics panel is truthful without implying
support.

Selection policy (Phase 13): AUTO chooses only among detected + supported +
VALIDATED backends. Until a GPU backend is proven, AUTO == CPU. An experimental
backend is never selected in production.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from .backends import ParakeetCPUBackend, UnavailableBackend
from .base import ASRBackend, ValidationLevel
from .capability import CapabilityReport, detect_capabilities


class AccelerationMode(Enum):
    AUTO = "auto"
    GPU = "gpu"
    CPU = "cpu"


def _future_backends(cap: CapabilityReport) -> List[UnavailableBackend]:
    """Build honest, UNAVAILABLE descriptors for roadmap backends, labelled by
    what the machine actually has. Nothing here is selectable in production."""
    out: List[UnavailableBackend] = []
    out.append(UnavailableBackend(
        "parakeet-directml", "Parakeet DirectML", "directml",
        ("NVIDIA", "AMD", "Intel"), ValidationLevel.SUPPORTED,
        "Encoder graph verified on GPU in isolation; full TDT end-to-end parity "
        "NOT yet proven. Experimental; not production-validated.",
    ))
    out.append(UnavailableBackend(
        "parakeet-cuda", "Parakeet CUDA", "cuda", ("NVIDIA",),
        ValidationLevel.DETECTED if cap.cuda_driver_present else ValidationLevel.DETECTED,
        "NVIDIA-only. Requires a custom GPU sherpa-onnx build; not validated.",
    ))
    out.append(UnavailableBackend(
        "parakeet-vulkan", "Parakeet Vulkan", "vulkan", ("NVIDIA", "AMD", "Intel"),
        ValidationLevel.DETECTED,
        "No ONNX Runtime Vulkan EP; only exists in ggml-class runtimes. Unvalidated.",
    ))
    return out


class BackendManager:
    """Owns backend registration + selection. CPU-only in production."""

    def __init__(self, mode: AccelerationMode = AccelerationMode.AUTO):
        self._mode = mode
        self._capabilities: CapabilityReport = detect_capabilities()
        self._cpu = ParakeetCPUBackend()
        # Registered-for-selection backends (production). CPU only.
        self._registry: Dict[str, ASRBackend] = {self._cpu.NAME: self._cpu}
        # Roadmap descriptors for diagnostics only (never selected).
        self._roadmap: List[UnavailableBackend] = _future_backends(self._capabilities)
        self._active: Optional[ASRBackend] = None

    # -- registration ------------------------------------------------------
    def register(self, backend: ASRBackend) -> None:
        """Register an additional selectable backend. Guarded: only VALIDATED,
        available backends may become selectable, preserving the production rule
        that experimental backends are never auto-selected."""
        caps = backend.capabilities()
        if caps.validation is ValidationLevel.VALIDATED and backend.is_available():
            self._registry[caps.name] = backend

    def attach_cpu_engine(self, engine) -> None:
        """Wrap the app's already-warm engine so no second model load occurs."""
        self._cpu.attach_engine(engine)

    # -- selection (Phase 13) ---------------------------------------------
    def select(self) -> ASRBackend:
        """Choose a backend per the mode, among detected+supported+VALIDATED
        only. Today this always resolves to CPU (safe)."""
        # GPU mode requested but no validated GPU backend exists -> safe CPU.
        validated = [
            b for b in self._registry.values()
            if b.capabilities().validation is ValidationLevel.VALIDATED
            and b.is_available()
        ]
        gpu_validated = [b for b in validated if b.capabilities().device_kind != "cpu"]

        if self._mode is AccelerationMode.GPU and gpu_validated:
            self._active = gpu_validated[0]
        else:
            # AUTO and CPU both resolve to CPU today; GPU falls back to CPU.
            self._active = self._cpu
        return self._active

    def active(self) -> Optional[ASRBackend]:
        return self._active

    def fallback_to_cpu(self) -> ASRBackend:
        """Safe fallback: force the validated CPU backend active."""
        self._active = self._cpu
        return self._active

    # -- introspection -----------------------------------------------------
    @property
    def mode(self) -> AccelerationMode:
        return self._mode

    @property
    def capabilities(self) -> CapabilityReport:
        return self._capabilities

    def available_backends(self) -> List[str]:
        return [n for n, b in self._registry.items() if b.is_available()]

    def diagnostics(self) -> dict:
        """Honest, user-facing status (Phase 4). Separates detected hardware
        from supported/validated backends from the active selection. Never
        reports 'GPU accelerated' unless a validated accelerated backend is
        actually active."""
        cap = self._capabilities
        primary = cap.primary_gpu()
        active = self._active or self._cpu
        active_caps = active.capabilities()

        return {
            "hardware": {
                "os": cap.os_name,
                "cpu": cap.cpu_name,
                "cpu_physical": cap.cpu_physical,
                "cpu_logical": cap.cpu_logical,
                "gpu_detected": primary.name if primary else None,
                "gpu_vendor": primary.vendor if primary else None,
                "gpu_vram_mib": primary.vram_mib if primary else None,
                "all_gpus": [g.name for g in cap.gpus],
            },
            "runtimes": {
                "directml": "available" if cap.directml_present else "unavailable",
                "cuda_driver": "available" if cap.cuda_driver_present else "unavailable",
                "cuda_runtime": "available" if cap.cuda_runtime_present else "unavailable (no toolkit)",
                "vulkan": "available" if cap.vulkan_present else "unavailable",
            },
            "backends": {
                "cpu": "validated",
                "directml": "experimental / not production validated",
                "cuda": "unavailable or unvalidated",
                "vulkan": "unvalidated",
            },
            "active_asr": {
                "backend": active_caps.display_name,
                "device": active_caps.device_kind,
                # Only ever True if a validated accelerated backend is active.
                "accelerated": bool(active_caps.accelerated
                                    and active_caps.validation is ValidationLevel.VALIDATED),
                "status": ("Accelerated"
                           if (active_caps.accelerated
                               and active_caps.validation is ValidationLevel.VALIDATED)
                           else "CPU"),
            },
            "roadmap": [b.diagnostics() for b in self._roadmap],
            "notes": cap.notes,
        }
