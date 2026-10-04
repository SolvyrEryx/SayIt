"""Phase 10 — wordfreq experiment benchmark (ISOLATED, no production change).

Compares:
  BASELINE : the 9F CandidateRanker as-is
  +FREQ    : the same ranker whose winning candidate's score is reduced by an
             ordinary-language frequency penalty (FrequencyPrior) before the
             accept decision — i.e. ordinary-looking spans are harder to correct.

Measured on: (a) the real 23-clip corpus (technical recall / exact / canonical /
WER / false subs / ordinary preservation), and (b) the hard-negative FP set
across contexts (the metric that matters for this experiment). Decision rule:
integrate (behind the flag) ONLY if ordinary preservation / false subs improve
WITHOUT losing technical recall/exact. Else REJECT/DEFER.
"""

from __future__ import annotations

import json
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))
sys.path.insert(0, str(ROOT / "tools" / "phase10"))

import metrics as M  # noqa: E402
from frequency_prior import FrequencyPrior  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.candidate_ranker import CandidateRanker, Decision, RankerConfig  # noqa: E402
from sayit.core.asr.post_context import Candidate, CandidatePack, CorrectorConfig, PostASRContextCorrector  # noqa: E402
from sayit.core.knowledge import CandidateRetriever, KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.adapter import knowledge_term_to_candidate  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
IDX = ROOT / "src" / "sayit" / "core" / "knowledge" / "data" / "knowledge_index.json"
OUT = ROOT / "artifacts" / "phase10"


class FreqAwareRanker(CandidateRanker):
    """9F ranker + ordinary-language frequency penalty on the winner."""
    def __init__(self, cfg, prior: FrequencyPrior):
        super().__init__(cfg)
        self._prior = prior

    def rank(self, observed_span, candidates, context=None, domain=None, metadata=None):
        dec = super().rank(observed_span, candidates, context, domain, metadata)
        if dec.decision is Decision.CORRECT:
            pen = self._prior.penalty(observed_span)
            if pen > 0.0:
                new_score = dec.score - pen
                # Re-apply the accept gate with the penalized score.
                if new_score < self._cfg.accept_threshold:
                    dec.decision = Decision.LEAVE_UNCHANGED
                    dec.winner = None
                    dec.reason = f"freq-prior penalty {pen} -> below threshold"
                dec.score = round(new_score, 5)
        return dec


def read_wav(p):
    w = wave.open(str(p), "rb"); sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n); w.close()
    d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        d = d.reshape(-1, ch)[:, 0]
    return d, sr, n / sr


def find_wav(e):
    wav = e.get("wav", e["id"] + ".wav")
    for base in (CORPUS, EVAL):
        if (base / wav).exists():
            return base / wav
    return None


def context_for(e):
    role, cat = e.get("pair_role"), e.get("category")
    if role == "technical" or cat in ("technical", "multiword"):
        return "developer"
    if role == "ordinary":
        return "email"
    if cat == "mixed":
        return "developer"
    return "email"


def greedy_clips():
    import sherpa_onnx
    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu", decoding_method="greedy_search",
        model_type="nemo_transducer")
    out = []
    for e in json.loads(LABELS.read_text(encoding="utf-8")):
        if e.get("needs_recording"):
            continue
        p = find_wav(e)
        if p is None:
            continue
        d, sr, _ = read_wav(p)
        s = rec.create_stream(); s.accept_waveform(sr, d); rec.decode_stream(s)
        out.append({"id": e["id"], "ref": e["reference"], "hyp": s.result.text.strip(),
                    "targets": e.get("target_terms", []), "negs": e.get("negative_terms", []),
                    "context": context_for(e)})
    return out


def correct(index, ranker, text, context, max_span=3):
    """Mini retrieve-once + rank + 9B apply, parameterized by the ranker."""
    retr = CandidateRetriever(index)
    words = (text or "").split()
    n = len(words)
    trusted = {}
    for i in range(n):
        for L in range(1, min(max_span, n - i) + 1):
            span = " ".join(words[i:i + L])
            cands = retr.retrieve(span, context, top_k=10)
            if not cands:
                continue
            dec = ranker.rank(span, cands, context)
            if dec.decision is Decision.CORRECT and dec.winner:
                for rc in cands:
                    if rc.term.canonical == dec.winner:
                        trusted.setdefault(rc.term.canonical, knowledge_term_to_candidate(rc.term))
                        break
    pack = CandidatePack(list(trusted.values()))
    return PostASRContextCorrector(pack, CorrectorConfig()).correct(text, context).text


