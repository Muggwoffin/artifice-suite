import json
from pathlib import Path
from unittest.mock import patch

import pytest

from artifice_ocr.export_ludwiglang import (
    MEDIUM_OPTIONS,
    assemble_collection,
    check_language,
    export_md,
    _build_frontmatter,
    _discover_pages,
    _format_frontmatter,
    _parse_page_num,
)


def _make_cleaned_page(json_dir: Path, stem: str, cleaned_text: str,
                       ok: bool = True) -> dict:
    data = {
        "source_file": f"{stem}.txt",
        "stage": "cleaned",
        "cleaned_text": cleaned_text,
        "guard": {"ok": ok, "reasons": [] if ok else ["guard failure"]},
    }
    (json_dir / f"{stem}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return data


# --------------------------------------------------------------------------- #
# _parse_page_num
# --------------------------------------------------------------------------- #

def test_parse_page_num_extracts_number():
    assert _parse_page_num("foo_p0001") == 1
    assert _parse_page_num("bar_p0042") == 42
    assert _parse_page_num("no_suffix") == 0
    assert _parse_page_num("KV-2-1234_p0003") == 3


# --------------------------------------------------------------------------- #
# _discover_pages
# --------------------------------------------------------------------------- #

def test_discover_pages_sorts_by_page_number(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0003", "page three")
    _make_cleaned_page(json_dir, "doc_p0001", "page one")
    _make_cleaned_page(json_dir, "doc_p0002", "page two")

    pages = _discover_pages(tmp_path)
    assert [p.page_num for p in pages] == [1, 2, 3]
    assert [p.cleaned_text for p in pages] == [
        "page one", "page two", "page three",
    ]


def test_discover_pages_skips_non_json_files(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "page one")
    (json_dir / "readme.txt").write_text("not json")
    (json_dir / "notes.md").write_text("# notes")

    pages = _discover_pages(tmp_path)
    assert len(pages) == 1


def test_discover_pages_skips_corrupt_json(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True)
    (json_dir / "bad.json").write_text("{not valid json}", encoding="utf-8")
    _make_cleaned_page(json_dir, "good_p0001", "fine")

    pages = _discover_pages(tmp_path)
    assert len(pages) == 1


def test_discover_pages_raises_on_missing_json_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        _discover_pages(tmp_path / "nonexistent")


# --------------------------------------------------------------------------- #
# assemble_collection
# --------------------------------------------------------------------------- #

def test_assemble_collection_concatenates_text(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Erste Seite.")
    _make_cleaned_page(json_dir, "doc_p0002", "Zweite Seite.")
    _make_cleaned_page(json_dir, "doc_p0003", "Dritte Seite.")

    result = assemble_collection(tmp_path)
    assert result.page_count == 3
    assert result.skipped_count == 0
    assert "Erste Seite." in result.body
    assert "Zweite Seite." in result.body
    assert "Dritte Seite." in result.body
    assert result.body.count("\n\n") == 2


def test_assemble_collection_excludes_guard_failed_pages(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Gute Seite.", ok=True)
    _make_cleaned_page(json_dir, "doc_p0002", "Schlechte Seite.", ok=False)
    _make_cleaned_page(json_dir, "doc_p0003", "Auch gut.", ok=True)

    result = assemble_collection(tmp_path)
    assert result.page_count == 2
    assert result.skipped_count == 1
    assert result.skipped_stems == ["doc_p0002"]
    assert "Gute Seite." in result.body
    assert "Schlechte Seite." not in result.body


def test_assemble_collection_with_page_markers(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Eins.")
    _make_cleaned_page(json_dir, "doc_p0005", "Zwei.")
    _make_cleaned_page(json_dir, "doc_p0010", "Zehn.")

    result = assemble_collection(tmp_path, page_markers=True)
    assert "-- 5 --" in result.body
    assert "-- 10 --" in result.body
    assert "-- 1 --" not in result.body  # no marker on first page


def test_assemble_collection_truncates_long_body(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True)
    long_text = "X" * 150_000
    _make_cleaned_page(json_dir, "doc_p0001", long_text)
    _make_cleaned_page(json_dir, "doc_p0002", "Y" * 100_000)

    result = assemble_collection(tmp_path)
    assert result.body_truncated is True
    assert len(result.body) <= 200_000


def test_assemble_collection_skips_empty_text(tmp_path):
    json_dir = tmp_path / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Nur dieser Text.")
    _make_cleaned_page(json_dir, "doc_p0002", "")

    result = assemble_collection(tmp_path)
    assert result.page_count == 2  # empty text is still kept (guard ok)
    assert "Nur dieser Text." in result.body


def test_assemble_collection_title_is_dir_name(tmp_path):
    collection = tmp_path / "Meine Sammlung"
    json_dir = collection / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Text.")

    result = assemble_collection(collection)
    assert result.title == "Meine Sammlung"


# --------------------------------------------------------------------------- #
# _build_frontmatter / _format_frontmatter
# --------------------------------------------------------------------------- #

def test_frontmatter_defaults():
    fm = _build_frontmatter(title="Test Doc", medium="print")
    assert fm["title"] == "Test Doc"
    assert fm["medium"] == "print"
    assert fm["language"] == "de"
    assert "author" not in fm
    assert "date" not in fm


def test_frontmatter_with_author_date():
    fm = _build_frontmatter(
        title="Test", medium="handwritten", author="Max", date="1944",
    )
    assert fm["author"] == "Max"
    assert fm["date"] == "1944"


def test_format_frontmatter():
    fm = {"title": "Doc", "medium": "print", "language": "de"}
    output = _format_frontmatter(fm)
    lines = output.split("\n")
    assert lines[0] == "---"
    assert "title: Doc" in lines
    assert "medium: print" in lines
    assert "language: de" in lines
    assert lines[-1] == "---"


# --------------------------------------------------------------------------- #
# check_language
# --------------------------------------------------------------------------- #

@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_language_gate_blocks_english(mock_detect):
    mock_detect.return_value = "en"
    error = check_language("This is an English text.")
    assert error is not None
    assert "English" in error


@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_language_gate_passes_german(mock_detect):
    mock_detect.return_value = "de"
    error = check_language("Das ist ein deutscher Text.")
    assert error is None


@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_language_gate_passes_unknown(mock_detect):
    mock_detect.return_value = "unknown"
    error = check_language("Ein bisschen Text.")
    assert error is None


def test_language_gate_empty_body():
    error = check_language("")
    assert error is not None
    assert "empty" in error.lower()


# --------------------------------------------------------------------------- #
# export_md
# --------------------------------------------------------------------------- #

@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_export_md_writes_file_with_frontmatter(mock_detect, tmp_path):
    mock_detect.return_value = "de"
    json_dir = tmp_path / "collection" / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Erster Absatz.")
    _make_cleaned_page(json_dir, "doc_p0002", "Zweiter Absatz.")

    output = tmp_path / "output"
    result_path = export_md(
        tmp_path / "collection",
        output_path=output / "text.md",
        medium="typed",
        author="Test Author",
    )

    assert result_path == output / "text.md"
    assert result_path.exists()
    content = result_path.read_text(encoding="utf-8")
    assert "title: collection" in content
    assert "medium: typed" in content
    assert "language: de" in content
    assert "author: Test Author" in content
    assert "Erster Absatz." in content
    assert "Zweiter Absatz." in content


@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_export_md_default_output_path(mock_detect, tmp_path):
    mock_detect.return_value = "de"
    json_dir = tmp_path / "mein_dokument" / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Text.")
    _make_cleaned_page(json_dir, "doc_p0002", "Mehr Text.")

    # Assumes ../output exists for "pipeline output dir" pattern
    result_path = export_md(tmp_path / "mein_dokument")
    assert result_path.name == "text.md"
    assert result_path.parent.name == "mein_dokument"


@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_export_md_raises_on_english_without_skip(mock_detect, tmp_path):
    mock_detect.return_value = "en"
    json_dir = tmp_path / "col" / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "English text.")

    with pytest.raises(ValueError, match="English"):
        export_md(tmp_path / "col")


@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_export_md_skip_language_gate(mock_detect, tmp_path):
    mock_detect.return_value = "en"
    json_dir = tmp_path / "col" / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "English text.")

    result_path = export_md(
        tmp_path / "col",
        skip_language_gate=True,
    )
    assert result_path.exists()


def test_export_md_invalid_medium(tmp_path):
    with pytest.raises(ValueError, match="medium"):
        export_md(
            tmp_path,
            medium="invalid",
        )


def test_export_md_medium_options_are_correct():
    assert "typed" in MEDIUM_OPTIONS
    assert "handwritten" in MEDIUM_OPTIONS
    assert "print" in MEDIUM_OPTIONS


@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_export_md_with_manifest_lookup(mock_detect, tmp_path):
    mock_detect.return_value = "de"
    json_dir = tmp_path / "Akten" / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Deutscher Text.")

    manifest = {
        "project": {"name": "Test", "bundle": "/tmp"},
        "pages": {
            "Akten/doc_p0001": {
                "item_title": "Max Hodann",
            },
        },
    }

    result_path = export_md(
        tmp_path / "Akten",
        manifest=manifest,
    )
    assert result_path.exists()


@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_export_md_logs_skipped_pages(mock_detect, tmp_path, caplog):
    mock_detect.return_value = "de"
    json_dir = tmp_path / "col" / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Gut.", ok=True)
    _make_cleaned_page(json_dir, "doc_p0002", "Schlecht.", ok=False)

    export_md(tmp_path / "col", skip_language_gate=True)
    assert "Skipped 1 page(s)" in caplog.text
    assert "doc_p0002" in caplog.text


@patch("artifice_ocr.export_ludwiglang._detect_language")
def test_export_md_idempotent_overwrite(mock_detect, tmp_path):
    mock_detect.return_value = "de"
    json_dir = tmp_path / "col" / "json"
    json_dir.mkdir(parents=True)
    _make_cleaned_page(json_dir, "doc_p0001", "Text.")
    output = tmp_path / "out" / "text.md"
    output.parent.mkdir(parents=True)

    first = export_md(tmp_path / "col", output_path=output)
    second = export_md(tmp_path / "col", output_path=output)
    assert first.read_bytes() == second.read_bytes()
