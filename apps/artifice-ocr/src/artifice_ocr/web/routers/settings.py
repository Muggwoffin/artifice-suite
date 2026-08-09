# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Settings, document types, templates, and health-check routes."""

from typing import Any

from fastapi import APIRouter, HTTPException

from model_harness.contract import EndpointRejected
from model_harness.endpoint_policy import EndpointPolicy

from ... import config
from ..._prompts import DOCUMENT_TYPES

router = APIRouter(tags=["settings"])

# ── Model endpoints ──────────────────────────────────────────────────────────
#
# The allowlist policy lives in ``model_harness.endpoint_policy`` — this app
# only wraps it with FastAPI's exception type.  See
# :class:`model_harness.endpoint_policy.EndpointPolicy` for the full
# rationale and constraint set.

_endpoint_policy = EndpointPolicy()


def _validate_base_url(raw: str, field_name: str) -> str:
    """Return *raw* after checking its scheme and host. Fails closed, loudly."""
    try:
        return _endpoint_policy.validate_url(raw)
    except EndpointRejected as e:
        raise HTTPException(status_code=400, detail=f"{field_name}: {e}") from e


_URL_FIELDS = ("ollama_url", "lm_studio_url", "api_base_url")

_CONFIG_KEYS = (
    "lm_studio_url", "ollama_url", "huggingface_token",
    "api_key", "api_base_url",
    "ocr_backend", "cleanup_backend", "translate_backend",
    "output_dir", "cleanup_model", "translate_model",
    "ocr_model", "document_type", "max_ocr_workers", "chunk_max_tokens",
    "resume", "confidence_enabled", "ollama_think",
    "tropy_last_path", "tropy_last_export_path",
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
    # Validate endpoint URLs before persisting — a bad value should be
    # refused when entered rather than only when used.
    for field in _URL_FIELDS:
        if field in allowed and allowed[field]:
            _validate_base_url(allowed[field], field)
    config.apply_overrides(allowed)
    config.save_user_settings(allowed)
    return {"ok": True}


@router.post("/api/config/reset")
def reset_config() -> dict:
    config.reset()
    config.load_config()
    return {k: _redact_config(k, config.get(k)) for k in _CONFIG_KEYS}


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
    from model_harness.discovery import probe_endpoint_sync

    backends = {
        config.get("ocr_backend") or "lm_studio",
        config.get("cleanup_backend") or "ollama",
        config.get("translate_backend") or "ollama",
    }

    results: dict[str, Any] = {}

    if "lm_studio" in backends:
        lm_studio_url = config.get("lm_studio_url") or "http://localhost:1234/v1"
        probe = probe_endpoint_sync(lm_studio_url, policy=_endpoint_policy, timeout_s=5)
        results["lm_studio"] = {
            "ok": probe.reachable,
            "detail": None if probe.reachable else (probe.hint or "Cannot reach LM Studio"),
            "url": lm_studio_url,
        }

    if "ollama" in backends:
        models = [config.get("ocr_model"), config.get("cleanup_model"), config.get("translate_model")]
        ollama_url = config.get("ollama_url") or "http://localhost:11434"
        probe = probe_endpoint_sync(ollama_url, policy=_endpoint_policy, timeout_s=10)
        ollama_reachable = probe.reachable
        available = set(probe.models)
        results["ollama"] = {
            "ok": ollama_reachable,
            "detail": None if ollama_reachable else (probe.hint or "Cannot reach Ollama"),
            "url": ollama_url,
        }
        results["models"] = [
            {"name": m, "ok": ollama_reachable and m in available}
            for m in models if m
        ]

    if "huggingface" in backends:
        token = config.get("huggingface_token")
        results["huggingface"] = {
            "ok": bool(token),
            "detail": None if token else "No Hugging Face token configured",
        }

    if "api_key" in backends:
        base_url = config.get("api_base_url") or "https://api.openai.com/v1"
        from ..._backend import get_client
        ok, detail = get_client("api_key").health_check()
        results["api_key"] = {"ok": ok, "detail": detail, "url": base_url}

    return results
