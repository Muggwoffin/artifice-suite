# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""BYOM onboarding endpoints — discover, test, and persist a model endpoint.

This router is mounted WITHOUT a prefix on the FastAPI app in ``main.py``
so that ``byom.js``'s hard-coded ``/api/byom/*`` paths resolve correctly.
Transcribe's main router (``api/v1/routes.py``) already uses
``APIRouter(prefix="/api/v1")``, and BYOM must not live behind ``/api/v1``.
"""

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

from ...api.v1.routes import _load_inference_config, _save_inference_config

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
#
# As of 2026-08, the registry carries text-only model recommendations for
# ``artifice-transcribe``'s optional post-transcription inference endpoint
# (summarize / cleanup).  The ``try/except KeyError`` guard was written when
# the registry deliberately omitted transcribe, and it remains as correct
# defensive code for any app that might be absent in the future.
# Transcribe separately uses ``ASR_MODELS`` for the transcription engines
# themselves — those are ASR models pulled from Hugging Face, not LLMs.


def _byom_recommendations(app_key: str) -> dict:
    """Serialise :func:`recommendations_for_app` for all three hardware tiers.

    Returns text-only model recommendations for transcribe's post-
    transcription inference endpoint.  Transcribe uses
    :data:`~model_harness.registry.ASR_MODELS` separately for the
    transcription engines themselves.
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
    cfg = _load_inference_config()
    base_url = cfg.get("base_url") or ""
    api_key = cfg.get("api_key") or ""
    model_name = cfg.get("model_name") or ""

    # An explicitly chosen model counts as configured, not just the endpoint.
    configured = is_configured(
        base_url, api_key, defaults=("http://localhost:11434/v1",), model=model_name
    )

    return {
        "app": "artifice-transcribe",
        "configured": configured,
        "endpoint": base_url or None,
        "model": model_name or None,
        # The roles this app supports. Transcribe's BYOM endpoint is chat-only;
        # derived from the same mapping POST /model honours (_ROLE_SETTING) so
        # the picker can never drift from what the app actually maps.
        "roles": list(_ROLE_SETTING),
        "recommendations": _byom_recommendations("artifice-transcribe"),
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
        _save_inference_config(
            {
                "base_url": req.url,
                "api_key": req.api_key,
                "model_name": _load_inference_config().get("model_name", ""),
                "vision_enabled": _load_inference_config().get("vision_enabled", False),
            }
        )

    return {
        "reachable": result.reachable,
        "provider": result.provider,
        "models": list(result.models),
        "hint": result.hint,
    }


# ── POST /api/byom/model ────────────────────────────────────────────────────


class ModelRequest(BaseModel):
    """A per-role model choice.

    Transcribe's BYOM endpoint is the *optional* one used for summaries and
    cleanup, so its only role is ``chat``. The Whisper and diarization models
    are a separate stack with their own download flow and are not set here.
    """

    model: str = ""
    role: str = "chat"


# Role → the inference-config key it writes. Transcribe supports a single role;
# GET /state publishes these keys as `roles`, so the picker is built from what
# the app actually maps, never from the recommendations registry.
_ROLE_SETTING = {
    "chat": "model_name",
}


@router.post("/model")
def byom_set_model(req: ModelRequest) -> dict:
    """Persist the user's model choice.

    Transcribe had no save path for a model anywhere — not in the app and not
    in the Hub, which has no transcribe entry in its role map. With nothing
    configured, ``InferenceEngine`` used to take whatever the server listed
    first. This closes that.

    An empty ``model`` clears the choice deliberately, returning the app to
    per-run resolution. That is a supported state, not an error.
    """
    if req.role not in _ROLE_SETTING:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"artifice-transcribe has no {req.role!r} role; "
                f"expected one of {sorted(_ROLE_SETTING)}."
            },
        )

    chosen = req.model.strip()
    existing = _load_inference_config()
    _save_inference_config(
        {
            "base_url": existing.get("base_url", ""),
            "api_key": existing.get("api_key", ""),
            "model_name": chosen,
            "vision_enabled": existing.get("vision_enabled", False),
        }
    )
    return {"model": chosen or None, "role": "chat"}
