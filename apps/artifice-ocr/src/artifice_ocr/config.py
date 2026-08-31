# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import importlib.resources
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

# Resolved through importlib.resources, NOT a __file__-relative path.  This
# file is distributed as a frozen .exe/.dmg, where __file__ points inside a
# temporary extraction directory and any ``.parent.parent.parent`` walk lands
# somewhere meaningless.  The previous form was
# ``Path(__file__).resolve().parent.parent.parent / "configs"``, which also
# put configs under ``apps/artifice-ocr/configs/`` — outside the package —
# so the example config was excluded from the wheel entirely.
_CONFIG_DIR = importlib.resources.files("artifice_ocr") / "configs"

_DEFAULTS: dict[str, Any] = {
    "lm_studio_url": "http://localhost:1234/v1",
    # Model names are resolved at run time (see artifice_ocr._resolution):
    # an empty string means "no explicit choice — resolve from what the local
    # server actually serves".  Shipping a concrete name here was the bug: the
    # OCR default was a Hugging Face repo id, not an Ollama tag, so a default
    # install failed before the user did anything.
    "ocr_model": "",
    "cleanup_model": "",
    "translate_model": "",
    "output_dir": "output",
    "translate_enabled": True,
    "title_enabled": False,  # opt-in stage
    # Live Tropy project browsing (read-only .tpy). Enabled by default per the
    # maintainer's decision (2026-08-25): it restores the "select a project,
    # don't type a path" flow the JSON-LD rewrite dropped. Still gated by the
    # read-only connection guarantee; ARTIFICE_OCR_TROPY_LIVE_READ overrides it.
    "tropy_live_browse_enabled": True,
    # 0 discovers the port from Tropy's state and then tries the stable/beta
    # defaults (2019/2029). A non-zero value is an advanced override for a
    # Tropy instance launched with a custom ``--port``.
    "tropy_api_port": 0,
    # Direct write-back of OCR results into the Tropy project's notes /
    # transcriptions tables. Opt-in and default OFF: writing to the user's
    # research database is the highest-risk operation in the suite, so it is
    # never on unless the user turns it on explicitly. Restored 2026-08-25,
    # knowingly reversing ebd89e6, as an opt-in alongside the JSON-LD bridge.
    "tropy_writeback_enabled": False,
    "title_max_chars": 120,
    "resume": True,
    "max_ocr_workers": 2,
    # P4: Pipeline optimization & robustness
    "chunk_max_tokens": 3500,
    "chunk_overlap_tokens": 200,
    # Model context window, in tokens. 0 means "leave it to the backend" —
    # the model's own default — which is the behaviour before this setting
    # existed, so a config that predates it keeps working unchanged.
    #
    # This is NOT chunk_max_tokens. That splits *text* before sending it to
    # the cleanup/translate/structure stages. This is the size of the window
    # the model itself is loaded with, and it is what a page image overflows:
    # "request (4107 tokens) exceeds the available context size (4096)".
    #
    # Only Ollama honours it. LM Studio fixes context when it *loads* a model,
    # and hosted APIs set it server-side — for those the UI says where to
    # change it rather than sending a value that is silently ignored.
    "context_size": 0,
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
    # Phase 1 deterministic image pre-processing, applied before the page is
    # sent to the vision model. Off by default: a clean scan needs none of it,
    # and it must never change behaviour for an existing user who has not asked
    # for it. The master toggle is the one UI control; the per-step keys are
    # advanced/config-only and used when the master is on. See
    # docs/OCR_PREPROCESSING_PLAN.md and stages/preprocess.py.
    "preprocess_enabled": False,
    "preprocess_grayscale": True,
    "preprocess_illumination": True,
    "preprocess_autocontrast": True,
    "preprocess_gamma": 1.0,  # 1.0 = no gamma; <1 lightens, >1 darkens mid-tones
    # OCR engine selection. "vision_model" (default) routes an image to a vision
    # LLM; "tesseract" runs the locally-installed Tesseract binary instead — a
    # fast, offline, deterministic transcriber. Tesseract is NOT bundled: the
    # binary is detected on PATH (or at tesseract_path). See docs/
    # OCR_TESSERACT_ENGINE_PLAN.md and _tesseract.py.
    "ocr_engine": "vision_model",
    "tesseract_lang": "eng",  # e.g. "eng", "deu", "deu+eng"; needs the traineddata
    "tesseract_path": "",  # explicit binary path when it is not on PATH
    # Independent safety net: when a vision-model page fails (repetition-guard
    # rejection or exhausted retries) and Tesseract is available, retry that page
    # with Tesseract rather than failing it. Off by default; provenance is
    # recorded as "tesseract-fallback" in the page metadata.
    "tesseract_fallback_on_failure": False,
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
    "history_db": None,  # defaults to ~/.artifice_ocr/history.db
    "gui_theme": "paper",  # "paper" (light) or "night" (dark)
    # ``"auto"`` means "use whichever local server is reachable and can serve
    # a suitable model".  The previous default presumed LM Studio for OCR and
    # Ollama for cleanup/translate, which broke a user running only Ollama
    # (the setup the Hub itself installs).  An explicit ``"ollama"`` /
    # ``"lm_studio"`` / ``"huggingface"`` / ``"api_key"`` is still honoured.
    "ocr_backend": "auto",
    "cleanup_backend": "auto",
    "translate_backend": "auto",
    "ollama_url": "http://localhost:11434",
    "huggingface_token": "",
    "api_key": "",
    "api_base_url": "https://api.openai.com/v1",
    # User-approved folders — an explicit, user-granted extension of the
    # allowed-roots list. Each entry is an absolute directory the user picked
    # through the native folder dialog (the consent step), so a Tropy project
    # on an external drive can be opened without the env var.
    "approved_folders": [],
}

