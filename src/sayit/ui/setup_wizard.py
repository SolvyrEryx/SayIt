from typing import Optional

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from ..core.asr.models.registry import get_all_models_with_status, is_model_downloaded
from ..core.audio import AudioRecorder, MicrophoneTestController, MicTestResult
from ..core.settings import HotkeyConfig, Settings, get_settings
from .download_dialog import ModelDownloadThread


class WelcomePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Welcome to SayIt")
        self.setSubTitle("Hold a hotkey, speak, and your words are typed for you.")

        layout = QVBoxLayout(self)

        intro = QLabel(
            "SayIt lets you dictate text into any app. Hold your hotkey, speak "
            "naturally, release it, and the transcribed text is inserted at your "
            "cursor.\n\n"
            "This short setup will help you pick a microphone, test it, choose a "
            "hotkey, and set up a speech model."
        )
        intro.setWordWrap(True)
        intro.setAccessibleName("Introduction")
        layout.addWidget(intro)

        privacy = QLabel(
            "Privacy: Core dictation is designed to run locally on your computer "
            "using a local speech model. Optional AI cleanup using a cloud "
            "provider is available in Settings but is turned off by default; when "
            "you turn it on, your transcript text is sent to the provider you "
            "choose. Downloading a speech model uses the network. Transcript "
            "history is off by default."
        )
        privacy.setWordWrap(True)
        privacy.setAccessibleName("Privacy statement")
        privacy.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(privacy)

        layout.addStretch()


