# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Ollama engine provisioning for the Artifice Hub.

Detects the local Ollama engine, queries the model-harness registry for the
recommended models of a given app, and validates ``ollama pull`` requests
against that frozen registry so no user-supplied string ever reaches a
subprocess argv.

The registry is the single source of model names.  Nothing here hardcodes a
model; every name comes from :func:`model_harness.registry.recommendations_for_app`.
"""

from __future__ import annotations

import shutil
import socket
from typing import Any

from model_harness.discovery import probe_endpoint
from model_harness.endpoint_policy import EndpointPolicy
from model_harness.registry import (
    KNOWN_ENDPOINTS,
    HardwareTier,
    recommendations_for_app,
)

# Ollama listens on 127.0.0.1:11434 by default (registry KNOWN_ENDPOINTS).
_OLLAMA_HOST = "127.0.0.1"
_OLLAMA_PORT = 11434
_SOCKET_TIMEOUT_S = 2.0


def _ollama_installed() -> bool:
    """Return ``True`` when the ``ollama`` binary is on ``PATH``."""
    return shutil.which("ollama") is not None


def _ollama_running() -> bool:
    """Return ``True`` when something listens on the Ollama port."""
    try:
        with socket.create_connection(
            (_OLLAMA_HOST, _OLLAMA_PORT), timeout=_SOCKET_TIMEOUT_S
        ):
            return True
    except OSError:
        return False


def _recommended_ollama_models(
    slug: str, tier: HardwareTier
) -> list[Any]:
    """Return the registry's Ollama recommendations for *slug* on *tier*.

    Raises:
        ValueError: if *slug* has no recommendations registered.
    """
    try:
        recs = recommendations_for_app(slug, tier)
    except KeyError as exc:
        raise ValueError(f"No model recommendations for app {slug}") from exc
    return [r for r in recs if r.provider == "ollama"]


async def get_engine_status(slug: str, tier: HardwareTier) -> dict[str, Any]:
    """Return the engine status dict for *slug* on *tier*.

    The shape is the fixed frontend contract consumed by ``hub.js``:

    ``{"ollama": {"installed", "running"}, "models": [...], "missing": [...],
    "all_satisfied": bool}``

    Raises:
        ValueError: if *slug* has no recommendations registered.
    """
    ollama_recs = _recommended_ollama_models(slug, tier)
    recommended = {r.model_name for r in ollama_recs}

    installed = _ollama_installed()
    running = installed and _ollama_running()
    installed_models: set[str] = set()

    if running:
        probe_result = await probe_endpoint(
            KNOWN_ENDPOINTS["ollama"].default_url, policy=EndpointPolicy()
        )
        installed_models = set(probe_result.models)

    missing = sorted(recommended - installed_models)

    return {
        "ollama": {
            "installed": installed,
            "running": running,
        },
        "models": [
            {
                "name": r.model_name,
                "role": r.role,
                "vision": r.vision,
                "min_vram_gb": r.min_vram_gb,
                "notes": r.notes,
                "badges": r.ethos_badges,
                "installed": r.model_name in installed_models,
            }
            for r in ollama_recs
        ],
        "missing": missing,
        "all_satisfied": installed and running and not missing,
    }


def pull_model_command(slug: str, tier: HardwareTier, model_name: str) -> list[str]:
    """Return the validated ``ollama pull`` argv for *model_name*.

    The model name is checked against the frozen registry recommendations for
    *slug* on *tier* before any command is built — a user-supplied string can
    never reach the subprocess.

    Raises:
        ValueError: if *slug* has no recommendations, or *model_name* is not
            a recommended Ollama model for *slug* on *tier*.
        RuntimeError: if the ``ollama`` binary is not installed.
    """
    ollama_recs = _recommended_ollama_models(slug, tier)
    recommended = {r.model_name for r in ollama_recs}

    if model_name not in recommended:
        raise ValueError(
            f"Model {model_name!r} is not recommended for {slug} on {tier.value}"
        )

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        raise RuntimeError("Ollama is not installed")

    return [ollama_bin, "pull", model_name]