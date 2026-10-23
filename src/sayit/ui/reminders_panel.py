"""Reminder management panel — view/complete/cancel/reschedule reminders.

A small, native-feeling top-level window reusing the SayIt theme. It is a thin
VIEW over a ``ReminderService`` (the authoritative store/scheduler layer); it
performs no scheduling logic itself and never touches the recorder, clipboard,
or network. All mutations go through the service so conversational and UI edits
share one source of truth.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import __display_name__
from ..core.reminders import ReminderService, ReminderStatus
from .theme import STYLESHEET


class RemindersPanel(QWidget):
    """Standalone reminder manager backed by a ReminderService."""

    closed = Signal()

    def __init__(self, service: ReminderService, parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint)
        self._service = service
        self.setWindowTitle(f"{__display_name__} — Reminders")
        self.setMinimumSize(520, 380)
        self.setStyleSheet(STYLESHEET)
        self._setup_ui()
        self.refresh()

    # -- UI --------------------------------------------------------------
    def _setup_ui(self) -> None:
        self.setObjectName("SayItRemindersPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        header = QHBoxLayout()
        title = QLabel("Reminders")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Title", "When", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self._table, 1)

        # Honest disclosure of the runtime limitation.
        disclosure = QLabel(
            "Reminders fire as desktop notifications while SayIt is running. "
            "If SayIt is closed when a reminder is due, it notifies you at the "
            "next launch."
        )
        disclosure.setWordWrap(True)
        disclosure.setStyleSheet("color: rgba(128,128,128,200); font-size: 11px;")
        layout.addWidget(disclosure)

        row = QHBoxLayout()
        self._complete_btn = QPushButton("Mark complete")
        self._complete_btn.clicked.connect(self._on_complete)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._reschedule_btn = QPushButton("Reschedule…")
        self._reschedule_btn.clicked.connect(self._on_reschedule)
        self._rename_btn = QPushButton("Rename…")
        self._rename_btn.clicked.connect(self._on_rename)
        for b in (self._complete_btn, self._cancel_btn, self._reschedule_btn, self._rename_btn):
            row.addWidget(b)
        row.addStretch()
        layout.addLayout(row)

    # -- data ------------------------------------------------------------
    def refresh(self) -> None:
        reminders = self._service.store.all()
        self._table.setRowCount(0)
        tz = getattr(self._service, "_tz", _dt.timezone.utc)
        for r in reminders:
            row = self._table.rowCount()
            self._table.insertRow(row)
            local = r.trigger_at.astimezone(tz)
            when = local.strftime("%a %b %d, %I:%M %p").replace(" 0", " ")
            title_item = QTableWidgetItem(r.title)
            title_item.setData(Qt.UserRole, r.id)  # stash the reminder id
            self._table.setItem(row, 0, title_item)
            self._table.setItem(row, 1, QTableWidgetItem(when))
            self._table.setItem(row, 2, QTableWidgetItem(r.status.value))

    def _selected_id(self) -> Optional[str]:
        items = self._table.selectedItems()
        if not items:
            return None
        return self._table.item(items[0].row(), 0).data(Qt.UserRole)

    # -- actions ---------------------------------------------------------
    def _require_selection(self) -> Optional[str]:
        rid = self._selected_id()
        if rid is None:
            QMessageBox.information(self, "No selection", "Select a reminder first.")
        return rid

    def _report(self, res) -> None:
        if res.ok:
            self.refresh()
        else:
            QMessageBox.warning(self, "Reminder", res.message)

    def _on_complete(self) -> None:
        rid = self._require_selection()
        if rid:
            self._report(self._service.complete(rid, source_text="(UI) complete"))

    def _on_cancel(self) -> None:
        rid = self._require_selection()
        if rid:
            self._report(self._service.cancel(rid, source_text="(UI) cancel"))

    def _on_rename(self) -> None:
        rid = self._require_selection()
        if not rid:
            return
        new_title, ok = QInputDialog.getText(self, "Rename reminder", "New title:")
        if ok and new_title.strip():
            self._report(self._service.retitle(rid, new_title.strip(), source_text="(UI) rename"))

    def _on_reschedule(self) -> None:
        rid = self._require_selection()
        if not rid:
            return
        # Minimal, dependency-free reschedule: accept a YYYY-MM-DD and HH:MM.
        date_str, ok = QInputDialog.getText(
            self, "Reschedule", "New date (YYYY-MM-DD), blank to keep:"
        )
        if not ok:
            return
        time_str, ok2 = QInputDialog.getText(
            self, "Reschedule", "New time (HH:MM 24h), blank to keep:"
        )
        if not ok2:
            return
        self._report(
            self._service.reschedule(
                rid,
                date_iso=date_str.strip() or None,
                time_24h=time_str.strip() or None,
                source_text="(UI) reschedule",
            )
        )

    # -- lifecycle -------------------------------------------------------
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)
        self.closed.emit()
