"""Settings, document types, templates, and health-check routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from ... import config
from ..._prompts import DOCUMENT_TYPES

router = APIRouter(tags=["settings"])

_CONFIG_KEYS = (
    "lm_studio_url", "ollama_url", "huggingface_token",
    "api_key", "api_base_url",
    "ocr_backend", "cleanup_backend", "translate_backend",
    "output_dir", "cleanup_model", "translate_model",
    "ocr_model", "document_type", "max_ocr_workers", "chunk_max_tokens",
    "resume", "confidence_enabled", "ollama_think",
)

# Keys whose values must not be returned verbatim in API responses.
_REDACTED_KEYS = frozenset({"api_key", "huggingface_token"})

REDACTED_PLACEHOLDER = "*" * 12


def _redact_config(key: str, value: str) -> str:
    """Return a placeholder if *key* holds a secret that is configured."""
    if key in _REDACTED_KEYS and value:
        return REDACTED_PLACEHOLDER
    return value


@router.get("/api/config")
def get_config() -> dict:
    return {k: _redact_config(k, config.get(k)) for k in _CONFIG_KEYS}


@router.post("/api/config")
def set_config(overrides: dict[str, Any]) -> dict:
    allowed = {k: v for k, v in overrides.items() if k in config.PERSISTED_KEYS}
    config.apply_overrides(allowed)
    config.save_user_settings(allowed)
    return {"ok": True}


@router.post("/api/config/reset")
def reset_config() -> dict:
    config.reset()
    config.load_config()
    return {k: config.get(k) for k in _CONFIG_KEYS}


@router.get("/api/templates")
def list_templates() -> dict:
    templates = config.get("run_templates") or {}
    return {"templates": templates}


@router.post("/api/templates/save")
def save_template(data: dict) -> dict:
    name = data.get("name")
    template_config = data.get("config", {})
    if not name:
        raise HTTPException(status_code=400, detail="Template name is required")
    templates = dict(config.get("run_templates") or {})
    templates[name] = template_config
    config.apply_overrides({"run_templates": templates})
    config.save_user_settings({"run_templates": templates})
    return {"ok": True, "templates": templates}


@router.post("/api/templates/delete")
def delete_template(data: dict) -> dict:
    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Template name is required")
    templates = dict(config.get("run_templates") or {})
    templates.pop(name, None)
    config.apply_overrides({"run_templates": templates})
    config.save_user_settings({"run_templates": templates})
    return {"ok": True, "templates": templates}


@router.post("/api/templates/apply")
def apply_template(data: dict) -> dict:
    name = data.get("name")
    templates = config.get("run_templates") or {}
    if name not in templates:
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found")
    overrides = templates[name]
    config.apply_overrides(overrides)
    config.save_user_settings(overrides)
    return {"ok": True}


@router.get("/api/document-types")
def document_types() -> dict:
    return {"types": DOCUMENT_TYPES}


@router.get("/api/health")
def health_check() -> dict:
    from ...utils import check_lm_studio, check_ollama

    backends = {
        config.get("ocr_backend") or "lm_studio",
        config.get("cleanup_backend") or "ollama",
        config.get("translate_backend") or "ollama",
    }

    results: dict[str, Any] = {}

    if "lm_studio" in backends:
        lm_err = check_lm_studio(config.get("lm_studio_url"))
        results["lm_studio"] = {
            "ok": lm_err is None,
            "detail": lm_err,
            "url": config.get("lm_studio_url"),
        }

    if "ollama" in backends:
        models = [config.get("ocr_model"), config.get("cleanup_model"), config.get("translate_model")]
        ollama_url = config.get("ollama_url")
        ollama_errors = check_ollama(models, url=ollama_url)
        ollama_reachable = not any("Cannot reach" in e for e in ollama_errors)
        results["ollama"] = {
            "ok": ollama_reachable,
            "detail": None if ollama_reachable else ollama_errors[0],
            "url": ollama_url or "http://localhost:11434",
        }
        results["models"] = [
            {"name": m, "ok": ollama_reachable and not any(m in e for e in ollama_errors)}
            for m in models if m
        ]

    if "huggingface" in backends:
        token = config.get("huggingface_token")
        results["huggingface"] = {
            "ok": bool(token),
            "detail": None if token else "No Hugging Face token configured",
        }

    if "api_key" in backends:
        api_key = config.get("api_key")
        base_url = config.get("api_base_url") or "https://api.openai.com/v1"
        if not api_key:
            results["api_key"] = {"ok": False, "detail": "No API key configured", "url": base_url}
        else:
            try:
                from openai import OpenAI
                client = OpenAI(base_url=base_url, api_key=api_key)
                client.models.list()
                results["api_key"] = {"ok": True, "detail": None, "url": base_url}
            except Exception as exc:
                results["api_key"] = {"ok": False, "detail": str(exc), "url": base_url}

    return results
