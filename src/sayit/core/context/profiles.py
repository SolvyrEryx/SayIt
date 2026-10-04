"""Phase 8A profiles: the deterministic map from a profile to the existing
correction flags, plus a conservative default application->profile mapping.

A profile in Phase 8A is intentionally small: it only decides how the existing
Phase 6G/6I correction layer is driven. It does NOT introduce any new text
rewriting. Concretely, a ``ProfileConfig`` is just the three booleans that
``correct_transcript`` already accepts:

    enable_technical  -> technical aliases + spelled acronyms (6G)
    enable_formatting -> structured values: versions / % / dates / URL / path (6G/6I)
    enable_structured -> the Phase 6I URL/path/email/vN sub-feature (gated by formatting)

So "Developer" simply keeps the full on-device technical layer on, while a
prose-oriented profile such as "Email" leaves ordinary language alone by turning
the aggressive structured/technical rewriting down. Nothing here can rewrite
arbitrary prose; it can only enable or disable rules that already exist and are
already conservative.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Profile(str, Enum):
    """The context/formatting profiles SayIt understands.

    ``str`` mixin so a profile serializes to a stable, human-readable token in
    the JSON settings (e.g. "developer") with no custom encoder needed.
    """

    NORMAL = "normal"
    DEVELOPER = "developer"
    EMAIL = "email"
    CHAT = "chat"
    NOTES = "notes"
    PROMPT = "prompt"

    @property
    def label(self) -> str:
        """Human-facing label, e.g. 'Developer'."""
        return self.value.capitalize()

    @classmethod
    def from_value(cls, value: "str | Profile | None") -> "Profile":
        """Parse a stored value to a Profile, defaulting to NORMAL.

        Fail-safe: unknown / malformed values resolve to NORMAL rather than
        raising, so a corrupted setting can never break dictation.
        """
        if isinstance(value, Profile):
            return value
        if not value:
            return cls.NORMAL
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.NORMAL


# Sentinel used by the override setting to mean "no manual override; use
# automatic detection". Stored as a plain string in settings.
AUTO = "auto"


@dataclass(frozen=True)
class ProfileConfig:
    """The correction-flag configuration a profile resolves to.

    These map 1:1 onto ``correct_transcript``'s existing parameters. Frozen so a
    profile's behavior is immutable and trivially comparable in tests.
    """

    enable_technical: bool
    enable_formatting: bool
    enable_structured: bool


# Deterministic profile -> correction-flag table.
#
# Rationale per profile (conservative; only toggles existing rules):
# - NORMAL / CHAT: keep today's shipped defaults (technical + formatting on).
#   This preserves 6G/6I behavior for users who never touch context. Chat is a
#   light-touch profile; it does not add any new conversational rewriting.
# - DEVELOPER / PROMPT: full technical + structured layer on (identifiers,
#   versions, paths, URLs preserved/normalized). This is the strongest form of
#   the existing layer, nothing new.
# - EMAIL / NOTES: prose-oriented. Keep the safe technical-term normalization
#   (so "git hub" still becomes GitHub in an email) but turn OFF the aggressive
#   structured URL/path/version rewriting that is undesirable in flowing prose.
#   Ordinary language is therefore left even more untouched than the default.
_PROFILE_TABLE: dict[Profile, ProfileConfig] = {
    Profile.NORMAL: ProfileConfig(True, True, True),
    Profile.CHAT: ProfileConfig(True, True, True),
    Profile.DEVELOPER: ProfileConfig(True, True, True),
    Profile.PROMPT: ProfileConfig(True, True, True),
    Profile.EMAIL: ProfileConfig(True, True, False),
    Profile.NOTES: ProfileConfig(True, True, False),
}


def profile_config(profile: Profile) -> ProfileConfig:
    """Return the deterministic correction-flag config for ``profile``.

    Unknown profiles fall back to NORMAL's config (fail-safe).
    """
    return _PROFILE_TABLE.get(profile, _PROFILE_TABLE[Profile.NORMAL])


PROFILE_DESCRIPTIONS: dict[Profile, str] = {
    Profile.NORMAL: "General dictation. Shipped defaults.",
    Profile.DEVELOPER: "Technical terms, identifiers, paths, URLs and versions "
    "preserved/normalized.",
    Profile.EMAIL: "Prose-oriented. Keeps safe term normalization; avoids "
    "structured URL/path/version rewriting.",
    Profile.CHAT: "Conversational. Light-touch formatting.",
    Profile.NOTES: "Readable notes. Prose-oriented formatting.",
    Profile.PROMPT: "Preserves technical terminology and structure.",
}


# Conservative, developer-focused default application->profile mapping.
#
# Keys are lowercase substrings matched against the detected process/executable
# name OR the window title (see engine). Substring (not exact) matching keeps the
# table small and robust across OS variations (e.g. "code.exe", "Code - foo").
# This map is deterministic and fully user-overridable via settings.
DEFAULT_APP_PROFILE_MAP: dict[str, Profile] = {
    # Developer tools / editors / terminals.
    "code": Profile.DEVELOPER,          # VS Code (code.exe)
    "vscode": Profile.DEVELOPER,
    "cursor": Profile.DEVELOPER,
    "devenv": Profile.DEVELOPER,        # Visual Studio
    "pycharm": Profile.DEVELOPER,
    "idea": Profile.DEVELOPER,          # IntelliJ
    "webstorm": Profile.DEVELOPER,
    "sublime_text": Profile.DEVELOPER,
    "sublime": Profile.DEVELOPER,
    "windowsterminal": Profile.DEVELOPER,
    "powershell": Profile.DEVELOPER,
    "cmd": Profile.DEVELOPER,
    "wezterm": Profile.DEVELOPER,
    "alacritty": Profile.DEVELOPER,
    "gnome-terminal": Profile.DEVELOPER,
    "konsole": Profile.DEVELOPER,
    "iterm": Profile.DEVELOPER,
    "nvim": Profile.DEVELOPER,
    "vim": Profile.DEVELOPER,
    # Email clients.
    "outlook": Profile.EMAIL,
    "thunderbird": Profile.EMAIL,
    "mailspring": Profile.EMAIL,
    # Chat.
    "slack": Profile.CHAT,
    "discord": Profile.CHAT,
    "teams": Profile.CHAT,
    "telegram": Profile.CHAT,
    "whatsapp": Profile.CHAT,
    # Notes / docs.
    "notion": Profile.NOTES,
    "obsidian": Profile.NOTES,
    "onenote": Profile.NOTES,
    "notepad": Profile.NOTES,
}
