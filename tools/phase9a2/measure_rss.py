import json
import os
import tempfile
import wave

import numpy as np
import sherpa_onnx

try:
    import psutil
    _p = psutil.Process()
    def rss():
        return round(_p.memory_info().rss / 1024 / 1024, 1)
except Exception:
    def rss():
        return None

m = os.path.join(os.environ["LOCALAPPDATA"], "SayIt", "models",
                 "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8")
v = "artifacts/phase9/9A1/temp_bpe_vocab/bpe.vocab"


def rd(p):
    w = wave.open(p, "rb")
    sr = w.getframerate()
    d = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    w.close()
    return d.astype(np.float32) / 32768.0, sr


data, sr = rd("artifacts/phase9/9A2/corpus/PAIR_PG_TECHNICAL.wav")


def mk(method, hw=""):
    kw = dict(encoder=os.path.join(m, "encoder.int8.onnx"),
              decoder=os.path.join(m, "decoder.int8.onnx"),
              joiner=os.path.join(m, "joiner.int8.onnx"),
              tokens=os.path.join(m, "tokens.txt"),
              num_threads=4, provider="cpu",
              decoding_method=method, model_type="nemo_transducer")
    if method == "modified_beam_search":
        kw["modeling_unit"] = "bpe"
        kw["bpe_vocab"] = v
        if hw:
            kw["hotwords_file"] = hw
            kw["hotwords_score"] = 2.0
    return sherpa_onnx.OfflineRecognizer.from_transducer(**kw)


res = {"rss_metric": "process RSS MiB (psutil) if available, else null"}
res["rss_baseline"] = rss()
hw = os.path.join(tempfile.gettempdir(), "_hw9a2r.txt")
open(hw, "w", encoding="utf-8").write("PostgreSQL\n")
for name, method, h in [("greedy", "greedy_search", ""),
                        ("beam", "modified_beam_search", ""),
                        ("hotword", "modified_beam_search", hw)]:
    r = mk(method, h)
    s = r.create_stream()
    s.accept_waveform(sr, data)
    r.decode_stream(s)
    res["rss_after_" + name] = rss()
os.remove(hw)
json.dump(res, open("artifacts/phase9/9A2R/performance_rss.json", "w"), indent=2)
print(json.dumps(res))
