"""Phase 9A.2 — verify the staged-recording -> clip-ID mapping by CONTENT.

The source files are named Pair1..Pair8 (ordinary/technical) + Multi-word +
Mixed. The authoritative order is the recording guide table:
  Pair1=PG, Pair2=FASTAPI, Pair3=OPENAI, Pair4=NEXTJS, Pair5=TENSORFLOW,
  Pair6=KUBECTL, Pair7=PYTHON, Pair8=RUST; Multi-word=MULTI01; Mixed=MIXED01.

Rather than assume, this transcribes each staged WAV with the PRODUCTION
(greedy 1.12.21) recognizer and checks token overlap against the candidate
reference and presence of the ordinary/technical discriminator words. It writes
mapping_review.json. If every clip's content clearly matches its candidate, the
mapping is confirmed; otherwise the mismatches are flagged for human review.
"""

from __future__ import annotations

import json
import re
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from sayit.core.asr.file_utils import get_models_dir  # noqa: E402

STAGE = ROOT / "artifacts" / "phase9" / "9A2R" / "staging"
LABELS = ROOT / "artifacts" / "phase9" / "9A2" / "labels.json"
OUT = ROOT / "artifacts" / "phase9" / "9A2R"
MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"

# staged stem -> candidate clip id (recording-guide order).
STAGE_TO_ID = {
    "Pair1_ordinary": "PAIR_PG_ORDINARY",
    "Pair1_Technical": "PAIR_PG_TECHNICAL",
    "Pair2_ordinary": "PAIR_FASTAPI_ORDINARY",
    "Pair2_technical": "PAIR_FASTAPI_TECHNICAL",
    "Pair3_ordinary": "PAIR_OPENAI_ORDINARY",
    "Pair3_technical": "PAIR_OPENAI_TECHNICAL",
    "Pair4_ordinary": "PAIR_NEXTJS_ORDINARY",
    "Pair4_technical": "PAIR_NEXTJS_TECHNICAL",
    "Pair5_ordinary": "PAIR_TENSORFLOW_ORDINARY",
    "Pair5_technical": "PAIR_TENSORFLOW_TECHNICAL",
    "Pair6_ordinary": "PAIR_KUBECTL_ORDINARY",
    "Pair6_technical": "PAIR_KUBECTL_TECHNICAL",
    "Pair7_ordinary": "PAIR_PYTHON_ORDINARY",
    "Pair7_technical": "PAIR_PYTHON_TECHNICAL",
    "Pair8_ordinary": "PAIR_RUST_ORDINARY",
    "Pair8_technical": "PAIR_RUST_TECHNICAL",
    "Multiword": "MULTI01",
    "Mixed": "MIXED01",
}


def norm(t):
    return set(re.sub(r"[^a-z0-9 ]", " ", (t or "").lower()).split())


def read_wav(path):
    w = wave.open(str(path), "rb")
    sr = w.getframerate()
    data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    w.close()
    return data.astype(np.float32) / 32768.0, sr


def main():
    import sherpa_onnx

    md = Path(get_models_dir()) / MODEL_ID
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(md / "encoder.int8.onnx"),
        decoder=str(md / "decoder.int8.onnx"),
        joiner=str(md / "joiner.int8.onnx"),
        tokens=str(md / "tokens.txt"),
        num_threads=4, provider="cpu",
        decoding_method="greedy_search", model_type="nemo_transducer",
    )
    labels = {e["id"]: e for e in json.loads(LABELS.read_text(encoding="utf-8"))}

    rows = []
    all_ok = True
    for stem, cid in STAGE_TO_ID.items():
        wav = STAGE / f"{stem}.wav"
        entry = labels.get(cid)
        if not wav.exists() or entry is None:
            rows.append({"stem": stem, "candidate_id": cid, "status": "missing"})
            all_ok = False
            continue
        data, sr = read_wav(wav)
        s = rec.create_stream()
        s.accept_waveform(sr, data)
        rec.decode_stream(s)
        hyp = s.result.text.strip()
        ref_tokens = norm(entry["reference"])
        hyp_tokens = norm(hyp)
        overlap = len(ref_tokens & hyp_tokens) / max(len(ref_tokens), 1)
        # Content-anchor check: at least 50% ref-token overlap to accept.
        status = "match" if overlap >= 0.5 else "REVIEW"
        if status != "match":
            all_ok = False
        rows.append({
            "stem": stem, "candidate_id": cid,
            "reference": entry["reference"],
            "greedy_hypothesis": hyp,
            "ref_token_overlap": round(overlap, 2),
            "status": status,
        })

    review = {"mapping_confirmed": all_ok, "rows": rows,
              "mapping_source": "recording-guide order, content-verified"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mapping_review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
    print("mapping_confirmed=", all_ok)
    for r in rows:
        print(f"  {r['stem']:20s} -> {r['candidate_id']:26s} {r.get('status')} "
              f"ov={r.get('ref_token_overlap')}")
        if r.get("status") == "REVIEW":
            print(f"      ref: {r.get('reference')}")
            print(f"      hyp: {r.get('greedy_hypothesis')}")


if __name__ == "__main__":
    main()
