# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""BYOM onboarding endpoints — discover, test, and persist a model endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from model_harness.contract import EndpointRejected
from model_harness.discovery import (
    ProbeResult,
    detect_local_servers,
    probe_endpoint,
)
from model_harness.endpoint_policy import EndpointPolicy
from model_harness.registry import (
    KNOWN_ENDPOINTS,
    HardwareTier,
    is_configured,
    recommendations_for_app,
)
from pydantic import BaseModel

from artifice_graph.config import EmbeddingConfig, LLMConfig, PipelineConfig

from ..config_helper import load_saved_config, save_user_config

router = APIRouter(prefix="/api/byom", tags=["byom"])

_policy = EndpointPolicy()

# ── Display-name mapping ─────────────────────────────────────────────────────


def _name_for_probe(r: ProbeResult) -> str:
    """Return a human-readable name for a probe result, derived from the
    registry when the provider matches a known endpoint."""
    for info in KNOWN_ENDPOINTS.values():
        if info.provider == r.provider:
            return info.display_name
    return str(r.provider) if r.provider else r.url


# ── Recommendations helper ──────────────────────────────────────────────────


def _byom_recommendations(app_key: str) -> dict:
    """Serialise :func:`recommendations_for_app` for all three hardware tiers.

    Uses the real ``ModelRecommendation`` field names (``model_name``,
    ``provider``, ``vision``, ``min_vram_gb``) — NOT ``{name, why, size_bytes}``.
    See the KNOWN CONTRACT MISMATCH comment atop ``byom.js``.
    """
    tier_keys = {
        "laptop": HardwareTier.LAPTOP,
        "desktop": HardwareTier.DESKTOP,
        "mac_unified": HardwareTier.MAC_UNIFIED,
    }
    result: dict[str, list[dict]] = {}
    for key, tier in tier_keys.items():
        try:
            recs = recommendations_for_app(app_key, tier)
        except KeyError:
            recs = []
        result[key] = [
            {
                "model_name": r.model_name,
                "provider": r.provider,
                "vision": r.vision,
                "min_vram_gb": r.min_vram_gb,
                "ethos_badges": list(r.ethos_badges),
                "role": r.role,
                "notes": r.notes,
            }
            for r in recs
        ]
    return result


# ── Request model ────────────────────────────────────────────────────────────


class TestRequest(BaseModel):
    url: str
    api_key: str = ""


# ── GET /api/byom/state ─────────────────────────────────────────────────────


@router.get("/state")
def byom_state() -> dict:
    """Return current BYOM configuration — no network calls, no probing."""
    cfg = load_saved_config()
    if cfg is not None:
        base_url = cfg.llm.base_url or ""
        api_key = cfg.llm.api_key or ""
        model = cfg.llm.model or ""
        emb_base_url = cfg.embedding.base_url or ""
        emb_model = cfg.embedding.model or ""
    else:
        base_url = ""
        api_key = ""
        model = ""
        emb_defaults = EmbeddingConfig()
        emb_base_url = emb_defaults.base_url
        emb_model = emb_defaults.model

    # An explicitly chosen model counts as configured, not just the endpoint.
    configured = is_configured(
        base_url, api_key, defaults=("http://localhost:11434/v1",), model=model
    )
    emb_configured = is_configured(
        emb_base_url, defaults=("http://localhost:11434",), model=emb_model
    )

    return {
        "app": "artifice-graph",
        "configured": configured,
        "endpoint": base_url or None,
        "model": model or None,
        "recommendations": _byom_recommendations("artifice-graph"),
        "embedding": {
            "configured": emb_configured,
            "endpoint": emb_base_url or None,
            "model": emb_model or None,
        },
    }


# ── GET /api/byom/detect ────────────────────────────────────────────────────


@router.get("/detect")
async def byom_detect() -> dict:
    """Probe known local endpoints and return results."""
    results = await detect_local_servers(policy=_policy)
    endpoints = [
        {
            "url": r.url,
            "name": _name_for_probe(r),
            "provider": r.provider,
            "reachable": r.reachable,
            "models": list(r.models),
            "hint": r.hint,
        }
        for r in results
    ]
    return {"endpoints": endpoints}


# ── POST /api/byom/test ─────────────────────────────────────────────────────


@router.post("/test")
async def byom_test(req: TestRequest) -> dict:
    """Validate and probe a user-supplied endpoint URL.

    On success the endpoint is persisted so the next ``/api/byom/state``
    reports ``configured: True``.
    """
    try:
        _policy.validate_url(req.url)
    except EndpointRejected as exc:
        exc_str = str(exc)
        return JSONResponse(status_code=400, content={"hint": exc_str, "error": exc_str})

    result = await probe_endpoint(req.url, policy=_policy)

    if result.reachable and req.api_key is not None:
        saved = load_saved_config()
        if saved is not None:
            saved.llm.base_url = req.url
            saved.llm.api_key = req.api_key
            save_user_config(saved)
        else:
            cfg = PipelineConfig(llm=LLMConfig(base_url=req.url, api_key=req.api_key))
            save_user_config(cfg)

    return {
        "reachable": result.reachable,
        "provider": result.provider,
        "models": list(result.models),
        "hint": result.hint,
    }


# ── POST /api/byom/model ────────────────────────────────────────────────────


class ModelRequest(BaseModel):
    """A per-role model choice. Graph has two roles: chat and embedding."""

    model: str = ""
    role: str = "chat"


@router.post("/model")
def byom_set_model(req: ModelRequest) -> dict:
    """Persist the user's model choice for a role.

    Graph previously had **no in-app way to set a model at all** — the Hub was
    the only writer, so a user running graph directly had to hand-edit
    config.json. This closes that.

    An empty ``model`` clears the choice deliberately, returning graph to
    per-run resolution against whatever the endpoint serves. That is a
    supported state, not an error.
    """
    if req.role not in ("chat", "embedding"):
        return JSONResponse(
            status_code=400,
            content={
                "error": f"artifice-graph has no {req.role!r} role; expected 'chat' or 'embedding'."
            },
        )

    chosen = req.model.strip()
    saved = load_saved_config() or PipelineConfig()
    if req.role == "chat":
        saved.llm.model = chosen
    else:
        saved.embedding.model = chosen
    save_user_config(saved)

    return {"model": chosen or None, "role": req.role}


# ── POST /api/byom/test-embedding ────────────────────────────────────────────


@router.post("/test-embedding")
async def byom_test_embedding(req: TestRequest) -> dict:
    """Validate and probe a user-supplied embedding endpoint URL.

    On success the embedding endpoint is persisted so the next
    ``/api/byom/state`` reports ``embedding.configured: True``.
    """
    # Validate the URL through the endpoint policy before any network call.
    try:
        _policy.validate_url(req.url)
    except EndpointRejected as exc:
        exc_str = str(exc)
        return JSONResponse(status_code=400, content={"hint": exc_str, "error": exc_str})

    result = await probe_endpoint(req.url, policy=_policy)

    if result.reachable and req.api_key is not None:
        saved = load_saved_config()
        if saved is not None:
            saved.embedding.base_url = req.url
            save_user_config(saved)
        else:
            cfg = PipelineConfig(embedding=EmbeddingConfig(base_url=req.url))
            save_user_config(cfg)

    return {
        "reachable": result.reachable,
        "provider": result.provider,
        "models": list(result.models),
        "hint": result.hint,
    }
