from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.settings import get_settings
from .. import __display_name__
from .tabs import (
    ConfigurationTab,
    EnhancementsTab,
    HistoryTab,
    HomeTab,
    PrivacyTab,
    SnippetsTab,
    VocabularyTab,
)


class SettingsWindow(QDialog):

    settings_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setWindowTitle(f"{__display_name__} Settings")
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)

        self._settings = get_settings()
        self._loading_overlay: Optional[QFrame] = None

        self._setup_ui()
        self._load_settings()

    def set_loading(self, loading: bool) -> None:
        if loading:
            if self._loading_overlay is None:
                self._loading_overlay = self._create_loading_overlay()
            self._loading_overlay.show()
            self._loading_overlay.raise_()
        else:
            if self._loading_overlay is not None:
                self._loading_overlay.hide()

    def _create_loading_overlay(self) -> QFrame:
        overlay = QFrame(self)
        overlay.setStyleSheet(
            """
            QFrame {
                background-color: rgba(0, 0, 0, 150);
                border-radius: 8px;
            }
            QLabel {
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
        """
        )

        layout = QVBoxLayout(overlay)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel("Loading model...")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        overlay.setGeometry(self.rect())

        return overlay

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._loading_overlay is not None:
            self._loading_overlay.setGeometry(self.rect())

    def _setup_ui(self) -> None:
        self.setObjectName("SayItMainWindow")
        layout = QVBoxLayout(self)

        # Header: SayIt mark + wordmark.
        from PySide6.QtGui import QPixmap

        from .theme import sayit_mark

        header = QHBoxLayout()
        header.setContentsMargins(4, 2, 4, 8)
        logo = QLabel()
        pm: QPixmap = sayit_mark(28)
        logo.setPixmap(pm)
        logo.setAccessibleName(f"{__display_name__} logo")
        wordmark = QLabel(__display_name__)
        wordmark.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(logo)
        header.addSpacing(8)
        header.addWidget(wordmark)
        header.addStretch()
        layout.addLayout(header)

        content_layout = QHBoxLayout()
        self._nav_list = QListWidget()
        self._nav_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav_list.setSpacing(2)
        self._nav_list.setFixedWidth(170)
        self._nav_list.setFrameShape(QFrame.NoFrame)

        self._stacked = QStackedWidget()

        self._home_tab = HomeTab(self)
        self._enhancements_tab = EnhancementsTab(self._settings, self)
        self._vocabulary_tab = VocabularyTab(self._settings, self)
        self._snippets_tab = SnippetsTab(self._settings, self)
        self._configuration_tab = ConfigurationTab(self._settings, self)
        self._history_tab = HistoryTab(self)
        self._privacy_tab = PrivacyTab(self._settings, self)
        self._configuration_tab.reset_requested.connect(self._reset_settings)

        pages = [
            ("Home", self._home_tab),
            ("Mode", self._enhancements_tab),
            ("Vocabulary", self._vocabulary_tab),
            ("Snippets", self._snippets_tab),
            ("Configuration", self._configuration_tab),
            ("History", self._history_tab),
            ("Privacy & Data", self._privacy_tab),
        ]
        for title, page in pages:
            self._nav_list.addItem(title)
            self._stacked.addWidget(page)

        self._nav_list.currentRowChanged.connect(self._on_nav_changed)
        self._nav_list.setCurrentRow(0)

        content_layout.addWidget(self._nav_list)
        content_layout.addWidget(self._stacked, 1)
        layout.addLayout(content_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._save_settings)
        layout.addWidget(buttons)

    def _on_nav_changed(self, index: int) -> None:
        # Reuse the existing stacked widgets; only the visible index changes.
        # The incoming page is faded in for a subtle sense of continuity. Purely
        # presentational — no app state is involved.
        self._stacked.setCurrentIndex(index)
        from .motion import NORMAL, fade_in

        current = self._stacked.currentWidget()
        if current is not None:
            fade_in(current, NORMAL)

    def _load_settings(self) -> None:
        self._configuration_tab.load_settings()
        self._enhancements_tab.load_settings()
        self._vocabulary_tab.load_settings()
        self._snippets_tab.load_settings()
        self._privacy_tab.load_settings()

    def _save_settings(self) -> None:
        if not self._configuration_tab.save_settings():
            return

        self._enhancements_tab.save_settings()
        self._vocabulary_tab.save_settings()
        self._snippets_tab.save_settings()
        self._privacy_tab.save_settings()

        self._settings.save()
        self.settings_changed.emit()

    def _save_and_close(self) -> None:
        self._save_settings()
        self.accept()

    def reject(self) -> None:
        self._load_settings()
        super().reject()

    def refresh_asr_model_list(self) -> None:
        self._configuration_tab.refresh_model_list()

    @property
    def home_tab(self):
        """The Home tab, for live workflow-state reflection by the app."""
        return self._home_tab

    def _reset_settings(self) -> None:
        """Reset, persist, and immediately apply all settings."""
        self._settings.reset_to_defaults()
        self._settings.save()
        self._load_settings()
        self.settings_changed.emit()
