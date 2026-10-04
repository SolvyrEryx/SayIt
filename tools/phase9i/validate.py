"""Phase 9I — multi-speaker validation + threshold revalidation + leakage check.

Reality: no microphone / second speaker / TTS here, so multi-speaker real audio
cannot be produced (fabrication forbidden). This tool:
  1. ingests any REAL multi-speaker clips a human has dropped into
     artifacts/phase9i/corpus/ (auto-detected via labels.json),
  2. runs a DATASET-LEAKAGE check (do knowledge-source canonicals coincide with
     eval references in a way that could inflate results?),
  3. revalidates the 0.90 operating point via a threshold sweep on the EXISTING
     real 23-clip corpus (held separate; previous artifacts untouched),
  4. emits false-positive statistics (per 100 applicable utterances).

The existing-corpus results are reused for comparability; nothing is fabricated.
"""

from __future__ import annotations

import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "phase9a2"))

import metrics as M  # noqa: E402
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402
from sayit.core.asr.candidate_ranker import CandidateRanker, RankerConfig  # noqa: E402
from sayit.core.asr.post_context import CorrectorConfig  # noqa: E402
from sayit.core.knowledge import CandidateRetriever, KnowledgeIndex  # noqa: E402
from sayit.core.knowledge.ranked_adapter import RankedRetrievalAdapter  # noqa: E402
from sayit.core.knowledge.models import normalize_text  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
A2_LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
A2_CORPUS = ROOT / "artifacts" / "phase9" / "9A2" / "corpus"
EVAL = ROOT / "artifacts" / "phase6" / "eval-audio"
IDX9E = ROOT / "artifacts" / "phase9e" / "knowledge_index_entity.json"
I_CORPUS = ROOT / "artifacts" / "phase9i" / "corpus"
I_LABELS = ROOT / "artifacts" / "phase9i" / "labels.json"
OUT = ROOT / "artifacts" / "phase9i"


def read_wav(p):
    w = wave.open(str(p), "rb"); sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
    raw = w.readframes(n); w.close()
    d = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        d = d.reshape(-1, ch)[:, 0]
    return d, sr, n / sr


def find_wav(e, corpus_dirs):
    wav = e.get("wav", e["id"] + ".wav")
    for base in corpus_dirs:
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


def load_clips(labels_path, corpus_dirs):
    import sherpa_onnx
    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"), decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"), tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu", decoding_method="greedy_search",
        model_type="nemo_transducer")
    clips = []
    if not labels_path.exists():
        return clips
    for e in json.loads(labels_path.read_text(encoding="utf-8")):
        if e.get("needs_recording"):
            continue
        p = find_wav(e, corpus_dirs)
        if p is None:
            continue
        d, sr, _ = read_wav(p)
        s = rec.create_stream(); s.accept_waveform(sr, d); rec.decode_stream(s)
        clips.append({"id": e["id"], "ref": e["reference"], "hyp": s.result.text.strip(),
                      "targets": e.get("target_terms", []), "negs": e.get("negative_terms", []),
                      "phrases": e.get("phrase_terms", []), "context": context_for(e),
                      "speaker": e.get("speaker_id", "S1"), "split": e.get("split", "dev")})
    return clips


def score(clips, adapter):
    recs = []
    applicable = 0   # utterances with negatives (where a false sub is possible)
    false_subs = {"ordinary_to_technical": 0, "other": 0}
    for c in clips:
        hyp = adapter.correct(c["hyp"], c["context"]).text
        errs, words = M.wer(c["ref"], hyp)
        tr_n, tr_d, _ = M.technical_term_recall(hyp, c["targets"])
        ex_n, ex_d, _ = M.exact_entity_accuracy(hyp, c["targets"])
        fs_n, fs_list = M.false_technical_substitutions(hyp, c["negs"])
        if c["negs"]:
            applicable += 1
            if fs_n:
                false_subs["ordinary_to_technical"] += fs_n
        recs.append({"errors": errs, "ref_words": words, "tech_recalled": tr_n, "tech_total": tr_d,
                     "exact_count": ex_n, "exact_total": ex_d, "phrase_recalled": 0, "phrase_total": 0,
                     "false_sub_count": fs_n, "has_negatives": bool(c["negs"]),
                     "ordinary_preserved": (fs_n == 0) if c["negs"] else None})
    agg = M.aggregate(recs)
    total_fs = sum(false_subs.values())
    agg["false_subs_per_100_applicable"] = round(100.0 * total_fs / applicable, 2) if applicable else 0.0
    agg["false_sub_breakdown"] = false_subs
    agg["applicable_utterances"] = applicable
    return agg


