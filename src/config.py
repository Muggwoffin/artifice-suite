"""Centralised settings for the copy-edit tool."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from src.models import EditingStyle, ExportFormat, LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    """Configuration values — override via environment variables if set."""

    ollama_model: str = "gemma4:12b"
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

    export_format: ExportFormat = ExportFormat.DOCX_TRACK_CHANGES

    enable_review: bool = False
    author_name: str = "AI Copy Editor"

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

        if env := os.environ.get("OLLAMA_MODEL"):
            cfg.ollama_model = env
        if env := os.environ.get("OLLAMA_URL"):
            cfg.ollama_base_url = env
        if env := os.environ.get("LLM_PROVIDER"):
            try:
                cfg.llm_provider = LLMProvider(env.lower())
            except ValueError:
                logger.warning("Unknown LLM_PROVIDER '%s', keeping default", env)

        if env := os.environ.get("OPENAI_API_KEY"):
            cfg.openai_api_key = env
        if env := os.environ.get("OPENAI_MODEL"):
            cfg.openai_model = env
        if env := os.environ.get("OPENAI_BASE_URL"):
            cfg.openai_base_url = env

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
        if self.llm_provider == LLMProvider.OLLAMA:
            return self.ollama_model
        elif self.llm_provider == LLMProvider.OPENAI:
            return self.openai_model
        elif self.llm_provider == LLMProvider.ANTHROPIC:
            return self.anthropic_model
        return self.ollama_model


if __name__ == "__main__":
    print(AppConfig())
