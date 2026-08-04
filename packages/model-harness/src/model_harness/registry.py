# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Single source of truth for model and endpoint data.

This module is pure data and accessors. It performs no I/O of any kind — no
network, no filesystem, no environment reads, no imports of ``httpx``,
``requests``, or ``os.environ``. Probing whether a server is actually reachable
belongs to :mod:`model_harness.discovery`, which is a separate step.

Data here drives consent dialogs (size figures shown to a user *before* they
approve a multi-gigabyte download) and model-selection guidance, so every
``size_bytes`` value is sourced from the Hugging Face API and annotated with
its provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from model_harness.contract import Provider


# ── Enums ────────────────────────────────────────────────────────────────────


class HardwareTier(Enum):
    """Hardware capability tiers for model recommendations.

    Ordered roughly by VRAM headroom:
    - ``LAPTOP``: integrated GPU or entry-level dGPU (≈ 4–8 GB VRAM).
    - ``DESKTOP``: discrete GPU with 12–24 GB VRAM.
    - ``MAC_UNIFIED``: Apple Silicon with unified memory (Metal acceleration).
    """

    LAPTOP = "laptop"
    DESKTOP = "desktop"
    MAC_UNIFIED = "mac_unified"


# ── Endpoint metadata ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class EndpointInfo:
    """Metadata for a known local model server."""

    display_name: str
    """Human-readable name, e.g. ``"Ollama"``."""

    default_url: str
    """Default base URL including the ``/v1`` path, e.g. ``"http://localhost:11434/v1"``."""

    provider: Provider
    """The :data:`Provider` literal this endpoint maps to."""

    default_port: int
    """Default TCP port the server listens on."""


KNOWN_ENDPOINTS: Mapping[str, EndpointInfo] = {
    "ollama": EndpointInfo(
        display_name="Ollama",
        default_url="http://localhost:11434/v1",
        provider="ollama",
        default_port=11434,
    ),
    "lm-studio": EndpointInfo(
        display_name="LM Studio",
        default_url="http://localhost:1234/v1",
        provider="lm-studio",
        default_port=1234,
    ),
    "vllm": EndpointInfo(
        display_name="vLLM / LocalAI",
        default_url="http://localhost:8080/v1",
        provider="generic-api",
        default_port=8080,
    ),
}
"""Known local model servers.

vLLM and LocalAI share port 8080 and map to ``"generic-api"`` — there is no
dedicated :data:`Provider` literal for either, and the call contract must not
gain new members as a side effect of this registry.
"""


# ── ASR model metadata ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AsrModelInfo:
    """Download metadata for an ASR model on Hugging Face.

    These figures are shown in consent dialogs *before* a download begins, so
    ``size_bytes`` must be a real sourced value, not an estimate.
    """

    hf_repo: str
    """Hugging Face repository, e.g. ``"openai/whisper-large-v3"``."""

    size_bytes: int
    """Download size in bytes.  Sourced from the Hugging Face API — see comments
    on each :data:`ASR_MODELS` entry."""

    requires_hf_token: bool
    """``True`` if the model is gated and requires a Hugging Face access token."""

    description: str
    """One-line description for use in UI labels."""


# Sizes sourced 2026-08-04 from the Hugging Face API
# (``https://huggingface.co/api/models/<repo>?blobs=true&expand[]=siblings``):
#
#   whisper-large-v3        model.safetensors          sibling.size = 3 087 130 976
#   parakeet-tdt-1.1b       parakeet-tdt-1.1b.nemo     sibling.size = 4 283 136 000
#   segmentation-3.0        pytorch_model.bin           sibling.size =     5 905 440
#   embedding               pytorch_model.bin           sibling.size =    96 383 626
#
# The speaker-diarization-3.0 pipeline repo is a config-only wrapper; its
# actual weights live in ``pyannote/segmentation-3.0``.  The size listed here
# reflects the segmentation model the pipeline downloads at first use.

ASR_MODELS: Mapping[str, AsrModelInfo] = {
    "whisper-large-v3": AsrModelInfo(
        hf_repo="openai/whisper-large-v3",
        size_bytes=3_087_130_976,
        requires_hf_token=False,
        description="OpenAI Whisper large-v3 — multilingual ASR and speech translation",
    ),
    "parakeet-tdt-1.1b": AsrModelInfo(
        hf_repo="nvidia/parakeet-tdt-1.1b",
        size_bytes=4_283_136_000,
        requires_hf_token=False,
        description="NVIDIA Parakeet TDT 1.1B — English ASR (NeMo)",
    ),
    "pyannote-speaker-diarization": AsrModelInfo(
        hf_repo="pyannote/speaker-diarization-3.0",
        # The pipeline repo is a config file; the size reflects the
        # ``pyannote/segmentation-3.0`` weights it depends on.
        size_bytes=5_905_440,
        requires_hf_token=True,
        description="pyannote speaker diarization 3.0 — identifies who spoke when",
    ),
    "pyannote-embedding": AsrModelInfo(
        hf_repo="pyannote/embedding",
        size_bytes=96_383_626,
        requires_hf_token=True,
        description="pyannote speaker embedding — speaker verification and identification",
    ),
}
"""ASR and diarization models available for :mod:`artifice_transcribe`.

Parakeet is data only — nothing in this repository implements it.  Its presence
here is forward-looking.  Do not imply a working code path.
"""


# ── Model recommendations ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ModelRecommendation:
    """A recommended model for a given app and hardware tier."""

    model_name: str
    """The model identifier as the provider expects it, e.g. ``"llava:7b"``."""

    provider: Provider
    """Which :data:`Provider` this model is served by."""

    vision: bool
    """``True`` if the model supports image inputs (vision-capable)."""

    min_vram_gb: float | None = None
    """Approximate minimum VRAM in GB. ``None`` when unknown."""


