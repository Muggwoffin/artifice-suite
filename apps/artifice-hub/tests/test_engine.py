# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the Hub's Ollama engine provisioning module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from artifice_hub.engine import EngineError, get_engine_status, pull_model_command
from artifice_hub.hardware import GpuKind
from model_harness.registry import HardwareTier, ModelRecommendation

_PROBE_PATCH = "artifice_hub.engine.probe_endpoint"


def _mock_rec(model_name: str = "llama3.2:3b") -> ModelRecommendation:
    return ModelRecommendation(
        model_name=model_name,
        provider="ollama",
        role="chat",
        vision=False,
        min_vram_gb=4.0,
        notes="",
        ethos_badges=[],
    )


def test_gpu_kind_to_tier_mapping():
    """GpuKind maps to the registry HardwareTier as designed."""
    from artifice_hub.web.server import _gpu_kind_to_tier

    assert _gpu_kind_to_tier(GpuKind.CUDA) == HardwareTier.DESKTOP
    assert _gpu_kind_to_tier(GpuKind.APPLE_SILICON) == HardwareTier.MAC_UNIFIED
    assert _gpu_kind_to_tier(GpuKind.CPU) == HardwareTier.LAPTOP


@pytest.mark.asyncio
async def test_missing_model_computation():
    """Missing models are the recommended set minus the installed set."""
    mock_probe = MagicMock()
    mock_probe.models = ["llama3.2:3b"]

    with (
        patch("artifice_hub.engine.recommendations_for_app", return_value=[_mock_rec()]),
        patch(_PROBE_PATCH, new_callable=AsyncMock, return_value=mock_probe),
        patch("shutil.which", return_value="/usr/bin/ollama"),
        patch("socket.create_connection", return_value=MagicMock()),
    ):
        status = await get_engine_status("artifice-draft", HardwareTier.LAPTOP)

    assert status["missing"] == []
    assert status["engine_ready"] is True
    assert status["all_satisfied"] is True
    assert status["installed_models"] == ["llama3.2:3b"]
    assert status["models"][0]["installed"] is True

    # No models installed → everything is missing
    mock_probe.models = []
    with (
        patch("artifice_hub.engine.recommendations_for_app", return_value=[_mock_rec()]),
        patch(_PROBE_PATCH, new_callable=AsyncMock, return_value=mock_probe),
        patch("shutil.which", return_value="/usr/bin/ollama"),
        patch("socket.create_connection", return_value=MagicMock()),
    ):
        status = await get_engine_status("test", HardwareTier.DESKTOP)

    assert status["missing"] == ["llama3.2:3b"]
    assert status["engine_ready"] is True
    assert status["all_satisfied"] is True  # engine_ready is True; models are advisory
    assert status["installed_models"] == []


@pytest.mark.asyncio
async def test_engine_status_dict_shape():
    """The status dict matches the frontend contract."""
    mock_probe = MagicMock()
    mock_probe.models = ["llama3.2:3b"]

    with (
        patch("artifice_hub.engine.recommendations_for_app", return_value=[_mock_rec()]),
        patch(_PROBE_PATCH, new_callable=AsyncMock, return_value=mock_probe),
        patch("shutil.which", return_value="/usr/bin/ollama"),
        patch("socket.create_connection", return_value=MagicMock()),
    ):
        status = await get_engine_status("artifice-draft", HardwareTier.DESKTOP)

    expected_keys = {
        "ollama",
        "engine_ready",
        "models",
        "missing",
        "installed_models",
        "all_satisfied",
    }
    assert set(status.keys()) == expected_keys
    assert status["ollama"] == {"installed": True, "running": True}
    assert set(status["models"][0].keys()) == {
        "name",
        "role",
        "vision",
        "min_vram_gb",
        "notes",
        "badges",
        "installed",
    }


def test_pull_model_command_valid():
    """A recommended model yields a validated list-form argv."""
    with (
        patch("artifice_hub.engine.recommendations_for_app", return_value=[_mock_rec()]),
        patch("shutil.which", return_value="/usr/bin/ollama"),
    ):
        cmd = pull_model_command("artifice-draft", HardwareTier.DESKTOP, "llama3.2:3b")

    assert cmd == ["/usr/bin/ollama", "pull", "llama3.2:3b"]


def test_pull_model_rejects_unrecommended():
    """A model outside the frozen registry is rejected before any argv."""
    with (
        patch("artifice_hub.engine.recommendations_for_app", return_value=[_mock_rec()]),
        pytest.raises(EngineError),
    ):
        pull_model_command("artifice-draft", HardwareTier.DESKTOP, "evil; rm -rf /")


def test_pull_model_requires_ollama_binary():
    """Pulling without the ollama binary raises EngineError."""
    with (
        patch("artifice_hub.engine.recommendations_for_app", return_value=[_mock_rec()]),
        patch("shutil.which", return_value=None),
        pytest.raises(EngineError),
    ):
        pull_model_command("artifice-draft", HardwareTier.DESKTOP, "llama3.2:3b")


def test_unknown_app_raises_engine_error():
    """An app with no registry recommendations raises EngineError."""
    with (
        patch("artifice_hub.engine.recommendations_for_app", side_effect=KeyError("nope")),
        pytest.raises(EngineError),
    ):
        pull_model_command("artifice-draft", HardwareTier.DESKTOP, "llama3.2:3b")
