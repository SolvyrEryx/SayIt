"""Read-only hardware capability detection for the hardware-adaptive ASR
foundation (Phase 3).

This module ONLY observes the machine. It never loads a model, never selects a
backend, and never changes production behavior. It deliberately keeps three
ideas separate (Phase 3/4):

    hardware_detected   -> a GPU / API is physically present on the machine
    backend_supported   -> SayIt has code that *could* target it
    backend_validated   -> SayIt has PROVEN end-to-end parity + stability for it

Detection answering "yes" to the first NEVER implies the second or third. The
only backend that is ``validated`` today is the CPU/Parakeet path.

Everything here is best-effort and fail-safe: any probe that errors is reported
as ``unknown``/``False`` rather than raising, so capability detection can never
break startup or dictation.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class GPUInfo:
    """A single detected GPU adapter (best-effort; fields may be None)."""

    name: str
    vendor: Optional[str] = None
    vram_mib: Optional[int] = None
    driver_version: Optional[str] = None
    source: str = "unknown"  # how we learned about it (nvidia-smi, wmi, ...)


@dataclass
class CapabilityReport:
    """A read-only snapshot of the machine's inference-relevant capabilities.

    This is HARDWARE/RUNTIME detection only. Whether a backend is *supported*
    and *validated* lives with the backend/manager, not here.
    """

    os_name: str
    cpu_name: Optional[str] = None
    cpu_logical: Optional[int] = None
    cpu_physical: Optional[int] = None

    gpus: List[GPUInfo] = field(default_factory=list)

    # API/runtime presence (detected != usable by SayIt).
    cuda_driver_present: bool = False      # nvcuda / nvidia-smi reachable
    cuda_runtime_present: bool = False     # cudart/cudnn present (toolkit)
    directml_present: bool = False         # DirectX 12 / DirectML.dll present
    vulkan_present: bool = False           # vulkan loader present

    notes: List[str] = field(default_factory=list)

    def has_gpu(self) -> bool:
        return bool(self.gpus)

    def primary_gpu(self) -> Optional[GPUInfo]:
        return self.gpus[0] if self.gpus else None


# --------------------------------------------------------------------------
# Individual probes (all best-effort, never raise)
# --------------------------------------------------------------------------
def _cpu_counts() -> tuple[Optional[int], Optional[int]]:
    logical = os.cpu_count()
    physical = None
    try:
        import psutil

        physical = psutil.cpu_count(logical=False)
    except Exception:
        physical = None
    return logical, physical


def _cpu_name() -> Optional[str]:
    try:
        if platform.system() == "Windows":
            # processor env var is a cheap, dependency-free hint.
            return os.environ.get("PROCESSOR_IDENTIFIER") or platform.processor() or None
        return platform.processor() or None
    except Exception:
        return None


def _probe_nvidia() -> List[GPUInfo]:
    """Use nvidia-smi if present. Absence simply means 'no NVIDIA info here'."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        gpus: List[GPUInfo] = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if not parts or not parts[0]:
                continue
            name = parts[0]
            vram = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            drv = parts[2] if len(parts) > 2 else None
            gpus.append(GPUInfo(name=name, vendor="NVIDIA", vram_mib=vram,
                                driver_version=drv, source="nvidia-smi"))
        return gpus
    except Exception:
        return []


def _probe_wmi_gpus() -> List[GPUInfo]:
    """Enumerate display adapters via WMI (Windows). Vendor inferred from name.

    This catches AMD/Intel/NVIDIA adapters that nvidia-smi cannot see. VRAM from
    WMI AdapterRAM is unreliable (32-bit wrap) so it is left None here.
    """
    if platform.system() != "Windows":
        return []
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | "
             "ForEach-Object { $_.Name }"],
            capture_output=True, text=True, timeout=8,
        )
        gpus: List[GPUInfo] = []
        for line in out.stdout.strip().splitlines():
            name = line.strip()
            if not name:
                continue
            low = name.lower()
            vendor = (
                "NVIDIA" if "nvidia" in low or "geforce" in low or "rtx" in low or "gtx" in low
                else "AMD" if "amd" in low or "radeon" in low
                else "Intel" if "intel" in low or "arc" in low
                else None
            )
            gpus.append(GPUInfo(name=name, vendor=vendor, source="wmi"))
        return gpus
    except Exception:
        return []


def _file_on_path_or_system32(names: List[str]) -> bool:
    for n in names:
        if shutil.which(n):
            return True
    if platform.system() == "Windows":
        win = os.environ.get("WINDIR", r"C:\Windows")
        for n in names:
            if os.path.exists(os.path.join(win, "System32", n)):
                return True
    return False


def _probe_cuda_driver() -> bool:
    if shutil.which("nvidia-smi"):
        return True
    return _file_on_path_or_system32(["nvcuda.dll"])


def _probe_cuda_runtime() -> bool:
    # The heavyweight toolkit runtime (cudart/cudnn). Its ABSENCE is the common
    # end-user case even with an NVIDIA GPU.
    return _file_on_path_or_system32(
        ["cudart64_12.dll", "cudart64_11.dll", "cudart64_10.dll",
         "cudnn64_9.dll", "cudnn64_8.dll"]
    )


def _probe_directml() -> bool:
    if platform.system() != "Windows":
        return False
    # DirectML.dll ships in System32 on modern Windows; DX12 is the real gate.
    return _file_on_path_or_system32(["DirectML.dll", "d3d12.dll"])


def _probe_vulkan() -> bool:
    return _file_on_path_or_system32(["vulkan-1.dll", "vulkaninfo", "vulkaninfo.exe"])


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def detect_capabilities() -> CapabilityReport:
    """Return a best-effort, read-only snapshot of the machine. Never raises."""
    logical, physical = _cpu_counts()
    report = CapabilityReport(
        os_name=f"{platform.system()} {platform.release()}",
        cpu_name=_cpu_name(),
        cpu_logical=logical,
        cpu_physical=physical,
    )

    # GPUs: prefer nvidia-smi detail, then fill in any adapters WMI sees that
    # nvidia-smi missed (AMD/Intel), de-duplicating by name.
    gpus = _probe_nvidia()
    seen = {g.name.lower() for g in gpus}
    for g in _probe_wmi_gpus():
        if g.name.lower() not in seen:
            gpus.append(g)
            seen.add(g.name.lower())
    report.gpus = gpus

    report.cuda_driver_present = _probe_cuda_driver()
    report.cuda_runtime_present = _probe_cuda_runtime()
    report.directml_present = _probe_directml()
    report.vulkan_present = _probe_vulkan()

    if report.cuda_driver_present and not report.cuda_runtime_present:
        report.notes.append(
            "CUDA driver present but no CUDA runtime/cuDNN (toolkit) installed."
        )
    return report
