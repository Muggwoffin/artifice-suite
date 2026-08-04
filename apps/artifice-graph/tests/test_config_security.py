# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Security tests for graph: file permissions, credential redaction, and
round-trip safety."""

from __future__ import annotations

import json

from secure_io import is_restricted

from artifice_graph.config import LLMConfig, PipelineConfig


class TestConfigFilePermissions:
    """Restrictive file permissions for config.json."""

    def test_save_user_config_creates_restricted_file(self, tmp_path, monkeypatch):
        """save_user_config must write a file restricted to the current user."""
        from artifice_graph.web import config_helper

        monkeypatch.setattr(config_helper, "CONFIG_FILE", tmp_path / "config.json")

        cfg = PipelineConfig(llm=LLMConfig(api_key="sk-test-secret"))
        config_helper.save_user_config(cfg)

        config_file = tmp_path / "config.json"
        assert config_file.exists()
        assert is_restricted(config_file)

    def test_save_user_config_contents_are_correct(self, tmp_path, monkeypatch):
        """The written file must contain the correct config data."""
        from artifice_graph.web import config_helper

        monkeypatch.setattr(config_helper, "CONFIG_FILE", tmp_path / "config.json")

        cfg = PipelineConfig(
            llm=LLMConfig(
                api_key="sk-test-456",
                base_url="http://localhost:11434/v1",
                model="test-model",
            ),
        )
        config_helper.save_user_config(cfg)

        data = json.loads((tmp_path / "config.json").read_text())
        assert data["llm"]["api_key"] == "sk-test-456"
        assert data["llm"]["base_url"] == "http://localhost:11434/v1"
        assert data["llm"]["model"] == "test-model"

    def test_existing_unprotected_file_is_tightened(self, tmp_path, monkeypatch):
        """A second save must restrict a file that already exists unprotected."""
        from artifice_graph.web import config_helper

        monkeypatch.setattr(config_helper, "CONFIG_FILE", tmp_path / "config.json")

        # Simulate an existing unprotected file.
        config_file = tmp_path / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(
            {"llm": {"api_key": "old-secret"}}, indent=2,
        ))

        # Platform note:
        # On Windows CI, default ACLs can already satisfy "restricted".
        # The behavior we care about is that save_user_config leaves the file
        # restricted and writes updated content.

        # A save must tighten it.
        cfg = PipelineConfig(llm=LLMConfig(api_key="new-secret"))
        config_helper.save_user_config(cfg)

        assert is_restricted(config_file)
        data = json.loads(config_file.read_text())
        assert data["llm"]["api_key"] == "new-secret"


class TestCredentialRedaction:
    """Redaction in _redact_config — follows OCR's pattern."""

    def test_redact_config_replaces_api_key_with_placeholder(self):
        """An LLMConfig with a real key must return the placeholder."""
        from artifice_graph.web.server import _redact_config

        cfg = PipelineConfig(llm=LLMConfig(api_key="sk-real-secret-789"))
        redacted = _redact_config(cfg)
        assert redacted.llm.api_key == "*" * 12

    def test_redact_config_preserves_empty_key(self):
        """An empty api_key must not become asterisks."""
        from artifice_graph.web.server import _redact_config

        cfg = PipelineConfig(llm=LLMConfig(api_key=""))
        redacted = _redact_config(cfg)
        assert redacted.llm.api_key == ""

    def test_redact_config_preserves_other_fields(self):
        """Redaction must not touch LLM fields that are not api_key."""
        from artifice_graph.web.server import _redact_config

        cfg = PipelineConfig(llm=LLMConfig(
            api_key="sk-secret",
            base_url="http://example.com:11434/v1",
            model="test-model",
        ))
        redacted = _redact_config(cfg)
        assert redacted.llm.base_url == "http://example.com:11434/v1"
        assert redacted.llm.model == "test-model"

    def test_redact_config_does_not_mutate_original(self):
        """The original PipelineConfig must be left intact."""
        from artifice_graph.web.server import _redact_config

        cfg = PipelineConfig(llm=LLMConfig(api_key="sk-original"))
        _redact_config(cfg)
        assert cfg.llm.api_key == "sk-original", (
            "Redaction must not mutate the original config"
        )


class TestRoundTripGuard:
    """Saving a config with the redacted placeholder must not overwrite the
    stored key."""

    def test_save_user_config_ignores_placeholder(self, tmp_path, monkeypatch):
        """save_user_config with a placeholder must not persist it."""
        from artifice_graph.web import config_helper

        monkeypatch.setattr(config_helper, "CONFIG_FILE", tmp_path / "config.json")

        # Store a real key first.
        cfg = PipelineConfig(llm=LLMConfig(api_key="sk-stored-key"))
        config_helper.save_user_config(cfg)

        # Now save a config where the LLM has the placeholder as its key
        # (simulates a round-trip from GET → POST).
        cfg_roundtripped = PipelineConfig(llm=LLMConfig(api_key="*" * 12, model="new-model"))
        config_helper.save_user_config(cfg_roundtripped)

        # The stored key must still be the original.
        data = json.loads((tmp_path / "config.json").read_text())
        assert data["llm"]["api_key"] == "sk-stored-key", (
            "The stored key must survive a round-trip of the redacted placeholder"
        )
        assert data["llm"]["model"] == "new-model"

    def test_load_saved_config_then_redact_returns_placeholder(self, tmp_path, monkeypatch):
        """load_saved_config + _redact_config must return the placeholder
        while the on-disk file keeps the real key."""
        from artifice_graph.web import config_helper, server

        monkeypatch.setattr(config_helper, "CONFIG_FILE", tmp_path / "config.json")

        cfg = PipelineConfig(llm=LLMConfig(api_key="sk-on-disk-key"))
        config_helper.save_user_config(cfg)

        # Load and redact.
        loaded = config_helper.load_saved_config()
        assert loaded is not None
        redacted = server._redact_config(loaded)
        assert redacted.llm.api_key == "*" * 12

        # The on-disk key must still be the real one.
        data = json.loads((tmp_path / "config.json").read_text())
        assert data["llm"]["api_key"] == "sk-on-disk-key"
