"""Tests for the read-only Tropy reader and page-level pipeline plumbing.

A miniature `.tropy` bundle is built on disk (real SQLite, real multi-page
PDF), so these exercise the same code paths as a genuine archive without
depending on one being present.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from artifice_ocr.tropy import (
    TropyProject,
    _page_stem,
    _safe_name,
    pages_to_job_items,
    write_manifest,
)

TITLE = "http://purl.org/dc/elements/1.1/title"

SCHEMA = """
CREATE TABLE project (project_id TEXT, name TEXT, created TEXT, base TEXT, store TEXT);
CREATE TABLE items (id INTEGER PRIMARY KEY, cover_image_id INTEGER);
CREATE TABLE photos (
    id INTEGER PRIMARY KEY, item_id INTEGER, position INTEGER, path TEXT,
    protocol TEXT DEFAULT 'file', mimetype TEXT, checksum TEXT,
    page INTEGER DEFAULT 0, filename TEXT, orientation INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE metadata (id INTEGER, property TEXT, value_id INTEGER);
CREATE TABLE metadata_values (value_id INTEGER PRIMARY KEY, datatype TEXT, text TEXT);
CREATE TABLE lists (list_id INTEGER PRIMARY KEY, name TEXT, parent_list_id INTEGER, position INTEGER);
CREATE TABLE list_items (list_id INTEGER, id INTEGER, position INTEGER, deleted NUMERIC);
CREATE TABLE tags (tag_id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE taggings (tag_id INTEGER, id INTEGER);
CREATE TABLE trash (id INTEGER PRIMARY KEY, deleted NUMERIC, reason TEXT);
"""


def _make_pdf(path: Path, pages: int) -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for n in range(pages):
        page = doc.new_page()
        page.insert_text((72, 100), f"Seite {n + 1}")
    doc.save(str(path))
    doc.close()


@pytest.fixture
def bundle(tmp_path):
    """A minimal but realistic .tropy managed project."""
    root = tmp_path / "Test Archive.tropy"
    assets = root / "assets"
    assets.mkdir(parents=True)

    _make_pdf(assets / "aaaa1111.pdf", pages=3)
    (assets / "bbbb2222.jpg").write_bytes(b"\xff\xd8\xff\xe0not-a-real-jpeg")

    con = sqlite3.connect(root / "project.tpy")
    con.executescript(SCHEMA)
    con.execute("INSERT INTO project VALUES ('uuid','Test Archive','2026-01-01','project','assets')")
    con.executemany("INSERT INTO items (id) VALUES (?)", [(1,), (2,), (3,)])

    # Item 1: a 3-page PDF. Note the backslash separator on the first row —
    # Tropy really does mix separators, and resolution must cope.
    con.executemany(
        "INSERT INTO photos (id,item_id,path,mimetype,page,filename) VALUES (?,?,?,?,?,?)",
        [
            (10, 1, r"assets\aaaa1111.pdf", "application/pdf", 0, "KV-2-1234.pdf"),
            (11, 1, "assets/aaaa1111.pdf", "application/pdf", 1, "KV-2-1234.pdf"),
            (12, 1, "assets/aaaa1111.pdf", "application/pdf", 2, "KV-2-1234.pdf"),
            (20, 2, "assets/bbbb2222.jpg", "image/jpeg", 0, "photo_001.jpg"),
            (30, 3, "assets/missing.pdf", "application/pdf", 0, "gone.pdf"),
        ],
    )

    values = [
        (1, "Max Hodann KV File"), (2, "Loose Photos"), (3, "Broken Item"),
    ]
    con.executemany("INSERT INTO metadata_values (value_id,datatype,text) VALUES (?,?,?)",
                    [(v, "text", t) for v, t in values])
    con.executemany("INSERT INTO metadata (id,property,value_id) VALUES (?,?,?)",
                    [(i, TITLE, i) for i, _ in values])

    # Nested lists: "KV Files" sits under "National Archives"
    con.executemany("INSERT INTO lists VALUES (?,?,?,?)",
                    [(0, "ROOT", None, 0), (1, "National Archives", 0, 0),
                     (2, "KV Files", 1, 0), (3, "Photos", 0, 1)])
    con.executemany("INSERT INTO list_items VALUES (?,?,?,?)",
                    [(2, 1, 0, None), (3, 2, 0, None)])

    con.execute("INSERT INTO tags VALUES (1,'resistance')")
    con.execute("INSERT INTO taggings VALUES (1,1)")
    con.commit()
    con.close()
    return root


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #

def test_opens_bundle_directory_and_reads_project(bundle):
    with TropyProject(bundle) as proj:
        assert proj.name == "Test Archive"
        assert proj.base == "project"
        assert proj.store == "assets"
        assert proj.db_path == bundle / "project.tpy"


def test_opens_project_tpy_directly(bundle):
    with TropyProject(bundle / "project.tpy") as proj:
        assert proj.name == "Test Archive"


def test_missing_project_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        TropyProject(tmp_path / "nope.tropy")


def test_lists_are_nested_with_counts(bundle):
    with TropyProject(bundle) as proj:
        lists = proj.lists()

    names = [(l.name, l.depth) for l in lists]
    assert ("National Archives", 0) in names
    assert ("KV Files", 1) in names
    assert "ROOT" not in [l.name for l in lists]

    archives = next(l for l in lists if l.name == "National Archives")
    # a parent list means "everything underneath it"
    assert archives.item_count == 1


def test_item_ids_in_list_descends_sub_lists(bundle):
    with TropyProject(bundle) as proj:
        assert proj.item_ids_in_list(1) == [1]   # parent
        assert proj.item_ids_in_list(2) == [1]   # the sub-list itself
        assert proj.item_ids_in_list(3) == [2]


def test_item_ids_with_tag(bundle):
    with TropyProject(bundle) as proj:
        assert proj.item_ids_with_tag("resistance") == [1]
        assert proj.item_ids_with_tag("nonexistent") == []


def test_items_carry_titles_and_page_counts(bundle):
    with TropyProject(bundle) as proj:
        items = {i.item_id: i for i in proj.items()}

    assert items[1].title == "Max Hodann KV File"
    assert items[1].photo_count == 3
    assert items[2].photo_count == 1


def test_trashed_items_are_excluded(bundle):
    con = sqlite3.connect(bundle / "project.tpy")
    con.execute("INSERT INTO trash VALUES (2, NULL, 'user')")
    con.commit()
    con.close()

    with TropyProject(bundle) as proj:
        assert 2 not in [i.item_id for i in proj.items()]


# --------------------------------------------------------------------------- #
# page resolution — the part that would silently corrupt a run
# --------------------------------------------------------------------------- #

def test_pdf_pages_get_distinct_output_stems(bundle):
    with TropyProject(bundle) as proj:
        pages = proj.pages([1])

    assert len(pages) == 3
    stems = [p.output_stem for p in pages]
    assert stems == [
        "Max Hodann KV File/KV-2-1234_p0001",
        "Max Hodann KV File/KV-2-1234_p0002",
        "Max Hodann KV File/KV-2-1234_p0003",
    ]
    # all three share one asset but address different pages
    assert len({p.path for p in pages}) == 1
    assert [p.page for p in pages] == [0, 1, 2]


def test_backslash_paths_resolve(bundle):
    """Tropy stores both separators; the real ISK project has 868 backslashes."""
    with TropyProject(bundle) as proj:
        pages = proj.pages([1])

    assert all(p.path.exists() for p in pages)
    assert pages[0].path.name == "aaaa1111.pdf"


def test_images_are_not_paginated(bundle):
    with TropyProject(bundle) as proj:
        pages = proj.pages([2])

    assert len(pages) == 1
    assert pages[0].is_pdf is False
    assert pages[0].output_stem == "Loose Photos/photo_001"
    assert pages[0].label == "photo_001.jpg"


def test_missing_assets_are_reported(bundle):
    with TropyProject(bundle) as proj:
        pages = proj.pages()
        missing = proj.missing_assets(pages)

    assert [p.filename for p in missing] == ["gone.pdf"]


def test_duplicate_filenames_within_an_item_do_not_collide(bundle):
    con = sqlite3.connect(bundle / "project.tpy")
    con.execute(
        "INSERT INTO photos (id,item_id,path,mimetype,page,filename) "
        "VALUES (40,2,'assets/bbbb2222.jpg','image/jpeg',0,'photo_001.jpg')"
    )
    con.commit()
    con.close()

    with TropyProject(bundle) as proj:
        stems = [p.output_stem for p in proj.pages([2])]

    assert len(stems) == len(set(stems))


def test_safe_name_strips_path_characters():
    assert _safe_name('KV/2: "file"?') == "KV_2_ _file__"
    assert _safe_name("") == "untitled"
    assert _safe_name("   ") == "untitled"


def test_page_stem_pads_page_numbers():
    stem = _page_stem("Item", "doc.pdf", 41, "application/pdf", Path("x.pdf"))
    assert stem == "Item/doc_p0042"


# --------------------------------------------------------------------------- #
# job items + manifest
# --------------------------------------------------------------------------- #

def test_pages_to_job_items_carry_page_and_stem(bundle):
    with TropyProject(bundle) as proj:
        items = pages_to_job_items(proj.pages([1]))

    assert [i.page for i in items] == [0, 1, 2]
    assert items[0].stem == "Max Hodann KV File/KV-2-1234_p0001"
    assert items[0].name == "KV-2-1234.pdf  p.1"
    assert items[0].source["photo_id"] == 10


def test_image_job_item_has_no_page(bundle):
    with TropyProject(bundle) as proj:
        items = pages_to_job_items(proj.pages([2]))

    assert items[0].page is None


def test_photo_orientation_defaults_to_normal(bundle):
    """None of the fixture rows set an orientation — the schema's own
    DEFAULT 1 should apply, same as a Tropy project where nobody has ever
    flagged a photo as rotated."""
    with TropyProject(bundle) as proj:
        pages = proj.pages([2])

    assert pages[0].orientation == 1
    assert pages[0].provenance()["orientation"] == 1


def test_photo_orientation_is_read_from_the_database(bundle):
    """Confirmed necessary on a real archive page: Tropy's orientation
    column is the one place a scan can be marked upside-down (EXIF 3) —
    if this isn't read, rotating the photo in Tropy does nothing."""
    con = sqlite3.connect(bundle / "project.tpy")
    con.execute(
        "INSERT INTO photos (id,item_id,path,mimetype,page,filename,orientation) "
        "VALUES (50,2,'assets/cccc3333.jpg','image/jpeg',0,'photo_002.jpg',3)"
    )
    con.commit()
    con.close()

    with TropyProject(bundle) as proj:
        pages = proj.pages([2])
        items = pages_to_job_items(pages)

    rotated = next(p for p in pages if p.photo_id == 50)
    assert rotated.orientation == 3
    assert rotated.provenance()["orientation"] == 3

    rotated_item = next(i for i in items if i.source.get("photo_id") == 50)
    assert rotated_item.source["orientation"] == 3


def test_manifest_maps_outputs_back_to_photos(bundle, tmp_path):
    out = tmp_path / "out"
    with TropyProject(bundle) as proj:
        pages = proj.pages([1])
        target = write_manifest(out, proj, pages)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["project"]["name"] == "Test Archive"

    entry = data["pages"]["Max Hodann KV File/KV-2-1234_p0002"]
    assert entry["photo_id"] == 11
    assert entry["item_id"] == 1
    assert entry["page"] == 1
    assert entry["page_number"] == 2
    assert entry["item_title"] == "Max Hodann KV File"


def test_manifest_merges_across_runs(bundle, tmp_path):
    out = tmp_path / "out"
    with TropyProject(bundle) as proj:
        write_manifest(out, proj, proj.pages([1]))
        target = write_manifest(out, proj, proj.pages([2]))

    data = json.loads(target.read_text(encoding="utf-8"))
    assert len(data["pages"]) == 4  # 3 PDF pages + 1 image


# --------------------------------------------------------------------------- #
# end to end: a real PDF through the real stage code, with the LLM mocked
# --------------------------------------------------------------------------- #

@patch("src.artifice_ocr.stages.ocr._ocr_single_image")
def test_each_pdf_page_writes_its_own_output(mock_ocr, bundle, tmp_path):
    """The collision hazard, tested directly.

    All three pages share one checksum-named PDF. Keyed on the filename stem
    they would overwrite each other; keyed on the page stem they must not.
    """
    from artifice_ocr.jobs import JobRunner, State

    calls: list[str] = []

    def fake_ocr(image_path):
        calls.append(Path(image_path).name)
        return f"text of {Path(image_path).stem}"

    mock_ocr.side_effect = fake_ocr
    out = tmp_path / "out"

    with TropyProject(bundle) as proj:
        items = pages_to_job_items(proj.pages([1]))

    runner = JobRunner(items, str(out), stages={"ocr"}, max_workers=1)
    runner.start()
    while runner.is_running:
        runner._thread.join(timeout=5)

    assert all(i.state is State.DONE for i in items)

    text_dir = out / "raw_ocr" / "text" / "Max Hodann KV File"
    written = sorted(p.name for p in text_dir.glob("*.txt"))
    assert written == ["KV-2-1234_p0001.txt", "KV-2-1234_p0002.txt",
                       "KV-2-1234_p0003.txt"]

    # each file holds the text of its own page, not the last page processed
    assert (text_dir / "KV-2-1234_p0001.txt").read_text(encoding="utf-8") \
        == "text of page_0001"
    assert (text_dir / "KV-2-1234_p0003.txt").read_text(encoding="utf-8") \
        == "text of page_0003"

    # only the requested page was rendered each time
    assert sorted(calls) == ["page_0001.png", "page_0002.png", "page_0003.png"]


@patch("src.artifice_ocr.stages.ocr._ocr_single_image", return_value="ocr text")
def test_page_outputs_resume_independently(mock_ocr, bundle, tmp_path):
    from artifice_ocr.pipeline import run_ocr_step

    out = tmp_path / "out"
    with TropyProject(bundle) as proj:
        pages = proj.pages([1])

    first = run_ocr_step(pages[0].path, str(out), stem=pages[0].output_stem,
                         page=pages[0].page)
    assert not first.get("_skipped")

    again = run_ocr_step(pages[0].path, str(out), stem=pages[0].output_stem,
                         page=pages[0].page)
    assert again["_skipped"] is True

    # a different page of the same PDF must NOT be considered done
    other = run_ocr_step(pages[1].path, str(out), stem=pages[1].output_stem,
                         page=pages[1].page)
    assert not other.get("_skipped")


@patch("src.artifice_ocr.stages.ocr._ocr_single_image", return_value="ocr text")
def test_out_of_range_page_raises_clearly(mock_ocr, bundle, tmp_path):
    from artifice_ocr.stages import ocr as ocr_stage

    pdf = bundle / "assets" / "aaaa1111.pdf"
    with pytest.raises(ValueError, match="out of range"):
        ocr_stage.perform(str(pdf), output_dir=str(tmp_path), page=99, stem="x")
