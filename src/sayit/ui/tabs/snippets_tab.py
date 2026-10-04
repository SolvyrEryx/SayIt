from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.settings import Settings
from ...core.snippets import Snippet, detect_snippet_conflicts, snippets_from_any


class SnippetsTab(QWidget):
    """Phase 8C snippet editor.

    A local, text-only expansion system distinct from vocabulary: an explicit
    spoken trigger expands into a (possibly multiline) block of saved text.
    Snippets are NEVER executed — the expansion is always inserted as literal
    text. Stored locally in settings; never transmitted.

    UI mirrors the Vocabulary tab's structure (add row + table + conflict note)
    for consistency.
    """

    _COL_ENABLED = 0
    _COL_TRIGGER = 1
    _COL_EXPANSION = 2
    _COL_CATEGORY = 3
    _COL_DELETE = 4

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._setup_ui()
        self.load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        add_group = QGroupBox("Add a snippet (spoken trigger \u2192 inserted text)")
        add_layout = QVBoxLayout(add_group)

        row1 = QHBoxLayout()
        self._trigger_edit = QLineEdit()
        self._trigger_edit.setPlaceholderText("Trigger (e.g. my github)")
        self._trigger_edit.setAccessibleName("Snippet trigger")
        row1.addWidget(self._trigger_edit)

        self._category_edit = QLineEdit()
        self._category_edit.setPlaceholderText("Category (optional)")
        self._category_edit.setAccessibleName("Snippet category")
        row1.addWidget(self._category_edit)
        add_layout.addLayout(row1)

        self._expansion_edit = QPlainTextEdit()
        self._expansion_edit.setPlaceholderText(
            "Expansion text (inserted literally; may be multiline). "
            "Never executed."
        )
        self._expansion_edit.setAccessibleName("Snippet expansion")
        self._expansion_edit.setFixedHeight(72)
        add_layout.addWidget(self._expansion_edit)

        add_btn = QPushButton("Add snippet")
        add_btn.setAccessibleName("Add snippet")
        add_btn.clicked.connect(self._add_entry)
        add_layout.addWidget(add_btn)

        layout.addWidget(add_group)

        list_group = QGroupBox("Snippets")
        list_layout = QVBoxLayout(list_group)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["On", "Trigger", "Expansion", "Category", ""]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(self._COL_ENABLED, QHeaderView.Fixed)
        header.setSectionResizeMode(self._COL_TRIGGER, QHeaderView.Stretch)
        header.setSectionResizeMode(self._COL_EXPANSION, QHeaderView.Stretch)
        header.setSectionResizeMode(self._COL_CATEGORY, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self._COL_DELETE, QHeaderView.Fixed)
        self._table.setColumnWidth(self._COL_ENABLED, 36)
        self._table.setColumnWidth(self._COL_DELETE, 40)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self._table.itemChanged.connect(self._on_item_changed)
        list_layout.addWidget(self._table)

        self._conflict_label = QLabel("")
        self._conflict_label.setWordWrap(True)
        self._conflict_label.setAccessibleName("Snippet conflicts")
        self._conflict_label.setStyleSheet("color: #b9770e; font-size: 11px;")
        list_layout.addWidget(self._conflict_label)

        note = QLabel(
            "A snippet fires when you say its trigger as the whole phrase. The "
            "expansion is inserted as plain text and is never run as a command. "
            "Stored locally; never sent anywhere."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        list_layout.addWidget(note)

        layout.addWidget(list_group)

    # --- rows -----------------------------------------------------------
    def _add_entry(self) -> None:
        trigger = self._trigger_edit.text().strip()
        expansion = self._expansion_edit.toPlainText()
        category = self._category_edit.text().strip()
        if not trigger or not expansion.strip():
            return
        self._add_table_row(
            Snippet(trigger=trigger, expansion=expansion, category=category)
        )
        self._trigger_edit.clear()
        self._expansion_edit.clear()
        self._category_edit.clear()
        self._trigger_edit.setFocus()
        self._refresh_conflicts()

    def _add_table_row(self, snippet: Snippet) -> None:
        self._table.blockSignals(True)
        row = self._table.rowCount()
        self._table.insertRow(row)

        container = QWidget()
        cl = QHBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setAlignment(Qt.AlignCenter)
        cb = QCheckBox()
        cb.setChecked(snippet.enabled)
        cb.setAccessibleName("Snippet enabled")
        cb.stateChanged.connect(self._refresh_conflicts)
        cl.addWidget(cb)
        self._table.setCellWidget(row, self._COL_ENABLED, container)

        trigger_item = QTableWidgetItem(snippet.trigger)
        self._table.setItem(row, self._COL_TRIGGER, trigger_item)
        # Show expansion single-line in the table (newlines shown as ⏎) but keep
        # the full text on the item for round-trip.
        display = snippet.expansion.replace("\n", " \u23ce ")
        expansion_item = QTableWidgetItem(display)
        expansion_item.setData(Qt.UserRole + 1, snippet.expansion)
        self._table.setItem(row, self._COL_EXPANSION, expansion_item)
        category_item = QTableWidgetItem(snippet.category)
        self._table.setItem(row, self._COL_CATEGORY, category_item)

        trigger_item.setData(
            Qt.UserRole,
            (snippet.created_at, snippet.usage_count, snippet.inline),
        )

        delete_btn = QPushButton("\U0001f5d1\ufe0f")
        delete_btn.setFixedWidth(36)
        delete_btn.setAccessibleName("Delete snippet")
        delete_btn.setStyleSheet("QPushButton { color: #e74c3c; border: none; }")
        delete_btn.clicked.connect(
            lambda checked, btn=delete_btn: self._delete_row(btn)
        )
        self._table.setCellWidget(row, self._COL_DELETE, delete_btn)
        self._table.blockSignals(False)

    def _delete_row(self, button: QPushButton) -> None:
        for r in range(self._table.rowCount()):
            if self._table.cellWidget(r, self._COL_DELETE) is button:
                self._table.removeRow(r)
                break
        self._refresh_conflicts()

    def _on_item_changed(self, _item) -> None:
        self._refresh_conflicts()

    # --- conflicts ------------------------------------------------------
    def _current_snippets(self) -> list:
        snippets = []
        for row in range(self._table.rowCount()):
            trigger_item = self._table.item(row, self._COL_TRIGGER)
            expansion_item = self._table.item(row, self._COL_EXPANSION)
            category_item = self._table.item(row, self._COL_CATEGORY)
            if trigger_item is None:
                continue
            container = self._table.cellWidget(row, self._COL_ENABLED)
            enabled = True
            if container is not None:
                cb = container.findChild(QCheckBox)
                if cb is not None:
                    enabled = cb.isChecked()
            created_at, usage, inline = ("", 0, False)
            data = trigger_item.data(Qt.UserRole)
            if isinstance(data, tuple) and len(data) == 3:
                created_at, usage, inline = data
            # Prefer the preserved full expansion text if present.
            expansion = ""
            if expansion_item is not None:
                full = expansion_item.data(Qt.UserRole + 1)
                expansion = full if isinstance(full, str) else expansion_item.text()
            snippets.append(
                Snippet(
                    trigger=trigger_item.text(),
                    expansion=expansion,
                    enabled=enabled,
                    category=category_item.text() if category_item else "",
                    inline=bool(inline),
                    created_at=created_at or "",
                    usage_count=int(usage or 0),
                )
            )
        return snippets

    def _refresh_conflicts(self) -> None:
        conflicts = detect_snippet_conflicts(self._current_snippets())
        if not conflicts.has_any:
            self._conflict_label.setText("")
            return
        self._conflict_label.setText(
            "Duplicate triggers (only one applies): "
            + ", ".join(f'"{d}"' for d in conflicts.duplicates)
        )

    # --- persistence ----------------------------------------------------
    def load_settings(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for snippet in snippets_from_any(self._settings.snippets):
            self._add_table_row(snippet)
        self._table.blockSignals(False)
        self._refresh_conflicts()

    def save_settings(self) -> None:
        snippets = self._current_snippets()
        self._settings.snippets = [s.to_dict() for s in snippets if s.is_valid()]
