# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Security tests for draft: file permissions on web_settings.json."""

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

        assert not is_restricted(settings_file), "precondition: file starts unprotected"

        # A save must tighten it.
        runtime.save_settings({"api_key": "new-secret"})

        assert is_restricted(settings_file)
        data = json.loads(settings_file.read_text())
        assert data["api_key"] == "new-secret"
