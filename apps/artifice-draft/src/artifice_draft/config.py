# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Centralised settings for the ArtificeDraft tool."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from artifice_draft.models import EditingStyle, ExportFormat, LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    """Configuration values — override via environment variables if set."""

    # Bring Your Own Model (BYOM) configuration
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "not-needed"
    # Empty means "the user has not chosen a model", NOT "use this one".
    # These previously named gemma4:12b, which most users do not have
    # installed, and nothing checked the name against what Ollama actually
    # serves — so the first inference call failed with a raw provider 404.
    # artifice_draft._resolution fills these in once per run from the models
    # the endpoint reports. The OpenAI and Anthropic defaults below stay
    # concrete on purpose: those are catalogue names the user reads, not a
    # local shelf that can be probed.
    model_name: str = ""
    vision_enabled: bool = False

    ollama_model: str = ""
    ollama_base_url: str = "http://localhost:11434"

    batch_size: int = 5
    temperature: float = 0.3
    num_ctx: int = 8192

    max_retries: int = 3
    retry_delay_secs: float = 2.0

    llm_provider: LLMProvider = LLMProvider.OLLAMA
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    editing_style: EditingStyle = EditingStyle.ACADEMIC
    custom_system_prompt: str = ""
    style_guide: str = ""

    export_format: ExportFormat = ExportFormat.DOCX_TRACK_CHANGES
    output_dir: str = "output"

    enable_review: bool = False
    author_name: str = "ArtificeDraft"

    log_level: str = "INFO"
    log_file: str = ""

    @property
    def ollama_generate_url(self) -> str:
        """Full URL for the Ollama generate API endpoint."""
        base = self.ollama_base_url.rstrip("/")
        return f"{base}/api/generate"

    @classmethod
    def from_env(cls) -> AppConfig:
        """Build config from environment variables."""
        cfg = cls()

        if env := os.environ.get("BASE_URL"):
            cfg.base_url = env
        if env := os.environ.get("API_KEY"):
            cfg.api_key = env
        if env := os.environ.get("MODEL_NAME"):
            cfg.model_name = env
            cfg.ollama_model = env
            cfg.openai_model = env
        if env := os.environ.get("VISION_ENABLED"):
            cfg.vision_enabled = env.lower() in ("1", "true", "yes")

        if env := os.environ.get("OLLAMA_MODEL"):
            cfg.ollama_model = env
            cfg.model_name = env
        if env := os.environ.get("OLLAMA_URL"):
            cfg.ollama_base_url = env
            cfg.base_url = env
        if env := os.environ.get("LLM_PROVIDER"):
            try:
                cfg.llm_provider = LLMProvider(env.lower())
            except ValueError:
                logger.warning("Unknown LLM_PROVIDER '%s', keeping default", env)

        if env := os.environ.get("OPENAI_API_KEY"):
            cfg.openai_api_key = env
            cfg.api_key = env
        if env := os.environ.get("OPENAI_MODEL"):
            cfg.openai_model = env
            cfg.model_name = env
        if env := os.environ.get("OPENAI_BASE_URL"):
            cfg.openai_base_url = env
            cfg.base_url = env

        if env := os.environ.get("ANTHROPIC_API_KEY"):
            cfg.anthropic_api_key = env
        if env := os.environ.get("ANTHROPIC_MODEL"):
            cfg.anthropic_model = env

        if env := os.environ.get("EDITING_STYLE"):
            try:
                cfg.editing_style = EditingStyle(env.lower())
            except ValueError:
                logger.warning("Unknown EDITING_STYLE '%s', keeping default", env)
        if env := os.environ.get("CUSTOM_SYSTEM_PROMPT"):
            cfg.custom_system_prompt = env
        if env := os.environ.get("STYLE_GUIDE"):
            cfg.style_guide = env

        if env := os.environ.get("EXPORT_FORMAT"):
            try:
                cfg.export_format = ExportFormat(env.lower())
            except ValueError:
                logger.warning("Unknown EXPORT_FORMAT '%s', keeping default", env)

        if env := os.environ.get("BATCH_SIZE"):
            try:
                cfg.batch_size = int(env)
            except ValueError:
                pass
        if env := os.environ.get("TEMPERATURE"):
            try:
                cfg.temperature = float(env)
            except ValueError:
                pass

        if env := os.environ.get("ENABLE_REVIEW"):
            cfg.enable_review = env.lower() in ("1", "true", "yes")
        if env := os.environ.get("AUTHOR_NAME"):
            cfg.author_name = env

        if env := os.environ.get("LOG_LEVEL"):
            cfg.log_level = env.upper()
        if env := os.environ.get("LOG_FILE"):
            cfg.log_file = env

        logger.debug(
            "Config loaded: provider=%s, model=%s, style=%s",
            cfg.llm_provider.value,
            cfg.active_model,
            cfg.editing_style.value,
        )
        return cfg

    @property
    def active_model(self) -> str:
        """Return the model name for the currently selected provider."""
        if self.model_name:
            return self.model_name
        if self.llm_provider == LLMProvider.OLLAMA:
            return self.ollama_model
        elif self.llm_provider == LLMProvider.OPENAI:
            return self.openai_model
        elif self.llm_provider == LLMProvider.ANTHROPIC:
            return self.anthropic_model
        return self.ollama_model

    def __post_init__(self) -> None:
        """Keep the model_name field synced with provider-specific fields.

        The test is emptiness, not equality with a particular model name.

        This block previously used the literal ``"gemma4:12b"`` as a sentinel
        meaning "unset" — in four comparisons. That worked only while the
        defaults happened to be that string, and it made a model name
        load-bearing for control flow: once the defaults became empty, every
        comparison would have been False and the provider-specific value would
        have silently stopped propagating. A sentinel should say "unset", not
        name a model.
        """
        if not self.model_name:
            if self.llm_provider == LLMProvider.OLLAMA and self.ollama_model:
                self.model_name = self.ollama_model
            elif self.llm_provider == LLMProvider.OPENAI and self.openai_model:
                self.model_name = self.openai_model
            elif self.llm_provider == LLMProvider.ANTHROPIC and self.anthropic_model:
                self.model_name = self.anthropic_model


if __name__ == "__main__":
    print(AppConfig())
