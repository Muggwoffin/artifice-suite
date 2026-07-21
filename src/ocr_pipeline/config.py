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
}

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


def reset():
    """Clear cached config (useful in tests)."""
    global _config_cache
    _config_cache = None
