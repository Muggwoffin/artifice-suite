"""Tests for the PDF export feature.

Covers the structure guard, structure stage, folder collection, and
end-to-end PDF rendering.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ocr_pipeline import _guard, config


# --------------------------------------------------------------------------- #
# structure guard
# --------------------------------------------------------------------------- #

def test_check_structure_only_rejects_word_change():
    """The structure guard must reject any change to a word."""
    original = "Der Bericht war unvollstaendig und teilweise unklar."
    structured = "Der Bericht war unvollstaendig und teilweise klar."

    result = _guard.check_structure_only(original, structured)

    assert result.ok is False
    assert "differs" in result.reasons[0] or "fewer" in result.reasons[0]


def test_check_structure_only_allows_paragraph_breaks():
    """The structure guard must accept paragraph breaks (whitespace only)."""
    original = "Der Bericht war unvollstaendig.\nEr war auch teilweise unklar."
    structured = "Der Bericht war unvollstaendig.\n\nEr war auch teilweise unklar."

    result = _guard.check_structure_only(original, structured)

    assert result.ok is True, result.reasons


def test_check_structure_only_rejects_empty_output():
    """Empty structured output must be rejected."""
    original = "Der Bericht war unvollstaendig."
    structured = "   "

    result = _guard.check_structure_only(original, structured)

    assert result.ok is False
    assert "output empty" in result.reasons


def test_check_structure_only_rejects_word_addition():
    """Adding words must be rejected."""
    original = "Der Bericht war kurz."
    structured = "Der Bericht war sehr kurz."

    result = _guard.check_structure_only(original, structured)

    assert result.ok is False
    assert result.words_deleted > 0


def test_check_structure_only_accepts_identical_text():
    """Identical text must pass."""
    text = "Der Bericht war unvollstaendig und teilweise unklar."

    result = _guard.check_structure_only(text, text)

    assert result.ok is True, result.reasons


# --------------------------------------------------------------------------- #
# structure stage
# --------------------------------------------------------------------------- #

@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_structure_perform_respects_resume(mock_chat, tmp_path):
    """Second call with existing output should be a no-op."""
    from src.ocr_pipeline.stages import structure

    raw = "Der Bericht war unvollstaendig.\nEr war unklar."
    structured = "Der Bericht war unvollstaendig.\n\nEr war unklar."
    mock_chat.return_value = MagicMock(message=MagicMock(content=structured))

    config.apply_overrides({"resume": True})

    # First run
    result1 = structure.perform(raw, source_file="test.txt", output_dir=str(tmp_path))
    assert result1["stage"] == "structured"

    # Second run should be skipped
    result2 = structure.perform(raw, source_file="test.txt", output_dir=str(tmp_path))
    assert result2.get("_skipped") is True
    assert mock_chat.call_count == 1  # only called once


@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_structure_perform_fallback_on_guard_reject(mock_chat, tmp_path):
    """When guard rejects, original text should be kept."""
    from src.ocr_pipeline.stages import structure

    raw = "Der Bericht war unvollstaendig."
    corrupted = "Der Bericht war kurz."  # model changed words
    mock_chat.return_value = MagicMock(message=MagicMock(content=corrupted))

    result = structure.perform(raw, source_file="test.txt", output_dir=str(tmp_path))

    assert result["guard"]["ok"] is False
    assert result["structured_text"] == raw  # original kept
    assert "rejected_structured_text" in result


@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_structure_perform_accepts_safe_restructure(mock_chat, tmp_path):
    """When guard accepts, structured text should be used."""
    from src.ocr_pipeline.stages import structure

    raw = "Der Bericht war unvollstaendig.\nEr war unklar."
    structured = "Der Bericht war unvollstaendig.\n\nEr war unklar."
    mock_chat.return_value = MagicMock(message=MagicMock(content=structured))

    result = structure.perform(raw, source_file="test.txt", output_dir=str(tmp_path))

    assert result["guard"]["ok"] is True
    assert result["structured_text"] == structured
    assert "rejected_structured_text" not in result


# --------------------------------------------------------------------------- #
# collect_folder
# --------------------------------------------------------------------------- #

def test_collect_folder_natural_sort(tmp_path):
    """Files should be natural-sorted when no manifest is present."""
    from src.ocr_pipeline import pdf_export

    # Create test files in the expected directory structure
    text_dir = tmp_path / "cleaned" / "text"
    text_dir.mkdir(parents=True)

    # Create files that would sort incorrectly with pure lexicographic sort
    (text_dir / "page2.txt").write_text("Page 2 text")
    (text_dir / "page10.txt").write_text("Page 10 text")
    (text_dir / "page1.txt").write_text("Page 1 text")

    pages = pdf_export.collect_folder(str(tmp_path), stage="cleaned")

    assert len(pages) == 3
    # Natural sort: page1, page2, page10 (not page1, page10, page2)
    assert pages[0].label == "page1"
    assert pages[1].label == "page2"
    assert pages[2].label == "page10"


def test_collect_folder_with_manifest(tmp_path):
    """When manifest exists, pages should be ordered by page_number."""
    from src.ocr_pipeline import pdf_export

    # Create test files
    text_dir = tmp_path / "cleaned" / "text"
    text_dir.mkdir(parents=True)

    (text_dir / "item_p0002.txt").write_text("Page 2 text")
    (text_dir / "item_p0001.txt").write_text("Page 1 text")

    # Create manifest
    manifest = {
        "item/item_p0001": {
            "photo_id": 1,
            "item_id": 10,
            "item_title": "Test Item",
            "page_number": 1,
        },
        "item/item_p0002": {
            "photo_id": 2,
            "item_id": 10,
            "item_title": "Test Item",
            "page_number": 2,
        },
    }
    (tmp_path / "tropy_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    pages = pdf_export.collect_folder(str(tmp_path), stage="cleaned")

    assert len(pages) == 2
    # Ordered by page_number from manifest
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2


def test_collect_folder_stage_fallback(tmp_path):
    """Should fall back through translated > cleaned > raw_ocr."""
    from src.ocr_pipeline import pdf_export

    # Only raw_ocr exists
    text_dir = tmp_path / "raw_ocr" / "text"
    text_dir.mkdir(parents=True)
    (text_dir / "test.txt").write_text("Raw text")

    pages = pdf_export.collect_folder(str(tmp_path), stage="cleaned")

    assert len(pages) == 1
    assert pages[0].text == "Raw text"


# --------------------------------------------------------------------------- #
# end-to-end with mocked model
# --------------------------------------------------------------------------- #

@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_compile_pdf_end_to_end(mock_chat, tmp_path):
    """Full pipeline: collect -> structure -> render, then verify PDF content."""
    import fitz  # PyMuPDF
    from src.ocr_pipeline import pdf_export

    # Create test files
    text_dir = tmp_path / "cleaned" / "text"
    text_dir.mkdir(parents=True)

    (text_dir / "page1.txt").write_text("Erster Absatz.\nZweiter Satz.")
    (text_dir / "page2.txt").write_text("Zweiter Absatz.\nDritter Satz.")

    # Mock the structure call
    def side_effect(*args, **kwargs):
        messages = kwargs.get("messages", [])
        for msg in messages:
            if msg["role"] == "user":
                text = msg["content"]
                # Simulate adding paragraph breaks
                return MagicMock(
                    message=MagicMock(content=text.replace("\n", "\n\n"))
                )
        return MagicMock(message=MagicMock(content="structured text"))

    mock_chat.side_effect = side_effect

    # Collect and structure
    pages = pdf_export.collect_folder(str(tmp_path), stage="cleaned")
    assert len(pages) == 2

    pages = pdf_export.structure_pages(pages)

    # Render PDF
    pdf_path = tmp_path / "output.pdf"
    result = pdf_export.render_pdf(pages, pdf_path, title="Test Document")

    assert result.exists()
    assert result == pdf_path

    # Verify PDF contains original words
    doc = fitz.open(str(pdf_path))
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()

    assert "Erster" in full_text
    assert "Absatz" in full_text
    assert "Zweiter" in full_text
    assert "Satz" in full_text


# --------------------------------------------------------------------------- #
# smoke test with real data (no model call)
# --------------------------------------------------------------------------- #

def test_compile_pdf_smoke_no_structure():
    """Smoke test against real data in the repo, no model call."""
    from src.ocr_pipeline import pdf_export

    real_folder = Path("E:/Claude Sandbox/OCR Pipeline Tool/output/cleaned/text/Fritz Eberhard KV")
    if not real_folder.exists():
        pytest.skip("Real test data not available")

    pages = pdf_export.collect_folder(str(real_folder), stage="cleaned")
    assert len(pages) >= 1

    # Render without structuring
    pdf_path = Path("E:/Claude Sandbox/OCR Pipeline Tool/output/smoke_test.pdf")
    result = pdf_export.render_pdf(pages, pdf_path, title="Fritz Eberhard KV")

    assert result.exists()
    assert result.stat().st_size > 0

    # Clean up
    result.unlink(missing_ok=True)
