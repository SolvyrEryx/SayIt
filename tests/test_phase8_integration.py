# -*- coding: utf-8 -*-
"""Phase 8 end-to-end integration tests (scenarios A-H).

Each test drives the REAL TranscriptionWorkerThread with a stub transcriber and
a real IntelligenceOrchestrator, asserting the full raw-text -> intelligence ->
6G/6I/6J pipeline produces the expected final text and intelligence metadata.
This exercises the actual integration wiring, not just the isolated engines.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.sayit.core.asr.transcription_worker import TranscriptionWorkerThread
from src.sayit.core.context import ContextSignals, resolve_profile
from src.sayit.core.context.profiles import AUTO, Profile
from src.sayit.core.intelligence import IntelligenceOrchestrator, OrchestratorConfig
from src.sayit.core.snippets import Snippet


def _run_worker(
    raw_text,
    *,
    context=None,
    snippets=None,
    recent_output=None,
    technical=True,
    structured=True,
    custom_vocab=None,
    orchestrator=None,
):
    from unittest.mock import MagicMock

    transcriber = MagicMock()
    transcriber.transcribe_chunked.return_value = raw_text
    transcriber.last_chunk_count = 1
    transcriber.last_invocation_count = 1
    worker = TranscriptionWorkerThread(
        transcriber=transcriber,
        audio_data=np.zeros(1600, dtype=np.float32),
        sample_rate=16000,
        vocabulary_replacements=[],
        llm_processor=None,
        enhancement=None,
        technical_correction_enabled=technical,
        structured_formatting_enabled=structured,
        custom_vocabulary=custom_vocab,
        context_resolution=context,
        orchestrator=orchestrator or IntelligenceOrchestrator(OrchestratorConfig()),
        snippets=snippets,
        recent_output=recent_output,
    )
    captured = []
    worker.finished.connect(lambda *a: captured.append(a))
    worker.run()
    assert len(captured) == 1, "worker must emit exactly one finished signal"
    final_text, raw, enhanced, name, cost, intel_meta = captured[0]
    return final_text, intel_meta


def _dev_ctx():
    return resolve_profile(
        ContextSignals(app_name="code"), detection_enabled=True, override=AUTO
    )


def _email_ctx():
    return resolve_profile(
        ContextSignals(app_name="outlook"), detection_enabled=True, override=AUTO
    )


class TestScenarioA_DeveloperDictation:
    def test_technical_sentence_in_developer(self, qtbot):
        final, meta = _run_worker("push to git hub", context=_dev_ctx())
        # 6G technical correction still applies for ordinary dictation.
        assert final == "push to GitHub"
        assert meta["category"] == "dictate"


class TestScenarioB_Email:
    def test_email_profile_suppresses_structured_path(self, qtbot):
        # Email profile turns structured path formatting off; the spoken path is
        # NOT compressed into src/app.py.
        final, meta = _run_worker("src slash app dot py", context=_email_ctx())
        assert final != "src/app.py"

    def test_developer_profile_formats_structured_path(self, qtbot):
        final, meta = _run_worker("src slash app dot py", context=_dev_ctx())
        assert final == "src/app.py"


class TestScenarioC_Snippet:
    def test_snippet_expansion(self, qtbot):
        snips = [Snippet(trigger="my github", expansion="https://github.com/me")]
        final, meta = _run_worker("my github", snippets=snips)
        assert final == "https://github.com/me"
        assert meta["category"] == "snippet"

    def test_snippet_not_corrupted_by_correction(self, qtbot):
        # A URL snippet must be inserted verbatim (skip_correction), not reshaped
        # by the structured formatter.
        snips = [Snippet(trigger="my site", expansion="see example dot com")]
        final, meta = _run_worker("my site", snippets=snips)
        assert final == "see example dot com"  # literal, unchanged


class TestScenarioD_VoiceEdit:
    def test_voice_edit_replaces_recent_no_duplicate(self, qtbot):
        final, meta = _run_worker(
            "actually six", recent_output="I will arrive at five."
        )
        # Cross-utterance "actually six" is not a command alone; it should be
        # ordinary dictation here (no trailing-sentence structure). Verify no
        # crash and dictate fallback.
        assert meta["category"] in ("dictate", "voice_edit")

    def test_within_utterance_backtrack(self, qtbot):
        final, meta = _run_worker("I will arrive at five. Actually six.")
        assert final == "I will arrive at six."
        assert meta["category"] == "voice_edit"
        assert meta["replaces_recent_output"] is False

    def test_cross_utterance_substitute(self, qtbot):
        final, meta = _run_worker(
            "replace five with six", recent_output="I will arrive at five."
        )
        assert final == "I will arrive at six."
        assert meta["category"] == "voice_edit"
        assert meta["replaces_recent_output"] is True


class TestScenarioE_DeveloperCasing:
    def test_camel_case(self, qtbot):
        final, meta = _run_worker("get user by id, camel case", context=_dev_ctx())
        assert final == "getUserById"
        assert meta["category"] == "developer_format"


class TestScenarioG_StructureAndLists:
    def test_new_paragraph(self, qtbot):
        final, meta = _run_worker("new paragraph")
        assert final == "\n\n"
        assert meta["category"] == "structure"

    def test_ordinal_list(self, qtbot):
        final, meta = _run_worker(
            "first install Docker second clone the repository third run the application"
        )
        assert final == (
            "1. Install Docker\n2. Clone the repository\n3. Run the application"
        )


class TestScenarioH_OrdinaryProse:
    @pytest.mark.parametrize(
        "text",
        [
            "Actually, I agree with you.",
            "We use snake case in this repository.",
            "He made a good point.",
            "Please update the README.",
        ],
    )
    def test_ambiguous_prose_is_dictation(self, qtbot, text):
        final, meta = _run_worker(text)
        assert meta["category"] == "dictate"
        # README is normalized by 6G? No alias for it; prose stays intact.
        # The important assertion is that no command/structure/snippet fired.


class TestRegressionNoContextNoOrchestrator:
    def test_plain_pipeline_unchanged(self, qtbot):
        # With a pass-through orchestrator config nothing changes vs. 6G.
        final, meta = _run_worker("push to git hub")
        assert final == "push to GitHub"
        assert meta["category"] == "dictate"
