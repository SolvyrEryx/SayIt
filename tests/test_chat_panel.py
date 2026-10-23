"""ChatPanel UI tests (headless pytest-qt).

Drive the panel with a real IntelligenceOrchestrator (local engine + a mock
cloud reply fn), asserting the user-visible behaviour: messages appear, the
pending-proposal preview tracks the latest revision, clarification is surfaced,
the voice button emits a signal (dictation stays separate), and a stale async
turn cannot overwrite a newer one.
"""

from __future__ import annotations

import datetime as _dt

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication  # noqa: E402

from sayit.core.conversation import ConversationEngine  # noqa: E402
from sayit.core.conversation.state import SlotName  # noqa: E402
from sayit.core.conversation import (  # noqa: E402
    CloudPolicy,
    IntelligenceOrchestrator,
)
from sayit.ui.chat_panel import ChatPanel  # noqa: E402

TODAY = _dt.date(2026, 10, 14)


def _app():
    return QApplication.instance() or QApplication([])


def _orch(cloud_enabled=False, provider_available=False, reply_fn=None):
    eng = ConversationEngine(today=TODAY)
    pol = CloudPolicy(cloud_enabled=cloud_enabled, provider_available=provider_available)
    return IntelligenceOrchestrator(eng, pol, cloud_reply_fn=reply_fn)


def test_submit_text_shows_message_and_proposal(qtbot):
    _app()
    panel = ChatPanel(_orch())
    qtbot.addWidget(panel)
    panel.submit_text("Remind me about the meeting tomorrow.")
    # The worker runs on a QThread; wait for the assistant reply to land.
    qtbot.waitUntil(lambda: "Assistant:" in panel._transcript.toPlainText(), timeout=3000)
    assert "You: Remind me about the meeting tomorrow." in panel._transcript.toPlainText()
    # Pending proposal preview is visible and reflects the task.
    qtbot.waitUntil(lambda: "Pending proposal" in panel._proposal.text(), timeout=2000)
    assert "reminder" in panel._proposal.text().lower()


def test_correction_updates_same_proposal_revision(qtbot):
    _app()
    o = _orch()
    panel = ChatPanel(o)
    qtbot.addWidget(panel)
    panel.submit_text("Remind me about the meeting tomorrow.")
    qtbot.waitUntil(lambda: "Pending proposal" in panel._proposal.text(), timeout=3000)
    panel.submit_text("Scratch that, Friday.")
    qtbot.waitUntil(
        lambda: "2026-10-16" in panel._proposal.text(), timeout=3000
    )
    # Single task; the correction updated it in place (date -> Friday).
    task = o._engine.state.active_task()
    assert task.get(SlotName.DATE) == "2026-10-16"
    assert len(o._engine.state.tasks) == 1


def test_clarification_surfaced(qtbot):
    _app()
    o = _orch()
    panel = ChatPanel(o)
    qtbot.addWidget(panel)
    # Seed two open tasks so an unqualified correction must clarify.
    o._engine.handle_turn("Schedule a meeting on Friday.")
    o._engine.state.new_task()
    o._engine.state.tasks[-1].set_slot(SlotName.GOAL, "reminder", source_text="seed")
    panel.submit_text("Move that to Saturday.")
    qtbot.waitUntil(
        lambda: "which" in panel._transcript.toPlainText().lower(), timeout=3000
    )
    assert "clarification" in panel._status.text().lower()


def test_voice_button_emits_signal_only(qtbot):
    _app()
    panel = ChatPanel(_orch())
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.voice_requested, timeout=1000):
        panel._voice_btn.click()


def test_cloud_disabled_status_is_local(qtbot):
    _app()
    panel = ChatPanel(_orch(cloud_enabled=False, provider_available=True,
                            reply_fn=lambda t, c: "CLOUD TEXT"))
    qtbot.addWidget(panel)
    panel.submit_text("Remind me tomorrow.")
    qtbot.waitUntil(lambda: "local" in panel._status.text().lower(), timeout=3000)
    assert "CLOUD TEXT" not in panel._transcript.toPlainText()


def test_stale_turn_ignored(qtbot):
    _app()
    panel = ChatPanel(_orch())
    qtbot.addWidget(panel)
    # Simulate a stale finished reply with an old turn id.
    panel._latest_turn_id = 5
    before = panel._transcript.toPlainText()
    panel._on_finished({"text": "stale reply", "needs_clarification": False,
                        "used_cloud": False, "cloud_skipped_reason": ""}, turn_id=3)
    assert panel._transcript.toPlainText() == before  # ignored
