# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Security tests for draft: file permissions, credential redaction, and
round-trip safety."""

from __future__ import annotations

import json

from secure_io import is_restricted


class TestConfigFilePermissions:
    """Restrictive file permissions for web_settings.json."""

    def test_save_settings_creates_restricted_file(self, tmp_path, monkeypatch):
        """save_settings must write a file restricted to the current user."""
        from artifice_draft.web import runtime

        monkeypatch.setattr(runtime, "_SETTINGS_PATH", tmp_path / "web_settings.json")

        runtime.save_settings({"api_key": "sk-test-secret", "base_url": "http://localhost:11434"})

        settings_file = tmp_path / "web_settings.json"
        assert settings_file.exists()
        assert is_restricted(settings_file)

    def test_save_settings_preserves_merge(self, tmp_path, monkeypatch):
        """A second save with a partial patch must not drop existing keys."""
        from artifice_draft.web import runtime

        monkeypatch.setattr(runtime, "_SETTINGS_PATH", tmp_path / "web_settings.json")

        runtime.save_settings({"api_key": "sk-test-123", "model_name": "gemma"})
        runtime.save_settings({"model_name": "llama"})

        data = json.loads((tmp_path / "web_settings.json").read_text())
        assert data["api_key"] == "sk-test-123"
        assert data["model_name"] == "llama"

    def test_existing_unprotected_file_is_tightened(self, tmp_path, monkeypatch):
        """A second save must restrict a file that already exists unprotected."""
        from artifice_draft.web import runtime

        monkeypatch.setattr(runtime, "_SETTINGS_PATH", tmp_path / "web_settings.json")

        # Simulate an existing unprotected file (default umask, typically 0o644).
        settings_file = tmp_path / "web_settings.json"
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(json.dumps({"api_key": "old-secret"}, indent=2))

        # Platform note:
        # On Windows CI, default ACLs can already satisfy "restricted".
        # The behavior we care about is that save_settings leaves the file
        # restricted and writes updated content.

        # A save must tighten it.
        runtime.save_settings({"api_key": "new-secret"})

        assert is_restricted(settings_file)
        data = json.loads(settings_file.read_text())
        assert data["api_key"] == "new-secret"


class TestCredentialRedaction:
    """API key redaction in serialize_settings — follows OCR's pattern."""

    def test_serialize_settings_redacts_api_key(self, monkeypatch, tmp_path):
        """serialize_settings must return a placeholder, not the real key."""
        from artifice_draft import config
        from artifice_draft.web.runtime import serialize_settings

        cfg = config.AppConfig()
        cfg.api_key = "sk-real-secret"

        result = serialize_settings(cfg)
        assert result["api_key"] == "*" * 12

    def test_serialize_settings_preserves_empty_key(self):
        """An empty/None api_key must not be redacted to asterisks."""
        from artifice_draft import config
        from artifice_draft.web.runtime import serialize_settings

        cfg = config.AppConfig()
        cfg.api_key = ""

        result = serialize_settings(cfg)
        assert result["api_key"] == ""

    def test_serialize_settings_preserves_other_fields(self):
        """Redaction must not touch non-secret fields."""
        from artifice_draft import config
        from artifice_draft.web.runtime import serialize_settings

        cfg = config.AppConfig()
        cfg.api_key = "sk-secret"
        cfg.model_name = "test-model"
        cfg.base_url = "http://example.com:1234"

        result = serialize_settings(cfg)
        assert result["model_name"] == "test-model"
        assert result["base_url"] == "http://example.com:1234"


class TestRoundTripGuard:
    """save_settings must reject the redacted placeholder."""

    def test_placeholder_is_not_written_to_file(self, tmp_path, monkeypatch):
        """A POST with the redacted placeholder must not overwrite the stored key."""
        from artifice_draft.web import runtime

        monkeypatch.setattr(runtime, "_SETTINGS_PATH", tmp_path / "web_settings.json")

        # Store a real key first.
        runtime.save_settings({"api_key": "sk-real-key-123"})

        # Simulate a round-trip: the client GETs settings, receives the
        # placeholder, and POSTs the same body back unmodified.
        runtime.save_settings({"api_key": "*" * 12, "model_name": "updated-model"})

        data = json.loads((tmp_path / "web_settings.json").read_text())
        assert data["api_key"] == "sk-real-key-123", (
            "The stored key must survive a round-trip of the redacted placeholder"
        )
        assert data["model_name"] == "updated-model"

    def test_empty_patch_after_cleaning_placeholder_does_not_crash(self, tmp_path, monkeypatch):
        """A patch containing only the placeholder should not error."""
        from artifice_draft.web import runtime

        monkeypatch.setattr(runtime, "_SETTINGS_PATH", tmp_path / "web_settings.json")

        runtime.save_settings({"api_key": "sk-real"})
        # Patch with only the placeholder — should be a no-op.
        result = runtime.save_settings({"api_key": "*" * 12})
        assert result["api_key"] == "sk-real", (
            "The returned settings must still show the stored key"
        )
