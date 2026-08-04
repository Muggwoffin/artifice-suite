# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for :mod:`model_harness.registry`.

Every ``size_bytes`` value in :data:`ASR_MODELS` is shown to a user *before*
they approve a download — a wrong figure is a wrong promise.  These tests
assert the data is internally consistent and that provider values stay in
sync with the :class:`Provider` literal in :mod:`model_harness.contract`.
"""

from __future__ import annotations

import sys
import types
from typing import get_args

import pytest

from model_harness.contract import Provider
from model_harness.registry import (
    ASR_MODELS,
    KNOWN_ENDPOINTS,
    HardwareTier,
    ModelRecommendation,
    get_asr_model,
    get_endpoint,
    recommendations_for_app,
)


# ── ASR_MODELS integrity ─────────────────────────────────────────────────────


def test_every_asr_model_has_nonzero_size():
    """A zero-byte model file is either a config stub or a data error — neither
    belongs in a consent dialog."""
    for key, info in ASR_MODELS.items():
        assert info.size_bytes > 0, f"{key}: size_bytes is {info.size_bytes}"


def test_every_asr_model_has_plausible_repo():
    """Every entry must carry a ``namespace/repo`` Hugging Face id."""
    for key, info in ASR_MODELS.items():
        assert "/" in info.hf_repo, f"{key}: hf_repo {info.hf_repo!r} does not look like a HF id"


def test_pyannote_models_require_token():
    """Both pyannote models are gated on Hugging Face."""
    diar = ASR_MODELS["pyannote-speaker-diarization"]
    emb = ASR_MODELS["pyannote-embedding"]
    assert diar.requires_hf_token is True, "pyannote-speaker-diarization must require a token"
    assert emb.requires_hf_token is True, "pyannote-embedding must require a token"


def test_whisper_does_not_require_token():
    """Whisper large-v3 is not gated."""
    assert ASR_MODELS["whisper-large-v3"].requires_hf_token is False


# ── KNOWN_ENDPOINTS ↔ Provider sync ──────────────────────────────────────────


_VALID_PROVIDERS: frozenset[str] = frozenset(get_args(Provider))


def test_every_endpoint_provider_is_a_valid_provider_literal():
    """If someone edits ``contract.Provider`` and not this registry, the test
    fails.  vLLM / LocalAI map to ``"generic-api"`` by design — that *is* a
    valid member of the literal."""
    for key, ep in KNOWN_ENDPOINTS.items():
        assert ep.provider in _VALID_PROVIDERS, (
            f"{key}: provider {ep.provider!r} is not in Provider literal; "
            f"valid values are {sorted(_VALID_PROVIDERS)}"
        )


def test_vllm_maps_to_generic_api():
    """vLLM and LocalAI have no dedicated provider — they must map to
    ``"generic-api"``.  Do not add new members to the ``Provider`` literal as
    a side effect."""
    assert KNOWN_ENDPOINTS["vllm"].provider == "generic-api"


# ── Recommendations ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("tier", list(HardwareTier))
def test_ocr_recommendations_are_vision_capable(tier: HardwareTier):
    """All OCR model recommendations must support image inputs."""
    recs = recommendations_for_app("artifice-ocr", tier)
    assert len(recs) > 0, f"no OCR recommendations for {tier}"
    for rec in recs:
        assert rec.vision is True, (
            f"OCR recommendation {rec.model_name!r} has vision=False"
        )


@pytest.mark.parametrize("app", ["artifice-graph", "artifice-draft"])
@pytest.mark.parametrize("tier", list(HardwareTier))
def test_graph_and_draft_recommendations_are_text_only(app: str, tier: HardwareTier):
    """Graph and draft models must not be vision models — they handle text."""
    recs = recommendations_for_app(app, tier)
    assert len(recs) > 0, f"no recommendations for {app}/{tier}"
    for rec in recs:
        assert rec.vision is False, (
            f"{app}/{tier} recommendation {rec.model_name!r} has vision=True"
        )


def test_recommendations_vary_by_tier():
    """A laptop and a desktop should not get the same first suggestion —
    that is the point of hardware tiers."""
    laptop = recommendations_for_app("artifice-ocr", HardwareTier.LAPTOP)
    desktop = recommendations_for_app("artifice-ocr", HardwareTier.DESKTOP)
    assert laptop[0].model_name != desktop[0].model_name, (
        "laptop and desktop first recommendations are identical"
    )


def test_recommendations_unknown_app_raises():
    with pytest.raises(KeyError):
        recommendations_for_app("nonexistent-app", HardwareTier.LAPTOP)


# ── Accessors ────────────────────────────────────────────────────────────────


def test_get_endpoint_returns_correct_info():
    info = get_endpoint("ollama")
    assert info.display_name == "Ollama"
    assert info.default_port == 11434


def test_get_endpoint_unknown_key_raises():
    with pytest.raises(KeyError):
        get_endpoint("nonexistent")


def test_get_asr_model_returns_correct_info():
    info = get_asr_model("whisper-large-v3")
    assert info.hf_repo == "openai/whisper-large-v3"
    assert info.requires_hf_token is False


def test_get_asr_model_unknown_key_raises():
    with pytest.raises(KeyError):
        get_asr_model("nonexistent")


# ── No I/O at import time ────────────────────────────────────────────────────

# Modules that would indicate the registry has grown I/O concerns.
_IO_FLAGS: frozenset[str] = frozenset({
    "httpx", "requests", "urllib", "http.client",
    "os", "pathlib", "socket", "subprocess",
})


def test_registry_imports_no_io_libraries():
    """The registry is pure data.  If it acquires an I/O dependency, this test
    fails and a reviewer needs to ask whether that dependency belongs in
    :mod:`model_harness.discovery` instead."""
    import model_harness.registry

    # Gather every name the module can reach.
    names = set(dir(model_harness.registry))
    # Also check what the module actually imported.
    for attr in names:
        obj = getattr(model_harness.registry, attr, None)
        if isinstance(obj, types.ModuleType):
            names.add(obj.__name__)

    flagged = names & _IO_FLAGS
    assert not flagged, (
        f"registry imports I/O-related names: {sorted(flagged)}. "
        f"Probing belongs in discovery.py, not here."
    )


# ── Types hold their shape ───────────────────────────────────────────────────


def test_model_recommendation_is_immutable():
    rec = ModelRecommendation(
        model_name="llava:7b", provider="ollama", vision=True
    )
    with pytest.raises((AttributeError, TypeError)):
        rec.model_name = "changed"  # type: ignore[misc]


def test_endpoint_info_is_immutable():
    ep = KNOWN_ENDPOINTS["ollama"]
    with pytest.raises((AttributeError, TypeError)):
        ep.default_port = 9999  # type: ignore[misc]


def test_asr_model_info_is_immutable():
    info = ASR_MODELS["whisper-large-v3"]
    with pytest.raises((AttributeError, TypeError)):
        info.size_bytes = 0  # type: ignore[misc]
