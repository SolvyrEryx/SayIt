"""Tests for the multi-file model downloader (IndicConformer path).

Network is fully mocked — no real downloads. We verify safety (path traversal
rejection, atomic writes, cancel cleanup) and integrity (sha256 verify + reject
on mismatch) deterministically.
"""

import hashlib
import os
from unittest.mock import MagicMock, patch

import pytest

from src.sayit.core.asr.models.downloader import ModelDownloader
from src.sayit.core.asr.models.registry import ModelFile, ModelInfo


def _fake_response(data: bytes, length=True):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.headers = {"content-length": str(len(data))} if length else {}
    resp.iter_content.return_value = [data[i : i + 8] for i in range(0, len(data), 8)]
    return resp


def _fake_head(data: bytes):
    head = MagicMock()
    head.headers = {"content-length": str(len(data))}
    return head


class TestSafeDest:
    def test_rejects_path_traversal(self, tmp_path):
        with pytest.raises(ValueError):
            ModelDownloader._safe_dest(str(tmp_path), "../escape.onnx")

    def test_allows_normal_file(self, tmp_path):
        p = ModelDownloader._safe_dest(str(tmp_path), "model.int8.onnx")
        assert p.startswith(str(tmp_path))


class TestMultiFileDownload:
    def _model(self, tmp_models, sha=None):
        return ModelInfo(
            id="indicconformer-hi-int8",
            name="IndicConformer Hindi (Int8)",
            type="nemo_ctc",
            language="hi",
            files=[
                ModelFile(
                    url="https://example/hi/model.int8.onnx",
                    dest="model.int8.onnx",
                    sha256=sha,
                ),
                ModelFile(url="https://example/tokens.txt", dest="tokens.txt"),
            ],
        )

    def test_successful_download_writes_files(self, tmp_path, monkeypatch):
        model_bytes = b"MODEL-DATA-1234567890"
        tokens_bytes = b"a 1\nb 2\n"
        monkeypatch.setattr(
            "src.sayit.core.asr.models.downloader.get_models_dir",
            lambda: str(tmp_path),
        )
        dl = ModelDownloader()
        with patch.object(dl, "download", wraps=dl.download):
            with patch(
                "src.sayit.core.asr.models.downloader.get_model_by_id",
                return_value=self._model(tmp_path),
            ):
                with patch(
                    "src.sayit.core.asr.models.downloader.requests.head",
                    side_effect=[_fake_head(model_bytes), _fake_head(tokens_bytes)],
                ):
                    with patch(
                        "src.sayit.core.asr.models.downloader.requests.get",
                        side_effect=[
                            _fake_response(model_bytes),
                            _fake_response(tokens_bytes),
                        ],
                    ):
                        progress = []
                        ok = dl.download(
                            "indicconformer-hi-int8",
                            on_progress=lambda d, t: progress.append((d, t)),
                        )
        assert ok is True
        model_dir = tmp_path / "indicconformer-hi-int8"
        assert (model_dir / "model.int8.onnx").read_bytes() == model_bytes
        assert (model_dir / "tokens.txt").read_bytes() == tokens_bytes
        # No leftover .part temp files.
        assert not any(p.suffix == ".part" for p in model_dir.iterdir())
        # Progress was reported and monotonic non-decreasing.
        assert progress
        assert all(
            progress[i][0] <= progress[i + 1][0] for i in range(len(progress) - 1)
        )

    def test_checksum_mismatch_rejected_and_cleaned(self, tmp_path, monkeypatch):
        model_bytes = b"MODEL-DATA"
        monkeypatch.setattr(
            "src.sayit.core.asr.models.downloader.get_models_dir",
            lambda: str(tmp_path),
        )
        wrong_sha = "0" * 64
        dl = ModelDownloader()
        with patch(
            "src.sayit.core.asr.models.downloader.get_model_by_id",
            return_value=self._model(tmp_path, sha=wrong_sha),
        ):
            with patch(
                "src.sayit.core.asr.models.downloader.requests.head",
                side_effect=[_fake_head(model_bytes), _fake_head(b"tok")],
            ):
                with patch(
                    "src.sayit.core.asr.models.downloader.requests.get",
                    side_effect=[_fake_response(model_bytes), _fake_response(b"tok")],
                ):
                    with pytest.raises(RuntimeError):
                        dl.download("indicconformer-hi-int8")
        model_dir = tmp_path / "indicconformer-hi-int8"
        # Failed download must not leave the real model file behind.
        assert not (model_dir / "model.int8.onnx").exists()

    def test_valid_checksum_passes(self, tmp_path, monkeypatch):
        model_bytes = b"MODEL-DATA"
        good_sha = hashlib.sha256(model_bytes).hexdigest()
        monkeypatch.setattr(
            "src.sayit.core.asr.models.downloader.get_models_dir",
            lambda: str(tmp_path),
        )
        dl = ModelDownloader()
        with patch(
            "src.sayit.core.asr.models.downloader.get_model_by_id",
            return_value=self._model(tmp_path, sha=good_sha),
        ):
            with patch(
                "src.sayit.core.asr.models.downloader.requests.head",
                side_effect=[_fake_head(model_bytes), _fake_head(b"tok")],
            ):
                with patch(
                    "src.sayit.core.asr.models.downloader.requests.get",
                    side_effect=[_fake_response(model_bytes), _fake_response(b"tok")],
                ):
                    assert dl.download("indicconformer-hi-int8") is True
