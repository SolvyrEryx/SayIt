import json
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from platformdirs import user_config_path, user_data_path
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...utils.logger import get_logger

logger = get_logger(__name__)

MAX_HISTORY_ENTRIES = 20  # Number of transcription history records to keep

APP_NAME = "SayIt"

# Shipped default ASR model. Changed from the fp16 Parakeet to the int8 variant
# in Phase 6E: on the tested 16 GB CPU machine the fp16 model failed to
# initialize ("bad allocation"), while the int8 variant loaded, ran, and
# produced the best observed WER on the shared benchmark. The int8 model is the
# evidence-based CPU default, not a claim of universal optimality.
DEFAULT_MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"

# Known-compatible fallback used only when the configured/default model fails to
# initialize at startup (see app startup fallback). Intentionally the same as
# the default so a healthy default install needs no fallback.
FALLBACK_MODEL_ID = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8"

# Bounded allowed values for the optional Whisper Small CPU-thread setting.
# Explicit set (not a machine heuristic): 4 = current default, 6 and 8 optional.
WHISPER_CPU_THREAD_CHOICES = (4, 6, 8)
DEFAULT_WHISPER_CPU_THREADS = 4


def _get_default_enhancements() -> List[dict]:
    from ..transcript_processor.llm_processor import get_default_enhancements

    return [e.model_dump() for e in get_default_enhancements()]


def get_config_dir() -> Path:
    return user_config_path(APP_NAME, appauthor=False, ensure_exists=True)


def get_data_dir() -> Path:
    return user_data_path(APP_NAME, appauthor=False, ensure_exists=True)


class HotkeyConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=False)

    modifiers: list[str] = Field(default_factory=lambda: ["ctrl"])
    key: str = "space"

    @field_validator("modifiers")
    @classmethod
    def modifiers_not_empty(cls, v):
        if not v or not all(isinstance(m, str) and m.strip() for m in v):
            raise ValueError("modifiers must be a non-empty list of non-empty strings")
        return v

    @field_validator("key")
    @classmethod
    def key_not_empty(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("key must be a non-empty string")
        return v

    def to_display_string(self) -> str:
        parts = [mod.capitalize() for mod in self.modifiers]
        parts.append(self.key.capitalize())
        return " + ".join(parts)


class TranscriptionRecord(BaseModel):
    model_config = ConfigDict(validate_assignment=False)

    timestamp: str  # ISO format datetime
    raw_text: str
    enhanced_text: Optional[str] = None
    enhancement_name: Optional[str] = None
    cost_usd: Optional[float] = None

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptionRecord":
        return cls.model_validate(data)


class LLMProviderSettings(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=False)

    model: str = ""
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    saved_models: List[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "LLMProviderSettings":
        return cls.model_validate(data)


class Settings(BaseModel):
    model_config = ConfigDict(validate_assignment=False)

    sample_rate: int = Field(default=16000, ge=8000, le=192000)
    input_device: Optional[str] = None

    hotkey: HotkeyConfig = Field(default_factory=HotkeyConfig)
    model_id: str = DEFAULT_MODEL_ID

    # Whisper Small opt-in CPU thread count (Advanced / Performance). ONLY the
    # Whisper Small Higher-Accuracy path reads this; Parakeet (the production
    # default) is unaffected and always uses its existing thread configuration.
    # Bounded to an explicit allowed set {4, 6, 8}; 4 is the current default.
    # Anything else (invalid, legacy, machine-specific) safely falls back to 4.
    # NOT coupled to intelligence_experimental_enabled.
    whisper_small_cpu_threads: int = 4

    start_minimized: bool = False
    auto_start_on_login: bool = False
    first_run_complete: bool = False
    accessibility_permissions_granted: bool = False

    # Persistent transcript history is OFF by default for privacy. When False,
    # transcripts are never written to history.json. Failed-insertion recovery
    # does NOT depend on this: the app keeps the current transcript in memory
    # and on the clipboard regardless of this setting.
    history_enabled: bool = False

    # Local, deterministic post-ASR correction (Phase 6G). Both run entirely
    # on-device with no network. Conservative by design, so ON by default.
    technical_correction_enabled: bool = True
    structured_formatting_enabled: bool = True

    # Phase 8A: local context engine + profiles. Fully local; reads only active
    # application/window metadata (never content). Detection is ON by default
    # but the override is "auto", so out of the box the resolved profile is
    # Normal unless an app mapping matches — preserving today's 6G/6I behavior.
    #   context_detection_enabled: master switch for automatic detection.
    #   context_override:          "auto" or a Profile value (e.g. "developer").
    #                              A concrete value always wins over detection.
    #   context_app_mappings:      user app-substring -> profile value. Merged
    #                              over the built-in default map; user wins.
    context_detection_enabled: bool = True
    context_override: str = "auto"
    context_app_mappings: Dict[str, str] = Field(default_factory=dict)

    # Phase 8B-8G: local intelligence layer. All local, deterministic, and
    # explainable. Each feature can be disabled; a disabled feature's engine is
    # not consulted. The master switch gates the whole intelligence layer.
    intelligence_enabled: bool = True
    voice_edit_enabled: bool = True
    snippets_enabled: bool = True
    structure_enabled: bool = True
    developer_mode_enabled: bool = True
    # Phase 8C snippets: list of dicts (trigger, expansion, enabled, category,
    # inline, created_at, usage_count). Local only; never transmitted.
    snippets: List[dict] = Field(default_factory=list)
    # Phase 8E Safe Zones: user-configured protected application substrings and
    # the master enable. Recording is blocked while a protected app is
    # foreground. Reuses 8A detection; no new detector.
    safe_zones_enabled: bool = True
    protected_apps: List[str] = Field(default_factory=list)
    # Phase 8F explicit learning: suppression keys for corrections the user
    # chose "Never" to remember. No passive learning ever occurs.
    correction_never_list: List[str] = Field(default_factory=list)
    remember_corrections_enabled: bool = True

    # Phase 9J/9K: experimental post-ASR recognition-intelligence stack
    # (9C retrieval + 9D domain/canonical + 9F ranking/abstention + 9B
    # correction). OFF BY DEFAULT. When False, dictation behaves exactly as it
    # does today. When True, the pipeline runs on the raw transcript BEFORE the
    # existing 6G/6I/6J correction, and fails safe (returns raw text) on any
    # error. Disabling restores prior behavior immediately (rollback).
    intelligence_experimental_enabled: bool = False
    intelligence_threshold: float = Field(default=0.90, ge=0.0, le=1.0)

    # Domain-coverage expansion: opt-in technical domains the user works in.
    # These only take effect when the experimental intelligence is enabled, and
    # only ever act as a BOUNDED PRIOR in ranking (never a forced correction).
    # Empty lists -> conservative default (context-suggested developer domains
    # only). `domain_aware` turns the domain prior on; off keeps ARM B behavior.
    intelligence_domain_aware: bool = False
    enabled_domains: List[str] = Field(default_factory=list)
    disabled_domains: List[str] = Field(default_factory=list)

    enhancements: List[dict] = Field(default_factory=list)
    active_enhancement_id: Optional[str] = None
    llm_provider: str = "openai"
    llm_provider_settings: Dict[str, dict] = Field(default_factory=dict)
    vocabulary_replacements: List[Tuple[str, str]] = Field(default_factory=list)

    # Phase 6J: user-controlled custom vocabulary (spoken -> written). Stored as
    # a list of plain dicts (spoken, written, enabled, category, created_at,
    # usage_count). Local only; never transmitted. When empty, the legacy
    # vocabulary_replacements list is migrated on first use. No SQLite — reuses
    # the existing JSON settings persistence.
    custom_vocabulary: List[dict] = Field(default_factory=list)

    window_geometry: Optional[Tuple[int, int, int, int]] = None

    @field_validator("model_id")
    @classmethod
    def model_id_not_empty(cls, v):
        if not isinstance(v, str) or not v.strip():
            raise ValueError("model_id must be a non-empty string")
        return v

    @field_validator("whisper_small_cpu_threads")
    @classmethod
    def whisper_threads_in_allowed_set(cls, v):
        # Bounded + safe: anything not in the explicit allowed set (invalid type,
        # legacy value, out-of-range) falls back to the default of 4. This keeps
        # old/missing settings working and never selects a machine-specific
        # value automatically. Whisper-only; does not affect Parakeet.
        if v in WHISPER_CPU_THREAD_CHOICES:
            return v
        return DEFAULT_WHISPER_CPU_THREADS

    @classmethod
    def load(cls) -> "Settings":
        config_file = get_config_dir() / "settings.json"

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    data = json.load(f)

                # Filter to valid keys only
                valid_keys = cls.model_fields.keys()
                filtered_data = {k: v for k, v in data.items() if k in valid_keys}

                # Handle nested HotkeyConfig
                if "hotkey" in filtered_data and isinstance(
                    filtered_data["hotkey"], dict
                ):
                    try:
                        filtered_data["hotkey"] = HotkeyConfig.model_validate(
                            filtered_data["hotkey"]
                        )
                    except Exception:
                        logger.warning(
                            "Invalid hotkey configuration, resetting to default"
                        )
                        filtered_data["hotkey"] = HotkeyConfig()

                if "enhancements" in filtered_data:
                    if not isinstance(filtered_data["enhancements"], list):
                        filtered_data["enhancements"] = []

                # Migration from old flat LLM settings
                old_llm_model = data.get("llm_model")
                old_llm_api_key = data.get("llm_api_key")
                old_llm_api_base = data.get("llm_api_base")
                old_provider = data.get("llm_provider", "openai")

                if old_llm_model or old_llm_api_key or old_llm_api_base:
                    if "llm_provider_settings" not in filtered_data:
                        filtered_data["llm_provider_settings"] = {}
                    if old_provider not in filtered_data["llm_provider_settings"]:
                        filtered_data["llm_provider_settings"][old_provider] = {
                            "model": old_llm_model or "",
                            "api_key": old_llm_api_key,
                            "api_base": old_llm_api_base,
                        }
                    logger.info(
                        f"Migrated old LLM settings to per-provider format for '{old_provider}'"
                    )

                # Validate each field individually, falling back to defaults on error
                settings = cls._load_with_fallbacks(filtered_data)

                # _load_with_fallbacks builds via model_construct (validators are
                # bypassed), so an out-of-set INTEGER thread value (e.g. 5, 7, 12)
                # could survive. Enforce the bounded allowed set explicitly here
                # so an invalid persisted value always falls back to 4.
                if settings.whisper_small_cpu_threads not in WHISPER_CPU_THREAD_CHOICES:
                    settings.whisper_small_cpu_threads = DEFAULT_WHISPER_CPU_THREADS

                if not settings.enhancements:
                    settings.enhancements = _get_default_enhancements()

                return settings
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    f"Could not load settings: {e}. Using defaults.", exc_info=True
                )
                return cls()

        settings = cls()
        settings.enhancements = _get_default_enhancements()
        return settings

    @classmethod
    def _load_with_fallbacks(cls, data: dict) -> "Settings":
        defaults = cls()
        result_data = {}

        for field_name, field_info in cls.model_fields.items():
            if field_name in data:
                try:
                    # Validate individual field by creating partial model
                    test_data = {field_name: data[field_name]}
                    # For nested models, they're already validated
                    if field_name == "hotkey" and isinstance(
                        data[field_name], HotkeyConfig
                    ):
                        result_data[field_name] = data[field_name]
                    else:
                        cls.model_validate({**defaults.model_dump(), **test_data})
                        result_data[field_name] = data[field_name]
                except Exception as e:
                    default_val = getattr(defaults, field_name)
                    logger.warning(
                        f"Invalid {field_name} {data[field_name]!r}, resetting to {default_val}"
                    )
                    result_data[field_name] = default_val
            else:
                result_data[field_name] = getattr(defaults, field_name)

        return cls.model_construct(**result_data)

    def save(self) -> None:
        config_file = get_config_dir() / "settings.json"

        data = self.model_dump()

        with open(config_file, "w") as f:
            json.dump(data, f, indent=2)

    def reset_to_defaults(self) -> None:
        """Reset settings while preserving typed nested models."""
        default = Settings()
        for key in Settings.model_fields:
            setattr(self, key, deepcopy(getattr(default, key)))

    def get_active_enhancement(self) -> Optional["Enhancement"]:
        if not self.active_enhancement_id:
            return None

        from ..transcript_processor.llm_processor import Enhancement

        for enh_dict in self.enhancements:
            if enh_dict.get("id") == self.active_enhancement_id:
                return Enhancement.model_validate(enh_dict)

        return None

    def get_provider_settings(self, provider_id: str) -> LLMProviderSettings:
        if provider_id in self.llm_provider_settings:
            return LLMProviderSettings.model_validate(
                self.llm_provider_settings[provider_id]
            )
        return LLMProviderSettings()

    def set_provider_settings(
        self, provider_id: str, settings: LLMProviderSettings
    ) -> None:
        self.llm_provider_settings[provider_id] = settings.model_dump()

    @property
    def llm_model(self) -> str:
        return self.get_provider_settings(self.llm_provider).model

    @llm_model.setter
    def llm_model(self, value: str) -> None:
        self._update_provider_setting("model", value)

    @property
    def llm_api_key(self) -> Optional[str]:
        return self.get_provider_settings(self.llm_provider).api_key

    @llm_api_key.setter
    def llm_api_key(self, value: Optional[str]) -> None:
        self._update_provider_setting("api_key", value)

    @property
    def llm_api_base(self) -> Optional[str]:
        return self.get_provider_settings(self.llm_provider).api_base

    @llm_api_base.setter
    def llm_api_base(self, value: Optional[str]) -> None:
        self._update_provider_setting("api_base", value)

    def _update_provider_setting(self, attr: str, value) -> None:
        provider_settings = self.get_provider_settings(self.llm_provider)
        setattr(provider_settings, attr, value)
        self.set_provider_settings(self.llm_provider, provider_settings)


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings.load()
    return _settings_instance


def get_history_file() -> Path:
    return get_config_dir() / "history.json"


def load_history() -> List[TranscriptionRecord]:
    history_file = get_history_file()

    if not history_file.exists():
        return []

    try:
        with open(history_file, "r") as f:
            data = json.load(f)

        records = [TranscriptionRecord.from_dict(item) for item in data]
        return records
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.warning(f"Could not load history: {e}. Starting fresh.")
        return []


def save_history(records: List[TranscriptionRecord]) -> None:
    history_file = get_history_file()
    records = records[-MAX_HISTORY_ENTRIES:]

    data = [record.to_dict() for record in records]

    with open(history_file, "w") as f:
        json.dump(data, f, indent=2)


def add_history_record(record: TranscriptionRecord) -> None:
    records = load_history()
    records.append(record)
    save_history(records)


def clear_history() -> None:
    history_file = get_history_file()
    if history_file.exists():
        history_file.unlink()
