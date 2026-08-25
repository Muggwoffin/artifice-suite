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
    normalise_base_url,
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

from ... import config

router = APIRouter(prefix="/api/byom", tags=["byom"])

_policy = EndpointPolicy()

# ── Display-name mapping ─────────────────────────────────────────────────────


def _name_for_probe(r: ProbeResult) -> str:
    """Return a human-readable name for a probe result, derived from the
    registry when the provider matches a known endpoint."""
    for info in KNOWN_ENDPOINTS.values():
        if info.provider == r.provider:
            return info.display_name
    # Fall back to the provider literal — it is a display-safe string.
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


class ModelRequest(BaseModel):
    """A per-role model choice. OCR has three roles."""

    model: str = ""
    role: str = "chat"


# Role → the settings key it writes. Mirrors artifice_ocr._resolution.ROLE_KEYS
# and the Hub's config_bridge._ROLE_KEY_MAP; all three must agree, because all
# three write the same ~/.artifice_ocr/settings.json.
_ROLE_SETTING = {
    "vision": "ocr_model",
    "chat": "cleanup_model",
    "translation": "translate_model",
}


# ── POST /api/byom/model ────────────────────────────────────────────────────


@router.post("/model")
def byom_set_model(req: ModelRequest) -> dict:
    """Persist the user's model choice for a role.

    An empty ``model`` clears the choice deliberately, returning the role to
    per-run resolution against whatever the endpoint serves. That is a
    supported state, not an error.
    """
    key = _ROLE_SETTING.get(req.role)
    if key is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"artifice-ocr has no {req.role!r} role; "
                f"expected one of {sorted(_ROLE_SETTING)}."
            },
        )

    chosen = req.model.strip()
    overrides = {key: chosen}
    config.apply_overrides(overrides)
    config.save_user_settings(overrides)
    return {"model": chosen or None, "role": req.role}


# ── GET /api/byom/state ─────────────────────────────────────────────────────


@router.get("/state")
def byom_state() -> dict:
    """Return current BYOM configuration — no network calls, no probing.

    The ``configured`` key drives first-run interception: when False,
    ``byom.js`` opens the onboarding screen on page load.
    """
    api_key = config.get("api_key") or ""
    api_base_url = config.get("api_base_url") or "https://api.openai.com/v1"
    ollama_url = config.get("ollama_url") or "http://localhost:11434"
    ocr_model = config.get("ocr_model") or ""

    # "Configured" means the user has intentionally set something beyond the
    # default out-of-the-box endpoints — including choosing a model, which
    # counts even when both endpoints are still the shipped defaults.
    configured = is_configured(
        api_base_url, api_key, defaults=("https://api.openai.com/v1",), model=ocr_model
    ) or is_configured(ollama_url, defaults=("http://localhost:11434",))

    return {
        "app": "artifice-ocr",
        "configured": configured,
        "endpoint": api_base_url if api_key else ollama_url,
        "model": ocr_model or None,
        # The roles this app supports, in stable order. Derived from the same
        # mapping POST /model honours (_ROLE_SETTING) so the picker can never
        # show a role the app cannot save, or omit one it can.
        "roles": list(_ROLE_SETTING),
        "recommendations": _byom_recommendations("artifice-ocr"),
    }


# ── GET /api/byom/detect ────────────────────────────────────────────────────


@router.get("/detect")
async def byom_detect() -> dict:
    """Probe known local endpoints and return results.

    Probes run concurrently so the total wall time is roughly one timeout
    rather than the sum.  Called on-demand when the BYOM screen opens —
    never on page load (see the brief's first-run interception design).
    """
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

    On success the endpoint is persisted to the app's config store so that
    ``GET /api/byom/state`` reports ``configured: True`` on the next load.
    """
    # Validate the URL through the endpoint policy before any network call.
    try:
        _policy.validate_url(req.url)
    except EndpointRejected as exc:
        exc_str = str(exc)
        return JSONResponse(status_code=400, content={"hint": exc_str, "error": exc_str})

    base_url = req.url

    result = await probe_endpoint(base_url, policy=_policy)

    # Persist on success so the next page load finds configured=True.
    if result.reachable and req.api_key is not None:
        overrides: dict[str, str] = {}
        if req.api_key:
            overrides["api_key"] = req.api_key
        if result.provider == "ollama":
            overrides["ollama_url"] = normalise_base_url(base_url)
        else:
            overrides["api_base_url"] = base_url.strip()
        config.apply_overrides(overrides)
        config.save_user_settings(overrides)

    return {
        "reachable": result.reachable,
        "provider": result.provider,
        "models": list(result.models),
        "hint": result.hint,
    }
