"""RemindersPanel UI tests (headless Qt). Modal dialogs are patched so direct
handler calls never block, matching the repo convention."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QApplication  # noqa: E402

from sayit.core.conversation import ConversationEngine  # noqa: E402
from sayit.core.reminders import ReminderService, ReminderStatus, ReminderStore  # noqa: E402
from sayit.ui.reminders_panel import RemindersPanel  # noqa: E402

ET = ZoneInfo("America/New_York")
NOW = _dt.datetime(2026, 10, 20, 9, 0, tzinfo=ET)


def _app():
    return QApplication.instance() or QApplication([])


def _svc(tmp_path):
    store = ReminderStore(path=tmp_path / "r.json", clock=lambda: NOW)
    return ReminderService(store, local_tz=ET)


def _seed(svc):
    eng = ConversationEngine(today=NOW.date())
    eng.handle_turn("Remind me about the project meeting tomorrow at 10 AM.")
    task = eng.state.active_task()
    svc.request_confirmation(task)
    return svc.confirm_and_schedule(task, expected_revision=task.revision_number).reminder


def test_panel_lists_reminders(qtbot, tmp_path):
    _app()
    svc = _svc(tmp_path)
    _seed(svc)
    panel = RemindersPanel(svc)
    qtbot.addWidget(panel)
    panel.refresh()
    assert panel._table.rowCount() == 1
    assert "project meeting" in panel._table.item(0, 0).text().lower()


def test_panel_complete_updates_store(qtbot, tmp_path, monkeypatch):
    _app()
    svc = _svc(tmp_path)
    rem = _seed(svc)
    panel = RemindersPanel(svc)
    qtbot.addWidget(panel)
    panel.refresh()
    panel._table.selectRow(0)
    panel._on_complete()
    assert svc.store.get(rem.id).status is ReminderStatus.COMPLETED


def test_panel_cancel_updates_store(qtbot, tmp_path):
    _app()
    svc = _svc(tmp_path)
    rem = _seed(svc)
    panel = RemindersPanel(svc)
    qtbot.addWidget(panel)
    panel.refresh()
    panel._table.selectRow(0)
    panel._on_cancel()
    assert svc.store.get(rem.id).status is ReminderStatus.CANCELLED


def test_panel_no_selection_warns_not_crash(qtbot, tmp_path, monkeypatch):
    _app()
    import sayit.ui.reminders_panel as rp
    monkeypatch.setattr(rp.QMessageBox, "information", lambda *a, **k: None)
    svc = _svc(tmp_path)
    _seed(svc)
    panel = RemindersPanel(svc)
    qtbot.addWidget(panel)
    panel._table.clearSelection()
    # No selection -> handler returns gracefully (info dialog patched).
    panel._on_complete()
    assert svc.store.all()[0].status is ReminderStatus.PENDING  # unchanged
