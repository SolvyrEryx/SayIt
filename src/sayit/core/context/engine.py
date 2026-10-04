"""Phase 8A context engine.

Collects **local** active-window / foreground-process signals and resolves them
to a :class:`~sayit.core.context.profiles.Profile`. Everything here is
local, cheap, and fail-safe.

Privacy boundary (enforced by tests): this module may read only the foreground
application's process/executable name and (optionally) its window title. It must
NOT capture screenshots, read the clipboard, scrape browser pages, or read
editor contents. There is deliberately no import of any screenshot/clipboard
library in this file.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from ...utils.logger import get_logger
from ...utils.platform import get_platform
from .profiles import (
    AUTO,
    DEFAULT_APP_PROFILE_MAP,
    Profile,
    ProfileConfig,
    profile_config,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class ContextSignals:
    """A snapshot of the local, non-sensitive signals used for context.

    Only identifiers/metadata — never content. ``app_name`` is the normalized
    executable / process name (lowercase, without extension), ``window_title``
    is the foreground window's title where the OS exposes it. Both may be empty
    when detection is unavailable or disabled.
    """

    app_name: str = ""
    window_title: str = ""
    detected: bool = False  # True if any live signal was obtained


@dataclass(frozen=True)
class ContextResolution:
    """The deterministic result of resolving signals + settings to a profile."""

    profile: Profile
    source: str  # "override" | "mapping" | "default" | "disabled"
    signals: ContextSignals = field(default_factory=ContextSignals)
    reason: str = ""

    @property
    def config(self) -> ProfileConfig:
        return profile_config(self.profile)

    def display(self) -> str:
        """Short UI string, e.g. 'Developer', 'Auto · VS Code', 'Normal'.

        - override -> just the chosen profile label.
        - mapping  -> 'Auto · <app>' so the user sees it was automatic.
        - default/disabled -> the profile label.
        """
        if self.source == "mapping" and self.signals.app_name:
            return f"Auto · {self.signals.app_name}"
        return self.profile.label


def _normalize_app_name(raw: str) -> str:
    """Lowercase, strip path + extension from a process/executable name."""
    if not raw:
        return ""
    name = raw.strip().lower().replace("\\", "/")
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if name.endswith(".exe"):
        name = name[:-4]
    return name


# --- local active-window detection ------------------------------------------

def _detect_windows() -> ContextSignals:
    """Foreground process name + window title on Windows via ctypes/user32.

    Uses only GetForegroundWindow / GetWindowText / process image name. No
    third-party dependency; no content access.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ContextSignals()

        # Window title (metadata only).
        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        window_title = title_buf.value or ""

        # Owning process id -> executable image name (metadata only).
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        app_name = ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if h_proc:
            try:
                buf = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                # QueryFullProcessImageNameW
                if kernel32.QueryFullProcessImageNameW(
                    h_proc, 0, buf, ctypes.byref(size)
                ):
                    app_name = buf.value or ""
            finally:
                kernel32.CloseHandle(h_proc)

        return ContextSignals(
            app_name=_normalize_app_name(app_name),
            window_title=window_title,
            detected=bool(app_name or window_title),
        )
    except Exception as e:  # pragma: no cover - platform specific
        logger.debug(f"Windows context detection unavailable: {e}")
        return ContextSignals()


def _detect_linux() -> ContextSignals:
    """Best-effort active-window detection on Linux via xdotool/xprop if present.

    Fail-safe: if the tools are absent (common on headless/Wayland) this simply
    returns empty signals and the engine falls back to Normal. No content is
    read; only the active window's class/title metadata.
    """
    try:
        import shutil
        import subprocess

        if not shutil.which("xdotool"):
            return ContextSignals()

        def _run(args: list[str]) -> str:
            try:
                out = subprocess.run(
                    args, capture_output=True, text=True, timeout=0.5
                )
                return (out.stdout or "").strip()
            except Exception:
                return ""

        win_id = _run(["xdotool", "getactivewindow"])
        if not win_id:
            return ContextSignals()
        title = _run(["xdotool", "getwindowname", win_id])
        cls = _run(["xdotool", "getwindowclassname", win_id])
        return ContextSignals(
            app_name=_normalize_app_name(cls),
            window_title=title,
            detected=bool(cls or title),
        )
    except Exception as e:  # pragma: no cover - platform specific
        logger.debug(f"Linux context detection unavailable: {e}")
        return ContextSignals()


def detect_signals() -> ContextSignals:
    """Return local active-window signals for the current platform.

    Never raises: any failure yields empty signals so the caller resolves to the
    Normal profile.
    """
    try:
        platform = get_platform()
        if platform == "windows":
            return _detect_windows()
        if platform == "linux":
            return _detect_linux()
        return ContextSignals()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"Context detection failed: {e}")
        return ContextSignals()


