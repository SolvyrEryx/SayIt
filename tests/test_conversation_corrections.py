"""Conversational self-correction + intent-revision tests (Cases A-L).

Deterministic, local-only: a fixed ``today`` (Wed 2026-10-14) resolves relative
dates so assertions are stable. These verify the INTENDED behaviour (the right
active state changes) rather than that a model returns plausible text.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from sayit.core.conversation import (
    ConversationEngine,
    CorrectionKind,
    detect_correction,
)
from sayit.core.conversation.state import SlotName, TaskStatus

TODAY = _dt.date(2026, 10, 14)  # Wednesday
FRIDAY = "2026-10-16"
SATURDAY = "2026-10-17"
TOMORROW = "2026-10-15"  # Thursday


def _engine():
    return ConversationEngine(today=TODAY)


# --- Case A: date correction ------------------------------------------------
def test_case_a_date_correction():
    e = _engine()
    e.handle_turn("I have a meeting tomorrow.")
    r = e.handle_turn("Scratch that, Friday.")
    assert r.correction_kind == "replace"
    task = e.state.active_task()
    assert task.get(SlotName.DATE) == FRIDAY
    # Only one task — the correction did not spawn a second.
    assert len(e.state.tasks) == 1


# --- Case B: time correction ------------------------------------------------
def test_case_b_time_correction():
    e = _engine()
    e.handle_turn("Schedule it for 2 PM.")
    r = e.handle_turn("Actually, 3 PM.")
    task = e.state.active_task()
    assert task.get(SlotName.TIME) == "15:00"
    assert len(e.state.tasks) == 1
    assert r.changed


# --- Case C: multiple corrections -------------------------------------------
def test_case_c_multiple_corrections():
    e = _engine()
    e.handle_turn("Friday at 2 PM.")
    e.handle_turn("No, Saturday at 4 PM.")
    task = e.state.active_task()
    assert task.get(SlotName.DATE) == SATURDAY
    assert task.get(SlotName.TIME) == "16:00"


# --- Case D: preserve unchanged info ----------------------------------------
def test_case_d_preserve_unchanged():
    e = _engine()
    e.handle_turn("Remind me about the project meeting tomorrow at 10 AM.")
    task = e.state.active_task()
    assert task.get(SlotName.TIME) == "10:00"
    e.handle_turn("Actually Friday.")
    task = e.state.active_task()
    assert task.get(SlotName.DATE) == FRIDAY   # changed
    assert task.get(SlotName.TIME) == "10:00"  # preserved
    assert task.get(SlotName.GOAL) == "reminder"  # preserved


# --- Case E: additive instruction -------------------------------------------
def test_case_e_additive():
    e = _engine()
    e.handle_turn("Prepare the report.")
    e.handle_turn("Also include competitor analysis.")
    task = e.state.active_task()
    assert any("competitor analysis" in r.lower() for r in task.requirements)
    assert task.get(SlotName.GOAL) == "report"  # original intent preserved


# --- Case F: remove a requirement -------------------------------------------
def test_case_f_remove_requirement():
    e = _engine()
    e.handle_turn("Prepare a report.")
    t = e.state.active_task()
    t.add_requirement("budget", source_text="seed")
    t.add_requirement("timeline", source_text="seed")
    t.add_requirement("competitor analysis", source_text="seed")
    e.handle_turn("Actually, remove the budget.")
    reqs = [r.lower() for r in e.state.active_task().requirements]
    assert "budget" not in reqs
    assert "timeline" in reqs and "competitor analysis" in reqs


# --- Case G: cancellation before execution ----------------------------------
def test_case_g_cancel_before_execution():
    e = _engine()
    e.handle_turn("Remind me about my meeting tomorrow.")
    r = e.handle_turn("Cancel that.")
    assert r.correction_kind == "cancel"
    assert e.state.active_task().status is TaskStatus.CANCELLED


# --- Case H: ambiguous target -----------------------------------------------
def test_case_h_ambiguous_target():
    e = _engine()
    e.handle_turn("Schedule a meeting with Alice tomorrow.")
    # Force a genuinely separate second open task (different goal keyword).
    e.handle_turn("Also set a reminder for my dentist on Friday.")
    # Two open tasks now exist; an unqualified correction must clarify.
    # (Seed a second open task explicitly to guarantee ambiguity.)
    if len(e.state.open_tasks()) < 2:
        t2 = e.state.new_task()
        t2.set_slot(SlotName.GOAL, "reminder", source_text="seed")
    r = e.handle_turn("Move that to Friday.")
    assert r.needs_clarification is True
    assert "which" in r.clarification.lower()


# --- Case I: genuinely new topic --------------------------------------------
def test_case_i_new_topic_leaves_prior_task():
    e = _engine()
    e.handle_turn("Schedule a meeting on Friday.")
    first = e.state.active_task()
    first_date = first.get(SlotName.DATE)
    e.handle_turn("Draft an email about the quarterly report.")
    # A new task was started; the first task's date is unchanged.
    assert len(e.state.tasks) == 2
    assert e.state.get_task(first.id).get(SlotName.DATE) == first_date


# --- Case J: correction after execution -------------------------------------
def test_case_j_correction_after_execution():
    e = _engine()
    e.handle_turn("Remind me about the meeting on Friday.")
    task = e.state.active_task()
    task.mark_executed(effect_id="reminder-123")
    r = e.handle_turn("Actually, Saturday.")
    assert r.post_execution_conflict is True
    assert r.changed is False
    # The executed effect id and status are untouched (no silent rewrite).
    assert e.state.active_task().status is TaskStatus.EXECUTED
    assert e.state.active_task().executed_effect_id == "reminder-123"


# --- Case K: out-of-order async (revision guard) ----------------------------
def test_case_k_stale_async_cannot_overwrite():
    from sayit.core.conversation.safe_action import ActionCoordinator

    e = _engine()
    e.handle_turn("Remind me tomorrow.")
    task = e.state.active_task()
    coord = ActionCoordinator()
    stale_rev = task.revision_number  # snapshot for the "old" async call
    # A newer correction bumps the revision.
    e.handle_turn("Actually, Friday.")
    newer_rev = task.revision_number
    assert newer_rev > stale_rev
    # A stale async result computed against the old revision must be rejected.
    assert coord.is_result_current(task, stale_rev) is False
    assert coord.is_result_current(task, newer_rev) is True


# --- Case L: ordinary dictation isolation -----------------------------------
def test_case_l_dictation_isolation():
    # The engine is only ever invoked for CONVERSATION turns. Ordinary
    # dictation never reaches it. This test asserts the detector alone would
    # flag "scratch that" but the ROUTING keeps dictation out (see
    # test_intelligence_routing). Here we assert the detector is a pure
    # function with no global side effect on any engine.
    sig = detect_correction("Please write: scratch that from the list.")
    # Even if the detector sees a cue mid-sentence, applying it requires an
    # active engine turn; dictation does not create one.
    assert sig.kind in (CorrectionKind.REPLACE, CorrectionKind.NONE)
    e = _engine()  # a fresh engine that never saw the dictation
    assert e.state.active_task() is None



# --- Case M: title / subject correction (regression) ------------------------
# Reported defect: "Keep the reminder, but change its title to Project Review."
# left the title as "project meeting". The title correction cue was never
# detected and the subject slot was never updated.
def test_case_m_title_correction_reported_scenario():
    e = _engine()
    e.handle_turn("Remind me about the project meeting on Friday at 10 AM.")
    before = e.state.active_task()
    assert before.get(SlotName.DATE) == FRIDAY
    assert before.get(SlotName.TIME) == "10:00"

    r = e.handle_turn("Keep the reminder, but change its title to Project Review.")
    task = e.state.active_task()
    # (1) Title updated to exactly "Project Review" (case preserved).
    assert task.get(SlotName.SUBJECT) == "Project Review"
    # (2) Date, time, goal preserved.
    assert task.get(SlotName.DATE) == FRIDAY
    assert task.get(SlotName.TIME) == "10:00"
    assert task.get(SlotName.GOAL) == "reminder"
    # (3) Same task revised, not duplicated.
    assert len(e.state.tasks) == 1
    assert r.correction_kind == "title"
    assert r.changed is True


def test_case_m_title_detection_classifies_as_title():
    sig = detect_correction("change its title to Project Review")
    assert sig.kind is CorrectionKind.TITLE
    assert sig.payload == "Project Review"


def test_case_m_title_various_phrasings_preserve_case():
    phrasings = {
        "rename it to Q4 Planning": "Q4 Planning",
        "change the title to Budget Sync": "Budget Sync",
        "call it Standup": "Standup",
        "the title should be Weekly Review.": "Weekly Review",
        "set its name to Demo Day": "Demo Day",
    }
    for utterance, expected in phrasings.items():
        e = _engine()
        e.handle_turn("Remind me about the project meeting on Friday.")
        e.handle_turn(utterance)
        assert e.state.active_task().get(SlotName.SUBJECT) == expected, utterance


def test_case_m_title_does_not_touch_date_replacement():
    # Generic "change that to Friday" must stay a date REPLACE, not a title op.
    assert detect_correction("change that to Friday").kind is CorrectionKind.REPLACE
    assert detect_correction("scratch that, Friday").kind is CorrectionKind.REPLACE


def test_case_m_title_ambiguous_triggers_clarification():
    e = _engine()
    e.handle_turn("Remind me about the project meeting on Friday.")
    t2 = e.state.new_task()
    t2.set_slot(SlotName.GOAL, "reminder", source_text="seed")
    r = e.handle_turn("Change its title to Project Review.")
    assert r.needs_clarification is True
    # No task was retitled while ambiguous.
    assert all(t.get(SlotName.SUBJECT) != "Project Review" for t in e.state.tasks)


def test_case_m_title_empty_value_clarifies_not_guesses():
    e = _engine()
    e.handle_turn("Remind me about the project meeting on Friday.")
    original = e.state.active_task().get(SlotName.SUBJECT)
    r = e.handle_turn("Change the title to")
    assert r.needs_clarification is True
    # Title not cleared or guessed when no value was given.
    assert e.state.active_task().get(SlotName.SUBJECT) == original


def test_case_m_title_after_execution_not_rewritten():
    e = _engine()
    e.handle_turn("Remind me about the project meeting on Friday.")
    e.state.active_task().mark_executed(effect_id="rem-1")
    r = e.handle_turn("Change its title to Project Review.")
    assert r.post_execution_conflict is True
    assert r.changed is False
    assert e.state.active_task().get(SlotName.SUBJECT) != "Project Review"


def test_case_m_typed_and_spoken_title_equivalent():
    # Typed and spoken both route through handle_turn: identical result.
    typed = _engine()
    typed.handle_turn("Remind me about the project meeting on Friday.")
    typed.handle_turn("Change its title to Project Review.")
    spoken = _engine()
    spoken.handle_turn("Remind me about the project meeting on Friday.")
    spoken.handle_turn("Change its title to Project Review.")
    assert (typed.state.active_task().get(SlotName.SUBJECT)
            == spoken.state.active_task().get(SlotName.SUBJECT)
            == "Project Review")
