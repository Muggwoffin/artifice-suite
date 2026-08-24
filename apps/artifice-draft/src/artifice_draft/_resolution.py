# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Once-per-run model resolution for artifice-draft.

``AppConfig`` now ships an empty ``model_name`` and ``ollama_model`` (see
:mod:`artifice_draft.config`).  An empty name means "the user has not chosen a
model", not "use this one" — the previous default named a specific model
(``gemma4:12b``) that most users do not have installed, and nothing checked it
against what Ollama actually serves, so the first inference call failed with a
raw provider 404.

This module turns "no choice" into a concrete model by asking the endpoint what
it serves and consulting :func:`model_harness.resolution.resolve_model`.

Draft is simpler than artifice-ocr, which is the reference implementation
(:mod:`artifice_ocr._resolution`), in two ways worth knowing:

* **One role.** Draft only ever makes ``chat`` calls; there is no vision or
  embedding role to resolve.
* **Provider, not per-stage backend.** Draft selects a provider once via
  ``llm_provider``.  Only :data:`~artifice_draft.models.LLMProvider.OLLAMA` is
  resolvable — OpenAI and Anthropic name their models in a catalogue the user
  reads, not a local shelf we can probe, and their existing defaults
  (``gpt-4o``, a dated Claude) are legitimate.  Those two are passed through
  untouched.

Resolution happens once where a run begins and writes the answer back into the
config, which ``AppConfig.active_model`` already reads.  It is idempotent: an
explicitly configured model is left alone.
"""

from __future__ import annotations

from model_harness.discovery import probe_endpoint_sync
from model_harness.endpoint_policy import EndpointPolicy
from model_harness.registry import HardwareTier
from model_harness.resolution import ResolutionSource, resolve_model

from artifice_draft.models import LLMProvider

__all__ = ["resolve_for_run"]

_policy = EndpointPolicy()

_PROBE_TIMEOUT_S = 5.0

# No server-side hardware detection exists yet — the BYOM screen keeps its tier
# in browser localStorage.  Draft's chat recommendation is the same across
# tiers, so the order only decides which model is *preferred* when several are
# installed.  LAPTOP first, so the smaller model wins on a modest machine.
_TIERS = (HardwareTier.LAPTOP, HardwareTier.DESKTOP, HardwareTier.MAC_UNIFIED)


def resolve_for_run(cfg) -> None:
    """Resolve ``cfg.model_name`` in place, once, before a run begins.

    Does nothing when the provider is not Ollama, or when a model is already
    explicitly configured and installed.

    Raises:
        RuntimeError: with a legible message naming the endpoint and what to
            do — never a raw provider 404.
    """
    if cfg.llm_provider is not LLMProvider.OLLAMA:
        return

    configured = (cfg.model_name or cfg.ollama_model or "").strip() or None

    url = cfg.ollama_base_url or "http://localhost:11434"
    probe = probe_endpoint_sync(url, policy=_policy, timeout_s=_PROBE_TIMEOUT_S)

    if not probe.reachable:
        raise RuntimeError(
            f"Cannot reach Ollama at {url}. "
            "Start Ollama (or set OLLAMA_BASE_URL to the right address), "
            "then retry."
        )

    installed = list(probe.models)
    resolution = _resolve_with_tiers(installed, configured)

    if resolution.model_name is None:
        raise _failure(url, resolution, configured)

    cfg.model_name = resolution.model_name
    cfg.ollama_model = resolution.model_name


def _resolve_with_tiers(installed: list[str], configured: str | None):
    """Call ``resolve_model`` across the tiers, returning the first real answer.

    ``USER_CHOICE`` and ``CONFIGURED_MISSING`` are tier-independent and return
    immediately; only a registry recommendation varies by tier.
    """
    result = None
    for tier in _TIERS:
        result = resolve_model(
            role="chat",
            installed=installed,
            app="artifice-draft",
            tier=tier,
            configured=configured,
        )
        if (
            result.model_name is not None
            or result.source is ResolutionSource.CONFIGURED_MISSING
        ):
            return result
    return result  # the last NONE_AVAILABLE


def _failure(url: str, resolution, configured: str | None) -> RuntimeError:
    """Build the user-facing error.

    The two cases need different wording: a model the user *chose* that is
    absent is a different problem from an empty shelf, and conflating them
    would send the user to the wrong remedy.
    """
    if resolution.configured_but_missing:
        return RuntimeError(
            f"The configured model '{configured}' is not installed on {url}. "
            f"Install it (e.g. 'ollama pull {configured}') or choose a "
            "different model in Settings."
        )
    return RuntimeError(
        f"No suitable model is installed on {url}. "
        "Install one (e.g. 'ollama pull llama3.2:3b') and retry."
    )
