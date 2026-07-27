from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class Document(BaseModel):
    """An ingested source document, usually one OCR output file."""

    id: str
    filename: str
    filepath: str
    subfolder: str = ""
    page_range: str = ""
    raw_text: str = ""
    chunk_ids: list[str] = Field(default_factory=list)


class TextChunk(BaseModel):
    """A sliding-window chunk of text derived from a Document."""

    id: str
    document_id: str
    chunk_index: int
    text: str
    start_char: int
    end_char: int
    subfolder: str = ""
    page_range: str = ""
