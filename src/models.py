"""Shared type definitions for the copy-edit pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypedDict


class ParagraphData(TypedDict):
    """A paragraph extracted from a .docx file with formatting metadata."""

    paragraph_index: int
    text: str
    style_name: str
    is_bold: bool
    is_italic: bool
    indent_level: int
    font_size: float | None
    font_name: str | None
    is_underline: bool
    alignment: str | None
    space_before: float | None
    space_after: float | None
    line_spacing: float | None
    is_list_item: bool
    list_level: int
    language: str | None


class ExportFormat(Enum):
    """Supported output formats for the edited document."""

    DOCX_TRACK_CHANGES = "docx_track_changes"
    DOCX_PLAIN = "docx_plain"
    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN_TEXT = "plain_text"


class EditingStyle(Enum):
    """Predefined editing style presets for the system prompt."""

    ACADEMIC = "academic"
    CREATIVE = "creative"
    CONCISE = "concise"
    BUSINESS = "business"
    CUSTOM = "custom"


class LLMProvider(Enum):
    """Supported LLM providers."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class ReviewDecision:
    """Represents a user's decision on a single edit."""

    paragraph_index: int
    approved: bool
    replacement_text: str | None = None


@dataclass
class ChangeLogEntry:
    """A single entry in the change log."""

    paragraph_index: int
    original_text: str
    edited_text: str
    change_type: str  # "grammar", "spelling", "clarity", "style", "unchanged"


@dataclass
class PipelineProgress:
    """Progress tracking for the pipeline."""

    total_paragraphs: int = 0
    current_paragraph: int = 0
    stage: str = ""  # "parsing", "llm_processing", "writing", "done"
    message: str = ""
    percentage: float = 0.0
    error: str | None = None

    def update(self, stage: str, current: int, message: str = "") -> None:
        self.stage = stage
        self.current_paragraph = current
        self.message = message
        if self.total_paragraphs > 0:
            self.percentage = (current / self.total_paragraphs) * 100

    def finish(self, message: str = "Done") -> None:
        self.stage = "done"
        self.percentage = 100.0
        self.message = message

    def fail(self, error: str) -> None:
        self.stage = "error"
        self.error = error
        self.message = f"Error: {error}"


# Type alias for progress callbacks
ProgressCallback = Callable[[PipelineProgress], None]
