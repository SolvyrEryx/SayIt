"""Phase 9A.1 environment inventory (production env, read-only).

Records executable facts about the current production environment and the
EXISTING Parakeet model. Writes artifacts/phase9/9A1/environment.json.
No model files are modified; nothing is downloaded.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sayit.core.asr.file_utils import get_models_dir  # noqa: E402

MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"
OUT = Path("artifacts/phase9/9A1")


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    import sherpa_onnx

    model_dir = Path(get_models_dir()) / MODEL_ID
    files = sorted(
        [str(f.relative_to(model_dir)) for f in model_dir.rglob("*") if f.is_file()]
    ) if model_dir.is_dir() else []

    tokens = model_dir / "tokens.txt"
    tok_count = None
    if tokens.exists():
        tok_count = len(tokens.read_text(encoding="utf-8").splitlines())

    try:
        import psutil

        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        ram_gb = None

    env = {
        "phase": "9A.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sherpa_onnx_version": getattr(sherpa_onnx, "__version__", "unknown"),
        "python_version": sys.version.split()[0],
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_gb": ram_gb,
        "model_id": MODEL_ID,
        "model_dir": str(model_dir),
        "model_present": model_dir.is_dir(),
        "model_files": files,
        "model_size_bytes": _dir_size(model_dir) if model_dir.is_dir() else None,
        "tokens_txt_present": tokens.exists(),
        "tokens_count": tok_count,
        "bpe_vocab_present": (model_dir / "bpe.vocab").exists(),
        "bpe_model_present": (model_dir / "bpe.model").exists(),
        "model_type": "nemo_transducer",
        "production_decoding_method": "greedy_search",
        "production_provider": "cpu",
        "production_num_threads": 4,
    }

    # Baseline load + inference timing on the model's own test wav (read-only).
    wav = model_dir / "test_wavs" / "0.wav"
    if model_dir.is_dir() and wav.exists():
        w = wave.open(str(wav), "rb")
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        w.close()
        audio = data.astype(np.float32) / 32768.0
        t0 = time.perf_counter()
        rec = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(model_dir / "encoder.int8.onnx"),
            decoder=str(model_dir / "decoder.int8.onnx"),
            joiner=str(model_dir / "joiner.int8.onnx"),
            tokens=str(tokens), num_threads=4, provider="cpu",
            decoding_method="greedy_search", model_type="nemo_transducer",
        )
        t1 = time.perf_counter()
        s = rec.create_stream()
        s.accept_waveform(sr, audio)
        rec.decode_stream(s)
        t2 = time.perf_counter()
        env["baseline_load_time_s"] = round(t1 - t0, 4)
        env["baseline_infer_time_s"] = round(t2 - t1, 4)
        env["baseline_sample_transcript_len"] = len(s.result.text)

    (OUT / "environment.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    print("Wrote environment.json")
    print(json.dumps({k: env[k] for k in (
        "sherpa_onnx_version", "python_version", "model_present",
        "tokens_count", "bpe_vocab_present", "baseline_load_time_s",
        "baseline_infer_time_s") if k in env}, indent=2))


if __name__ == "__main__":
    main()