class MicrophonePage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Microphone")
        self.setSubTitle("Choose your microphone and test that it is working.")

        layout = QVBoxLayout(self)

        # Status uses a text prefix (not color alone) so it is accessible.
        # Created early because _populate_devices may write to it.
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setAccessibleName("Microphone test status")

        device_label = QLabel("Input Device:")
        layout.addWidget(device_label)

        self._device_combo = QComboBox()
        self._device_combo.setAccessibleName("Microphone input device")
        device_label.setBuddy(self._device_combo)
        self._populate_devices()
        self._device_combo.currentIndexChanged.connect(self._on_device_changed)
        layout.addWidget(self._device_combo)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh Devices")
        self._refresh_btn.setAccessibleName("Refresh microphone device list")
        self._refresh_btn.clicked.connect(self._refresh_devices)
        btn_row.addWidget(self._refresh_btn)

        self._test_btn = QPushButton("Test Microphone")
        self._test_btn.setAccessibleName("Test microphone")
        self._test_btn.clicked.connect(self._on_test_clicked)
        btn_row.addWidget(self._test_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._level_bar = QProgressBar()
        self._level_bar.setRange(0, 100)
        self._level_bar.setValue(0)
        self._level_bar.setTextVisible(False)
        self._level_bar.setAccessibleName("Microphone input level")
        self._level_bar.hide()
        layout.addWidget(self._level_bar)

        layout.addWidget(self._status_label)

        layout.addStretch()

        self._mic_test: Optional[MicrophoneTestController] = None

    def _populate_devices(self) -> None:
        self._device_combo.clear()
        self._device_combo.addItem("System Default", None)
        try:
            devices = AudioRecorder.list_devices()
        except Exception:
            devices = []
        for device in devices:
            self._device_combo.addItem(device.name, device.name)

        if self._device_combo.count() <= 1:
            self._status_label.setText(
                "No microphone detected. Connect one and press Refresh Devices."
            )

    def _refresh_devices(self) -> None:
        current = self._device_combo.currentData()
        self._populate_devices()
        if current:
            idx = self._device_combo.findData(current)
            if idx >= 0:
                self._device_combo.setCurrentIndex(idx)

    def _on_device_changed(self) -> None:
        # Reset the test state when the selected device changes.
        self._status_label.setText("")
        self._level_bar.hide()
        self._level_bar.setValue(0)

    def _on_test_clicked(self) -> None:
        if self._mic_test is not None and self._mic_test.is_running:
            return
        self._test_btn.setEnabled(False)
        self._status_label.setText("Testing… please speak.")
        self._level_bar.show()
        self._level_bar.setValue(0)

        self._mic_test = MicrophoneTestController(
            device=self._device_combo.currentData()
        )
        self._mic_test.level.connect(self._on_level)
        self._mic_test.finished.connect(self._on_test_finished)
        self._mic_test.start()

    def _on_level(self, level: float) -> None:
        self._level_bar.setValue(int(max(0.0, min(1.0, level)) * 100))

    def _on_test_finished(self, result: MicTestResult) -> None:
        self._level_bar.setValue(0)
        self._level_bar.hide()
        self._test_btn.setEnabled(True)
        prefix = "OK: " if result.is_success else "Problem: "
        self._status_label.setText(prefix + result.message)

    def cleanup(self) -> None:
        if self._mic_test is not None and self._mic_test.is_running:
            self._mic_test.cancel()

    def get_selected_device(self) -> Optional[str]:
        return self._device_combo.currentData()


class ModelSelectionPage(QWizardPage):
    """Model setup. Non-blocking: the wizard can be completed even if no model
    is installed yet. The page honestly reflects Ready / Not configured."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Speech Model")
        self.setSubTitle("A local model is needed to transcribe your speech.")

        layout = QVBoxLayout(self)

        model_label = QLabel("Model:")
        layout.addWidget(model_label)

        model_row = QHBoxLayout()
        self._model_combo = QComboBox()
        self._model_combo.setAccessibleName("Speech recognition model")
        model_label.setBuddy(self._model_combo)
        self._refresh_model_list()
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        model_row.addWidget(self._model_combo, 1)

        self._download_btn = QPushButton("Download")
        self._download_btn.setAccessibleName("Download selected model")
        self._download_btn.clicked.connect(self._on_download_clicked)
        model_row.addWidget(self._download_btn)
        layout.addLayout(model_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.hide()
        self._progress_bar.setAccessibleName("Model download progress")
        layout.addWidget(self._progress_bar)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.hide()
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self._cancel_btn)

        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        self._status_label.setAccessibleName("Model status")
        layout.addWidget(self._status_label)

        info = QLabel(
            "The recommended model offers good accuracy. Smaller models are "
            "faster but less accurate. You can finish setup without a model and "
            "install one later from Settings — dictation will be available once a "
            "model is installed."
        )
        info.setStyleSheet("color: gray; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()

        self._download_thread: Optional[ModelDownloadThread] = None
        self._update_status()

    def _refresh_model_list(self) -> None:
        self._model_combo.clear()
        for model, status in get_all_models_with_status():
            indicator = "(installed)" if status == "downloaded" else "(not installed)"
            self._model_combo.addItem(f"{model.name}  {indicator}", model.id)

    def _on_model_changed(self, index: int) -> None:
        self._update_status()

    def _update_status(self) -> None:
        model_id = self._model_combo.currentData()
        downloaded = is_model_downloaded(model_id) if model_id else False
        self._download_btn.setEnabled(not downloaded)
        if downloaded:
            self._status_label.setText("Ready: this model is installed.")
        else:
            self._status_label.setText(
                "Not installed: download this model, or finish setup and install "
                "it later."
            )

    def _on_download_clicked(self) -> None:
        model_id = self._model_combo.currentData()
        if not model_id:
            return
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._cancel_btn.show()
        self._download_btn.setEnabled(False)
        self._model_combo.setEnabled(False)
        self._status_label.setText("Downloading…")

        self._download_thread = ModelDownloadThread(model_id)
        self._download_thread.progress.connect(self._on_progress)
        self._download_thread.status_changed.connect(self._status_label.setText)
        self._download_thread.finished.connect(self._on_download_finished)
        self._download_thread.error.connect(self._on_download_error)
        self._download_thread.start()

    def _on_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setValue(int((downloaded / total) * 100))

    def _on_download_error(self, message: str) -> None:
        # Honest failure state with recovery guidance.
        self._status_label.setText(
            f"Download failed: {message}. Check your connection and try again, "
            "or finish setup and install later."
        )

    def _on_download_finished(self, success: bool) -> None:
        self._progress_bar.hide()
        self._cancel_btn.hide()
        self._model_combo.setEnabled(True)
        self._download_thread = None
        if success:
            self._refresh_model_list()
        self._update_status()
        self.completeChanged.emit()

    def _on_cancel_clicked(self) -> None:
        if self._download_thread:
            self._download_thread.cancel()
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText("Cancelling…")

    def isComplete(self) -> bool:
        # Non-blocking: always allow proceeding. Model readiness is reported
        # honestly on this page and on the completion page.
        return True

    def is_model_ready(self) -> bool:
        model_id = self._model_combo.currentData()
        return is_model_downloaded(model_id) if model_id else False

    def get_selected_model(self) -> str:
        return self._model_combo.currentData() or ""


class HotkeyPage(QWizardPage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Push-to-Talk Hotkey")
        self.setSubTitle("Choose the key combination to hold while speaking.")

        layout = QVBoxLayout(self)

        prompt = QLabel("Click the field and press your desired hotkey:")
        layout.addWidget(prompt)

        self._hotkey_edit = QKeySequenceEdit()
        self._hotkey_edit.setKeySequence(QKeySequence("Ctrl+Space"))
        self._hotkey_edit.setAccessibleName("Push-to-talk hotkey")
        prompt.setBuddy(self._hotkey_edit)
        layout.addWidget(self._hotkey_edit)

        instructions = QLabel(
            "Recommended: Ctrl + Space.\n\n"
            "Hold this combination to record, release to transcribe. Press Esc "
            "while dictating to cancel.\n\n"
            "Note: a few applications may block global shortcuts; if the hotkey "
            "doesn't work in one app, try another."
        )
        instructions.setStyleSheet("color: gray; font-size: 11px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        layout.addStretch()

    def get_hotkey_config(self) -> HotkeyConfig:
        key_sequence = self._hotkey_edit.keySequence()
        if key_sequence.isEmpty():
            return HotkeyConfig()

        seq_str = key_sequence.toString()
        if not seq_str:
            return HotkeyConfig()

        parts = seq_str.split("+")
        if not parts:
            return HotkeyConfig()

        modifiers = []
        key = parts[-1].lower()
        for part in parts[:-1]:
            mod = part.lower()
            if mod in ("ctrl", "control"):
                modifiers.append("ctrl")
            elif mod in ("alt", "option"):
                modifiers.append("alt")
            elif mod in ("shift",):
                modifiers.append("shift")
            elif mod in ("meta", "cmd", "command", "win"):
                modifiers.append("cmd")

        if not modifiers:
            # A modifier-less push-to-talk key is prone to accidental triggers;
            # fall back to the safe default rather than persisting a risky combo.
            return HotkeyConfig()

        return HotkeyConfig(modifiers=modifiers, key=key)


class TryItPage(QWizardPage):
    """Honest 'try your first dictation' step.

    This page never fabricates a transcript. When a model is installed it tells
    the user how to try dictation after setup; when no model is installed it
    explains what remains. The actual model-backed transcription runs in the
    main app, not here, so this page cannot show a fake success.
    """

    def __init__(self, model_page: ModelSelectionPage, hotkey_page: HotkeyPage, parent=None):
        super().__init__(parent)
        self._model_page = model_page
        self._hotkey_page = hotkey_page
        self.setTitle("Try Your First Dictation")
        self.setSubTitle("How to use SayIt once setup is complete.")

        layout = QVBoxLayout(self)
        self._body = QLabel("")
        self._body.setWordWrap(True)
        self._body.setAccessibleName("Dictation instructions")
        layout.addWidget(self._body)
        layout.addStretch()

    def initializePage(self) -> None:
        hotkey = self._hotkey_page.get_hotkey_config().to_display_string()
        if self._model_page.is_model_ready():
            self._body.setText(
                f"You're ready to dictate.\n\n"
                f"1. Hold {hotkey}.\n"
                f"2. Speak a short sentence.\n"
                f"3. Release the keys — SayIt transcribes and types the text at "
                f"your cursor.\n\n"
                f"Press Esc while dictating to cancel. Give it a try in any text "
                f"field after you finish setup."
            )
        else:
            self._body.setText(
                "A speech model isn't installed yet, so dictation can't run "
                "right now.\n\n"
                "You can finish setup now and install a model later from "
                "Settings → model. Once a model is installed, hold your hotkey "
                "and speak to dictate.\n\n"
                "SayIt will not show a transcript until a real model is "
                "installed — nothing here is simulated."
            )


class CompletePage(QWizardPage):
    def __init__(self, model_page: ModelSelectionPage, parent=None):
        super().__init__(parent)
        self._model_page = model_page
        self.setTitle("Setup Complete")
        self.setSubTitle("Here's what's ready and what's left.")

        layout = QVBoxLayout(self)
        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setAccessibleName("Setup summary")
        layout.addWidget(self._summary)
        layout.addStretch()

    def initializePage(self) -> None:
        ready = [
            "• Microphone selected",
            "• Hotkey configured",
        ]
        remaining = []
        if self._model_page.is_model_ready():
            ready.append("• Local speech model installed")
        else:
            remaining.append("• Install a local speech model (Settings → model)")

        text = "Ready:\n" + "\n".join(ready)
        if remaining:
            text += "\n\nRemaining before you can dictate:\n" + "\n".join(remaining)
            text += (
                "\n\nSayIt will run in the tray. Open Settings to install a model "
                "when you're ready."
            )
        else:
            text += (
                "\n\nSayIt is ready. Look for the icon in your system tray; "
                "right-click it for Settings or Quit."
            )
        self._summary.setText(text)


class SetupWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SayIt Setup")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(520, 420)
        # Keyboard-friendly navigation with explicit, named buttons.
        self.setOption(QWizard.NoBackButtonOnStartPage, True)

        self._settings = get_settings()

        self.addPage(WelcomePage())

        self._mic_page = MicrophonePage()
        self.addPage(self._mic_page)

        self._model_page = ModelSelectionPage()
        self.addPage(self._model_page)

        self._hotkey_page = HotkeyPage()
        self.addPage(self._hotkey_page)

        self.addPage(TryItPage(self._model_page, self._hotkey_page))
        self.addPage(CompletePage(self._model_page))

    def accept(self) -> None:
        # Release any in-progress mic test before closing.
        self._mic_page.cleanup()

        self._settings.input_device = self._mic_page.get_selected_device()
        selected_model = self._model_page.get_selected_model()
        if selected_model:
            self._settings.model_id = selected_model
        self._settings.hotkey = self._hotkey_page.get_hotkey_config()
        self._settings.first_run_complete = True
        self._settings.save()

        super().accept()

    def reject(self) -> None:
        self._mic_page.cleanup()
        super().reject()
