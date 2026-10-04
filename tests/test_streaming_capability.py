"""Documents the Phase 6H streaming-capability finding (real, not a mock).

The application loads every model with Sherpa-ONNX's **offline** recognizer
(``OfflineRecognizer``). This test records the empirical reason true stateful
streaming is not available with the current default model: the offline Parakeet
TDT export cannot be loaded by the **online** recognizer
(``OnlineRecognizer.from_transducer``) — the native library aborts the process
because the encoder export has no streaming cache tensors.

Because the failure is a native abort (not a catchable Python exception), the
attempt is run in a subprocess and we assert it does NOT succeed. The test is
marked ``slow`` and SKIPS when the model is not installed; it never downloads.
"""

import os
import subprocess
import sys
import textwrap

import pytest

from src.sayit.core.asr.models.registry import is_model_downloaded

_MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"


@pytest.mark.slow
class TestStreamingCapability:
    def test_offline_parakeet_cannot_load_as_online(self):
        if not is_model_downloaded(_MODEL_ID):
            pytest.skip(f"Model '{_MODEL_ID}' not installed; this test never downloads.")

        # Child program: try to load the offline export via OnlineRecognizer and
        # print a sentinel on (unexpected) success. A native abort or any failure
        # means success is NOT printed.
        child = textwrap.dedent(
            f"""
            import os, sys
            import sherpa_onnx
            sys.path.insert(0, "src")
            from sayit.core.asr.file_utils import get_models_dir
            d = os.path.join(get_models_dir(), "{_MODEL_ID}")
            enc = os.path.join(d, "encoder.int8.onnx")
            dec = os.path.join(d, "decoder.int8.onnx")
            joi = os.path.join(d, "joiner.int8.onnx")
            tok = os.path.join(d, "tokens.txt")
            try:
                sherpa_onnx.OnlineRecognizer.from_transducer(
                    encoder=enc, decoder=dec, joiner=joi, tokens=tok,
                    num_threads=2, provider="cpu",
                )
                print("ONLINE_LOAD_SUCCESS")
            except Exception:
                print("ONLINE_LOAD_FAILED")
            """
        )
        proc = subprocess.run(
            [sys.executable, "-c", child],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
            timeout=180,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        # The offline export must NOT load as a streaming/online recognizer.
        assert "ONLINE_LOAD_SUCCESS" not in out, (
            "Unexpected: offline Parakeet export loaded as OnlineRecognizer; "
            "re-evaluate streaming feasibility."
        )

    def test_backend_uses_offline_recognizer(self):
        # Static guarantee independent of model installation: the backend code
        # path uses the OFFLINE recognizer factories only.
        from src.sayit.core.asr import backends

        src = backends.__file__
        with open(src, "r", encoding="utf-8") as f:
            code = f.read()
        assert "OfflineRecognizer.from_whisper" in code
        assert "OfflineRecognizer.from_transducer" in code
        assert "OnlineRecognizer" not in code
