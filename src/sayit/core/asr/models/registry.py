import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from ..file_utils import get_models_dir, is_valid_model_dir

GITHUB_RELEASE_BASE = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models"
)


@dataclass
class ModelFile:
    """One remote file to fetch for a multi-file model.

    ``url``  absolute HTTPS source.
    ``dest`` filename to write inside the model directory.
    ``sha256`` optional authentic published hash for integrity verification.
    """

    url: str
    dest: str
    sha256: Optional[str] = None


@dataclass
class ModelInfo:
    id: str
    name: str
    type: str
    # Additive, optional metadata (defaults preserve all existing behaviour).
    language: str = "en"  # ISO code: "en", "hi", "kn"
    source: str = ""  # provenance / upstream repo
    license: str = ""  # license of the source weights
    # Multi-file download spec. When non-empty, the downloader fetches each
    # ``ModelFile`` individually (used by HF-hosted IndicConformer models that
    # share a root tokens.txt). When empty, the legacy tar.bz2 archive path is
    # used (unchanged for all existing English/Whisper models).
    files: List[ModelFile] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"{GITHUB_RELEASE_BASE}/{self.id}.tar.bz2"

    @property
    def is_multi_file(self) -> bool:
        return bool(self.files)


def _parse_model(item: dict) -> ModelInfo:
    data = dict(item)
    raw_files = data.pop("files", None) or []
    files = [ModelFile(**f) for f in raw_files]
    return ModelInfo(files=files, **data)


def load_models() -> List[ModelInfo]:
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, "models.json")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [_parse_model(item) for item in data]
    except Exception as e:
        print(f"Error loading models.json: {e}")
        return []


AVAILABLE_MODELS: List[ModelInfo] = load_models()


DownloadStatus = Literal["downloaded", "not_downloaded"]


def get_model_by_id(model_id: str) -> ModelInfo | None:
    for model in AVAILABLE_MODELS:
        if model.id == model_id:
            return model
    return None


def get_models_for_language(language: str) -> List[ModelInfo]:
    """Return models whose declared language matches ``language``."""
    return [m for m in AVAILABLE_MODELS if m.language == language]


def get_available_languages() -> List[str]:
    """Distinct languages that have at least one registered model, en first."""
    seen: Dict[str, None] = {}
    for m in AVAILABLE_MODELS:
        seen.setdefault(m.language, None)
    langs = list(seen.keys())
    langs.sort(key=lambda c: (c != "en", c))
    return langs


def is_model_downloaded(model_id: str) -> bool:
    models_dir = get_models_dir()
    model_path = os.path.join(models_dir, model_id)

    if not os.path.isdir(model_path):
        return False

    return is_valid_model_dir(model_path)


def get_model_download_status(model_id: str) -> DownloadStatus:
    return "downloaded" if is_model_downloaded(model_id) else "not_downloaded"


def get_all_models_with_status() -> List[tuple[ModelInfo, DownloadStatus]]:
    return [(model, get_model_download_status(model.id)) for model in AVAILABLE_MODELS]


def get_installed_asr_models() -> List[str]:
    models_dir = get_models_dir()

    if not os.path.exists(models_dir):
        return []

    models = [
        name
        for name in os.listdir(models_dir)
        if os.path.isdir(os.path.join(models_dir, name))
        and is_valid_model_dir(os.path.join(models_dir, name))
    ]
    models.sort()
    return models


def delete_asr_model(model_name: str) -> tuple[bool, str]:
    import shutil

    models_dir = get_models_dir()
    model_path = os.path.join(models_dir, model_name)

    if not os.path.exists(model_path):
        return False, f"Model '{model_name}' not found"

    if not os.path.isdir(model_path):
        return False, f"'{model_name}' is not a directory"

    try:
        shutil.rmtree(model_path)
        return True, f"Deleted '{model_name}'"
    except Exception as e:
        return False, f"Failed to delete model: {str(e)}"
