"""Safe Zone matching (Phase 8E).

Pure matching against a user-configured list of protected application
substrings, using the same ContextSignals shape produced by Phase 8A.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..context.engine import ContextSignals, detect_signals


@dataclass
class SafeZoneResult:
    protected: bool
    matched_entry: str = ""   # the protected list entry that matched
    app_name: str = ""        # the detected app (for the UI message)
    reason: str = ""


def protected_match(
    signals: ContextSignals, protected_apps: List[str]
) -> Optional[str]:
    """Return the protected-list entry that matches the signals, or None.

    Substring, case-insensitive, matched against the normalized app name first
    then the window title (same discipline as the 8A app map). Longest entry
    first for determinism.
    """
    if not protected_apps:
        return None
    haystacks = [
        (signals.app_name or "").lower(),
        (signals.window_title or "").lower(),
    ]
    for entry in sorted((e for e in protected_apps if e and e.strip()), key=len, reverse=True):
        e = entry.strip().lower()
        for hay in haystacks:
            if hay and e in hay:
                return entry
    return None


def is_protected(
    protected_apps: List[str],
    enabled: bool = True,
    detector=None,
) -> SafeZoneResult:
    """Evaluate whether the CURRENT foreground app is a protected Safe Zone.

    Fail-safe: any detection error or empty signals -> not protected. A custom
    ``detector`` (returning ContextSignals) can be injected for tests so no real
    OS call happens in CI.
    """
    if not enabled or not protected_apps:
        return SafeZoneResult(protected=False, reason="safe zones disabled")
    try:
        signals = (detector or detect_signals)()
    except Exception:
        return SafeZoneResult(protected=False, reason="detection failed (fail-safe)")

    entry = protected_match(signals, protected_apps)
    if entry is None:
        return SafeZoneResult(
            protected=False,
            app_name=signals.app_name,
            reason="no protected app matched",
        )
    return SafeZoneResult(
        protected=True,
        matched_entry=entry,
        app_name=signals.app_name,
        reason=f"protected app '{entry}' is foreground",
    )
