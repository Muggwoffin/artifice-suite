# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the hardware probe."""

import subprocess
from unittest.mock import patch

from artifice_hub.hardware import GpuKind, probe


def test_probe_cuda_detected():
    """When nvidia-smi is on PATH and returns a GPU name, probe reports CUDA."""

    def mock_which(cmd):
        return "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None

    class MockResult:
        returncode = 0
        stdout = "NVIDIA GeForce RTX 3060\n"

    with (
        patch("shutil.which", side_effect=mock_which),
        patch("subprocess.run", return_value=MockResult()),
    ):
        result = probe()
        assert result.gpu == GpuKind.CUDA
        assert "RTX 3060" in result.detail


def test_probe_nvidia_smi_fails():
    """When nvidia-smi exists but returns non-zero, fall through to CPU."""

    def mock_which(cmd):
        return "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None

    class MockResult:
        returncode = 1
        stdout = ""

    with (
        patch("shutil.which", side_effect=mock_which),
        patch("subprocess.run", return_value=MockResult()),
    ):
        result = probe()
        assert result.gpu == GpuKind.CPU


def test_probe_nvidia_smi_crashes():
    """When nvidia-smi raises, fall through to CPU."""

    def mock_which(cmd):
        return "/usr/bin/nvidia-smi" if cmd == "nvidia-smi" else None

    with (
        patch("shutil.which", side_effect=mock_which),
        patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(["nvidia-smi"], 5),
        ),
    ):
        result = probe()
        assert result.gpu == GpuKind.CPU


def test_probe_apple_silicon(monkeypatch):
    """On macOS with an Apple CPU, probe reports Apple Silicon."""
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    def mock_which(cmd):
        return None  # no nvidia-smi

    class MockResult:
        returncode = 0
        stdout = "Apple M2 Pro"

    with (
        patch("shutil.which", side_effect=mock_which),
        patch("subprocess.run", return_value=MockResult()),
    ):
        result = probe()
        assert result.gpu == GpuKind.APPLE_SILICON
        assert "Apple" in result.detail


def test_probe_macos_intel_falls_to_cpu(monkeypatch):
    """On macOS with an Intel CPU (no "Apple" in brand string), fall to CPU."""
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    def mock_which(cmd):
        return None

    class MockResult:
        returncode = 0
        stdout = "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz"

    with (
        patch("shutil.which", side_effect=mock_which),
        patch("subprocess.run", return_value=MockResult()),
    ):
        result = probe()
        assert result.gpu == GpuKind.CPU


def test_probe_no_gpu():
    """Without nvidia-smi and not on macOS Apple Silicon, probe returns CPU."""

    def mock_which(cmd):
        return None

    with patch("shutil.which", side_effect=mock_which):
        result = probe()
        assert result.gpu == GpuKind.CPU
        assert result.detail == "CPU"
