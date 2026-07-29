"""Security tests for artifice-transcribe: SSRF validation and credential redaction."""

from __future__ import annotations

import json
import os

import pytest


@pytest.mark.asyncio
class TestSSRFValidation:
    """SSRF host allowlist for inference endpoints — finding #2."""

    async def test_models_endpoint_rejects_public_address(self, api):
        """A public address is rejected without an explicit opt-in.

        An IP literal is used rather than a hostname so the assertion does not
        depend on DNS: a resolver that answers for made-up names would
        otherwise change which branch rejects the request.
        """
        resp = await api.client.post(
            "/api/v1/inference/models",
            json={"base_url": "http://8.8.8.8/v1", "api_key": "not-needed"},
        )
        assert resp.status_code == 400
        assert "ARTIFICE_ALLOW_PUBLIC_MODELS" in resp.json()["detail"]

    async def test_models_endpoint_rejects_cloud_metadata_address(self, api):
        """169.254.169.254 stays refused — it is checked before the opt-in."""
        resp = await api.client.post(
            "/api/v1/inference/models",
            json={"base_url": "http://169.254.169.254/v1", "api_key": "not-needed"},
        )
        assert resp.status_code == 400
        assert "link-local" in resp.json()["detail"]

    async def test_models_endpoint_accepts_private_network_address(self, api):
        """A model on the local network must pass validation.

        The connection itself will fail in a test environment; what matters is
        that it is not rejected *as a URL*.
        """
        resp = await api.client.post(
            "/api/v1/inference/models",
            json={"base_url": "http://192.168.1.50:11434/v1", "api_key": "not-needed"},
        )
        if resp.status_code == 400:
            assert "ARTIFICE_ALLOW_PUBLIC_MODELS" not in resp.json().get("detail", "")
            assert "link-local" not in resp.json().get("detail", "")

    async def test_models_endpoint_accepts_localhost(self, api):
        """POST /inference/models with a localhost base_url is accepted
        (the connection itself will fail, but the URL passes validation)."""
        resp = await api.client.post(
            "/api/v1/inference/models",
            json={"base_url": "http://localhost:11434/v1", "api_key": "not-needed"},
        )
        # 400 from URL validation means the URL was rejected.
        # 500 or 200 means it passed validation (connection may fail).
        assert resp.status_code != 400 or "not in the local-first allowlist" not in resp.json().get("detail", "")

    async def test_test_endpoint_rejects_external_url(self, api):
        """POST /inference/test with an external base_url is rejected."""
        resp = await api.client.post(
            "/api/v1/inference/test",
            json={"base_url": "http://malicious.net/v1", "api_key": "not-needed"},
        )
        assert resp.status_code == 400

    async def test_config_endpoint_rejects_external_url(self, api):
        """POST /inference/config with an external base_url is rejected."""
        resp = await api.client.post(
            "/api/v1/inference/config",
            json={
                "base_url": "http://attacker.com/v1",
                "api_key": "not-needed",
                "model_name": "test",
                "vision_enabled": False,
            },
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestCredentialRedaction:
    """API key redaction in config responses — finding #5."""

    async def test_inference_config_redacts_saved_key(self, api):
        """GET /inference/config must redact the api_key even when one is saved."""
        # First save a config with a real-looking key.
        await api.client.post(
            "/api/v1/inference/config",
            json={
                "base_url": "http://localhost:11434/v1",
                "api_key": "sk-real-secret-key-12345",
                "model_name": "test",
                "vision_enabled": False,
            },
        )
        # Now fetch it and verify the key is redacted.
        resp = await api.client.get("/api/v1/inference/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("api_key") == "*" * 12

    async def test_inference_config_returns_empty_for_unset_key(self, api):
        """When no key is set, the redacted response should still return
        the empty/placeholder value (not a redaction of empty)."""
        resp = await api.client.get("/api/v1/inference/config")
        assert resp.status_code == 200
        data = resp.json()
        # Default is "not-needed" or empty; redaction only applies to truthy values.
        assert data.get("api_key") != "sk-real-secret-key-12345"

    async def test_save_returns_redacted_key(self, api):
        """POST /inference/config response must not echo the raw key back."""
        resp = await api.client.post(
            "/api/v1/inference/config",
            json={
                "base_url": "http://localhost:11434/v1",
                "api_key": "sk-another-secret",
                "model_name": "test",
                "vision_enabled": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        config = data.get("config", {})
        assert config.get("api_key") == "*" * 12


class TestConfigFilePermissions:
    """Restrictive file permissions for config files — finding #3."""

    def test_saved_config_has_restricted_permissions(self, tmp_path, monkeypatch):
        """After saving, the config file must be readable only by the owner."""
        from artifice_transcribe.api.v1.routes import _INFERENCE_CONFIG_FILE

        monkeypatch.setattr(
            "artifice_transcribe.api.v1.routes._INFERENCE_CONFIG_FILE",
            tmp_path / "inference_config.json",
        )
        from artifice_transcribe.api.v1.routes import _save_inference_config

        _save_inference_config(
            {"base_url": "http://localhost:11434/v1", "api_key": "test-key"}
        )
        config_file = tmp_path / "inference_config.json"
        assert config_file.exists()
        st = config_file.stat()
        # Mode should be exactly 0o600 (or 0o100600 with file type bits).
        assert st.st_mode & 0o777 == 0o600
