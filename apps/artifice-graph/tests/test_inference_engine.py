# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for InferenceEngine endpoint policy enforcement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from artifice_graph.extraction.inference_engine import InferenceEngine
from model_harness.contract import EndpointRejected
from model_harness.discovery import ProbeResult


# ---------------------------------------------------------------------------
# Endpoint policy: constructor validates base_url
# ---------------------------------------------------------------------------


def test_inference_engine_rejects_link_local():
    """Construction with a link-local URL raises EndpointRejected."""
    with pytest.raises(EndpointRejected, match="link-local"):
        InferenceEngine(base_url="http://169.254.169.254/v1")


def test_inference_engine_accepts_localhost():
    """Construction with a localhost URL succeeds."""
    engine = InferenceEngine(base_url="http://localhost:11434")
    assert engine.base_url == "http://localhost:11434/v1"


def test_inference_engine_accepts_wsl_gateway():
    """The WSL gateway address (default always-allowed) passes validation."""
    engine = InferenceEngine(base_url="http://172.21.176.1:11434/v1")
    assert "172.21.176.1" in engine.base_url


def test_inference_engine_rejects_public_by_default():
    """A public IP is refused without ARTIFICE_ALLOW_PUBLIC_MODELS."""
    with pytest.raises(EndpointRejected, match="public address"):
        InferenceEngine(base_url="http://8.8.8.8/v1")


def test_inference_engine_accepts_public_with_allow(monkeypatch):
    """A public IP is accepted when the policy permits public endpoints."""
    monkeypatch.setenv("ARTIFICE_ALLOW_PUBLIC_MODELS", "1")
    engine = InferenceEngine(base_url="http://8.8.8.8/v1")
    assert "8.8.8.8" in engine.base_url


# ---------------------------------------------------------------------------
# health_check and get_available_models delegate to discovery.probe_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_delegates_to_probe_endpoint():
    """health_check uses discovery.probe_endpoint and maps reachable → bool."""
    engine = InferenceEngine(base_url="http://localhost:11434")

    with patch(
        "artifice_graph.extraction.inference_engine.probe_endpoint"
    ) as mock_probe:
        mock_probe.return_value = ProbeResult(
            url="http://localhost:11434/v1", reachable=True, models=()
        )

        result = await engine.health_check()

        mock_probe.assert_called_once()
        assert result is True
        assert engine.last_status == "connected"


@pytest.mark.asyncio
async def test_health_check_reports_unreachable():
    """health_check returns False when the endpoint is not reachable."""
    engine = InferenceEngine(base_url="http://localhost:11434")

    with patch(
        "artifice_graph.extraction.inference_engine.probe_endpoint"
    ) as mock_probe:
        mock_probe.return_value = ProbeResult(
            url="http://localhost:11434/v1",
            reachable=False,
            hint="Server down",
        )

        result = await engine.health_check()

        assert result is False
        assert engine.last_status == "error"


@pytest.mark.asyncio
async def test_get_available_models_delegates_to_probe_endpoint():
    """get_available_models uses discovery.probe_endpoint and builds ModelInfo."""
    engine = InferenceEngine(base_url="http://localhost:11434")

    with patch(
        "artifice_graph.extraction.inference_engine.probe_endpoint"
    ) as mock_probe:
        mock_probe.return_value = ProbeResult(
            url="http://localhost:11434/v1",
            reachable=True,
            models=("llama3.2:3b", "gemma2:27b", "llava:13b"),
        )

        text_models, vision_models = await engine.get_available_models()

        mock_probe.assert_called_once()
        # "llava" matches vision indicators
        assert len(text_models) == 3
        assert len(vision_models) == 1
        assert vision_models[0].id == "llava:13b"
        assert vision_models[0].supports_vision is True


@pytest.mark.asyncio
async def test_get_available_models_deduplicates():
    """get_available_models does not duplicate model names."""
    engine = InferenceEngine(base_url="http://localhost:11434")

    with patch(
        "artifice_graph.extraction.inference_engine.probe_endpoint"
    ) as mock_probe:
        mock_probe.return_value = ProbeResult(
            url="http://localhost:11434/v1",
            reachable=True,
            models=("llama3.2:3b", "llama3.2:3b", "gemma2:27b"),
        )

        text_models, _vision_models = await engine.get_available_models()

        assert len(text_models) == 2  # deduplicated
