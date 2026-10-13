import hashlib
import os
import shutil
import tarfile
import tempfile
from typing import Callable, Optional

import requests

from ....utils.logger import get_logger
from ..file_utils import get_models_dir
from .registry import ModelFile, ModelInfo, get_model_by_id

ProgressCallback = Callable[[int, int], None]
StatusCallback = Callable[[str], None]


class ModelDownloader:
    def __init__(self):
        self._cancelled = False
        self._logger = get_logger(__name__)

    def download(
        self,
        model_id: str,
        on_progress: Optional[ProgressCallback] = None,
        on_status: Optional[StatusCallback] = None,
    ) -> bool:
        self._cancelled = False

        model_info = get_model_by_id(model_id)
        if not model_info:
            raise ValueError(f"Unknown model: {model_id}")

        models_dir = get_models_dir()
        os.makedirs(models_dir, exist_ok=True)

        if model_info.is_multi_file:
            return self._download_multi_file(
                model_info, models_dir, on_progress, on_status
            )
        return self._download_archive(model_info, models_dir, on_progress, on_status)

    # -- legacy tar.bz2 archive path (unchanged behaviour) -----------------
    def _download_archive(
        self,
        model_info: ModelInfo,
        models_dir: str,
        on_progress: Optional[ProgressCallback],
        on_status: Optional[StatusCallback],
    ) -> bool:
        url = model_info.url
        self._logger.info(f"Downloading model from {url}")

        if on_status:
            on_status("Downloading...")

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".tar.bz2", delete=False
            ) as tmp_file:
                tmp_path = tmp_file.name

                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 8192

                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self._cancelled:
                        self._logger.info("Download cancelled")
                        return False

                    tmp_file.write(chunk)
                    downloaded += len(chunk)

                    if on_progress and total_size > 0:
                        on_progress(downloaded, total_size)

            self._logger.info(f"Extracting to {models_dir}")
            if on_status:
                on_status("Extracting files...")
            with tarfile.open(tmp_path, "r:bz2") as tar:
                tar.extractall(path=models_dir, filter="data")

            self._logger.info(f"Model {model_info.id} downloaded successfully")
            return True

        except requests.RequestException as e:
            self._logger.error(f"Download failed: {e}")
            raise
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # -- multi-file HF path (IndicConformer hi/kn) -------------------------
    def _download_multi_file(
        self,
        model_info: ModelInfo,
        models_dir: str,
        on_progress: Optional[ProgressCallback],
        on_status: Optional[StatusCallback],
    ) -> bool:
        """Fetch each declared file into the model directory.

        - Aggregate progress is reported across all files so the UI shows one
          continuous bar.
        - Each file is written to a temp path and atomically renamed, so an
          interrupted/cancelled download never leaves a half-written file that
          would be mistaken for a valid model.
        - ``dest`` is sanitised to prevent path traversal outside the model dir.
        - When a published sha256 is present it is verified; a mismatch raises.
        - On any failure or cancel, partial output for THIS download is removed.
        """
        model_dir = os.path.join(models_dir, model_info.id)
        os.makedirs(model_dir, exist_ok=True)

        files = model_info.files

        # Pre-flight: determine total bytes via HEAD so aggregate progress is
        # meaningful. Missing content-length (LFS) degrades gracefully to a
        # per-file byte count with an unknown grand total.
        per_file_total = {}
        grand_total = 0
        for f in files:
            try:
                head = requests.head(f.url, allow_redirects=True, timeout=30)
                size = int(head.headers.get("content-length", 0))
            except requests.RequestException:
                size = 0
            per_file_total[f.dest] = size
            grand_total += size

        downloaded_total = 0
        written: list[str] = []
        try:
            for f in files:
                if self._cancelled:
                    self._logger.info("Download cancelled")
                    self._cleanup(written)
                    return False

                dest_path = self._safe_dest(model_dir, f.dest)
                if on_status:
                    on_status(f"Downloading {f.dest}...")

                before = downloaded_total
                downloaded_total = self._download_one(
                    f,
                    dest_path,
                    grand_total,
                    before,
                    on_progress,
                )
                written.append(dest_path)

                if self._cancelled:
                    self._cleanup(written)
                    return False

            self._logger.info(f"Model {model_info.id} downloaded successfully")
            return True
        except Exception as e:
            self._logger.error(f"Multi-file download failed: {e}")
            self._cleanup(written)
            raise

    def _download_one(
        self,
        f: ModelFile,
        dest_path: str,
        grand_total: int,
        already_done: int,
        on_progress: Optional[ProgressCallback],
    ) -> int:
        """Download a single file atomically. Returns the new cumulative byte
        count across the whole model download."""
        tmp_path = dest_path + ".part"
        hasher = hashlib.sha256() if f.sha256 else None
        cumulative = already_done
        try:
            response = requests.get(f.url, stream=True, timeout=30)
            response.raise_for_status()
            with open(tmp_path, "wb") as out:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._cancelled:
                        break
                    out.write(chunk)
                    if hasher:
                        hasher.update(chunk)
                    cumulative += len(chunk)
                    if on_progress and grand_total > 0:
                        on_progress(min(cumulative, grand_total), grand_total)

            if self._cancelled:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                return cumulative

            if hasher and f.sha256 and hasher.hexdigest().lower() != f.sha256.lower():
                raise RuntimeError(
                    f"Checksum mismatch for {f.dest}: expected {f.sha256}, "
                    f"got {hasher.hexdigest()}"
                )

            os.replace(tmp_path, dest_path)
            return cumulative
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _safe_dest(model_dir: str, dest: str) -> str:
        """Resolve ``dest`` inside ``model_dir``, rejecting path traversal."""
        model_dir_abs = os.path.abspath(model_dir)
        full = os.path.abspath(os.path.join(model_dir_abs, dest))
        if os.path.commonpath([model_dir_abs, full]) != model_dir_abs:
            raise ValueError(f"Unsafe model file path: {dest!r}")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        return full

    @staticmethod
    def _cleanup(paths: list[str]) -> None:
        for p in paths:
            try:
                if os.path.exists(p):
                    os.unlink(p)
            except OSError:
                pass

    def cancel(self) -> None:
        self._cancelled = True
