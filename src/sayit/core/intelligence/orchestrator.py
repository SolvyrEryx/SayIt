"""Deterministic intelligence orchestrator (Phase 8H).

Resolves ONE utterance to an :class:`IntelligenceResult` by consulting the
independent 8B-8G engines in a fixed priority order. Explicit user commands win
over passive context. The orchestrator is pure given its inputs (no I/O, no
network), so it is fully unit-testable and deterministic.

Priority (highest first), per the Phase 8 spec:

    VOICE_EDIT (8B)  -> modify recent output / backtrack
    SNIPPET (8C)     -> whole-utterance snippet expansion
    STRUCTURE (8G)   -> explicit structure commands
    DEVELOPER_FORMAT (8D) -> explicit casing / code block
    DICTATE          -> ordinary dictation (fallback)

Safe Zones (8E) are intentionally NOT handled here: they are a recording-time
gate evaluated before any audio is captured (see app wiring). By the time text
reaches the orchestrator, recording was already allowed.

Loop prevention: each engine is consulted at most once, in order, and the first
match wins and returns immediately. There is no re-feeding of one engine's
output into another, so A->B->C->A cycles are structurally impossible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..context import ContextResolution, Profile
from ..developer import detect_casing_command, detect_code_block
from ..snippets import Snippet, match_snippet
from ..structure import detect_structure
from ..voice_commands import detect_voice_edit
from .contracts import IntelligenceResult, IntentCategory, IntentResult


@dataclass
class OrchestratorConfig:
    """Which intelligence features are enabled. All deterministic.

    A disabled feature does not participate (its engine is skipped entirely), so
    a disabled feature can never win intent resolution.
    """

    voice_edit_enabled: bool = True
    snippets_enabled: bool = True
    structure_enabled: bool = True
    developer_mode_enabled: bool = True
    # Developer casing/code-block only auto-activate when the resolved context
    # profile is Developer/Prompt, OR when developer_mode is forced on. Casing
    # is an explicit trailing command regardless, so this only gates whether we
    # consult the developer engine at all.
    developer_requires_profile: bool = False


class IntelligenceOrchestrator:
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self._config = config or OrchestratorConfig()

    def process(
        self,
        text: str,
        *,
        context: Optional[ContextResolution] = None,
        snippets: Optional[List[Snippet]] = None,
        recent_output: Optional[str] = None,
    ) -> IntelligenceResult:
        """Resolve ``text`` to an IntelligenceResult. Deterministic."""
        if text is None:
            text = ""
        cfg = self._config

        # 1) VOICE EDIT (8B) -------------------------------------------------
        if cfg.voice_edit_enabled:
            edit = detect_voice_edit(text, recent_output)
            if edit.is_edit:
                res = IntelligenceResult(
                    text=edit.new_text,
                    intent=IntentResult(
                        category=IntentCategory.VOICE_EDIT,
                        confidence=1.0,
                        payload=edit,
                        reason=edit.summary or edit.rule,
                    ),
                    replaces_recent_output=edit.replaces_recent,
                    replaced_span_text=recent_output if edit.replaces_recent else None,
                )
                res.add_change("voice_edit", text, edit.new_text, edit.rule)
                return res

        # 2) SNIPPET (8C) ----------------------------------------------------
        if cfg.snippets_enabled and snippets:
            match = match_snippet(text, snippets)
            if match is not None:
                res = IntelligenceResult(
                    text=match.expansion,
                    intent=IntentResult(
                        category=IntentCategory.SNIPPET,
                        confidence=1.0,
                        payload=match,
                        reason=f"snippet '{match.snippet.trigger}'",
                    ),
                    # A snippet expansion is literal text; do NOT run prose /
                    # technical correction over it (would corrupt URLs/templates).
                    skip_correction=True,
                )
                res.add_change("snippet", text, match.expansion, "user_snippet")
                return res

        # 3) STRUCTURE (8G) --------------------------------------------------
        if cfg.structure_enabled:
            structure = detect_structure(text)
            if structure.is_structure:
                res = IntelligenceResult(
                    text=structure.text,
                    intent=IntentResult(
                        category=IntentCategory.STRUCTURE,
                        confidence=1.0,
                        payload=structure,
                        reason=structure.rule,
                    ),
                    # Standalone break commands and ready-made lists are literal
                    # structure; skip prose correction for them.
                    skip_correction=structure.standalone or structure.rule == "ordinal_list",
                )
                res.add_change("structure", text, structure.text, structure.rule)
                return res

        # 4) DEVELOPER FORMAT (8D) ------------------------------------------
        if cfg.developer_mode_enabled and self._developer_active(context):
            # Code block first (block wrapper), then explicit casing.
            code = detect_code_block(text)
            if code.is_command:
                res = IntelligenceResult(
                    text=code.text,
                    intent=IntentResult(
                        category=IntentCategory.DEVELOPER_FORMAT,
                        confidence=1.0,
                        payload=code,
                        reason="code block",
                    ),
                    skip_correction=True,  # preserve code verbatim
                )
                res.add_change("developer", text, code.text, code.rule)
                return res

            casing = detect_casing_command(text)
            if casing.is_command:
                res = IntelligenceResult(
                    text=casing.identifier,
                    intent=IntentResult(
                        category=IntentCategory.DEVELOPER_FORMAT,
                        confidence=1.0,
                        payload=casing,
                        reason=f"{casing.style} case",
                    ),
                    skip_correction=True,  # the identifier is final
                )
                res.add_change("developer", text, casing.identifier, casing.rule)
                return res

        # 5) DICTATE (fallback) ---------------------------------------------
        return IntelligenceResult(
            text=text,
            intent=IntentResult(category=IntentCategory.DICTATE, confidence=1.0,
                                reason="ordinary dictation"),
        )

    def _developer_active(self, context: Optional[ContextResolution]) -> bool:
        """Whether to consult the developer engine.

        Casing/code-block are explicit trailing/leading commands, so they are
        safe to offer whenever Developer Mode is enabled. If
        ``developer_requires_profile`` is set, they are only offered under a
        Developer/Prompt context profile.
        """
        if not self._config.developer_requires_profile:
            return True
        if context is None:
            return False
        return context.profile in (Profile.DEVELOPER, Profile.PROMPT)
