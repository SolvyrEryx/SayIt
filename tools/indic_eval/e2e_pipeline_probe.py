"""End-to-end REAL-pipeline smoke test for Hindi/Kannada using the INSTALLED
packaged bundle. Audio source is a real recorded FLEURS clip (not live human
voice, which no automated agent can produce), fed through the app's actual
TranscriptionWorkerThread -> correction -> TextOutputController clipboard/paste
path, inserting into a foreground Notepad window.

Clearly labelled: this validates the real transcription+insertion pipeline with
RECORDED audio injection, not live-microphone human speech.
"""

import io
import os
import struct
import sys
import time

import numpy as np

root = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "SayIt")
sys.path.insert(0, os.path.join(root, "app"))
sys.path.insert(0, os.path.join(root, "app_packages"))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import sayit  # noqa: E402

print("sayit bundle:", sayit.__file__)

from sayit.core.asr.transcriber import TranscriptionEngine  # noqa: E402
from sayit.core.asr.transcription_worker import TranscriptionWorkerThread  # noqa: E402
from sayit.core.output.text_output import TextOutputController  # noqa: E402


def wav_f32(b):
    assert b[:4] == b"RIFF"
    pos = 12
    fmt = sr = bits = ch = None
    data = None
    while pos + 8 <= len(b):
        cid = b[pos : pos + 4]
        (sz,) = struct.unpack_from("<I", b, pos + 4)
        body = b[pos + 8 : pos + 8 + sz]
        if cid == b"fmt ":
            fmt, ch, sr, _, _, bits = struct.unpack_from("<HHIIHH", body, 0)
        elif cid == b"data":
            data = body
        pos += 8 + sz + (sz & 1)
    if fmt == 3 and bits == 32:
        a = np.frombuffer(data, dtype="<f4").astype(np.float32)
    elif fmt == 1 and bits == 16:
        a = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
    else:
        raise ValueError(f"fmt {fmt} bits {bits}")
    if ch and ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def first_clip(lang):
    import tarfile

    tar = os.path.join("artifacts", "indic_eval", lang, "dev.tar.gz")
    with tarfile.open(tar, "r:gz") as t:
        for m in t:
            if m.name.endswith(".wav"):
                return wav_f32(t.extractfile(m).read())
    raise RuntimeError("no clip")


app = QApplication.instance() or QApplication(sys.argv)
out = TextOutputController()

for lang, model in (("hi", "indicconformer-hi-int8"), ("kn", "indicconformer-kn-int8")):
    audio, sr = first_clip(lang)
    eng = TranscriptionEngine(model_name=model)
    eng.load_model()

    result = {}
    loop = QEventLoop()

    worker = TranscriptionWorkerThread(
        transcriber=eng,
        audio_data=audio,
        sample_rate=sr,
        vocabulary_replacements=[],
        llm_processor=None,
        enhancement=None,
    )

    # finished = Signal(str raw, str final, object, object, object, object)
    def on_done(raw_text, final_text, *rest):
        result["raw"] = raw_text
        result["text"] = final_text
        loop.quit()

    def on_err(msg):
        result["error"] = msg
        loop.quit()

    worker.finished.connect(on_done)
    worker.error.connect(on_err)
    worker.start()
    QTimer.singleShot(60000, loop.quit)  # safety timeout
    loop.exec()

    text = result.get("text") or ""
    nonlatin = any(ord(c) > 0x900 for c in text)
    print(f"[{lang}] worker transcript: {text[:80]}")
    print(f"[{lang}] native-script output: {nonlatin}")

    # Real insertion via the app's TextOutputController (clipboard + paste).
    inserted = out.output_text(text)
    print(f"[{lang}] TextOutputController.output_text returned: {inserted}")
    eng.unload()

print("E2E REAL-PIPELINE (recorded-audio injection) DONE")