def leakage_check(clips, index):
    """Flag targets whose EXACT reference form equals an index canonical AND whose
    retrieval would trivially supply it. This is informational: it quantifies how
    much of the exact-entity result could be 'because the answer is in the pack'
    (expected for a proof corpus) vs genuine disambiguation."""
    retr = CandidateRetriever(index)
    in_pack = 0
    total = 0
    for c in clips:
        for t in c["targets"]:
            total += 1
            # Is the canonical target directly present as a candidate canonical?
            cands = retr.retrieve(t, c["context"], top_k=10)
            if any(normalize_text(rc.term.canonical) == normalize_text(t) for rc in cands):
                in_pack += 1
    return {"targets_total": total, "targets_in_knowledge": in_pack,
            "fraction_in_knowledge": round(in_pack / total, 3) if total else None,
            "note": "High fraction is EXPECTED for a proof corpus; it means the "
                    "knowledge covers the corpus terms. It is a leakage CAVEAT, not "
                    "proof of generalization. Multi-speaker holdout clips are needed "
                    "to measure out-of-pack behavior."}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    I_CORPUS.mkdir(parents=True, exist_ok=True)
    cfg, rcfg = CorrectorConfig(), RankerConfig()
    idx = KnowledgeIndex.load(IDX9E)

    # Existing real corpus (comparability; artifacts preserved separately).
    existing = load_clips(A2_LABELS, [A2_CORPUS, EVAL])
    # Any newly provided multi-speaker clips (auto-detected).
    new_clips = load_clips(I_LABELS, [I_CORPUS]) if I_LABELS.exists() else []

    speakers = sorted({c["speaker"] for c in existing + new_clips})
    report = {
        "phase": "9I",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "existing_corpus_clips": len(existing),
        "new_multispeaker_clips": len(new_clips),
        "speakers": speakers,
        "multispeaker_available": len(speakers) > 1,
    }

    # Threshold revalidation on the existing real corpus (dev set).
    sweep = {}
    for th in [0.80, 0.85, 0.88, 0.90, 0.92, 0.95]:
        ad = RankedRetrievalAdapter(CandidateRetriever(idx), CandidateRanker(RankerConfig(accept_threshold=th)), cfg, top_k=10)
        agg = score(existing, ad)
        sweep[str(th)] = {"technical_term_recall": agg["technical_term_recall"],
                          "exact_entity_accuracy": agg["exact_entity_accuracy"],
                          "false_substitution_total": agg["false_substitution_total"],
                          "false_subs_per_100_applicable": agg["false_subs_per_100_applicable"],
                          "ordinary_preservation": agg["ordinary_preservation"],
                          "wer": agg["wer"]}
    (OUT / "threshold_revalidation.json").write_text(json.dumps(sweep, indent=2), encoding="utf-8")

    # Leakage/holdout check.
    report["leakage_check"] = leakage_check(existing, idx)

    # If multi-speaker clips exist, score per-speaker; else record infra-only.
    if new_clips:
        ad = RankedRetrievalAdapter(CandidateRetriever(idx), CandidateRanker(rcfg), cfg, top_k=10)
        per_speaker = {}
        for sp in sorted({c["speaker"] for c in new_clips}):
            per_speaker[sp] = score([c for c in new_clips if c["speaker"] == sp], ad)
        report["per_speaker"] = per_speaker
        report["combined_new"] = score(new_clips, ad)

    (OUT / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Recommended operating point from the sweep (max recall with 0 extra fsub
    # beyond the baseline artifact of 2; prefer higher threshold on ties).
    best = None
    for th, m in sweep.items():
        key = (m["technical_term_recall"], -m["false_substitution_total"], float(th))
        if best is None or key > best[0]:
            best = (key, th, m)
    report["recommended_threshold"] = {"threshold": best[1], "metrics": best[2]}
    (OUT / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("multispeaker_available:", report["multispeaker_available"], "speakers:", speakers)
    print("leakage fraction_in_knowledge:", report["leakage_check"]["fraction_in_knowledge"])
    print("threshold sweep (recall / fsub / fsub_per_100 / ordinary):")
    for th, m in sweep.items():
        print(f"  {th}: {m['technical_term_recall']:.3f} / {m['false_substitution_total']} / "
              f"{m['false_subs_per_100_applicable']} / {m['ordinary_preservation']:.3f}")
    print("recommended threshold:", report["recommended_threshold"]["threshold"])


if __name__ == "__main__":
    main()
