from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.settings import Settings
from ...core.transcript_processor import (
    VocabularyEntry,
    detect_conflicts,
    entries_from_any,
)


class VocabularyTab(QWidget):
    """Phase 6J user-controlled custom vocabulary editor.

    Spoken-form -> written-form mappings the user explicitly manages. Supports
    add / edit / delete / enable-disable / category, plus a deterministic
    conflict summary (duplicate and overlapping spoken forms). Nothing is learned
    automatically; every entry is user-created. Stored locally in settings.
    """

    # Column indices.
    _COL_ENABLED = 0
    _COL_SPOKEN = 1
    _COL_WRITTEN = 2
    _COL_CATEGORY = 3
    _COL_DELETE = 4

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._setup_ui()
        self.load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        add_group = QGroupBox("Add a vocabulary entry (spoken \u2192 written)")
        add_layout = QHBoxLayout(add_group)

        self._spoken_edit = QLineEdit()
        self._spoken_edit.setPlaceholderText("Spoken form (e.g. next js)")
        self._spoken_edit.setAccessibleName("Spoken form")
        add_layout.addWidget(self._spoken_edit)

        self._written_edit = QLineEdit()
        self._written_edit.setPlaceholderText("Written form (e.g. Next.js)")
        self._written_edit.setAccessibleName("Written form")
        add_layout.addWidget(self._written_edit)

        self._category_edit = QLineEdit()
        self._category_edit.setPlaceholderText("Category (optional)")
        self._category_edit.setAccessibleName("Category")
        add_layout.addWidget(self._category_edit)

        add_btn = QPushButton("Add")
        add_btn.setAccessibleName("Add vocabulary entry")
        add_btn.clicked.connect(self._add_entry)
        add_layout.addWidget(add_btn)

        self._spoken_edit.returnPressed.connect(self._add_entry)
        self._written_edit.returnPressed.connect(self._add_entry)

        layout.addWidget(add_group)

        list_group = QGroupBox("Vocabulary")
        list_layout = QVBoxLayout(list_group)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["On", "Spoken", "Written", "Category", ""]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(self._COL_ENABLED, QHeaderView.Fixed)
        header.setSectionResizeMode(self._COL_SPOKEN, QHeaderView.Stretch)
        header.setSectionResizeMode(self._COL_WRITTEN, QHeaderView.Stretch)
        header.setSectionResizeMode(self._COL_CATEGORY, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self._COL_DELETE, QHeaderView.Fixed)
        self._table.setColumnWidth(self._COL_ENABLED, 36)
        self._table.setColumnWidth(self._COL_DELETE, 40)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Spoken / Written / Category are editable in place (edit support).
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self._table.itemChanged.connect(self._on_item_changed)

        list_layout.addWidget(self._table)

        self._conflict_label = QLabel("")
        self._conflict_label.setWordWrap(True)
        self._conflict_label.setAccessibleName("Vocabulary conflicts")
        self._conflict_label.setStyleSheet("color: #b9770e; font-size: 11px;")
        list_layout.addWidget(self._conflict_label)

        note = QLabel(
            "Matching is case-insensitive and whole-word; multi-word spoken "
            "forms are supported and longer forms take precedence. Stored "
            "locally; never sent anywhere."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        list_layout.addWidget(note)

        layout.addWidget(list_group)

    # --- row management -------------------------------------------------
    def _add_entry(self) -> None:
        spoken = self._spoken_edit.text().strip()
        written = self._written_edit.text().strip()
        category = self._category_edit.text().strip()
        if not spoken:
            return
        self._add_table_row(
            VocabularyEntry(spoken=spoken, written=written, category=category)
        )
        self._spoken_edit.clear()
        self._written_edit.clear()
        self._category_edit.clear()
        self._spoken_edit.setFocus()
        self._refresh_conflicts()

    def _add_table_row(self, entry: VocabularyEntry) -> None:
        self._table.blockSignals(True)
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Enabled checkbox (centered in a container).
        container = QWidget()
        cl = QHBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setAlignment(Qt.AlignCenter)
        cb = QCheckBox()
        cb.setChecked(entry.enabled)
        cb.setAccessibleName("Entry enabled")
        cb.stateChanged.connect(self._refresh_conflicts)
        cl.addWidget(cb)
        self._table.setCellWidget(row, self._COL_ENABLED, container)

        spoken_item = QTableWidgetItem(entry.spoken)
        self._table.setItem(row, self._COL_SPOKEN, spoken_item)
        written_item = QTableWidgetItem(entry.written)
        self._table.setItem(row, self._COL_WRITTEN, written_item)
        category_item = QTableWidgetItem(entry.category)
        self._table.setItem(row, self._COL_CATEGORY, category_item)

        # Preserve created_at / usage_count on the spoken item for round-trip.
        spoken_item.setData(Qt.UserRole, (entry.created_at, entry.usage_count))

        delete_btn = QPushButton("\U0001f5d1\ufe0f")
        delete_btn.setFixedWidth(36)
        delete_btn.setAccessibleName("Delete entry")
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
    def _current_entries(self) -> list:
        entries = []
        for row in range(self._table.rowCount()):
            spoken_item = self._table.item(row, self._COL_SPOKEN)
            written_item = self._table.item(row, self._COL_WRITTEN)
            category_item = self._table.item(row, self._COL_CATEGORY)
            if spoken_item is None:
                continue
            container = self._table.cellWidget(row, self._COL_ENABLED)
            enabled = True
            if container is not None:
                cb = container.findChild(QCheckBox)
                if cb is not None:
                    enabled = cb.isChecked()
            created_at, usage = ("", 0)
            data = spoken_item.data(Qt.UserRole)
            if isinstance(data, tuple) and len(data) == 2:
                created_at, usage = data
            entries.append(
                VocabularyEntry(
                    spoken=spoken_item.text(),
                    written=written_item.text() if written_item else "",
                    enabled=enabled,
                    category=category_item.text() if category_item else "",
                    created_at=created_at or "",
                    usage_count=int(usage or 0),
                )
            )
        return entries

    def _refresh_conflicts(self) -> None:
        entries = self._current_entries()
        conflicts = detect_conflicts(entries)
        if not conflicts.has_any:
            self._conflict_label.setText("")
            return
        parts = []
        if conflicts.duplicates:
            parts.append(
                "Duplicate spoken forms (only one applies): "
                + ", ".join(f'"{d}"' for d in conflicts.duplicates)
            )
        if conflicts.overlaps:
            parts.append(
                "Overlapping forms (longer wins): "
                + ", ".join(f'"{a}" \u2282 "{b}"' for a, b in conflicts.overlaps)
            )
        self._conflict_label.setText("  \u2022  ".join(parts))

    # --- persistence ----------------------------------------------------
    def load_settings(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        entries = entries_from_any(
            self._settings.custom_vocabulary,
            self._settings.vocabulary_replacements,
        )
        for entry in entries:
            self._add_table_row(entry)
        self._table.blockSignals(False)
        self._refresh_conflicts()

    def save_settings(self) -> None:
        entries = self._current_entries()
        self._settings.custom_vocabulary = [
            e.to_dict() for e in entries if e.is_valid()
        ]
        # Keep the legacy list in sync (enabled entries only) so any legacy
        # consumer still works and old settings files remain readable.
        self._settings.vocabulary_replacements = [
            (e.spoken, e.written) for e in entries if e.is_valid() and e.enabled
        ]
