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


# --------------------------------------------------------------------------- #
# compile() function (refactored entry point)
# --------------------------------------------------------------------------- #

@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_structure_pages_calls_on_progress_in_order(mock_chat, tmp_path):
    """on_progress should be called once per page, in order, with messages."""
    from src.ocr_pipeline import pdf_export
    from src.ocr_pipeline.pdf_export import PageText

    def side_effect(*args, **kwargs):
        messages = kwargs.get("messages", [])
        for msg in messages:
            if msg["role"] == "user":
                text = msg["content"]
                return MagicMock(
                    message=MagicMock(content=text.replace("\n", "\n\n"))
                )
        return MagicMock(message=MagicMock(content="structured"))

    mock_chat.side_effect = side_effect

    pages = [
        PageText(label="page_a", text="Page A text.\nSecond line.",
                 source_path=tmp_path / "a.txt"),
        PageText(label="page_b", text="Page B text.\nSecond line.",
                 source_path=tmp_path / "b.txt"),
    ]

    calls = []
    result = pdf_export.structure_pages(
        pages, on_progress=lambda msg: calls.append(msg))

    assert len(calls) == 2
    assert "Structuring 1/2: page_a" in calls[0]
    assert "Structuring 2/2: page_b" in calls[1]
    assert len(result) == 2


@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_structure_pages_calls_on_rejected(mock_chat, tmp_path, monkeypatch):
    """on_rejected should be called when the guard rejects a page."""
    # Disable resume so structure.perform always runs the model call
    from src.ocr_pipeline import config as _cfg
    _cfg.apply_overrides({"resume": False})
    from src.ocr_pipeline import pdf_export
    from src.ocr_pipeline.pdf_export import PageText

    # Model returns a word-change that the guard will reject
    mock_chat.return_value = MagicMock(
        message=MagicMock(content="Changed text."))

    pages = [
        PageText(label="page_one",
                 text="Original text that must be kept.",
                 source_path=tmp_path / "unique_test_page.txt"),
    ]

    rejected = []
    result = pdf_export.structure_pages(
        pages, on_rejected=lambda l: rejected.append(l))

    assert len(rejected) == 1
    assert rejected[0] == "page_one"
    # Original text should be kept
    assert result[0].text == "Original text that must be kept."


@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_compile_function_end_to_end(mock_chat, tmp_path):
    """pdf_export.compile() should collect, structure and render."""
    from src.ocr_pipeline import pdf_export

    text_dir = tmp_path / "cleaned" / "text"
    text_dir.mkdir(parents=True)
    (text_dir / "page1.txt").write_text("Erster Absatz.\nZweiter Satz.")
    (text_dir / "page2.txt").write_text("Zweiter Absatz.\nDritter Satz.")

    def side_effect(*args, **kwargs):
        messages = kwargs.get("messages", [])
        for msg in messages:
            if msg["role"] == "user":
                text = msg["content"]
                return MagicMock(
                    message=MagicMock(content=text.replace("\n", "\n\n"))
                )
        return MagicMock(message=MagicMock(content="structured text"))

    mock_chat.side_effect = side_effect

    output_path = tmp_path / "result.pdf"
    progress = []
    result = pdf_export.compile(
        str(tmp_path),
        stage="cleaned",
        structure=True,
        output=str(output_path),
        on_progress=lambda msg: progress.append(msg),
    )

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert any("Collecting" in m for m in progress)
    assert any("Found" in m for m in progress)
    assert any("Rendering" in m for m in progress)
    assert any("Done" in m for m in progress)


@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_compile_function_no_structure(mock_chat, tmp_path):
    """compile() with structure=False should skip the model call."""
    from src.ocr_pipeline import pdf_export

    text_dir = tmp_path / "cleaned" / "text"
    text_dir.mkdir(parents=True)
    (text_dir / "page1.txt").write_text("Page 1 text.")

    output_path = tmp_path / "result.pdf"
    result = pdf_export.compile(
        str(tmp_path),
        stage="cleaned",
        structure=False,
        output=str(output_path),
    )

    assert result.exists()
    mock_chat.assert_not_called()


