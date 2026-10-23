"""Unit tests for the correction detector and slot extractor."""

from __future__ import annotations

import datetime as _dt

from sayit.core.conversation.corrections import CorrectionKind, detect_correction
from sayit.core.conversation.slots import extract_slots, resolve_relative_date

TODAY = _dt.date(2026, 10, 14)  # Wednesday


# --- correction detector ----------------------------------------------------
def test_detect_cancel_and_undo():
    assert detect_correction("cancel that").kind is CorrectionKind.CANCEL
    assert detect_correction("never mind").kind is CorrectionKind.CANCEL
    assert detect_correction("undo that").kind is CorrectionKind.UNDO
    assert detect_correction("forget the last change").kind is CorrectionKind.UNDO


def test_detect_replace_variants():
    for t in ("scratch that, Friday", "actually, 3 PM", "no make it Saturday",
              "change that to Monday", "I meant Tuesday", "move that to Friday"):
        assert detect_correction(t).kind is CorrectionKind.REPLACE, t


def test_detect_add_and_remove():
    assert detect_correction("also include competitor analysis").kind is CorrectionKind.ADD
    assert detect_correction("one more thing: add the appendix").kind is CorrectionKind.ADD
    assert detect_correction("remove the budget").kind is CorrectionKind.REMOVE
    assert detect_correction("drop the timeline").kind is CorrectionKind.REMOVE


def test_no_overtrigger_on_plain_prose():
    # Ordinary statements with no correction cue at a clause boundary.
    assert detect_correction("I have a meeting on Friday").kind is CorrectionKind.NONE
    assert detect_correction("The report covers the budget and timeline").kind is CorrectionKind.NONE


def test_fillers_tolerated():
    sig = detect_correction("um, uh, scratch that, Friday")
    assert sig.kind is CorrectionKind.REPLACE
    assert "friday" in sig.payload.lower()


def test_empty_is_none():
    assert detect_correction("").kind is CorrectionKind.NONE
    assert detect_correction("   ").kind is CorrectionKind.NONE


# --- slot extractor ---------------------------------------------------------
def test_relative_date_resolution():
    assert resolve_relative_date("tomorrow", TODAY) == "2026-10-15"
    assert resolve_relative_date("today", TODAY) == "2026-10-14"
    assert resolve_relative_date("Friday", TODAY) == "2026-10-16"
    # Same-weekday resolves to today, not +7.
    assert resolve_relative_date("Wednesday", TODAY) == "2026-10-14"
    assert resolve_relative_date("day after tomorrow", TODAY) == "2026-10-16"
    assert resolve_relative_date("2027-01-01", TODAY) == "2027-01-01"
    assert resolve_relative_date("someday", TODAY) is None


def test_time_extraction_ampm_and_24h():
    s = extract_slots("meet at 2 PM", TODAY)
    assert s.time_24h == "14:00"
    s = extract_slots("at 9:30 am", TODAY)
    assert s.time_24h == "09:30"
    s = extract_slots("at 14:45", TODAY)
    assert s.time_24h == "14:45"
    s = extract_slots("at 12 am", TODAY)
    assert s.time_24h == "00:00"


def test_goal_and_date_extraction():
    s = extract_slots("remind me about the meeting tomorrow", TODAY)
    assert s.goal == "reminder"
    assert s.date_iso == "2026-10-15"
    assert s.date_phrase.lower() == "tomorrow"


def test_no_date_when_absent():
    s = extract_slots("just some plain text", TODAY)
    assert s.date_iso is None and s.time_24h is None
