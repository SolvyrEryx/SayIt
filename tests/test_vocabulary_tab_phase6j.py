"""Phase 6J UI + pipeline-integration tests."""

import numpy as np
from unittest.mock import MagicMock

from src.sayit.core.settings import Settings
from src.sayit.ui.tabs.vocabulary_tab import VocabularyTab


class TestVocabularyTabUI:
    def test_add_and_save(self, qtbot):
        s = Settings()
        tab = VocabularyTab(s)
        qtbot.addWidget(tab)
        tab._spoken_edit.setText("next js")
        tab._written_edit.setText("Next.js")
        tab._category_edit.setText("frameworks")
        tab._add_entry()
        tab.save_settings()
        assert len(s.custom_vocabulary) == 1
        assert s.custom_vocabulary[0]["spoken"] == "next js"
        assert s.custom_vocabulary[0]["written"] == "Next.js"
        assert s.custom_vocabulary[0]["category"] == "frameworks"
        assert s.custom_vocabulary[0]["enabled"] is True

    def test_load_existing(self, qtbot):
        s = Settings()
        s.custom_vocabulary = [
            {"spoken": "open ai", "written": "OpenAI", "enabled": True},
            {"spoken": "fast api", "written": "FastAPI", "enabled": False},
        ]
        tab = VocabularyTab(s)
        qtbot.addWidget(tab)
        assert tab._table.rowCount() == 2

    def test_disable_entry_excluded_from_legacy(self, qtbot):
        s = Settings()
        s.custom_vocabulary = [
            {"spoken": "foo", "written": "F", "enabled": False},
        ]
        tab = VocabularyTab(s)
        qtbot.addWidget(tab)
        tab.save_settings()
        # Disabled entry retained in custom_vocabulary but NOT in legacy list.
        assert s.custom_vocabulary[0]["enabled"] is False
        assert ("foo", "F") not in s.vocabulary_replacements

    def test_migration_from_legacy_on_load(self, qtbot):
        s = Settings()
        s.vocabulary_replacements = [("git hub", "GitHub")]
        tab = VocabularyTab(s)
        qtbot.addWidget(tab)
        assert tab._table.rowCount() == 1
        tab.save_settings()
        assert s.custom_vocabulary[0]["spoken"] == "git hub"

    def test_conflict_label_shows_overlap(self, qtbot):
        s = Settings()
        s.custom_vocabulary = [
            {"spoken": "new", "written": "N", "enabled": True},
            {"spoken": "new york", "written": "NYC", "enabled": True},
        ]
        tab = VocabularyTab(s)
        qtbot.addWidget(tab)
        assert "Overlapping" in tab._conflict_label.text()

    def test_no_conflict_label_when_clean(self, qtbot):
        s = Settings()
        s.custom_vocabulary = [
            {"spoken": "alpha", "written": "A", "enabled": True},
        ]
        tab = VocabularyTab(s)
        qtbot.addWidget(tab)
        assert tab._conflict_label.text() == ""


class TestWorkerPipelineOrder:
    """Phase 6J vocabulary must run AFTER Phase 6G/6I correction, same position
    as the legacy vocabulary step, and BEFORE optional LLM."""

    def _worker(self, raw, custom_vocab):
        from src.sayit.core.asr.transcription_worker import (
            TranscriptionWorkerThread,
        )

        transcriber = MagicMock()
        transcriber.transcribe_chunked.return_value = raw
        transcriber.last_chunk_count = 1
        transcriber.last_invocation_count = 1
        return TranscriptionWorkerThread(
            transcriber=transcriber,
            audio_data=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            vocabulary_replacements=[],
            llm_processor=None,
            enhancement=None,
            custom_vocabulary=custom_vocab,
        )

    def test_vocab_runs_after_correction(self, qtbot):
        # ASR says "git hub" -> Phase 6G makes "GitHub" -> vocab maps "GitHub"
        # to "GH". Proves vocab sees the corrected text (runs after 6G).
        worker = self._worker(
            "push to git hub",
            [{"spoken": "GitHub", "written": "GH", "enabled": True}],
        )
        finished = []
        worker.finished.connect(lambda *a: finished.append(a))
        worker.run()
        assert len(finished) == 1
        final_text = finished[0][0]
        assert final_text == "push to GH"

    def test_phase6g_6i_preserved_without_custom_vocab(self, qtbot):
        # No custom vocabulary -> Phase 6G/6I still applied via correction.
        worker = self._worker("visit example dot com", None)
        finished = []
        worker.finished.connect(lambda *a: finished.append(a))
        worker.run()
        assert finished[0][0] == "visit example.com"