# --- pure resolution ---------------------------------------------------------

def _match_mapping(
    signals: ContextSignals, app_map: Dict[str, Profile]
) -> Optional[Profile]:
    """Deterministic substring match of signals against the app->profile map.

    Longest key first so the most specific mapping wins. Matches against the
    normalized app name first, then the window title, both lowercased.
    """
    if not app_map:
        return None
    haystacks = [signals.app_name.lower(), signals.window_title.lower()]
    for key in sorted(app_map, key=len, reverse=True):
        k = key.strip().lower()
        if not k:
            continue
        for hay in haystacks:
            if hay and k in hay:
                return app_map[key]
    return None


def resolve_profile(
    signals: ContextSignals,
    *,
    detection_enabled: bool,
    override: "str | Profile",
    app_map: Optional[Dict[str, Profile]] = None,
) -> ContextResolution:
    """Deterministically resolve signals + settings to a ContextResolution.

    Precedence (highest first):
      1. A manual override that is a concrete profile (not AUTO) always wins.
      2. If detection is disabled -> Normal (source "disabled").
      3. An app->profile mapping match -> that profile (source "mapping").
      4. Otherwise -> Normal (source "default").

    Pure and side-effect free; this is the unit-testable core.
    """
    # 1) Manual override.
    if override and str(override).strip().lower() != AUTO:
        prof = Profile.from_value(override)
        return ContextResolution(
            profile=prof,
            source="override",
            signals=signals,
            reason=f"manual override -> {prof.label}",
        )

    # 2) Detection disabled.
    if not detection_enabled:
        return ContextResolution(
            profile=Profile.NORMAL,
            source="disabled",
            signals=signals,
            reason="context detection disabled",
        )

    # 3) Mapping match.
    app_map = app_map if app_map is not None else DEFAULT_APP_PROFILE_MAP
    matched = _match_mapping(signals, app_map)
    if matched is not None:
        return ContextResolution(
            profile=matched,
            source="mapping",
            signals=signals,
            reason=f"app '{signals.app_name or signals.window_title}' -> "
            f"{matched.label}",
        )

    # 4) Default.
    return ContextResolution(
        profile=Profile.NORMAL,
        source="default",
        signals=signals,
        reason="no mapping matched",
    )


class ContextEngine:
    """Thin stateful wrapper around detection + resolution.

    Reads its configuration from a settings-like object lazily at call time so
    changes in Settings take effect without re-wiring. A custom ``detector`` can
    be injected for tests (so no real OS calls happen in CI).
    """

    def __init__(
        self,
        settings,
        detector: Optional[Callable[[], ContextSignals]] = None,
    ):
        self._settings = settings
        self._detector = detector or detect_signals
        # Local, non-persisted diagnostics: last resolution + last detect time.
        self._last: Optional[ContextResolution] = None
        self._last_detect_ms: float = 0.0

    def _user_app_map(self) -> Dict[str, Profile]:
        """Merge the built-in default map with the user's mappings.

        User entries override built-ins for the same key. Malformed user entries
        are skipped (fail-safe).
        """
        merged: Dict[str, Profile] = dict(DEFAULT_APP_PROFILE_MAP)
        raw = getattr(self._settings, "context_app_mappings", None) or {}
        if isinstance(raw, dict):
            for key, val in raw.items():
                try:
                    merged[str(key).strip().lower()] = Profile.from_value(val)
                except Exception:
                    continue
        return merged

    def resolve(self) -> ContextResolution:
        """Detect signals (if enabled) and resolve to a profile.

        Fail-safe end to end: on any error returns a Normal resolution. Records
        detection latency locally (never logged with any content).
        """
        detection_enabled = bool(
            getattr(self._settings, "context_detection_enabled", True)
        )
        override = getattr(self._settings, "context_override", AUTO) or AUTO

        signals = ContextSignals()
        # Only touch the OS if detection is enabled AND there is no concrete
        # override (an override makes detection irrelevant, so skip the work).
        need_signals = detection_enabled and (
            str(override).strip().lower() == AUTO
        )
        if need_signals:
            t0 = time.perf_counter()
            try:
                signals = self._detector()
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(f"Context detect error (ignored): {e}")
                signals = ContextSignals()
            self._last_detect_ms = (time.perf_counter() - t0) * 1000.0

        resolution = resolve_profile(
            signals,
            detection_enabled=detection_enabled,
            override=override,
            app_map=self._user_app_map(),
        )
        self._last = resolution
        return resolution

    @property
    def last_resolution(self) -> Optional[ContextResolution]:
        return self._last

    @property
    def last_detect_ms(self) -> float:
        return self._last_detect_ms