def score(index, ranker, clips):
    recs = []
    for c in clips:
        hyp = correct(index, ranker, c["hyp"], c["context"])
        errs, words = M.wer(c["ref"], hyp)
        tr_n, tr_d, _ = M.technical_term_recall(hyp, c["targets"])
        ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, c["targets"])
        fs_n, _ = M.false_technical_substitutions(hyp, c["negs"])
        recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n, "tech_total": tr_d,
                     "exact_count": ex_n, "exact_total": ex_d, "phrase_recalled": 0, "phrase_total": 0,
                     "false_sub_count": fs_n, "has_negatives": bool(c["negs"]),
                     "ordinary_preserved": (fs_n == 0) if c["negs"] else None})
    return M.aggregate(recs)


HARD_NEG = [
    ("i ate an apple for lunch", "Apple"), ("michael jordan was a great player", "Jordan"),
    ("we sailed down the amazon river", "Amazon"), ("i need to go to the store", "Go"),
    ("there is rust on the gate", "Rust"), ("that was a swift decision", "Swift"),
    ("the python slithered away", "Python"), ("i need a fast api for the service", "FastAPI"),
]


def fp_count(index, ranker):
    total = 0
    for text, risky in HARD_NEG:
        for ctx in ("normal", "developer", "email", "chat", "notes", "prompt"):
            out = correct(index, ranker, text, ctx)
            if risky.lower() in out.lower() and risky.lower() not in text.lower():
                total += 1
    return total


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    clips = greedy_clips()
    index = KnowledgeIndex.load(IDX)
    cfg = RankerConfig()
    baseline = CandidateRanker(cfg)
    freq = FreqAwareRanker(cfg, FrequencyPrior(max_penalty=0.15, threshold=0.7))

    t0 = time.perf_counter(); base_corpus = score(index, baseline, clips); base_ms = (time.perf_counter() - t0) * 1000 / len(clips)
    t0 = time.perf_counter(); freq_corpus = score(index, freq, clips); freq_ms = (time.perf_counter() - t0) * 1000 / len(clips)
    base_fp = fp_count(index, baseline)
    freq_fp = fp_count(index, freq)

    def pick(a):
        return {k: a[k] for k in ("technical_term_recall", "exact_entity_accuracy",
                                  "false_substitution_total", "ordinary_preservation", "wer")}
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment": "wordfreq ordinary-language frequency prior (isolated; self-contained table, NO new dependency)",
        "baseline_9F": pick(base_corpus) | {"corpus_false_subs": base_corpus["false_substitution_total"],
                                            "hard_negative_false_subs": base_fp,
                                            "latency_ms_per_clip": round(base_ms, 3)},
        "with_freq_prior": pick(freq_corpus) | {"corpus_false_subs": freq_corpus["false_substitution_total"],
                                                "hard_negative_false_subs": freq_fp,
                                                "latency_ms_per_clip": round(freq_ms, 3)},
    }
    # Decision logic.
    improved_fp = (freq_fp < base_fp) or (freq_corpus["false_substitution_total"] < base_corpus["false_substitution_total"])
    lost_recall = (freq_corpus["technical_term_recall"] < base_corpus["technical_term_recall"]) or \
                  (freq_corpus["exact_entity_accuracy"] < base_corpus["exact_entity_accuracy"])
    if improved_fp and not lost_recall:
        decision = "INTEGRATE_BEHIND_FLAG"
    elif improved_fp and lost_recall:
        decision = "REJECT (improves FP but regresses technical recall/exact)"
    else:
        decision = "REJECT (no measurable false-positive improvement)"
    result["decision"] = decision
    (OUT / "wordfreq_experiment.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("baseline:", result["baseline_9F"])
    print("+freq   :", result["with_freq_prior"])
    print("DECISION:", decision)


if __name__ == "__main__":
    main()
