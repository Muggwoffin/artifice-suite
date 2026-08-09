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
    local_path: str | None = None  # subdirectory under apps/, e.g. "artifice-ocr"
    window_extra: bool = True  # whether the app has a [window] extra (pywebview)


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
        local_path="artifice-ocr",
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
        local_path="artifice-draft",
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
        local_path="artifice-graph",
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
        local_path="artifice-transcribe",
    ),
}


def get_install_spec(
    slug: str, variant: AsrVariant | None = None, *, repo_root: str | None = None
) -> str:
    """Return the full PEP 508 install specifier for *slug* + optional ASR variant.

    If *repo_root* is provided, builds a local-path specifier with bracket
    extras (e.g. ``\"./apps/artifice-ocr[web,window]\"``).  Otherwise falls
    back to the PyPI install specifier.
    """
    spec = APPS[slug]
    if repo_root:
        if slug == "artifice-transcribe":
            if variant == AsrVariant.CUDA:
                return f"{repo_root}/apps/{spec.local_path}[asr-cuda,window]"
            if variant == AsrVariant.CPU:
                return f"{repo_root}/apps/{spec.local_path}[asr,window]"
            return f"{repo_root}/apps/{spec.local_path}[window]"
        return f"{repo_root}/apps/{spec.local_path}[web,window]"
    # PyPI fallback — keep existing behavior exactly
    if variant == AsrVariant.CUDA:
        return "artifice-transcribe[asr-cuda]"
    if variant == AsrVariant.CPU:
        return "artifice-transcribe[asr]"
    return spec.install_spec
