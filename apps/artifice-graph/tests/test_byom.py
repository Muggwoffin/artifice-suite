# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the BYOM onboarding endpoints in artifice-graph."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import httpx
import pytest
from artifice_graph.config import EmbeddingConfig, LLMConfig, PipelineConfig
from artifice_graph.web import config_helper
from artifice_graph.web.server import app
from fastapi.testclient import TestClient
from model_harness.discovery import ProbeResult


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Isolate config and preferences per test."""
    cfg_dir = tmp_path / "artifice_graph_test"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config_helper, "CONFIG_FILE", cfg_dir / "config.json")
    monkeypatch.setattr(config_helper, "PREFERENCES_FILE", cfg_dir / "preferences.json")
    return TestClient(app)


# ── GET /api/byom/state ───────────────────────────────────────────────────


class TestByomState:
    def test_returns_all_keys_in_default_state(self, client):
        r = client.get("/api/byom/state")
        assert r.status_code == 200
        body = r.json()

        assert body["app"] == "artifice-graph"
        assert body["configured"] is False
        assert body["endpoint"] is None
        assert body["model"] is None
        assert "recommendations" in body

    def test_configured_true_when_api_key_set(self, client):
        cfg = PipelineConfig(llm=LLMConfig(api_key="sk-123"))
        config_helper.save_user_config(cfg)

        r = client.get("/api/byom/state")
        assert r.status_code == 200
        assert r.json()["configured"] is True

    def test_configured_true_when_base_url_changed(self, client):
        cfg = PipelineConfig(llm=LLMConfig(base_url="http://localhost:9999/v1"))
        config_helper.save_user_config(cfg)

        r = client.get("/api/byom/state")
        assert r.status_code == 200
        assert r.json()["configured"] is True

    def test_model_returned_from_config(self, client):
        cfg = PipelineConfig(llm=LLMConfig(model="qwen2.5:32b"))
        config_helper.save_user_config(cfg)

        r = client.get("/api/byom/state")
        assert r.json()["model"] == "qwen2.5:32b"

    def test_recommendations_have_correct_fields(self, client):
        r = client.get("/api/byom/state")
        recs = r.json()["recommendations"]

        for tier in ("laptop", "desktop", "mac_unified"):
            assert tier in recs
            for entry in recs[tier]:
                assert "model_name" in entry
                assert "provider" in entry
                assert "vision" in entry
                assert "min_vram_gb" in entry
                assert "ethos_badges" in entry
                assert "role" in entry
                assert "notes" in entry

    def test_response_is_json_serialisable(self, client):
        r = client.get("/api/byom/state")
        json.dumps(r.json())


# ── GET /api/byom/detect ──────────────────────────────────────────────────


class TestByomDetect:
    def test_returns_endpoints_array(self, client):
        with patch("artifice_graph.web.routers.byom.detect_local_servers") as mock_detect:
            mock_detect.return_value = [
                ProbeResult(
                    url="http://localhost:11434/v1",
                    reachable=True,
                    provider="ollama",
                    models=("qwen2.5:32b",),
                    hint=None,
                ),
            ]

            r = client.get("/api/byom/detect")
            assert r.status_code == 200
            ep = r.json()["endpoints"][0]
            assert ep["name"] == "Ollama"
            assert ep["reachable"] is True
            assert ep["models"] == ["qwen2.5:32b"]

    def test_unreachable_endpoint_has_hint(self, client):
        with patch("artifice_graph.web.routers.byom.detect_local_servers") as mock_detect:
            mock_detect.return_value = [
                ProbeResult(
                    url="http://localhost:8080/v1",
                    reachable=False,
                    provider="generic-api",
                    models=(),
                    hint="Server not running",
                ),
            ]

            r = client.get("/api/byom/detect")
            ep = r.json()["endpoints"][0]
            assert ep["reachable"] is False
            assert ep["name"] == "vLLM / LocalAI"


# ── POST /api/byom/test ───────────────────────────────────────────────────


class TestByomTest:
    def test_rejects_empty_url(self, client):
        r = client.post("/api/byom/test", json={"url": "", "api_key": ""})
        assert r.status_code == 400
        body = r.json()
        assert "hint" in body
        assert "error" in body

    def test_rejects_bad_scheme(self, client):
        r = client.post("/api/byom/test", json={"url": "ftp://localhost/v1", "api_key": ""})
        assert r.status_code == 400
        body = r.json()
        assert "hint" in body
        assert "error" in body

    def test_rejects_public_url_by_default(self, client):
        r = client.post("/api/byom/test", json={"url": "https://api.example.com/v1", "api_key": ""})
        assert r.status_code == 400
        body = r.json()
        assert "hint" in body
        assert "error" in body

    def test_successful_probe_saves_config(self, client):
        with patch("artifice_graph.web.routers.byom.probe_endpoint") as mock_probe:
            mock_probe.return_value = ProbeResult(
                url="http://localhost:9999/v1",
                reachable=True,
                provider="generic-api",
                models=("model-x",),
                hint=None,
            )

            r = client.post(
                "/api/byom/test",
                json={
                    "url": "http://localhost:9999/v1",
                    "api_key": "sk-real",
                },
            )
            assert r.status_code == 200
            assert r.json()["reachable"] is True

            state_r = client.get("/api/byom/state")
            assert state_r.json()["configured"] is True

    def test_unreachable_probe_does_not_save(self, client):
        with patch("artifice_graph.web.routers.byom.probe_endpoint") as mock_probe:
            mock_probe.return_value = ProbeResult(
                url="http://localhost:1234/v1",
                reachable=False,
                provider="lm-studio",
                models=(),
                hint="Not running",
            )

            r = client.post(
                "/api/byom/test",
                json={
                    "url": "http://localhost:1234/v1",
                    "api_key": "sk-test",
                },
            )
            assert r.json()["reachable"] is False

            state_r = client.get("/api/byom/state")
            assert state_r.json()["configured"] is False

    def test_api_key_persisted_on_success(self, client):
        with patch("artifice_graph.web.routers.byom.probe_endpoint") as mock_probe:
            mock_probe.return_value = ProbeResult(
                url="http://localhost:9999/v1",
                reachable=True,
                provider="generic-api",
                models=(),
                hint=None,
            )

            client.post(
                "/api/byom/test",
                json={
                    "url": "http://localhost:9999/v1",
                    "api_key": "sk-secret-123",
                },
            )

            saved = config_helper.load_saved_config()
            assert saved is not None
            assert saved.llm.api_key == "sk-secret-123"

    def test_non_llm_config_sections_survive_byom_save(self, client):
        """Probing a new LLM endpoint must preserve other config sections."""
        from artifice_graph.config import EmbeddingConfig, IngestionConfig

        # Pre-save a config with non-default values in non-LLM sections.
        cfg = PipelineConfig(
            llm=LLMConfig(base_url="http://localhost:11434/v1", api_key="sk-old"),
            embedding=EmbeddingConfig(base_url="http://localhost:8888/v1", model="bge-m3"),
            ingestion=IngestionConfig(chunk_size=800),
        )
        config_helper.save_user_config(cfg)

        with patch("artifice_graph.web.routers.byom.probe_endpoint") as mock_probe:
            mock_probe.return_value = ProbeResult(
                url="http://localhost:9999/v1",
                reachable=True,
                provider="generic-api",
                models=(),
                hint=None,
            )

            client.post(
                "/api/byom/test",
                json={
                    "url": "http://localhost:9999/v1",
                    "api_key": "sk-new",
                },
            )

        saved = config_helper.load_saved_config()
        assert saved is not None
        # LLM section was updated.
        assert saved.llm.base_url == "http://localhost:9999/v1"
        assert saved.llm.api_key == "sk-new"
        # Other sections survived.
        assert saved.embedding.base_url == "http://localhost:8888/v1"
        assert saved.embedding.model == "bge-m3"
        assert saved.ingestion.chunk_size == 800


# ── Contract + SSRF + first-paint tests (pytest-httpx) ────────────────────


class TestByomContractAndSsrf:
    """Drive the real HTTP layer so the JSON keys match what byom.js reads."""

    # -- GET /api/byom/state ---------------------------------------------

    def test_state_json_keys_default(self, client):
        r = client.get("/api/byom/state")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {
            "app",
            "configured",
            "endpoint",
            "model",
            "recommendations",
            "embedding",
        }
        assert body["app"] == "artifice-graph"
        assert body["configured"] is False
        assert body["embedding"]["configured"] is False
        assert body["embedding"]["endpoint"] == "http://localhost:11434"
        # No model has been chosen, so state reports none. The default used to
        # be "bge-m3"; naming a model the user may not have installed is the
        # defect this branch removes — resolution picks one per run instead.
        assert body["embedding"]["model"] is None

    def test_state_json_keys_configured(self, client):
        cfg = PipelineConfig(llm=LLMConfig(base_url="http://localhost:9999/v1", api_key="sk-real"))
        config_helper.save_user_config(cfg)
        r = client.get("/api/byom/state")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {
            "app",
            "configured",
            "endpoint",
            "model",
            "recommendations",
            "embedding",
        }
        assert body["configured"] is True

    # -- GET /api/byom/detect --------------------------------------------

    def test_detect_json_keys_all_down(self, client, httpx_mock):
        for url in ("http://localhost:11434", "http://localhost:1234", "http://localhost:8080"):
            httpx_mock.add_exception(
                httpx.ConnectError("Connection refused"), url=url + "/api/tags"
            )

        r = client.get("/api/byom/detect")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"endpoints"}
        assert len(body["endpoints"]) == 3
        for ep in body["endpoints"]:
            assert set(ep.keys()) == {"url", "name", "provider", "reachable", "models", "hint"}
            assert ep["reachable"] is False

    def test_detect_json_keys_one_up(self, client, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:11434/api/tags", json={"models": [{"name": "qwen2.5:32b"}]}
        )
        httpx_mock.add_response(
            url="http://localhost:11434/v1/models", json={"data": [{"id": "qwen2.5:32b"}]}
        )
        for url in ("http://localhost:1234", "http://localhost:8080"):
            httpx_mock.add_exception(
                httpx.ConnectError("Connection refused"), url=url + "/api/tags"
            )

        r = client.get("/api/byom/detect")
        assert r.status_code == 200
        reachable = [ep for ep in r.json()["endpoints"] if ep["reachable"]]
        assert len(reachable) == 1
        assert reachable[0]["provider"] == "ollama"

    # -- POST /api/byom/test ---------------------------------------------

    def test_test_json_keys_reachable(self, client, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:11434/api/tags", json={"models": [{"name": "qwen2.5:32b"}]}
        )
        httpx_mock.add_response(
            url="http://localhost:11434/v1/models", json={"data": [{"id": "qwen2.5:32b"}]}
        )

        r = client.post("/api/byom/test", json={"url": "http://localhost:11434/v1", "api_key": ""})
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"reachable", "provider", "models", "hint"}
        assert body["reachable"] is True

    def test_test_json_keys_refused(self, client, httpx_mock):
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"), url="http://localhost:11434/api/tags"
        )

        r = client.post("/api/byom/test", json={"url": "http://localhost:11434/v1", "api_key": ""})
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"reachable", "provider", "models", "hint"}
        assert body["reachable"] is False

    def test_test_json_keys_timeout(self, client, httpx_mock):
        httpx_mock.add_exception(
            httpx.TimeoutException("Timed out"), url="http://localhost:11434/api/tags"
        )

        r = client.post("/api/byom/test", json={"url": "http://localhost:11434/v1", "api_key": ""})
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"reachable", "provider", "models", "hint"}
        assert body["reachable"] is False

    # -- POST /api/byom/test-embedding ------------------------------------

    def test_test_embedding_json_keys_reachable(self, client, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:11434/api/tags", json={"models": [{"name": "bge-m3"}]}
        )
        httpx_mock.add_response(
            url="http://localhost:11434/v1/models", json={"data": [{"id": "bge-m3"}]}
        )

        r = client.post(
            "/api/byom/test-embedding", json={"url": "http://localhost:11434/v1", "api_key": ""}
        )
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"reachable", "provider", "models", "hint"}
        assert body["reachable"] is True
        assert body["provider"] == "ollama"

    def test_test_embedding_json_keys_refused(self, client, httpx_mock):
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"), url="http://localhost:11434/api/tags"
        )

        r = client.post(
            "/api/byom/test-embedding", json={"url": "http://localhost:11434/v1", "api_key": ""}
        )
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"reachable", "provider", "models", "hint"}
        assert body["reachable"] is False

    def test_test_embedding_json_keys_timeout(self, client, httpx_mock):
        httpx_mock.add_exception(
            httpx.TimeoutException("Timed out"), url="http://localhost:11434/api/tags"
        )

        r = client.post(
            "/api/byom/test-embedding", json={"url": "http://localhost:11434/v1", "api_key": ""}
        )
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"reachable", "provider", "models", "hint"}
        assert body["reachable"] is False

    def test_embedding_success_saves_config(self, client, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:11434/api/tags", json={"models": [{"name": "bge-m3"}]}
        )
        httpx_mock.add_response(
            url="http://localhost:11434/v1/models", json={"data": [{"id": "bge-m3"}]}
        )

        r = client.post(
            "/api/byom/test-embedding", json={"url": "http://localhost:11434/v1", "api_key": ""}
        )
        assert r.status_code == 200
        assert r.json()["reachable"] is True

        saved = config_helper.load_saved_config()
        assert saved is not None
        assert saved.embedding.base_url == "http://localhost:11434/v1"

    def test_embedding_unreachable_does_not_save(self, client, httpx_mock):
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"), url="http://localhost:11434/api/tags"
        )

        r = client.post(
            "/api/byom/test-embedding", json={"url": "http://localhost:11434/v1", "api_key": ""}
        )
        assert r.json()["reachable"] is False

        saved = config_helper.load_saved_config()
        assert saved is None

    def test_embedding_empty_url_rejected(self, client, httpx_mock):
        r = client.post("/api/byom/test-embedding", json={"url": "", "api_key": ""})
        assert r.status_code == 400
        body = r.json()
        assert "hint" in body
        assert "error" in body

    def test_embedding_rejects_link_local_before_network(self, client, httpx_mock):
        r = client.post(
            "/api/byom/test-embedding",
            json={"url": "http://169.254.169.254/latest/meta-data/", "api_key": ""},
        )
        assert r.status_code == 400
        assert "hint" in r.json()
        assert not httpx_mock.get_requests(), "a request was issued for a rejected URL"

    def test_embedding_rejects_public_host_before_network(self, client, httpx_mock):
        r = client.post(
            "/api/byom/test-embedding", json={"url": "https://api.openai.com/v1", "api_key": ""}
        )
        assert r.status_code == 400
        assert "hint" in r.json()
        assert not httpx_mock.get_requests(), "a request was issued for a rejected URL"

    def test_embedding_rejects_file_scheme_before_network(self, client, httpx_mock):
        r = client.post(
            "/api/byom/test-embedding", json={"url": "file:///etc/passwd", "api_key": ""}
        )
        assert r.status_code == 400
        assert "hint" in r.json()
        assert not httpx_mock.get_requests(), "a request was issued for a rejected URL"

    def test_embedding_state_reports_defaults(self, client):
        """When no config is saved, embedding reports EmbeddingConfig field defaults."""
        r = client.get("/api/byom/state")
        assert r.status_code == 200
        emb = r.json()["embedding"]
        assert emb["configured"] is False
        assert emb["endpoint"] == "http://localhost:11434"
        # Neither case sets a model, so state reports none rather than the old
        # "bge-m3" default. These tests are about the endpoint being
        # configured; the model is chosen per run by _resolution.
        assert emb["model"] is None

    def test_embedding_state_reports_configured(self, client):
        """When the embedding URL is changed, state reports configured=True."""
        cfg = PipelineConfig(
            llm=LLMConfig(),
            embedding=EmbeddingConfig(base_url="http://localhost:8888/v1"),
        )
        config_helper.save_user_config(cfg)

        r = client.get("/api/byom/state")
        emb = r.json()["embedding"]
        assert emb["configured"] is True
        assert emb["endpoint"] == "http://localhost:8888/v1"
        # Neither case sets a model, so state reports none rather than the old
        # "bge-m3" default. These tests are about the endpoint being
        # configured; the model is chosen per run by _resolution.
        assert emb["model"] is None

    # -- SSRF surface -----------------------------------------------------

    def _assert_rejected_before_network(self, r, httpx_mock):
        assert r.status_code == 400
        body = r.json()
        assert "hint" in body
        assert "error" in body
        assert isinstance(body["hint"], str)
        assert not httpx_mock.get_requests(), "a request was issued for a rejected URL"

    def test_rejects_link_local_before_network(self, client, httpx_mock):
        r = client.post(
            "/api/byom/test",
            json={"url": "http://169.254.169.254/latest/meta-data/", "api_key": ""},
        )
        self._assert_rejected_before_network(r, httpx_mock)

    def test_rejects_public_host_before_network(self, client, httpx_mock):
        r = client.post("/api/byom/test", json={"url": "https://api.openai.com/v1", "api_key": ""})
        self._assert_rejected_before_network(r, httpx_mock)

    def test_rejects_file_scheme_before_network(self, client, httpx_mock):
        r = client.post("/api/byom/test", json={"url": "file:///etc/passwd", "api_key": ""})
        self._assert_rejected_before_network(r, httpx_mock)

    def test_rejects_no_host_before_network(self, client, httpx_mock):
        r = client.post("/api/byom/test", json={"url": "http:///v1", "api_key": ""})
        self._assert_rejected_before_network(r, httpx_mock)

    # -- First paint must not block ---------------------------------------

    def test_root_does_not_probe_and_links_assets(self, client, httpx_mock):
        for url in ("http://localhost:11434", "http://localhost:1234", "http://localhost:8080"):
            httpx_mock.add_exception(
                httpx.ConnectError("Connection refused"), url=url + "/api/tags", is_optional=True
            )
        for url in (
            "http://localhost:11434/v1",
            "http://localhost:1234/v1",
            "http://localhost:8080/v1",
        ):
            httpx_mock.add_exception(
                httpx.ConnectError("Connection refused"), url=url + "/models", is_optional=True
            )

        start = time.perf_counter()
        r = client.get("/")
        elapsed = time.perf_counter() - start

        assert r.status_code == 200
        assert elapsed < 0.5, f"GET / took {elapsed:.3f}s, root must not probe"
        assert not httpx_mock.get_requests(), "root route made a network request"
        html = r.text
        assert "/shared/byom.css" in html
        assert "/shared/byom.js" in html
