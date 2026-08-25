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

from ..runtime import load_settings, save_settings

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
    settings = load_settings()
    base_url = settings.get("base_url") or ""
    model_name = settings.get("model_name") or ""

    # An explicitly chosen model counts as configured, not just the endpoint.
    configured = is_configured(base_url, model=model_name)

    return {
        "app": "artifice-draft",
        "configured": configured,
        "endpoint": base_url or None,
        "model": model_name or None,
        # The roles this app supports. Draft is chat-only; derived from the
        # same mapping POST /model honours (_ROLE_SETTING) so the picker can
        # never show a role the app cannot save, or omit one it can.
        "roles": list(_ROLE_SETTING),
        "recommendations": _byom_recommendations("artifice-draft"),
    }


# ── POST /api/byom/model ────────────────────────────────────────────────────


class ModelRequest(BaseModel):
    """A per-role model choice. Draft has a single role, ``chat``."""

    model: str = ""
    role: str = "chat"


# Role → the settings key it writes. Draft supports a single role; GET /state
# publishes these keys as `roles`, so the picker is built from what the app
# actually maps, never from the recommendations registry.
_ROLE_SETTING = {
    "chat": "model_name",
}


@router.post("/model")
def byom_set_model(req: ModelRequest) -> dict:
    """Persist the user's model choice for a role.

    Until this existed the BYOM screen could detect and test an endpoint but
    never record which model to use, so the app fell back to a shipped literal
    — the defect this whole change set removes. The Hub could write a choice;
    an app launched directly could not.

    An empty ``model`` clears the choice deliberately, returning the app to
    per-run resolution against whatever the endpoint serves. That is a
    supported state, not an error.
    """
    if req.role not in _ROLE_SETTING:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"artifice-draft has no {req.role!r} role; "
                f"expected one of {sorted(_ROLE_SETTING)}."
            },
        )

    chosen = req.model.strip()
    save_settings({_ROLE_SETTING[req.role]: chosen})
    return {"model": chosen or None, "role": "chat"}


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
        save_settings(
            {
                "base_url": req.url,
                "api_key": req.api_key,
            }
        )

    return {
        "reachable": result.reachable,
        "provider": result.provider,
        "models": list(result.models),
        "hint": result.hint,
    }
