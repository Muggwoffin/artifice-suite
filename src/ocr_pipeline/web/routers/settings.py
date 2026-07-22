"""Settings, document types, templates, and health-check routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from ... import config
from ..._prompts import DOCUMENT_TYPES

router = APIRouter(tags=["settings"])

_CONFIG_KEYS = (
    "lm_studio_url", "output_dir", "cleanup_model", "translate_model",
    "ocr_model", "document_type", "max_ocr_workers", "chunk_max_tokens",
    "resume", "confidence_enabled", "ollama_think",
)


@router.get("/api/config")
def get_config() -> dict:
    return {k: config.get(k) for k in _CONFIG_KEYS}


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

    lm_err = check_lm_studio()
    models = [config.get("cleanup_model"), config.get("translate_model")]
    ollama_errors = check_ollama(models)
    ollama_reachable = not any("Cannot reach" in e for e in ollama_errors)

    return {
        "lm_studio": {"ok": lm_err is None, "detail": lm_err,
                      "url": config.get("lm_studio_url")},
        "ollama": {"ok": ollama_reachable,
                  "detail": None if ollama_reachable else ollama_errors[0]},
        "models": [
            {"name": m, "ok": ollama_reachable and not any(m in e for e in ollama_errors)}
            for m in models
        ],
    }
