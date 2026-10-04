"""Privacy & Data settings tab.

Exposes the real privacy-relevant controls and state:
- Save transcript history (bound to settings.history_enabled; OFF by default).
- Cloud enhancement status + provider disclosure (read-only; derived from the
  existing enhancement settings — changed on the Mode tab).
- A truthful explanation of local processing vs. network activity.
- Clear Data (reuses the existing data_manager; describes exactly what it removes).

This tab does not introduce a second source of truth: the history toggle maps
directly to settings.history_enabled, and the cloud status is derived from the
existing enhancement/provider settings.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.settings import Settings
from ...core.settings.data_manager import (
    get_all_data_paths,
    schedule_cleanup_and_exit,
)
from ...core.transcript_processor import PROVIDERS

# Providers that run locally (no transcript text leaves the device). Everything
# else in PROVIDERS is treated as a remote/cloud provider for disclosure.
_LOCAL_PROVIDERS = {"ollama"}


def describe_enhancement_status(settings: Settings) -> str:
    """Return a human-readable, accurate description of enhancement state.

    - No active enhancement -> Off.
    - Active + local provider -> Local.
    - Active + remote provider -> Cloud (provider name).
    """
    if not settings.active_enhancement_id:
        return "Off"

    provider_id = settings.llm_provider
    display_name = PROVIDERS.get(provider_id, (provider_id, None, None))[0]

    if provider_id in _LOCAL_PROVIDERS:
        return f"On — Local ({display_name})"
    return f"On — Cloud ({display_name})"


def enhancement_sends_transcript_to_cloud(settings: Settings) -> bool:
    """True only when an enhancement is active AND the provider is remote."""
    if not settings.active_enhancement_id:
        return False
    return settings.llm_provider not in _LOCAL_PROVIDERS


class PrivacyTab(QWidget):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Privacy & Data")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        title.setAccessibleName("Privacy and Data")
        layout.addWidget(title)

        self._sections = [
            self._dictation_group(),
            self._enhancement_group(),
            self._history_group(),
            self._clear_data_group(),
        ]
        for section in self._sections:
            layout.addWidget(section)
        layout.addStretch()

    # --- Dictation processing -------------------------------------------
    def _dictation_group(self) -> QWidget:
        group = QGroupBox("Dictation processing")
        v = QVBoxLayout(group)
        text = QLabel(
            "Core dictation runs locally using the speech model installed on "
            "this computer. Network activity can still occur: downloading a "
            "speech model requires the internet, and optional cloud enhancement "
            "(below) sends transcript text to a provider when you enable it."
        )
        text.setWordWrap(True)
        text.setAccessibleName("Dictation processing explanation")
        v.addWidget(text)
        return group

    # --- Cloud enhancement disclosure -----------------------------------
    def _enhancement_group(self) -> QWidget:
        group = QGroupBox("Cloud enhancement")
        v = QVBoxLayout(group)

        self._enhancement_status_label = QLabel()
        self._enhancement_status_label.setAccessibleName("Cloud enhancement status")
        v.addWidget(self._enhancement_status_label)

        self._enhancement_detail_label = QLabel()
        self._enhancement_detail_label.setWordWrap(True)
        self._enhancement_detail_label.setStyleSheet("color: #888; font-size: 11px;")
        self._enhancement_detail_label.setAccessibleName(
            "Cloud enhancement explanation"
        )
        v.addWidget(self._enhancement_detail_label)

        hint = QLabel("Change this in the Mode tab.")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        v.addWidget(hint)
        return group

    # --- Transcript history ---------------------------------------------
    def _history_group(self) -> QWidget:
        group = QGroupBox("Transcript history")
        v = QVBoxLayout(group)

        from ..widgets import AnimatedToggle

        row = QHBoxLayout()
        # Attribute name kept as _history_checkbox so load/save (which call
        # isChecked()/setChecked()) work unchanged with the toggle.
        self._history_checkbox = AnimatedToggle()
        self._history_checkbox.setAccessibleName("Save transcript history")
        toggle_label = QLabel("Save transcript history")
        toggle_label.setAccessibleName("Save transcript history label")
        row.addWidget(self._history_checkbox)
        row.addSpacing(8)
        row.addWidget(toggle_label)
        row.addStretch()
        v.addLayout(row)

        desc = QLabel(
            "Save completed transcripts to local history for later review. Off by "
            "default. Turning this off stops saving new transcripts; it does not "
            "delete transcripts already saved — use Clear Data for that. "
            "Dictated text remains recoverable right after dictation even when "
            "history is off."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        desc.setAccessibleName("Transcript history explanation")
        v.addWidget(desc)
        return group

    # --- Clear data ------------------------------------------------------
    def _clear_data_group(self) -> QWidget:
        group = QGroupBox("Clear data")
        v = QVBoxLayout(group)

        desc = QLabel(
            "Permanently delete locally stored SayIt data: your settings, "
            "transcript history, logs, and downloaded speech models. SayIt will "
            "close and you will need to set it up again (including re-downloading "
            "a model). This cannot be undone."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        desc.setAccessibleName("Clear data explanation")
        v.addWidget(desc)

        self._clear_data_btn = QPushButton("Clear Data…")
        self._clear_data_btn.setAccessibleName("Clear data")
        self._clear_data_btn.clicked.connect(self._on_clear_data_clicked)
        v.addWidget(self._clear_data_btn)
        return group

    def _on_clear_data_clicked(self) -> None:
        paths = get_all_data_paths()
        if not paths:
            QMessageBox.information(
                self,
                "Nothing to Remove",
                "No SayIt data was found on this computer.",
            )
            return

        paths_list = "\n".join(f"  • {p}" for p in paths)
        reply = QMessageBox.warning(
            self,
            "Clear all SayIt data?",
            "This will permanently delete the following and cannot be undone:\n\n"
            f"{paths_list}\n\n"
            "SayIt will close immediately and the data will be removed in the "
            "background. You will need to set SayIt up again, including "
            "re-downloading a speech model.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return

        schedule_cleanup_and_exit()
        QApplication.quit()

    # --- settings load/save ---------------------------------------------
    def load_settings(self) -> None:
        self._history_checkbox.setChecked(self._settings.history_enabled)
        self._refresh_enhancement_status()

    def _refresh_enhancement_status(self) -> None:
        status = describe_enhancement_status(self._settings)
        self._enhancement_status_label.setText(f"Status: {status}")

        if enhancement_sends_transcript_to_cloud(self._settings):
            self._enhancement_detail_label.setText(
                "Transcript text is sent to this cloud provider when a "
                "transcription is enhanced."
            )
        elif self._settings.active_enhancement_id:
            self._enhancement_detail_label.setText(
                "Enhancement runs locally; transcript text is not sent to a "
                "cloud provider."
            )
        else:
            self._enhancement_detail_label.setText(
                "No enhancement is active. Transcript text is not sent anywhere."
            )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Reflect any enhancement changes made on the Mode tab.
        self._refresh_enhancement_status()
        # Subtle staggered entrance for the first-level sections.
        from ..motion import stagger

        stagger(self._sections)

    def save_settings(self) -> None:
        self._settings.history_enabled = self._history_checkbox.isChecked()
