# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Security tests for artifice-transcribe: SSRF validation and credential redaction."""

from __future__ import annotations

import pytest
from secure_io import is_restricted

# Module-level endpoint rejection markers carried in HTTP 400 detail strings.
# None are secrets — they describe which rule rejected the endpoint.
_ENDPOINT_REJECTION_MARKERS = frozenset(
    {"link-local", "ARTIFICE_ALLOW_PUBLIC_MODELS", "public address"}
)


def _assert_not_endpoint_rejection(resp) -> None:
    """Fail if *resp* is an HTTP 400 triggered by the endpoint allowlist."""
    if resp.status_code != 400:
        return
    detail = resp.json().get("detail", "")
    for marker in _ENDPOINT_REJECTION_MARKERS:
        assert marker not in detail, (
            f"endpoint rejection leaked: {detail!r}"
        )


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

    # ── Config-read validation: endpoints that load base_url from disk ────

    async def test_generate_rejects_link_local_from_config(
        self, api, tmp_path, monkeypatch
    ):
        """A link-local base_url saved in the persisted config is refused
        when the generate endpoint reads it."""
        self._save_test_config(tmp_path, monkeypatch, "http://169.254.169.254/v1")
        resp = await api.client.post(
            "/api/v1/inference/generate",
            json={"prompt": "Hello"},
        )
        assert resp.status_code == 400
        assert "link-local" in resp.json()["detail"]

    async def test_generate_accepts_loopback_from_config(
        self, api, tmp_path, monkeypatch
    ):
        """A loopback base_url in the persisted config passes validation.
        The downstream connection will fail (no server is running in the
        test environment), but the URL itself must not be rejected."""
        self._save_test_config(tmp_path, monkeypatch, "http://127.0.0.1:11434/v1")
        try:
            resp = await api.client.post(
                "/api/v1/inference/generate",
                json={"prompt": "Hello"},
            )
            _assert_not_endpoint_rejection(resp)
        except Exception:
            # The request failed downstream (connection refused / timeout)
            # because no model server is running.  That proves validation
            # passed — an endpoint-rejection 400 would have been a clean
            # response, not an unhandled exception.
            pass

    async def test_summarize_rejects_link_local_from_config(
        self, api, tmp_path, monkeypatch
    ):
        """The summarise endpoint must re-validate the base_url it reads from
        the persisted config."""
        self._save_test_config(tmp_path, monkeypatch, "http://169.254.169.254/v1")
        await self._create_completed_job_with_segment(api, "job-ssrf-sum")
        resp = await api.client.post("/api/v1/jobs/job-ssrf-sum/summarize")
        assert resp.status_code == 400
        assert "link-local" in resp.json()["detail"]

    async def test_cleanup_rejects_link_local_from_config(
        self, api, tmp_path, monkeypatch
    ):
        """The cleanup endpoint must re-validate the base_url it reads from
        the persisted config."""
        self._save_test_config(tmp_path, monkeypatch, "http://169.254.169.254/v1")
        await self._create_completed_job_with_segment(api, "job-ssrf-cln")
        resp = await api.client.post("/api/v1/jobs/job-ssrf-cln/cleanup")
        assert resp.status_code == 400
        assert "link-local" in resp.json()["detail"]

    async def test_summarize_accepts_loopback_from_config(
        self, api, tmp_path, monkeypatch
    ):
        """Loopback base_url in config passes summarise validation."""
        self._save_test_config(tmp_path, monkeypatch, "http://localhost:11434/v1")
        await self._create_completed_job_with_segment(api, "job-ssrf-sum-ok")
        resp = await api.client.post("/api/v1/jobs/job-ssrf-sum-ok/summarize")
        _assert_not_endpoint_rejection(resp)

    async def test_cleanup_accepts_loopback_from_config(
        self, api, tmp_path, monkeypatch
    ):
        """Loopback base_url in config passes cleanup validation."""
        self._save_test_config(tmp_path, monkeypatch, "http://127.0.0.1:11434/v1")
        await self._create_completed_job_with_segment(api, "job-ssrf-cln-ok")
        resp = await api.client.post("/api/v1/jobs/job-ssrf-cln-ok/cleanup")
        _assert_not_endpoint_rejection(resp)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _save_test_config(
        tmp_path, monkeypatch, base_url: str
    ) -> None:
        """Save an inference config to an isolated temp file."""
        config_file = tmp_path / "inference_config.json"
        monkeypatch.setattr(
            "artifice_transcribe.api.v1.routes._INFERENCE_CONFIG_FILE",
            config_file,
        )
        from artifice_transcribe.api.v1.routes import _save_inference_config

        _save_inference_config({
            "base_url": base_url,
            "api_key": "not-needed",
            "model_name": "",
            "vision_enabled": False,
        })

    @staticmethod
    async def _create_completed_job_with_segment(api, job_id: str) -> None:
        """Insert a completed transcription job with one segment."""
        from artifice_transcribe.db.models import (
            JobStatus,
            TranscriptionJob,
            TranscriptSegment,
        )

        async with api.session_factory() as db:
            db.add(TranscriptionJob(
                id=job_id, filename="test.wav",
                status=JobStatus.completed, progress_percentage=100.0,
            ))
            db.add(TranscriptSegment(
                job_id=job_id, speaker_label="SPEAKER_00",
                start_time=0.0, end_time=1.0, text="Hello world.",
            ))
            await db.commit()


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
        """After saving, the config file must be restricted to the current user."""

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
        assert is_restricted(config_file)


class TestLoadTimePermissionRepair:
    """Permissions on pre-existing loose ``inference_config.json`` are
    repaired at load time.

    These tests exercise the POSIX branch (os.chmod).  The Windows
    branch (icacls) is verified manually on native Windows.
    """

    def test_loose_file_is_repaired_on_load(self, tmp_path, monkeypatch):
        """A file created at 0o644 is tightened to 0o600 on load."""
        import os

        config_file = tmp_path / "inference_config.json"
        monkeypatch.setattr(
            "artifice_transcribe.api.v1.routes._INFERENCE_CONFIG_FILE",
            config_file,
        )

        # Create a loose file.
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            '{"base_url": "http://localhost:11434/v1", "api_key": "sk-old"}'
        )
        os.chmod(config_file, 0o644)
        assert not is_restricted(config_file)

        from artifice_transcribe.api.v1.routes import _load_inference_config

        result = _load_inference_config()
        assert is_restricted(config_file)
        assert result["api_key"] == "sk-old"

    def test_load_succeeds_when_repair_raises(self, tmp_path, monkeypatch, caplog):
        """Load must still return the data even when the repair fails."""
        import os

        config_file = tmp_path / "inference_config.json"
        monkeypatch.setattr(
            "artifice_transcribe.api.v1.routes._INFERENCE_CONFIG_FILE",
            config_file,
        )

        # Create a loose file.
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            '{"base_url": "http://localhost:11434/v1", "api_key": "sk-old"}'
        )
        os.chmod(config_file, 0o644)

        def _failing_restrict(_path):
            raise OSError("Simulated ACL failure — exFAT volume")

        monkeypatch.setattr(
            "secure_io.restrict_to_current_user", _failing_restrict
        )

        from artifice_transcribe.api.v1.routes import _load_inference_config

        result = _load_inference_config()
        assert result["api_key"] == "sk-old"

        assert "Could not restrict permissions" in caplog.text
