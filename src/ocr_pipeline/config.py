import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs"

_DEFAULTS: dict[str, Any] = {
    "lm_studio_url": "http://localhost:1234/v1",
    "ocr_model": "allenai/olmocr-2-7b",
    "cleanup_model": "gemma4:12b",
    "translate_model": "translategemma:4b",
    "output_dir": "output",
    "translate_enabled": True,
    "resume": True,
    "max_ocr_workers": 2,
    # P4: Pipeline optimization & robustness
    "chunk_max_tokens": 3500,
    "chunk_overlap_tokens": 200,
    "confidence_enabled": True,
    "document_type": "default",
    # P7: throughput. Reasoning models burn ~17x the tokens they need on
    # mechanical cleanup; leaving this False keeps the cleanup stage fast.
    # Set True only if you swap in a model whose reasoning you actually want.
    "ollama_think": False,
    # Hard ceiling on generated tokens (None = no cap). A runaway-generation
    # guard; leave unset unless you have seen one, since a cap that bites
    # truncates the document silently.
    "max_output_tokens": None,
    # Degeneracy guard for the OCR stage. When a vision model is given an
    # image it fundamentally can't parse (confirmed cause: a scan with no
    # orientation metadata anywhere saying it was upside-down), greedy
    # decoding can hallucinate filler and then loop on it — one real page
    # produced 900+ lines of the same repeated sentence. Unlike the other
    # guards below, a rejected page has no source text to fall back to, so
    # this fails the item outright instead of silently writing the loop to
    # raw_ocr/ as if it were a real transcription.
    "ocr_repetition_guard": True,
    # Content-preservation guard for cleanup. When the model's output looks
    # lossy or has altered a proper noun, the raw text is kept instead, so a
    # page is either cleaned or untouched — never quietly truncated.
    "cleanup_guard": True,
    "cleanup_guard_max_deleted_words": 2,
    "cleanup_guard_min_length_ratio": 0.97,  # letters, not characters
    "cleanup_guard_protect_nouns": True,
    # Content-preservation guard for the structure stage. When the model's
    # output has altered any word, the original text is kept instead, so a
    # page is either structured or untouched — never reworded.
    "structure_guard": True,
    # An LLM asked to "translate into English" text that is already English
    # has nothing to genuinely translate, and reliably "helps" by rewording,
    # dropping, or otherwise rewriting it instead — corrupting an
    # already-correct document. When the language-detection pass confidently
    # identifies English, skip the translate call entirely and pass the
    # cleaned text through untouched. Only ever skips on a confident "en"
    # result; an uncertain/failed detection still translates as before.
    "skip_translation_if_english": True,
    # P6: GUI persistence
    "history_db": None,  # defaults to ~/.ocr_pipeline/history.db
    "gui_theme": "paper",  # "paper" (light) or "night" (dark)
}

_USER_DIR = Path.home() / ".ocr_pipeline"
_SETTINGS_PATH = _USER_DIR / "settings.json"

# Keys the GUI is allowed to persist between sessions.
PERSISTED_KEYS = (
    "lm_studio_url",
    "ocr_model",
    "cleanup_model",
    "translate_model",
    "output_dir",
    "max_ocr_workers",
    "resume",
    "document_type",
    "confidence_enabled",
    "chunk_max_tokens",
    "gui_theme",
    "ollama_think",
)

_config_cache: dict[str, Any] | None = None


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML file, merged over defaults.

    Resolution order:
      1. Explicit config_path argument
      2. OCR_PIPELINE_CONFIG env var
      3. configs/default.yaml (if it exists)
      4. Built-in _DEFAULTS only
    """
    global _config_cache

    if _config_cache is not None and config_path is None:
        return _config_cache

    merged = dict(_DEFAULTS)

    if config_path is None:
        config_path = os.environ.get("OCR_PIPELINE_CONFIG")
    if config_path is None:
        default_path = _CONFIG_DIR / "default.yaml"
        if default_path.exists():
            config_path = default_path

    if config_path is not None:
        p = Path(config_path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                file_cfg = yaml.safe_load(f) or {}
            merged.update(file_cfg)

    env_overrides = {
        "ocr_model": "OCR_MODEL",
        "cleanup_model": "CLEANUP_MODEL",
        "translate_model": "TRANSLATE_MODEL",
        "lm_studio_url": "LM_STUDIO_URL",
        "output_dir": "OUTPUT_DIR",
    }
    for key, env_var in env_overrides.items():
        val = os.environ.get(env_var)
        if val is not None:
            merged[key] = val

    _config_cache = merged
    return merged


def get(key: str, default: Any = None) -> Any:
    """Shorthand: get a single config value."""
    return load_config().get(key, default)


def apply_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply runtime overrides to the current config cache.

    Returns the updated config dict. Useful for GUI settings.
    """
    global _config_cache
    if _config_cache is None:
        load_config()
    _config_cache.update(overrides)
    return _config_cache


def load_user_settings() -> dict[str, Any]:
    """Read GUI-persisted settings from ~/.ocr_pipeline/settings.json."""
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        import json
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if k in PERSISTED_KEYS}
    except Exception:
        return {}


def save_user_settings(settings: dict[str, Any]) -> None:
    """Persist GUI settings. Only whitelisted keys are written.

    Merges onto whatever is already saved rather than replacing the file
    outright. The desktop Settings tab always saves its full field set, so it
    never noticed, but the web build persists single fields in isolation
    (`output_dir` alone, right after starting a run) — a plain overwrite would
    silently discard every other saved setting each time that happened.
    """
    import json
    _USER_DIR.mkdir(parents=True, exist_ok=True)
    merged = load_user_settings()
    merged.update({k: v for k, v in settings.items() if k in PERSISTED_KEYS})
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2)


def reset():
    """Clear cached config (useful in tests)."""
    global _config_cache
    _config_cache = None