_USER_DIR = Path.home() / ".artifice_ocr"
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
    "context_size",
    "preprocess_enabled",
    "preprocess_grayscale",
    "preprocess_illumination",
    "preprocess_autocontrast",
    "preprocess_gamma",
    "ocr_engine",
    "tesseract_lang",
    "tesseract_path",
    "tesseract_fallback_on_failure",
    "gui_theme",
    "ollama_think",
    "run_templates",
    "onboarding_dismissed",
    "ocr_backend",
    "title_enabled",
    "title_max_chars",
    "cleanup_backend",
    "translate_backend",
    "ollama_url",
    "huggingface_token",
    "api_key",
    "api_base_url",
    "tropy_last_path",
    "tropy_last_export_path",
    "tropy_live_browse_enabled",
    "tropy_api_port",
    "tropy_writeback_enabled",
    "approved_folders",
)

_config_cache: dict[str, Any] | None = None


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML file, merged over defaults.

    Resolution order:
      1. Explicit config_path argument
      2. ARTIFICE_OCR_CONFIG env var
      3. configs/default.yaml (if it exists)
      4. Built-in _DEFAULTS only
    """
    global _config_cache

    if _config_cache is not None and config_path is None:
        return _config_cache

    merged = dict(_DEFAULTS)

    if config_path is None:
        config_path = os.environ.get("ARTIFICE_OCR_CONFIG")
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
        "ollama_url": "OLLAMA_URL",
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
    """Read GUI-persisted settings from ~/.artifice_ocr/settings.json."""
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        from secure_io import ensure_restricted

        ensure_restricted(_SETTINGS_PATH)
    except Exception:
        import logging

        logging.warning(
            "Could not restrict permissions on %s — continuing anyway",
            _SETTINGS_PATH,
        )
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
    from secure_io import is_restricted, write_private_json

    _USER_DIR.mkdir(parents=True, exist_ok=True)
    merged = load_user_settings()
    merged.update({k: v for k, v in settings.items() if k in PERSISTED_KEYS})
    write_private_json(_SETTINGS_PATH, merged)

    # Align write-time verification with the public is_restricted() contract
    # (see artifice-graph config_helper.save_user_config for rationale).
    if not is_restricted(_SETTINGS_PATH):
        write_private_json(_SETTINGS_PATH, merged)
        if not is_restricted(_SETTINGS_PATH):
            raise PermissionError(f"Failed to secure settings file after retry: {_SETTINGS_PATH}")


def reset():
    """Clear cached config (useful in tests)."""
    global _config_cache
    _config_cache = None
