# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the Tropy JSON-LD bridge — parser, containment, round-trip.

No real Tropy project needed. Every test builds a synthetic JSON-LD file in a
temp directory, with or without backing images as needed.
"""

import json
from pathlib import Path

import pytest

from artifice_ocr.tropy_jsonld import (
    ImportedPhoto,
    ImportedItem,
    ImportPreview,
    ExportPhoto,
    TropyImportError,
    MAX_FILE_BYTES,
    MAX_DEPTH,
    MAX_NODES,
    TROPY_CONTEXT,
    _note_html,
    build_export,
    export_json,
    load_export,
    page_stem,
    photos_to_job_items,
    safe_name,
    write_manifest,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _make_export(path: Path, payload: dict | list) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _simple_export(tmp_path, photos=None):
    """Create a minimal JSON-LD export with one item."""
    if photos is None:
        photos = [
            {"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"},
        ]
    export = {"@graph": [{"@type": "Item", "title": "Test Item", "photo": photos}]}
    f = tmp_path / "export.json"
    (tmp_path / "a.png").write_bytes(b"x")
    return _make_export(f, export)


# --------------------------------------------------------------------------- #
# parser: shape acceptance
# --------------------------------------------------------------------------- #


def test_accepts_graph_envelope(tmp_path):
    export = {
        "@graph": [
            {"@type": "Item", "title": "X",
             "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}]}
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert preview.export_name == "e.json"


def test_accepts_bare_list(tmp_path):
    export = [
        {"@type": "Item", "title": "X",
         "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}]}
    ]
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert len(preview.items) == 1


def test_accepts_single_object(tmp_path):
    export = {"@type": "Item", "title": "X",
              "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}]}
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert len(preview.items) == 1


def test_accepts_jsonld_suffix(tmp_path):
    export = {
        "@graph": [
            {"@type": "Item", "title": "X",
             "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}]}
        ]
    }
    f = tmp_path / "e.jsonld"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert preview.export_name == "e.jsonld"


# --------------------------------------------------------------------------- #
# parser: title extraction
# --------------------------------------------------------------------------- #


def test_extracts_compact_title(tmp_path):
    f = _simple_export(tmp_path)
    preview = load_export(f)
    assert preview.items[0].title == "Test Item"


def test_extracts_expanded_title(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "http://purl.org/dc/elements/1.1/title": "Expanded Title",
                "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}],
            }
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert preview.items[0].title == "Expanded Title"


def test_title_falls_back_to_index(tmp_path):
    export = {
        "@graph": [
            {"@type": "Item",
             "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}]}
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert preview.items[0].title == "Item 1"


def test_extracts_title_from_dc_terms(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "http://purl.org/dc/terms/title": "DC Title",
                "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}],
            }
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert preview.items[0].title == "DC Title"


# --------------------------------------------------------------------------- #
# parser: photo extraction
# --------------------------------------------------------------------------- #


def test_extracts_photos(tmp_path):
    f = _simple_export(tmp_path)
    preview = load_export(f)
    assert len(preview.items[0].photos) == 1
    photo = preview.items[0].photos[0]
    assert photo.path_rel == "a.png"
    assert photo.checksum == "abc"
    assert photo.mimetype == "image/png"
    assert not photo.missing


def test_normalises_single_photo_dict(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "title": "X",
                "photo": {"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"},
            }
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert len(preview.items[0].photos) == 1


def test_skips_non_dict_photo_entries(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "title": "X",
                "photo": [
                    "nope",
                    {"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"},
                ],
            }
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert len(preview.items[0].photos) == 1
    assert len(preview.warnings) == 1


def test_skips_photo_with_no_path(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "title": "X",
                "photo": [
                    {"@type": "Photo", "checksum": "x", "mimetype": "image/png"},
                    {"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"},
                ],
            }
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert len(preview.items[0].photos) == 1
    assert len(preview.warnings) >= 1


def test_skips_template_and_list_nodes(tmp_path):
    export = {
        "@graph": [
            {"@type": "Template", "name": "Generic"},
            {"@type": "List", "name": "My List"},
            {"@type": "Item", "title": "Doc 1",
             "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}]},
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert len(preview.items) == 1


def test_reports_missing_files(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "title": "Missing",
                "photo": [{"@type": "Photo", "path": "gone.jpg", "checksum": "x", "mimetype": "image/jpeg"}],
            }
        ]
    }
    f = _make_export(tmp_path / "e.json", export)
    preview = load_export(f)
    assert preview.items[0].photos[0].missing is True


# --------------------------------------------------------------------------- #
# parser: rejections
# --------------------------------------------------------------------------- #


def test_rejects_bad_suffix(tmp_path):
    f = tmp_path / "export.txt"
    f.write_text("{}")
    with pytest.raises(TropyImportError, match="not a JSON-LD file"):
        load_export(f)


def test_rejects_missing_file(tmp_path):
    with pytest.raises(TropyImportError, match="not a file"):
        load_export(tmp_path / "gone.json")


def test_rejects_oversized_file(tmp_path):
    f = tmp_path / "big.json"
    f.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    with pytest.raises(TropyImportError, match="too large"):
        load_export(f)


def test_rejects_invalid_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json")
    with pytest.raises(TropyImportError, match="Could not parse"):
        load_export(f)


def test_rejects_deeply_nested_json(tmp_path):
    payload = {}
    current = payload
    for i in range(MAX_DEPTH + 5):
        current["nested"] = {}
        current = current["nested"]
    f = _make_export(tmp_path / "deep.json", payload)
    with pytest.raises(TropyImportError, match="exceeds maximum depth"):
        load_export(f)


def test_rejects_too_many_nodes(tmp_path):
    payload = [{"k": i} for i in range(MAX_NODES + 10)]
    f = tmp_path / "big.json"
    f.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TropyImportError, match="exceeds maximum node count"):
        load_export(f)


# --------------------------------------------------------------------------- #
# parser: path safety
# --------------------------------------------------------------------------- #


def test_rejects_absolute_posix_path(tmp_path):
    export = {"@graph": [{"@type": "Item", "title": "X", "photo": [{"@type": "Photo", "path": "/etc/passwd"}]}]}
    f = _make_export(tmp_path / "e.json", export)
    with pytest.raises(TropyImportError, match="absolute"):
        load_export(f)


def test_rejects_windows_drive_path(tmp_path):
    export = {"@graph": [{"@type": "Item", "title": "X", "photo": [{"@type": "Photo", "path": "C:/Windows/secret"}]}]}
    f = _make_export(tmp_path / "e.json", export)
    with pytest.raises(TropyImportError, match="absolute"):
        load_export(f)


def test_rejects_unc_path(tmp_path):
    export = {"@graph": [{"@type": "Item", "title": "X", "photo": [{"@type": "Photo", "path": "//server/share/file"}]}]}
    f = _make_export(tmp_path / "e.json", export)
    with pytest.raises(TropyImportError, match="UNC"):
        load_export(f)


def test_rejects_dotdot_escape(tmp_path):
    export = {"@graph": [{"@type": "Item", "title": "X", "photo": [{"@type": "Photo", "path": "../secret"}]}]}
    f = _make_export(tmp_path / "e.json", export)
    with pytest.raises(TropyImportError, match="escapes"):
        load_export(f)


def test_rejects_symlink_escape(tmp_path):
    export = {"@graph": [{"@type": "Item", "title": "X", "photo": [{"@type": "Photo", "path": "link"}]}]}
    f = _make_export(tmp_path / "e.json", export)
    # Create a symlink that resolves outside the export dir
    outside = tmp_path.parent / "escape_file"
    outside.write_text("secret")
    symlink = tmp_path / "link"
    symlink.symlink_to(outside)
    try:
        with pytest.raises(TropyImportError, match="escapes"):
            load_export(f)
    finally:
        symlink.unlink(missing_ok=True)


def test_error_message_never_contains_resolved_path(tmp_path):
    export = {"@graph": [{"@type": "Item", "title": "X", "photo": [{"@type": "Photo", "path": "../secret"}]}]}
    f = _make_export(tmp_path / "e.json", export)
    try:
        load_export(f)
    except TropyImportError as exc:
        msg = str(exc)
        assert str(tmp_path.resolve()) not in msg
        assert str(Path.home()) not in msg
    else:
        pytest.fail("Expected TropyImportError")


# --------------------------------------------------------------------------- #
# parser: backslash normalisation
# --------------------------------------------------------------------------- #


def test_normalises_backslash_paths(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "title": "Backslash",
                "photo": [{"@type": "Photo", "path": r"assets\a.png", "checksum": "abc", "mimetype": "image/png"}],
            }
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)
    assert preview.items[0].photos[0].path_rel == "assets/a.png"
    assert not preview.items[0].photos[0].missing


# --------------------------------------------------------------------------- #
# parser: pdf page handling
# --------------------------------------------------------------------------- #


def test_pdf_page_is_non_null(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "title": "PDF Item",
                "photo": [
                    {"@type": "Photo", "path": "doc.pdf", "checksum": "x", "mimetype": "application/pdf", "page": 2}
                ],
            }
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")
    _make_export(f, export)
    preview = load_export(f)
    assert preview.items[0].photos[0].page == 2


def test_image_page_is_none(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item",
                "title": "Photo Item",
                "photo": [
                    {"@type": "Photo", "path": "a.png", "checksum": "x", "mimetype": "image/png"}
                ],
            }
        ]
    }
    f = _simple_export(tmp_path)
    preview = load_export(f)
    assert preview.items[0].photos[0].page is None


# --------------------------------------------------------------------------- #
# page_stem
# --------------------------------------------------------------------------- #


def test_page_stem_pdf():
    stem = page_stem("My Item", "doc.pdf", 41, "application/pdf", Path("doc.pdf"))
    assert stem == "My Item/doc_p0042"


def test_page_stem_image():
    stem = page_stem("Photos", "img001.jpg", None, "image/jpeg", Path("img001.jpg"))
    assert stem == "Photos/img001"


def test_safe_name_filters_unsafe_chars():
    assert safe_name('KV/2: "file"?') == "KV_2_ _file__"
    assert safe_name("") == "untitled"
    assert safe_name("   ") == "untitled"


# --------------------------------------------------------------------------- #
# photos_to_job_items
# --------------------------------------------------------------------------- #


def test_pages_to_job_items_carry_origin(tmp_path):
    f = _simple_export(tmp_path)
    preview = load_export(f)
    items = photos_to_job_items(preview)
    assert len(items) == 1
    assert items[0].source["origin"] == "tropy-jsonld"
    assert items[0].source["item_title"] == "Test Item"
    assert items[0].source["tropy_group"] is not None
    assert items[0].source["photo_path_rel"] == "a.png"


def test_pages_to_job_items_can_filter_by_group(tmp_path):
    export = {
        "@graph": [
            {
                "@type": "Item", "title": "Keep",
                "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}],
            },
            {
                "@type": "Item", "title": "Skip",
                "photo": [{"@type": "Photo", "path": "a.png", "checksum": "abc", "mimetype": "image/png"}],
            },
        ]
    }
    f = tmp_path / "e.json"
    (tmp_path / "a.png").write_bytes(b"x")
    _make_export(f, export)
    preview = load_export(f)

    # Filter to just the first item's group
    group0 = preview.items[0].group
    filtered = photos_to_job_items(preview, groups=[group0])
    assert len(filtered) == 1
    assert filtered[0].source["tropy_group"] == group0


# --------------------------------------------------------------------------- #
# export: note HTML
# --------------------------------------------------------------------------- #


def test_note_html_escapes_tags():
    html = _note_html("<script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_note_html_wraps_lines_in_paragraphs():
    html = _note_html("line one\nline two")
    assert "<p>line one</p>" in html
    assert "<p>line two</p>" in html


def test_note_html_handles_empty_text():
    html = _note_html("")
    assert "<p>" in html


# --------------------------------------------------------------------------- #
# export: build_export
# --------------------------------------------------------------------------- #


def test_build_export_produces_valid_structure(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF")
    photos = [
        ExportPhoto(
            abs_path=f,
            text="Der Bericht ist fertig.",
            label="doc.pdf  p.1",
            language="de",
            item_node={"@type": "Item", "title": "Doc", "photo": [{"@type": "Photo", "path": "doc.pdf"}]},
            group="abc:0",
            photo_index=0,
            path_rel="doc.pdf",
            checksum="abc123",
            mimetype="application/pdf",
        ),
    ]
    doc = build_export(photos)
    assert "@context" in doc
    assert "@graph" in doc
    assert "generator" in doc
    assert len(doc["@graph"]) >= 1

    item = doc["@graph"][0]
    assert item["@type"] == "Item"
    assert "photo" in item
    assert len(item["photo"]) >= 1


def test_build_export_preserves_item_metadata(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF")
    original_node = {
        "@type": "Item",
        "title": "Original Title",
        "template": "https://tropy.org/v1/templates/generic#item",
        "tag": [{"@type": "Tag", "name": "important"}],
    }
    photos = [
        ExportPhoto(
            abs_path=f,
            text="Some text",
            label="doc.pdf p.1",
            language="de",
            item_node=original_node,
            group="abc:0",
            photo_index=0,
            path_rel="doc.pdf",
            checksum="abc",
            mimetype="application/pdf",
        ),
    ]
    doc = build_export(photos)
    item = doc["@graph"][0]
    assert item["title"] == "Original Title"
    assert item["template"].endswith("generic#item")
    assert "tag" in item


def test_build_export_includes_note_with_text_and_html(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF")
    photos = [
        ExportPhoto(
            abs_path=f,
            text="Der Bericht\nZweiter Absatz",
            label="doc.pdf p.1",
            language="de",
            item_node={"@type": "Item", "title": "Doc"},
            group="abc:0",
            photo_index=0,
            path_rel="doc.pdf",
            checksum="abc",
            mimetype="application/pdf",
        ),
    ]
    doc = build_export(photos)
    note = doc["@graph"][0]["photo"][0]["note"][0]
    assert note["text"] == "Der Bericht\nZweiter Absatz"
    assert "<p>Der Bericht</p>" in note["html"]
    assert "<p>Zweiter Absatz</p>" in note["html"]


def test_ad_hoc_photos_produce_minimal_nodes(tmp_path):
    f = tmp_path / "scan.png"
    f.write_bytes(b"PNG\x00")
    photos = [
        ExportPhoto(
            abs_path=f,
            text="Some OCR text",
            label="scan.png",
            language="de",
            item_node=None,
            group=None,
            photo_index=None,
            path_rel=None,
            checksum="",
            mimetype="",
        ),
    ]
    doc = build_export(photos)
    assert len(doc["@graph"]) == 1
    item = doc["@graph"][0]
    assert item["@type"] == "Item"
    assert item["title"] == "scan"
    assert item["template"] == "https://tropy.org/v1/templates/generic#item"
    assert len(item["photo"]) == 1


def test_export_json_produces_indented_json(tmp_path):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF")
    photos = [
        ExportPhoto(
            abs_path=f, text="text", label="l", language="de",
            item_node={"@type": "Item", "title": "Doc"},
            group="g", photo_index=0, path_rel="d", checksum="c", mimetype="m",
        ),
    ]
    s = export_json(photos)
    assert s.startswith("{")
    data = json.loads(s)
    assert "generator" in data


# --------------------------------------------------------------------------- #
# round-trip: import → export → re-import
# --------------------------------------------------------------------------- #


def test_round_trip_preserves_title(tmp_path):
    # Create an export with a real image
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF")
    export = {
        "@graph": [
            {
                "@type": "Item",
                "title": "Round Trip Doc",
                "template": "https://tropy.org/v1/templates/generic#item",
                "photo": [
                    {
                        "@type": "Photo",
                        "path": "doc.pdf",
                        "checksum": "abc123",
                        "mimetype": "application/pdf",
                        "page": 0,
                    }
                ],
            }
        ]
    }
    ef = _make_export(tmp_path / "export.json", export)
    preview = load_export(ef)
    assert preview.items[0].title == "Round Trip Doc"

    # Build export from the imported data
    photos = []
    for item in preview.items:
        for photo in item.photos:
            photos.append(
                ExportPhoto(
                    abs_path=photo.resolved,
                    text="Some OCR result",
                    label=item.label,
                    language="de",
                    item_node=photo.item_node,
                    group=photo.group,
                    photo_index=photo.photo_index,
                    path_rel=photo.path_rel,
                    checksum=photo.checksum,
                    mimetype=photo.mimetype,
                )
            )
    doc = build_export(photos)
    item = doc["@graph"][0]
    # The title survives the round-trip via the compact "title" key
    assert item["title"] == "Round Trip Doc"
    assert item["template"].endswith("generic#item")


# --------------------------------------------------------------------------- #
# manifest writer
# --------------------------------------------------------------------------- #


def test_write_manifest_creates_file(tmp_path):
    f = _simple_export(tmp_path)
    preview = load_export(f)
    out = tmp_path / "output"
    manifest = write_manifest(out, preview)
    assert manifest is not None
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "export" in data
    assert "pages" in data
    assert data["export"]["name"] == "export.json"


def test_write_manifest_handles_nonexistent_dir(tmp_path):
    f = _simple_export(tmp_path)
    preview = load_export(f)
    out = tmp_path / "deeply" / "nested" / "output"
    manifest = write_manifest(out, preview)
    assert manifest is not None
    assert manifest.exists()


def test_write_manifest_merges_across_runs(tmp_path):
    f = _simple_export(tmp_path)
    preview = load_export(f)
    out = tmp_path / "output"
    write_manifest(out, preview)

    # Second call should merge, not overwrite
    manifest2 = write_manifest(out, preview)
    assert manifest2 is not None
    data = json.loads(manifest2.read_text(encoding="utf-8"))
    assert len(data["pages"]) >= 1


# --------------------------------------------------------------------------- #
# context completeness
# --------------------------------------------------------------------------- #


def test_tropy_context_has_required_keys():
    assert "@version" in TROPY_CONTEXT
    assert TROPY_CONTEXT["@version"] == "1.1"
    assert "@vocab" in TROPY_CONTEXT
    assert "photo" in TROPY_CONTEXT
    assert "note" in TROPY_CONTEXT
