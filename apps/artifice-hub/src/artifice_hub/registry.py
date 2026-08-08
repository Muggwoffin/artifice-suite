# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Frozen app registry for the Artifice Suite.

This is the injection-safety boundary — app names are constants, never user
input.  Any function that accepts an app ``slug`` must validate it against
this registry before passing it to a subprocess.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AsrVariant(Enum):
    CUDA = "cuda"
    CPU = "cpu"
    BASE = "base"


@dataclass(frozen=True)
class AppSpec:
    """Immutable registration record for one Artifice Suite application."""

    slug: str
    display_name: str
    description: str
    install_spec: str  # full PEP 508 specifier, e.g. "artifice-ocr[web]"
    entry_point: str  # executable name, e.g. "artifice-ocr-web"
    self_opens_browser: bool
    default_port: int | None  # transcribe: 8000; others None
    has_asr_variants: bool


APPS: dict[str, AppSpec] = {
    "artifice-ocr": AppSpec(
        slug="artifice-ocr",
        display_name="Artifice OCR",
        description="Local-first OCR processing for historical documents.",
        install_spec="artifice-ocr[web]",
        entry_point="artifice-ocr-web",
        self_opens_browser=True,
        default_port=None,
        has_asr_variants=False,
    ),
    "artifice-draft": AppSpec(
        slug="artifice-draft",
        display_name="Artifice Draft",
        description="Local-first copy editing for academic writing.",
        install_spec="artifice-draft[web]",
        entry_point="artifice-draft-web",
        self_opens_browser=True,
        default_port=None,
        has_asr_variants=False,
    ),
    "artifice-graph": AppSpec(
        slug="artifice-graph",
        display_name="Artifice Graph",
        description="Knowledge graph creator from extracted text.",
        install_spec="artifice-graph[web]",
        entry_point="artifice-graph-web",
        self_opens_browser=True,
        default_port=None,
        has_asr_variants=False,
    ),
    "artifice-transcribe": AppSpec(
        slug="artifice-transcribe",
        display_name="Artifice Transcribe",
        description="Oral history transcription via Whisper/Parakeet & pyannote.",
        install_spec="artifice-transcribe",
        entry_point="artifice-transcribe",
        self_opens_browser=False,
        default_port=8000,
        has_asr_variants=True,
    ),
}


def get_install_spec(slug: str, variant: AsrVariant | None = None) -> str:
    """Return the full PEP 508 install specifier for *slug* + optional ASR variant."""
    spec = APPS[slug]
    if variant == AsrVariant.CUDA:
        return "artifice-transcribe[asr-cuda]"
    if variant == AsrVariant.CPU:
        return "artifice-transcribe[asr]"
    return spec.install_spec
