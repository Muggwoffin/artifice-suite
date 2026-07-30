# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Security tests for graph: file permissions on config.json."""

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

        assert not is_restricted(config_file), "precondition: file starts unprotected"

        # A save must tighten it.
        cfg = PipelineConfig(llm=LLMConfig(api_key="new-secret"))
        config_helper.save_user_config(cfg)

        assert is_restricted(config_file)
        data = json.loads(config_file.read_text())
        assert data["llm"]["api_key"] == "new-secret"