# App → HardwareTier → recommendations.
# These are guidance, not requirements — the suite is BYOM, and any model the
# provider serves is fair game.  Every name listed here is a model known to
# exist on Ollama as of 2026-08-04.
_RECOMMENDATIONS: Mapping[str, Mapping[HardwareTier, Sequence[ModelRecommendation]]] = {
    "artifice-ocr": {
        HardwareTier.LAPTOP: [
            ModelRecommendation(
                model_name="llava:7b",
                provider="ollama",
                vision=True,
                min_vram_gb=8.0,
            ),
            ModelRecommendation(
                model_name="minicpm-v:8b",
                provider="ollama",
                vision=True,
                min_vram_gb=8.0,
            ),
        ],
        HardwareTier.DESKTOP: [
            ModelRecommendation(
                model_name="llava:13b",
                provider="ollama",
                vision=True,
                min_vram_gb=16.0,
            ),
            ModelRecommendation(
                model_name="minicpm-v:8b",
                provider="ollama",
                vision=True,
                min_vram_gb=8.0,
            ),
        ],
        HardwareTier.MAC_UNIFIED: [
            ModelRecommendation(
                model_name="llava:7b",
                provider="ollama",
                vision=True,
                min_vram_gb=8.0,
            ),
            ModelRecommendation(
                model_name="minicpm-v:8b",
                provider="ollama",
                vision=True,
                min_vram_gb=8.0,
            ),
        ],
    },
    "artifice-graph": {
        HardwareTier.LAPTOP: [
            ModelRecommendation(
                model_name="llama3.2:3b",
                provider="ollama",
                vision=False,
                min_vram_gb=4.0,
            ),
            ModelRecommendation(
                model_name="qwen2.5:7b",
                provider="ollama",
                vision=False,
                min_vram_gb=8.0,
            ),
        ],
        HardwareTier.DESKTOP: [
            ModelRecommendation(
                model_name="qwen2.5:32b",
                provider="ollama",
                vision=False,
                min_vram_gb=24.0,
            ),
            ModelRecommendation(
                model_name="llama3.1:8b",
                provider="ollama",
                vision=False,
                min_vram_gb=8.0,
            ),
        ],
        HardwareTier.MAC_UNIFIED: [
            ModelRecommendation(
                model_name="llama3.2:3b",
                provider="ollama",
                vision=False,
                min_vram_gb=4.0,
            ),
            ModelRecommendation(
                model_name="qwen2.5:7b",
                provider="ollama",
                vision=False,
                min_vram_gb=8.0,
            ),
        ],
    },
    "artifice-draft": {
        HardwareTier.LAPTOP: [
            ModelRecommendation(
                model_name="llama3.2:3b",
                provider="ollama",
                vision=False,
                min_vram_gb=4.0,
            ),
            ModelRecommendation(
                model_name="qwen2.5:7b",
                provider="ollama",
                vision=False,
                min_vram_gb=8.0,
            ),
        ],
        HardwareTier.DESKTOP: [
            ModelRecommendation(
                model_name="qwen2.5:32b",
                provider="ollama",
                vision=False,
                min_vram_gb=24.0,
            ),
            ModelRecommendation(
                model_name="llama3.1:8b",
                provider="ollama",
                vision=False,
                min_vram_gb=8.0,
            ),
        ],
        HardwareTier.MAC_UNIFIED: [
            ModelRecommendation(
                model_name="llama3.2:3b",
                provider="ollama",
                vision=False,
                min_vram_gb=4.0,
            ),
            ModelRecommendation(
                model_name="qwen2.5:7b",
                provider="ollama",
                vision=False,
                min_vram_gb=8.0,
            ),
        ],
    },
}
"""
Model recommendations by app and hardware tier.

``artifice-ocr`` receives vision models; ``artifice-graph`` and
``artifice-draft`` receive text-only models.  ``artifice-transcribe`` uses
:data:`ASR_MODELS` instead of these recommendations.
"""


# ── Accessors ────────────────────────────────────────────────────────────────


def get_endpoint(key: str) -> EndpointInfo:
    """Return the :class:`EndpointInfo` for a known endpoint key.

    Raises:
        KeyError: if *key* is not in :data:`KNOWN_ENDPOINTS`.
    """
    return KNOWN_ENDPOINTS[key]


def get_asr_model(key: str) -> AsrModelInfo:
    """Return the :class:`AsrModelInfo` for an ASR model key.

    Raises:
        KeyError: if *key* is not in :data:`ASR_MODELS`.
    """
    return ASR_MODELS[key]


def recommendations_for_app(
    app: str, tier: HardwareTier
) -> Sequence[ModelRecommendation]:
    """Return recommended models for *app* on the given *tier*.

    Args:
        app: One of ``"artifice-ocr"``, ``"artifice-graph"``,
            ``"artifice-draft"``.
        tier: The hardware capability tier.

    Returns:
        A (possibly empty) sequence of :class:`ModelRecommendation` instances
        ordered from most- to least-preferred.

    Raises:
        KeyError: if *app* has no recommendations registered, or if *tier*
            has no entries for the given app.
    """
    return _RECOMMENDATIONS[app][tier]


__all__ = [
    "ASR_MODELS",
    "AsrModelInfo",
    "EndpointInfo",
    "HardwareTier",
    "KNOWN_ENDPOINTS",
    "ModelRecommendation",
    "get_asr_model",
    "get_endpoint",
    "recommendations_for_app",
]
