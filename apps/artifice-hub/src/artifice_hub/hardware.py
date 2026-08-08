# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""GPU / OS probe for the Artifice Hub.

Detects whether the host has a CUDA-capable NVIDIA GPU, an Apple Silicon GPU,
or CPU-only inference, so the installer can offer the right ASR pack.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum


class GpuKind(Enum):
    CUDA = "cuda"
    APPLE_SILICON = "apple-silicon"
    CPU = "cpu"


@dataclass(frozen=True)
class HardwareProfile:
    gpu: GpuKind
    detail: str


def probe() -> HardwareProfile:
    """Return a hardware profile describing the host's GPU capability."""
    # 1. NVIDIA: check nvidia-smi exists AND runs
    if shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if result.returncode == 0 and result.stdout.strip():
                return HardwareProfile(
                    GpuKind.CUDA, result.stdout.strip().splitlines()[0]
                )
        except Exception:
            pass

    # 2. macOS Apple Silicon
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and "Apple" in result.stdout:
                return HardwareProfile(GpuKind.APPLE_SILICON, result.stdout.strip())
        except Exception:
            pass

    # 3. Fallback
    return HardwareProfile(GpuKind.CPU, "CPU")
