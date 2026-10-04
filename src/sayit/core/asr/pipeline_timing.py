"""Privacy-safe dictation pipeline timing (Phase 6H).

Records monotonic timestamps for the stages of a single dictation job and
derives the latencies the Phase 6H objective cares about (time to final
transcript, stop->final, Phase 6G overhead, end-to-end). It is a developer
diagnostic only: it records timestamps, durations, counters, a job id, and
character/word counts — and NEVER transcript content.

The current engine is an offline (non-streaming) Sherpa-ONNX recognizer, so the
"first partial" stage is only populated if a true partial ever occurs; with the
offline path it stays ``None`` and is reported as not-applicable. This keeps the
instrumentation honest about what actually happened rather than implying
streaming that does not exist.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional


def _now() -> float:
    return time.perf_counter()


@dataclass
class PipelineTiming:
    """Monotonic stage timestamps for one dictation job (seconds, perf_counter).

    All fields are ``None`` until the corresponding stage occurs. ``mark`` is
    idempotent per stage name is NOT enforced; the first non-None write wins for
    derived metrics via the helper properties, but callers normally mark each
    stage once.
    """

    job_id: int
    recording_start: Optional[float] = None
    recording_stop: Optional[float] = None
    asr_start: Optional[float] = None
    first_partial: Optional[float] = None  # offline path: stays None
    asr_final: Optional[float] = None
    correction_start: Optional[float] = None
    correction_end: Optional[float] = None
    insertion_start: Optional[float] = None
    insertion_end: Optional[float] = None

    # --- Phase 5: finer-grained user-visible stages (all additive/optional) ---
    # Recorder finalize split: the time from hotkey release to the audio array
    # being ready for handoff (buffer concat + stream teardown).
    recorder_finalized: Optional[float] = None
    # Audio handed to the transcription worker (thread start boundary).
    asr_handoff: Optional[float] = None
    # Preprocessing (dtype/channel/normalization) inside the backend, if marked.
    preprocess_start: Optional[float] = None
    preprocess_end: Optional[float] = None
    # Intelligence (8H orchestrator + optional experimental pipeline).
    intelligence_start: Optional[float] = None
    intelligence_end: Optional[float] = None
    # Clipboard write vs paste keystroke split (inside insertion).
    clipboard_write_start: Optional[float] = None
    clipboard_write_end: Optional[float] = None
    paste_start: Optional[float] = None
    paste_end: Optional[float] = None
    # UI result becomes visible (Home updated / state back to IDLE).
    ui_visible: Optional[float] = None

    # Counters (no transcript text).
    asr_invocations: int = 0
    chunk_count: int = 0
    final_char_count: int = 0
    extra: Dict[str, float] = field(default_factory=dict)

    def mark(self, stage: str, when: Optional[float] = None) -> None:
        """Record the timestamp for a named stage (defaults to now)."""
        if not hasattr(self, stage):
            # Unknown stage goes into extra so instrumentation never crashes the
            # dictation workflow.
            self.extra[stage] = when if when is not None else _now()
            return
        setattr(self, stage, when if when is not None else _now())

    # --- derived latencies (seconds); None when inputs are missing ------
    @staticmethod
    def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
        if a is None or b is None:
            return None
        return b - a

    @property
    def time_to_first_partial(self) -> Optional[float]:
        return self._delta(self.asr_start, self.first_partial)

    @property
    def time_to_final_transcript(self) -> Optional[float]:
        return self._delta(self.asr_start, self.asr_final)

    @property
    def stop_to_final_text(self) -> Optional[float]:
        return self._delta(self.recording_stop, self.correction_end)

    @property
    def correction_overhead(self) -> Optional[float]:
        return self._delta(self.correction_start, self.correction_end)

    @property
    def end_to_end(self) -> Optional[float]:
        # Prefer insertion_end; fall back to correction_end if insertion was not
        # reached (e.g. empty audio).
        end = self.insertion_end if self.insertion_end is not None else self.correction_end
        return self._delta(self.recording_start, end)

    @property
    def recording_duration(self) -> Optional[float]:
        return self._delta(self.recording_start, self.recording_stop)

    # --- Phase 5 derived latencies (all seconds; None when inputs missing) ---
    @property
    def recorder_finalize_overhead(self) -> Optional[float]:
        """Hotkey release (recording_stop) -> audio array ready."""
        return self._delta(self.recording_stop, self.recorder_finalized)

    @property
    def handoff_overhead(self) -> Optional[float]:
        """Audio ready -> worker thread picks it up (scheduling/thread boundary)."""
        return self._delta(self.recorder_finalized, self.asr_handoff)

    @property
    def preprocess_overhead(self) -> Optional[float]:
        return self._delta(self.preprocess_start, self.preprocess_end)

    @property
    def intelligence_overhead(self) -> Optional[float]:
        return self._delta(self.intelligence_start, self.intelligence_end)

    @property
    def clipboard_overhead(self) -> Optional[float]:
        return self._delta(self.clipboard_write_start, self.clipboard_write_end)

    @property
    def paste_overhead(self) -> Optional[float]:
        return self._delta(self.paste_start, self.paste_end)

    @property
    def insertion_overhead(self) -> Optional[float]:
        """Full insertion (clipboard write + paste), as bracketed by the app."""
        return self._delta(self.insertion_start, self.insertion_end)

    @property
    def ui_overhead(self) -> Optional[float]:
        """Insertion complete -> UI result visible. MUST be off the critical
        path (UI must never delay insertion). Measured to prove it."""
        return self._delta(self.insertion_end, self.ui_visible)

    @property
    def stop_to_text(self) -> Optional[float]:
        """The headline user-visible metric: hotkey release -> text inserted."""
        end = self.insertion_end if self.insertion_end is not None else self.correction_end
        return self._delta(self.recording_stop, end)

    def _fmt(self, v: Optional[float]) -> str:
        return f"{v:.3f}s" if v is not None else "n/a"

    def summary(self) -> str:
        """A single privacy-safe log line. No transcript text, ever."""
        ttf = self._fmt(self.time_to_first_partial)
        if self.first_partial is None:
            ttf = "n/a(offline)"
        return (
            f"[timing job {self.job_id}] "
            f"rec={self._fmt(self.recording_duration)} "
            f"to_first_partial={ttf} "
            f"to_final={self._fmt(self.time_to_final_transcript)} "
            f"stop_to_final_text={self._fmt(self.stop_to_final_text)} "
            f"correction={self._fmt(self.correction_overhead)} "
            f"end_to_end={self._fmt(self.end_to_end)} "
            f"asr_calls={self.asr_invocations} chunks={self.chunk_count} "
            f"chars={self.final_char_count}"
        )



# ---------------------------------------------------------------------------
# Phase 5: percentile aggregation across many dictation jobs.
# ---------------------------------------------------------------------------
# The per-stage names aggregated. Each maps to a PipelineTiming property that
# returns seconds (or None). We report milliseconds in the summary.
_AGGREGATED_STAGES = (
    "recorder_finalize_overhead",
    "handoff_overhead",
    "preprocess_overhead",
    "time_to_final_transcript",   # ASR
    "intelligence_overhead",
    "correction_overhead",
    "clipboard_overhead",
    "paste_overhead",
    "insertion_overhead",
    "ui_overhead",
    "stop_to_text",               # headline
)


def _percentile(sorted_vals: list, q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = max(0, min(len(sorted_vals) - 1, int(round((len(sorted_vals) - 1) * q))))
    return sorted_vals[i]


class TimingAggregator:
    """Collects PipelineTiming objects across runs and reports per-stage
    p50/p75/p90/p95/max (milliseconds). Privacy-safe: durations only.

    Measure, don't infer: this is how the dominant stop->text bottleneck is
    identified from real runs rather than guessed.
    """

    def __init__(self):
        self._samples: Dict[str, list] = {s: [] for s in _AGGREGATED_STAGES}
        self._n = 0

    def add(self, timing: "PipelineTiming") -> None:
        self._n += 1
        for stage in _AGGREGATED_STAGES:
            val = getattr(timing, stage, None)
            if val is not None:
                self._samples[stage].append(val * 1000.0)  # -> ms

    @property
    def count(self) -> int:
        return self._n

    def stats(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for stage, vals in self._samples.items():
            if not vals:
                continue
            s = sorted(vals)
            out[stage] = {
                "n": len(s),
                "p50": round(_percentile(s, 0.50), 1),
                "p75": round(_percentile(s, 0.75), 1),
                "p90": round(_percentile(s, 0.90), 1),
                "p95": round(_percentile(s, 0.95), 1),
                "max": round(max(s), 1),
            }
        return out

    def summary(self) -> str:
        lines = [f"[timing-agg n={self._n}] per-stage ms (p50/p75/p90/p95/max):"]
        for stage, st in self.stats().items():
            lines.append(
                f"  {stage:28s} "
                f"{st['p50']:8.1f}/{st['p75']:8.1f}/{st['p90']:8.1f}/"
                f"{st['p95']:8.1f}/{st['max']:8.1f}  (n={st['n']})"
            )
        return "\n".join(lines)