# --------------------------------------------------------------------------- #
# Markdown export
# --------------------------------------------------------------------------- #

@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_render_markdown_creates_file(mock_chat, tmp_path):
    """compile() with format='md' should produce a Markdown file."""
    from src.ocr_pipeline import pdf_export

    text_dir = tmp_path / "cleaned" / "text"
    text_dir.mkdir(parents=True)
    (text_dir / "page1.txt").write_text("Erster Absatz.\nZweiter Satz.")
    (text_dir / "page2.txt").write_text("Zweiter Absatz.\nDritter Satz.")

    mock_chat.side_effect = lambda **kw: MagicMock(
        message=MagicMock(content=kw["messages"][-1]["content"].replace("\n", "\n\n"))
    )

    output_path = pdf_export.compile(
        str(tmp_path), stage="cleaned", structure=False,
        output=str(tmp_path / "out.md"), format="md",
    )

    assert output_path.exists()
    assert output_path.suffix == ".md"
    content = output_path.read_text(encoding="utf-8")
    assert "## Page 1" in content
    assert "## Page 2" in content
    assert "[page1]" in content
    assert "[page2]" in content
    assert "Erster Absatz." in content


# --------------------------------------------------------------------------- #
# PDF style presets
# --------------------------------------------------------------------------- #

@patch("src.ocr_pipeline.stages.structure.ollama.chat")
def test_compile_with_style_preset(mock_chat, tmp_path):
    """compile() with style='compact' should produce a valid PDF."""
    import fitz
    from src.ocr_pipeline import pdf_export

    text_dir = tmp_path / "cleaned" / "text"
    text_dir.mkdir(parents=True)
    (text_dir / "page1.txt").write_text("Erster Absatz.\nZweiter Satz.")

    mock_chat.side_effect = lambda **kw: MagicMock(
        message=MagicMock(content=kw["messages"][-1]["content"].replace("\n", "\n\n"))
    )

    output_path = pdf_export.compile(
        str(tmp_path), stage="cleaned", structure=False,
        output=str(tmp_path / "out.pdf"), format="pdf", style="compact",
    )

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    doc = fitz.open(str(output_path))
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()
    assert "Erster Absatz." in full_text


def test_compile_function_raises_on_empty_folder(tmp_path):
    """compile() should raise ValueError when no pages are found."""
    from src.ocr_pipeline import pdf_export

    empty = tmp_path / "empty"
    empty.mkdir()

    with pytest.raises(ValueError, match="No pages found"):
        pdf_export.compile(str(empty), stage="cleaned", structure=False)


# --------------------------------------------------------------------------- #
# Bilingual export
# --------------------------------------------------------------------------- #

def test_collect_bilingual_folder_pairs_by_stem(tmp_path):
    """collect_bilingual_folder() should pair cleaned + translated by stem."""
    from src.ocr_pipeline import pdf_export

    cleaned_dir = tmp_path / "cleaned" / "text"
    cleaned_dir.mkdir(parents=True)
    (cleaned_dir / "page1.txt").write_text("Original text A")
    (cleaned_dir / "page2.txt").write_text("Original text B")

    translated_dir = tmp_path / "translated" / "text"
    translated_dir.mkdir(parents=True)
    (translated_dir / "page1.txt").write_text("Translated A")
    (translated_dir / "page2.txt").write_text("Translated B")

    pages = pdf_export.collect_bilingual_folder(str(tmp_path))

    assert len(pages) == 2
    assert pages[0].original_text == "Original text A"
    assert pages[0].translated_text == "Translated A"
    assert pages[1].original_text == "Original text B"
    assert pages[1].translated_text == "Translated B"


