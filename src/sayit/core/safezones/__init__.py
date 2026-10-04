"""Phase 8E Safe Zones: block recording in user-designated protected apps.

A Safe Zone is a GATE, not a text transformation. It is evaluated BEFORE
recording begins, using the SAME local active-window detection as Phase 8A
(``core.context.detect_signals``) — it does not add a second detection
subsystem, and it reads only foreground application/window metadata (never
screenshots, clipboard, or content).

Behavior:
- If the foreground app matches an enabled protected entry, recording must not
  begin and no audio is captured.
- Fail-safe: if detection yields nothing (unknown app, headless, Wayland), the
  zone is NOT considered protected, so dictation is never silently disabled by a
  detection failure. (Protection requires a positive match.)
"""

from .zones import SafeZoneResult, is_protected, protected_match

__all__ = ["SafeZoneResult", "is_protected", "protected_match"]
