"""Deterministic slot extraction (dates, times, goal, subject).

Pure and timezone/current-date aware: relative dates ("tomorrow", "Friday") are
resolved against an injected ``today`` (the app passes the configured local
date) so the engine never guesses the current date. When a date/time cannot be
resolved it is left as a phrase for the caller to clarify — we never invent a
calendar value.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from typing import Optional

from .state import SlotName

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_GOAL_KEYWORDS = {
    "reminder": "reminder",
    "remind": "reminder",
    "meeting": "meeting",
    "email": "email",
    "draft": "draft",
    "report": "report",
    "note": "note",
    "event": "event",
    "schedule": "meeting",
    "appointment": "meeting",
}


@dataclass
class ExtractedSlots:
    date_iso: Optional[str] = None
    date_phrase: Optional[str] = None
    time_24h: Optional[str] = None
    time_phrase: Optional[str] = None
    goal: Optional[str] = None
    subject: Optional[str] = None


def resolve_relative_date(phrase: str, today: _dt.date) -> Optional[str]:
    """Resolve a relative/absolute date phrase to an ISO date, or None.

    Supports: today, tomorrow, day after tomorrow, weekday names (next
    occurrence, same-day counts as today), and explicit YYYY-MM-DD.
    """
    p = phrase.strip().lower()
    if not p:
        return None
    if p in ("today",):
        return today.isoformat()
    if p in ("tomorrow", "tmrw", "tmr"):
        return (today + _dt.timedelta(days=1)).isoformat()
    if "day after tomorrow" in p:
        return (today + _dt.timedelta(days=2)).isoformat()
    for name, wd in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", p):
            delta = (wd - today.weekday()) % 7
            # "Friday" when today is Friday means today; a plain weekday that
            # has passed this week resolves to next week.
            if delta == 0:
                return today.isoformat()
            return (today + _dt.timedelta(days=delta)).isoformat()
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", p)
    if m:
        try:
            return _dt.date.fromisoformat(m.group(1)).isoformat()
        except ValueError:
            return None
    return None


_DATE_PHRASE_RE = re.compile(
    r"\b(day after tomorrow|tomorrow|today|tmrw|tmr|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)

_TIME_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b|\b(\d{1,2}):(\d{2})\b",
    re.IGNORECASE,
)

# Spelled-out hour words (common in speech: "two PM", "ten AM", "at four").
_WORD_HOURS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_WORD_TIME_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
    r"\s*(a\.?m\.?|p\.?m\.?|o'?clock)?",
    re.IGNORECASE,
)


def extract_time(phrase: str) -> tuple[Optional[str], Optional[str]]:
    """Return (HH:MM 24h, matched phrase) or (None, None).

    Handles digit forms (2 PM, 14:45, 9:30 am) and spelled-out hours that read
    as a time in context ("two PM", "at four", "ten o'clock"). A bare spelled
    number with no am/pm/o'clock + no time preposition is NOT treated as a time
    to avoid false positives.
    """
    m = _TIME_RE.search(phrase)
    if m:
        if m.group(1) is not None:  # am/pm form
            hour = int(m.group(1))
            minute = int(m.group(2) or 0)
            ampm = m.group(3).replace(".", "").lower()
            if ampm == "pm" and hour != 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
        else:  # 24h HH:MM
            hour = int(m.group(4))
            minute = int(m.group(5))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}", m.group(0)

    # Spelled-out hour. Only accept when an am/pm/o'clock marker OR a time
    # preposition ("at <word>") is present, so "four reports" isn't a time.
    wm = _WORD_TIME_RE.search(phrase)
    if wm:
        marker = wm.group(2)
        preceded_by_at = re.search(
            r"\bat\s+" + re.escape(wm.group(1)) + r"\b", phrase, re.IGNORECASE
        )
        if marker or preceded_by_at:
            hour = _WORD_HOURS[wm.group(1).lower()]
            ampm = marker.replace(".", "").lower() if marker and marker != "o'clock" else None
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            elif ampm is None and 1 <= hour <= 6:
                # Bare afternoon-ish hour in a scheduling context ("at four")
                # conventionally means PM. Documented heuristic; explicit am/pm
                # always wins.
                hour += 12
            return f"{hour:02d}:00", wm.group(0)
    return None, None


def extract_slots(text: str, today: _dt.date) -> ExtractedSlots:
    """Extract date/time/goal/subject slots from a user message."""
    out = ExtractedSlots()

    dm = _DATE_PHRASE_RE.search(text)
    if dm:
        out.date_phrase = dm.group(0)
        out.date_iso = resolve_relative_date(dm.group(0), today)

    t24, tphrase = extract_time(text)
    if t24:
        out.time_24h = t24
        out.time_phrase = tphrase

    low = text.lower()
    for kw, goal in _GOAL_KEYWORDS.items():
        if re.search(rf"\b{kw}\b", low):
            out.goal = goal
            break

    # Subject: a noun-ish phrase following "about"/"for" (best-effort, local).
    sm = re.search(r"\b(?:about|for)\s+(?:my |the |a |an )?([a-z][a-z \-]{2,40})", low)
    if sm:
        subj = sm.group(1).strip()
        # Trim trailing date/time words from the subject.
        subj = _DATE_PHRASE_RE.sub("", subj).strip(" -")
        if subj:
            out.subject = subj

    return out
