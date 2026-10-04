"""Phase 8H intelligence orchestrator package.

Exposes the shared contracts and the single ``IntelligenceOrchestrator`` that
sequences the independent 8B-8G engines deterministically. The orchestrator does
NOT re-implement any engine's logic; it only decides which engine owns an
utterance and assembles an :class:`IntelligenceResult`.
"""

from .contracts import (
    IntelligenceResult,
    IntentCategory,
    IntentResult,
)
from .orchestrator import IntelligenceOrchestrator, OrchestratorConfig

__all__ = [
    "IntentCategory",
    "IntentResult",
    "IntelligenceResult",
    "IntelligenceOrchestrator",
    "OrchestratorConfig",
]
