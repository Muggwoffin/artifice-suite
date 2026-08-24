# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Once-per-run model resolution for artifice-graph.

``LLMConfig.model`` and ``EmbeddingConfig.model`` now ship empty. An empty name
means "the user has not chosen a model", not "use this one" — the previous
defaults named ``gemma2:27b`` and ``bge-m3``, and nothing checked either against
what the endpoint actually serves, so the first call failed with a raw provider
error.

This module fills them in by asking each endpoint what it serves and consulting
:func:`model_harness.resolution.resolve_model`.  It follows
:mod:`artifice_ocr._resolution`, which is the reference implementation.

Graph differs from the other apps in two ways that shape this module:

* **Two roles on potentially two endpoints.** ``chat`` and ``embedding`` carry
  their own ``base_url``, so each is probed separately rather than sharing one
  installed-model list.
* **Graph has no in-app model picker.** The Hub is the only writer of its model
  names today, so "nothing has ever been chosen" is graph's *normal* state, not
  an edge case — resolution has to work well with no user input at all.
"""

from __future__ import annotations

from model_harness.discovery import probe_endpoint_sync
from model_harness.endpoint_policy import EndpointPolicy
from model_harness.registry import HardwareTier
from model_harness.resolution import ResolutionSource, resolve_model

__all__ = ["resolve_for_run"]

_policy = EndpointPolicy()

_PROBE_TIMEOUT_S = 5.0

# No server-side hardware detection exists yet — the BYOM screen keeps its tier
# in browser localStorage.  Order only decides which model is *preferred* when
# several are installed; LAPTOP first, so the smaller wins on a modest machine.
_TIERS = (HardwareTier.LAPTOP, HardwareTier.DESKTOP, HardwareTier.MAC_UNIFIED)

_ROLE_LABELS = {"chat": "extraction", "embedding": "embedding"}


def resolve_for_run(cfg) -> None:
    """Resolve ``cfg.llm.model`` and ``cfg.embedding.model`` in place.

    Idempotent: an explicitly configured model that is installed is kept.

    Raises:
        RuntimeError: with a legible message naming the role, the endpoint and
            what to do — never a raw provider error.
    """
    cfg.llm.model = _resolve_one(
        role="chat",
        url=cfg.llm.base_url,
        configured=cfg.llm.model,
    )
    cfg.embedding.model = _resolve_one(
        role="embedding",
        url=cfg.embedding.base_url,
        configured=cfg.embedding.model,
    )


def _resolve_one(*, role: str, url: str, configured: str) -> str:
    label = _ROLE_LABELS[role]
    chosen = (configured or "").strip() or None

    probe = probe_endpoint_sync(url, policy=_policy, timeout_s=_PROBE_TIMEOUT_S)
    if not probe.reachable:
        raise RuntimeError(
            f"Cannot reach the {label} model server at {url}. "
            "Start Ollama (or correct the URL in Settings), then retry."
        )

    resolution = _resolve_with_tiers(role, list(probe.models), chosen)
    if resolution.model_name is None:
        raise _failure(label, role, url, resolution, chosen)
    return resolution.model_name


def _resolve_with_tiers(role: str, installed: list[str], configured: str | None):
    """Call ``resolve_model`` across the tiers, returning the first real answer.

    ``USER_CHOICE`` and ``CONFIGURED_MISSING`` are tier-independent and return
    immediately; only a registry recommendation varies by tier.
    """
    result = None
    for tier in _TIERS:
        result = resolve_model(
            role=role,
            installed=installed,
            app="artifice-graph",
            tier=tier,
            configured=configured,
        )
        if result.model_name is not None or result.source is ResolutionSource.CONFIGURED_MISSING:
            return result
    return result  # the last NONE_AVAILABLE


def _failure(label: str, role: str, url: str, resolution, configured: str | None) -> RuntimeError:
    """Build the user-facing error.

    The two cases need different wording because they have different remedies:
    a model the user chose that is absent is not the same problem as an empty
    shelf, and conflating them sends the user to the wrong fix.
    """
    if resolution.configured_but_missing:
        return RuntimeError(
            f"The configured {label} model '{configured}' is not installed on "
            f"{url}. Install it (e.g. 'ollama pull {configured}') or choose a "
            "different model in the Hub."
        )

    hint = (
        " An embedding model is required; a chat model cannot be substituted."
        if role == "embedding"
        else ""
    )
    return RuntimeError(
        f"No suitable {label} model is installed on {url}.{hint} Install one and retry."
    )
