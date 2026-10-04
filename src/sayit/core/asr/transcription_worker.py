from datetime import datetime
from threading import Event
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal

from ...utils.logger import get_logger
from ..transcript_processor import (
    Enhancement,
    LLMProcessor,
    apply_vocabulary_replacements,
)
from .transcriber import TranscriptionEngine

logger = get_logger(__name__)


class TranscriptionWorkerThread(QThread):
    """
    Background thread for transcription + LLM enhancement.

    Performs the entire transcription pipeline in a background thread:
    1. Audio transcription via ASR engine
    2. Vocabulary replacements
    3. LLM enhancement (if configured)

    Cancellation is cooperative. The underlying ASR call is CPU-bound native
    code that cannot be safely interrupted mid-execution, so ``cancel()`` only
    sets a flag. The thread is never force-killed; instead it checks the flag at
    safe points (before/after the ASR call and before the optional LLM step) and
    skips remaining work. Regardless, the owning app discards the result by job
    id, so a cancelled job can never insert text.

    Signals:
        finished: Emitted when processing completes
                  (final_text, raw_text, enhanced_text, enhancement_name, cost,
                   intelligence_meta)
        error: Emitted when processing fails (error_message)
    """

    # (final_text, raw_text, enhanced_text, enhancement_name, cost, intel_meta)
    finished = Signal(str, str, object, object, object, object)
    error = Signal(str)

    def __init__(
        self,
        transcriber: TranscriptionEngine,
        audio_data: np.ndarray,
        sample_rate: int,
        vocabulary_replacements: dict,
        llm_processor: Optional[LLMProcessor],
        enhancement: Optional[Enhancement],
        parent=None,
        technical_correction_enabled: bool = True,
        structured_formatting_enabled: bool = True,
        timing=None,
        custom_vocabulary=None,
        context_resolution=None,
        orchestrator=None,
        snippets=None,
        recent_output=None,
        post_asr_pipeline=None,
    ):

        super().__init__(parent)
        self._transcriber = transcriber
        self._audio_data = audio_data
        self._sample_rate = sample_rate
        self._vocabulary_replacements = vocabulary_replacements
        self._custom_vocabulary = custom_vocabulary
        self._llm_processor = llm_processor
        self._enhancement = enhancement
        self._technical_correction_enabled = technical_correction_enabled
        self._structured_formatting_enabled = structured_formatting_enabled
        self._context_resolution = context_resolution
        # Phase 8H: optional intelligence orchestrator + its inputs. When
        # present, the orchestrator runs on the raw ASR text BEFORE the existing
        # 6G/6I/6J pipeline. It may transform the text (snippet/structure/
        # developer) or flag a voice edit of recent output. It never bypasses
        # the safe output path and never executes anything.
        self._orchestrator = orchestrator
        self._snippets = snippets
        self._recent_output = recent_output
        # Phase 9K: optional post-ASR intelligence pipeline (9C+9D+9F+9B),
        # OFF BY DEFAULT (the owner passes None unless the experimental flag is
        # on). When present it runs on the raw ASR text BEFORE 8H/6G/6I/6J and
        # is fail-safe (returns the text unchanged on any error). When None, the
        # pipeline is byte-identical to today's behavior.
        self._post_asr_pipeline = post_asr_pipeline
        # Phase 6H: optional privacy-safe timing object owned by the caller. The
        # worker only records stage marks on it; it never logs transcript text.
        self._timing = timing
        self._cancelled = Event()

    def cancel(self) -> None:
        """Request cooperative cancellation. Safe to call from any thread."""
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def run(self):
        import time

        start_time = time.time()

        try:
            if self._cancelled.is_set():
                logger.info("Transcription cancelled before start")
                self.error.emit("Cancelled")
                return

            logger.info(
                f"Background transcription started: {len(self._audio_data)} samples"
            )
            if self._timing is not None:
                self._timing.mark("asr_start")
            raw_text = self._transcriber.transcribe_chunked(
                self._audio_data, self._sample_rate
            )
            if self._timing is not None:
                self._timing.mark("asr_final")
                # Counters only (no transcript text).
                self._timing.chunk_count = getattr(
                    self._transcriber, "last_chunk_count", 1
                )
                self._timing.asr_invocations = getattr(
                    self._transcriber, "last_invocation_count", 1
                )

            if self._cancelled.is_set():
                # Result is no longer wanted. Report as an error so the owner
                # resolves state; the owner also rejects it by job id.
                logger.info("Transcription cancelled after ASR; discarding result")
                self.error.emit("Cancelled")
                return

            if not raw_text:
                logger.warning("Transcription returned empty result")
                self.error.emit("Transcription returned empty result")
                return

            duration = time.time() - start_time
            logger.info(
                f"ASR completed in {duration:.2f}s ({len(raw_text)} chars)"
            )

            # Phase 9K: optional experimental post-ASR intelligence pipeline
            # (9C retrieval + 9D domain/canonical + 9F ranking/abstention + 9B
            # correction), applied to the raw transcript BEFORE 8H/6G/6I/6J.
            # Only present when the owner enabled the experimental flag; None
            # otherwise (byte-identical to prior behavior). Fail-safe: the
            # pipeline returns the text unchanged on any error, so a failure
            # here can never break dictation.
            if self._post_asr_pipeline is not None:
                try:
                    if self._timing is not None:
                        self._timing.mark("post_asr_intelligence_start")
                    ctx_profile = None
                    if self._context_resolution is not None:
                        ctx_profile = getattr(
                            self._context_resolution.profile, "value", None)
                    pr = self._post_asr_pipeline.process(raw_text, ctx_profile)
                    if pr.text:
                        raw_text = pr.text
                    if self._timing is not None:
                        self._timing.mark("post_asr_intelligence_end")
                    logger.info(
                        f"[post-asr-intelligence] changed={pr.changed} "
                        f"reason={pr.reason}"
                    )
                except Exception as e:
                    logger.debug(f"Post-ASR intelligence skipped (safe): {e}")

            # Phase 8H: run the intelligence orchestrator on the raw ASR text.
            # It resolves intent (voice edit / snippet / structure / developer /
            # dictate) deterministically and may transform the text or request a
            # voice edit of recent output. It never executes anything and always
            # returns via the existing safe output path. Fail-safe: on any error
            # we fall back to the raw text (ordinary dictation).
            intel_text = raw_text
            intel_skip_correction = False
            intel_meta = None
            if self._orchestrator is not None:
                try:
                    if self._timing is not None:
                        self._timing.mark("intelligence_start")
                    ir = self._orchestrator.process(
                        raw_text,
                        context=self._context_resolution,
                        snippets=self._snippets,
                        recent_output=self._recent_output,
                    )
                    intel_text = ir.text
                    intel_skip_correction = ir.skip_correction
                    intel_meta = {
                        "category": ir.intent.category.value,
                        "reason": ir.intent.reason,
                        "replaces_recent_output": ir.replaces_recent_output,
                        "replaced_span_text": ir.replaced_span_text,
                    }
                    if self._timing is not None:
                        self._timing.mark("intelligence_end")
                    logger.info(
                        f"[intelligence] intent={ir.intent.category.value} "
                        f"skip_correction={intel_skip_correction} "
                        f"replaces_recent={ir.replaces_recent_output}"
                    )
                except Exception as e:  # fail-safe to ordinary dictation
                    logger.debug(f"Intelligence orchestrator skipped: {e}")
                    intel_text = raw_text
                    intel_skip_correction = False
                    intel_meta = None

            # Phase 6G: local deterministic technical correction + formatting,
            # applied before the existing user vocabulary replacements. Runs
            # on-device; no network, no transcript logging.
            #
            # Phase 8A: the resolved context *profile* refines which of these
            # already-existing flags are active. The profile can only narrow the
            # user's master toggles (logical AND), never widen them: if the user
            # turned a correction off globally, no profile can turn it back on.
            #
            # Phase 8H: when the orchestrator produced literal output (snippet,
            # code block, structure, casing identifier), ``intel_skip_correction``
            # is set and the 6G/6I/6J normalization is bypassed so the literal
            # text is preserved verbatim.
            enable_technical = self._technical_correction_enabled and not intel_skip_correction
            enable_formatting = self._structured_formatting_enabled and not intel_skip_correction
            enable_structured = self._structured_formatting_enabled and not intel_skip_correction
            if self._context_resolution is not None and not intel_skip_correction:
                cfg = self._context_resolution.config
                enable_technical = enable_technical and cfg.enable_technical
                enable_formatting = enable_formatting and cfg.enable_formatting
                enable_structured = enable_structured and cfg.enable_structured
                # Explainability: record the context decision for this job
                # (profile + source + reason only; never transcript content).
                logger.info(
                    f"[context] profile={self._context_resolution.profile.value} "
                    f"source={self._context_resolution.source} "
                    f"flags(tech={enable_technical},fmt={enable_formatting},"
                    f"struct={enable_structured})"
                )

            corrected_text = intel_text
            if enable_technical or enable_formatting:
                from ..transcript_processor import correct_transcript

                if self._timing is not None:
                    self._timing.mark("correction_start")
                correction = correct_transcript(
                    intel_text,
                    enable_technical=enable_technical,
                    enable_formatting=enable_formatting,
                    enable_structured=enable_structured,
                )
                corrected_text = correction.text
                # Phase 8A explainability: prepend a context Change so a reader
                # of the change list can see why formatting behavior differed.
                if self._context_resolution is not None:
                    from ..transcript_processor import Change

                    self._context_change = Change(
                        category="context",
                        original="",
                        replacement=self._context_resolution.profile.value,
                        rule=f"{self._context_resolution.profile.value}_profile",
                    )
                if self._timing is not None:
                    self._timing.mark("correction_end")
            elif self._timing is not None:
                # Correction disabled: still mark a zero-width boundary so the
                # downstream timing summary is complete and honest.
                self._timing.mark("correction_start")
                self._timing.mark("correction_end", self._timing.correction_start)

            # Phase 6J: user-controlled custom vocabulary. Runs in the SAME
            # pipeline position as the legacy vocabulary step (after Phase
            # 6G/6I correction, before optional LLM). Skipped when the
            # orchestrator produced literal output (snippet/code/structure).
            if intel_skip_correction:
                processed_text = corrected_text
            elif self._custom_vocabulary:
                from ..transcript_processor import (
                    apply_user_vocabulary,
                    entries_from_any,
                )

                entries = entries_from_any(
                    self._custom_vocabulary, self._vocabulary_replacements
                )
                processed_text, _vocab_changes, _usage = apply_user_vocabulary(
                    corrected_text, entries
                )
            else:
                processed_text = apply_vocabulary_replacements(
                    corrected_text, self._vocabulary_replacements
                )

            final_text = processed_text
            enhanced_text = None
            enhancement_name = None
            cost = None

            if self._llm_processor and self._enhancement:
                if self._cancelled.is_set():
                    logger.info("Cancelled before LLM enhancement; skipping")
                    self.error.emit("Cancelled")
                    return
                if self._llm_processor.is_configured():
                    logger.info(f"Applying LLM enhancement: {self._enhancement.title}")
                    response = self._llm_processor.process(
                        processed_text, self._enhancement
                    )
                    final_text = response.content
                    enhanced_text = response.content
                    enhancement_name = self._enhancement.title
                    cost = response.cost_usd
                else:
                    logger.warning("LLM processor not configured, skipping enhancement")

            if enhanced_text is None and processed_text != raw_text:
                enhanced_text = processed_text
                enhancement_name = "Vocabulary Replacement"

            if self._cancelled.is_set():
                logger.info("Cancelled before emit; discarding result")
                self.error.emit("Cancelled")
                return

            total_duration = time.time() - start_time
            logger.info(f"Total processing completed in {total_duration:.2f}s")

            self.finished.emit(
                final_text, raw_text, enhanced_text, enhancement_name, cost, intel_meta
            )

        except Exception as e:
            logger.exception(f"Background transcription error: {e}")
            self.error.emit(str(e))