def test_collect_bilingual_folder_missing_translation(tmp_path):
    """Missing translated files should produce blank right column."""
    from src.ocr_pipeline import pdf_export

    cleaned_dir = tmp_path / "cleaned" / "text"
    cleaned_dir.mkdir(parents=True)
    (cleaned_dir / "page1.txt").write_text("Original text")
    (cleaned_dir / "page2.txt").write_text("Original text 2")

    translated_dir = tmp_path / "translated" / "text"
    translated_dir.mkdir(parents=True)
    (translated_dir / "page1.txt").write_text("Translated text")

    pages = pdf_export.collect_bilingual_folder(str(tmp_path))

    assert len(pages) == 2
    assert pages[0].translated_text == "Translated text"
    assert pages[1].translated_text == ""


def test_collect_bilingual_folder_no_translated_dir(tmp_path):
    """When no translated dir exists, all translated_text should be blank."""
    from src.ocr_pipeline import pdf_export

    cleaned_dir = tmp_path / "cleaned" / "text"
    cleaned_dir.mkdir(parents=True)
    (cleaned_dir / "page1.txt").write_text("Original text")

    pages = pdf_export.collect_bilingual_folder(str(tmp_path))

    assert len(pages) == 1
    assert pages[0].original_text == "Original text"
    assert pages[0].translated_text == ""


def test_collect_bilingual_folder_with_manifest(tmp_path):
    """Manifest ordering should be respected for bilingual collection."""
    from src.ocr_pipeline import pdf_export

    cleaned_dir = tmp_path / "cleaned" / "text"
    cleaned_dir.mkdir(parents=True)
    (cleaned_dir / "item_p0002.txt").write_text("Page 2")
    (cleaned_dir / "item_p0001.txt").write_text("Page 1")

    translated_dir = tmp_path / "translated" / "text"
    translated_dir.mkdir(parents=True)
    (translated_dir / "item_p0002.txt").write_text("Trans Page 2")
    (translated_dir / "item_p0001.txt").write_text("Trans Page 1")

    manifest = {
        "item/item_p0001": {"item_title": "Test", "page_number": 1},
        "item/item_p0002": {"item_title": "Test", "page_number": 2},
    }
    (tmp_path / "tropy_manifest.json").write_text(json.dumps(manifest))

    pages = pdf_export.collect_bilingual_folder(str(tmp_path))

    assert len(pages) == 2
    assert pages[0].page_number == 1
    assert pages[0].original_text == "Page 1"
    assert pages[0].translated_text == "Trans Page 1"
    assert pages[1].page_number == 2


def test_render_bilingual_pdf_produces_valid_pdf(tmp_path):
    """render_bilingual_pdf() should produce a valid PDF with two-column table."""
    import fitz
    from src.ocr_pipeline import pdf_export

    pages = [
        pdf_export.BilingualPageText(
            label="page1",
            text="Original text",
            source_path=tmp_path / "p1.txt",
            original_text="Der erste Absatz.\n\nDer zweite Absatz.",
            translated_text="The first paragraph.\n\nThe second paragraph.",
        ),
    ]

    pdf_path = tmp_path / "bilingual.pdf"
    result = pdf_export.render_bilingual_pdf(pages, pdf_path, title="Test")

    assert result.exists()
    assert result.stat().st_size > 0

    doc = fitz.open(str(pdf_path))
    full_text = ""
    for p in doc:
        full_text += p.get_text()
    doc.close()

    assert "Der erste Absatz." in full_text
    assert "The first paragraph." in full_text
    assert "Der zweite Absatz." in full_text
    assert "The second paragraph." in full_text


def test_render_bilingual_pdf_missing_translation(tmp_path):
    """Bilingual PDF with missing translations should still produce valid PDF."""
    from src.ocr_pipeline import pdf_export

    pages = [
        pdf_export.BilingualPageText(
            label="page1",
            text="Original text",
            source_path=tmp_path / "p1.txt",
            original_text="Original paragraph.",
            translated_text="",
        ),
    ]

    pdf_path = tmp_path / "bilingual_partial.pdf"
    result = pdf_export.render_bilingual_pdf(pages, pdf_path)

    assert result.exists()
    assert result.stat().st_size > 0


