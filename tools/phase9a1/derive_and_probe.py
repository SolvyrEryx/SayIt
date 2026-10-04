"""Phase 9A.1 — derive bpe.vocab from tokens.txt and probe modeling_unit=bpe.

This is the critical difference from Phase 9A: 9A probed modified_beam_search
with modeling_unit="cjkchar" (and no bpe.vocab), which aborted. The current
upstream Parakeet hotword example instead uses modeling_unit="bpe" with a
bpe.vocab derived from tokens.txt. This script reproduces that derivation into
an ISOLATED temp directory (the model dir is never modified) and probes:

    probe=mbs_bpe_nohw   : modified_beam_search + modeling_unit=bpe, no hotwords
    probe=mbs_bpe_hw     : modified_beam_search + modeling_unit=bpe + hotwords

It is intended to be run as a SUBPROCESS so a native C++ abort terminates only
this process. It prints RESULT:<outcome> lines and never raises into a caller.

Usage (single probe):
    python derive_and_probe.py <model_dir> <bpe_vocab_path> <probe> [hotwords_file]
"""

from __future__ import annotations

import os
import sys


def derive_bpe_vocab(tokens_path: str, out_path: str) -> int:
    """Derive a SentencePiece-style vocab file from tokens.txt.

    tokens.txt lines are '<token> <id>'. sherpa-onnx's bpe_vocab expects
    '<token> <score>' lines (SentencePiece .vocab format). The upstream example
    derives a usable vocab from tokens.txt; we reproduce that by emitting each
    token with a score of 0 (scores are not used for hotword segmentation beyond
    presence). Special tokens (<unk>, <blk>, <s>, </s>, etc.) are preserved as
    written. Returns the number of entries written.
    """
    n = 0
    with open(tokens_path, encoding="utf-8") as f, open(
        out_path, "w", encoding="utf-8"
    ) as out:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            # Split only on the LAST space (token may itself be a space-like).
            parts = line.rsplit(" ", 1)
            if len(parts) != 2:
                continue
            token = parts[0]
            out.write(f"{token} 0\n")
            n += 1
    return n


def main():
    model_dir = sys.argv[1]
    bpe_vocab = sys.argv[2]
    probe = sys.argv[3]
    hotwords_file = sys.argv[4] if len(sys.argv) > 4 else ""

    import sherpa_onnx

    enc = os.path.join(model_dir, "encoder.int8.onnx")
    dec = os.path.join(model_dir, "decoder.int8.onnx")
    join = os.path.join(model_dir, "joiner.int8.onnx")
    tok = os.path.join(model_dir, "tokens.txt")

    kw = dict(
        encoder=enc, decoder=dec, joiner=join, tokens=tok,
        num_threads=2, provider="cpu",
        decoding_method="modified_beam_search", model_type="nemo_transducer",
        modeling_unit="bpe", bpe_vocab=bpe_vocab,
    )
    if probe == "mbs_bpe_hw":
        kw["hotwords_file"] = hotwords_file
        kw["hotwords_score"] = 2.0

    try:
        rec = sherpa_onnx.OfflineRecognizer.from_transducer(**kw)
        print("RESULT:LOADED")
        # Try a decode on the model's own test wav to confirm it runs.
        import wave

        import numpy as np

        wav = os.path.join(model_dir, "test_wavs", "0.wav")
        if os.path.exists(wav):
            w = wave.open(wav, "rb")
            sr = w.getframerate()
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            w.close()
            s = rec.create_stream()
            s.accept_waveform(sr, data.astype(np.float32) / 32768.0)
            rec.decode_stream(s)
            print("RESULT:DECODED:" + repr(s.result.text[:80]))
    except BaseException as e:
        print("RESULT:PYERROR:" + type(e).__name__ + ":" + str(e)[:200])


if __name__ == "__main__":
    main()
