# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the BYOM onboarding endpoints in artifice-draft."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import httpx
import pytest
from artifice_draft.web import runtime
from artifice_draft.web.server import app
from fastapi.testclient import TestClient
from model_harness.discovery import ProbeResult


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Never let a test touch the real ~/.artifice_draft/web_settings.json."""
    monkeypatch.setattr(runtime, "_SETTINGS_PATH", tmp_path / "web_settings.json")


@pytest.fixture()
def client():
    return TestClient(app)


# ── GET /api/byom/state ───────────────────────────────────────────────────


class TestByomState:
    def test_returns_all_keys_in_default_state(self, client):
        r = client.get("/api/byom/state")
        assert r.status_code == 200
        body = r.json()

        assert body["app"] == "artifice-draft"
        assert body["configured"] is False
        assert body["endpoint"] is None
        assert body["model"] is None
        assert "recommendations" in body

    def test_configured_true_when_base_url_set(self, client):
        runtime.save_settings({"base_url": "http://localhost:11434/v1"})

        r = client.get("/api/byom/state")
        assert r.status_code == 200
        assert r.json()["configured"] is True

    def test_configured_false_for_empty_base_url(self, client):
        runtime.save_settings({"base_url": ""})

        r = client.get("/api/byom/state")
        assert r.status_code == 200
        assert r.json()["configured"] is False

    def test_model_returned_from_settings(self, client):
        runtime.save_settings({"model_name": "llama3.2:3b"})

        r = client.get("/api/byom/state")
        assert r.json()["model"] == "llama3.2:3b"

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

    def test_state_roles_match_role_setting(self, client):
        """state.roles is derived from _ROLE_SETTING keys — derive one from the
        other and assert equality, so the two can never drift apart."""
        from artifice_draft.web.routers.byom import _ROLE_SETTING

        r = client.get("/api/byom/state")
        assert r.status_code == 200
        assert r.json()["roles"] == list(_ROLE_SETTING)
        assert r.json()["roles"] == ["chat"]


# ── GET /api/byom/detect ──────────────────────────────────────────────────


class TestByomDetect:
    def test_returns_endpoints_array(self, client):
        with patch("artifice_draft.web.routers.byom.detect_local_servers") as mock_detect:
            mock_detect.return_value = [
                ProbeResult(
                    url="http://localhost:11434/v1",
                    reachable=True,
                    provider="ollama",
                    models=("llama3.2:3b", "qwen2.5:7b"),
                    hint=None,
                ),
            ]

            r = client.get("/api/byom/detect")
            assert r.status_code == 200
            eps = r.json()["endpoints"]
            assert len(eps) == 1
            ep = eps[0]
            assert ep["name"] == "Ollama"
            assert ep["provider"] == "ollama"
            assert ep["reachable"] is True
            assert ep["models"] == ["llama3.2:3b", "qwen2.5:7b"]

    def test_unreachable_endpoint_has_hint(self, client):
        with patch("artifice_draft.web.routers.byom.detect_local_servers") as mock_detect:
            mock_detect.return_value = [
                ProbeResult(
                    url="http://localhost:1234/v1",
                    reachable=False,
                    provider="lm-studio",
                    models=(),
                    hint="Ensure the LM Studio server is running",
                ),
            ]

            r = client.get("/api/byom/detect")
            ep = r.json()["endpoints"][0]
            assert ep["reachable"] is False
            assert ep["hint"] == "Ensure the LM Studio server is running"


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
        with patch("artifice_draft.web.routers.byom.probe_endpoint") as mock_probe:
            mock_probe.return_value = ProbeResult(
                url="http://localhost:11434/v1",
                reachable=True,
                provider="ollama",
                models=("llama3.2:3b",),
                hint=None,
            )

            r = client.post(
                "/api/byom/test",
                json={
                    "url": "http://localhost:11434/v1",
                    "api_key": "",
                },
            )
            assert r.status_code == 200
            assert r.json()["reachable"] is True

            # Config was saved — base_url is set.
            state_r = client.get("/api/byom/state")
            assert state_r.json()["configured"] is True

    def test_unreachable_probe_does_not_save(self, client):
        with patch("artifice_draft.web.routers.byom.probe_endpoint") as mock_probe:
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
        with patch("artifice_draft.web.routers.byom.probe_endpoint") as mock_probe:
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

            saved = runtime.load_settings()
            assert saved.get("api_key") == "sk-secret-123"
            assert saved.get("base_url") == "http://localhost:9999/v1"


# ── Contract + SSRF + first-paint tests (pytest-httpx) ────────────────────


class TestByomContractAndSsrf:
    """Drive the real HTTP layer so the JSON keys match what byom.js reads."""

    # -- GET /api/byom/state ---------------------------------------------

    def test_state_json_keys_default(self, client):
        r = client.get("/api/byom/state")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {
            "app", "configured", "endpoint", "model", "roles", "recommendations"
        }
        assert body["app"] == "artifice-draft"
        assert body["configured"] is False

    def test_state_json_keys_configured(self, client):
        runtime.save_settings({"base_url": "http://localhost:11434/v1", "api_key": "sk-real"})
        r = client.get("/api/byom/state")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {
            "app", "configured", "endpoint", "model", "roles", "recommendations"
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
            url="http://localhost:11434/api/tags", json={"models": [{"name": "llama3.2:3b"}]}
        )
        httpx_mock.add_response(
            url="http://localhost:11434/v1/models", json={"data": [{"id": "llama3.2:3b"}]}
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
            url="http://localhost:11434/api/tags", json={"models": [{"name": "llama3.2:3b"}]}
        )
        httpx_mock.add_response(
            url="http://localhost:11434/v1/models", json={"data": [{"id": "llama3.2:3b"}]}
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