def test_render_bilingual_markdown_creates_file(tmp_path):
    """render_bilingual_markdown() should produce a pipe-table Markdown file."""
    from src.ocr_pipeline import pdf_export

    pages = [
        pdf_export.BilingualPageText(
            label="page1",
            text="Original text",
            source_path=tmp_path / "p1.txt",
            original_text="Der erste Absatz.\n\nDer zweite Absatz.",
            translated_text="The first paragraph.\n\nThe second paragraph.",
        ),
    ]

    md_path = tmp_path / "bilingual.md"
    result = pdf_export.render_bilingual_markdown(pages, md_path, title="Test")

    assert result.exists()
    content = result.read_text(encoding="utf-8")

    assert "# Test" in content
    assert "| Original | Translation |" in content
    assert "Der erste Absatz." in content
    assert "The first paragraph." in content
    assert "Der zweite Absatz." in content
    assert "The second paragraph." in content


def test_compile_bilingual_pdf_end_to_end(tmp_path):
    """compile() with bilingual=True should produce a two-column PDF."""
    import fitz
    from src.ocr_pipeline import pdf_export

    cleaned_dir = tmp_path / "cleaned" / "text"
    cleaned_dir.mkdir(parents=True)
    (cleaned_dir / "page1.txt").write_text("Erster Absatz.\n\nZweiter Absatz.")
    (cleaned_dir / "page2.txt").write_text("Dritter Absatz.")

    translated_dir = tmp_path / "translated" / "text"
    translated_dir.mkdir(parents=True)
    (translated_dir / "page1.txt").write_text("First paragraph.\n\nSecond paragraph.")
    (translated_dir / "page2.txt").write_text("Third paragraph.")

    output_path = tmp_path / "bilingual_output.pdf"
    result = pdf_export.compile(
        str(tmp_path),
        bilingual=True,
        structure=False,
        output=str(output_path),
    )

    assert result == output_path
    assert output_path.exists()

    doc = fitz.open(str(output_path))
    full_text = ""
    for p in doc:
        full_text += p.get_text()
    doc.close()

    assert "Erster Absatz." in full_text
    assert "First paragraph." in full_text
    assert "Dritter Absatz." in full_text
    assert "Third paragraph." in full_text


def test_compile_bilingual_markdown(tmp_path):
    """compile() with bilingual=True and format='md' should produce bilingual Markdown."""
    from src.ocr_pipeline import pdf_export

    cleaned_dir = tmp_path / "cleaned" / "text"
    cleaned_dir.mkdir(parents=True)
    (cleaned_dir / "page1.txt").write_text("Original text.")

    translated_dir = tmp_path / "translated" / "text"
    translated_dir.mkdir(parents=True)
    (translated_dir / "page1.txt").write_text("Translated text.")

    output_path = tmp_path / "bilingual_output.md"
    result = pdf_export.compile(
        str(tmp_path),
        bilingual=True,
        structure=False,
        output=str(output_path),
        format="md",
    )

    assert result.exists()
    assert result.suffix == ".md"
    content = result.read_text(encoding="utf-8")
    assert "| Original | Translation |" in content
    assert "Original text." in content
    assert "Translated text." in content


def test_compile_bilingual_skips_structure_by_default(tmp_path):
    """compile(bilingual=True, structure=False) should not call the model."""
    from src.ocr_pipeline import pdf_export

    cleaned_dir = tmp_path / "cleaned" / "text"
    cleaned_dir.mkdir(parents=True)
    (cleaned_dir / "page1.txt").write_text("Original text.")

    translated_dir = tmp_path / "translated" / "text"
    translated_dir.mkdir(parents=True)
    (translated_dir / "page1.txt").write_text("Translated text.")

    output_path = tmp_path / "bilingual_no_struct.pdf"
    with patch("src.ocr_pipeline.stages.structure.ollama.chat") as mock_chat:
        result = pdf_export.compile(
            str(tmp_path),
            bilingual=True,
            structure=False,
            output=str(output_path),
        )
        mock_chat.assert_not_called()
    assert result.exists()
