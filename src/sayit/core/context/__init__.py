"""Phase 8A: SayIt local context engine + profiles.

A deterministic, local-only layer that detects *where* SayIt is being used
(active application/window metadata only) and resolves a formatting **profile**.
The profile influences ONLY the existing on-device correction flags
(Phase 6G technical correction / structured formatting). It never rewrites
arbitrary prose and never calls a network or LLM.

Design guarantees (see tests/test_context_phase8a.py):

- **Local only.** Detection reads active-window / foreground-process metadata
  via OS APIs. It never takes screenshots, reads the clipboard, scrapes browser
  pages, or reads editor contents.
- **Fail-safe.** Any detection error yields the ``Normal`` profile; dictation is
  never blocked by context detection.
- **Deterministic.** The same signals + settings always resolve to the same
  profile, and a profile always maps to the same correction flags.
- **Explainable.** Resolution produces a reason string and the pipeline emits a
  ``Change(category="context", ...)`` record so the UI can explain the choice.
- **Overridable.** A manual override (Auto / a specific profile) always wins over
  automatic detection.
"""

from .profiles import (
    DEFAULT_APP_PROFILE_MAP,
    PROFILE_DESCRIPTIONS,
    Profile,
    ProfileConfig,
    profile_config,
)
from .engine import (
    ContextEngine,
    ContextResolution,
    ContextSignals,
    resolve_profile,
)

__all__ = [
    "Profile",
    "ProfileConfig",
    "profile_config",
    "PROFILE_DESCRIPTIONS",
    "DEFAULT_APP_PROFILE_MAP",
    "ContextSignals",
    "ContextResolution",
    "ContextEngine",
    "resolve_profile",
]
