Tropy Integration — Design Notes (not yet implemented)
======================================================

Status: **planned, deferred.** Decision taken 2026-07-21: folder output only.
The tool will never write into a Tropy project database.

This document records what was verified about the real archives on this
machine so the work can start cold.


WHAT WAS INSPECTED
------------------

Tropy stores recent projects in `%APPDATA%/Tropy/state.json`:

    E:\Tropy\ISK Project Primary Sources.tropy
    E:\iCloudDrive\Archives\Tropy Databases\Alpenpost.tropy
    E:\iCloudDrive\Archives\Tropy Databases\ISK Project Primary Sources.tropy

A `.tropy` "managed" project is a directory, not a file:

    ISK Project Primary Sources.tropy/
      project.tpy        SQLite database (~16 MB here)
      project.tpy-wal    present while Tropy is running
      assets/            content-addressed originals, <sha256>.pdf / .jpg

Contents of the ISK project as of inspection:

    items            72
    photos        6,070
    notes         1,101
    selections        0
    transcriptions    0      (table exists, unused)

Schema version: migration `2412161647`.


THE FACTS THAT SHAPE THE DESIGN
-------------------------------

1. **Photos are pages, not files.** `photos` has both `path`
   (`assets/<sha>.pdf`, relative to the bundle) and `page` (0-based index).
   6,070 photos across 72 items means most items are multi-page PDFs — the
   KV-2 series from the National Archives.

2. **`ocr.perform()` is file-granular, Tropy is page-granular.**
   `stages/ocr.py` renders every page of a PDF and joins them with
   `--- Page Break ---`. Tropy needs one result per page, so a page-level
   entry point is required. PyMuPDF is already a dependency, so rendering a
   single page is cheap — the work is API shape, not capability.

3. **Stem collisions are a real hazard.** `pipeline._output_exists()` keys on
   `Path(x).stem`. Every page of a Tropy PDF shares the same checksum stem, so
   naive use would make page 2 "resume" from page 1's output across a
   200-page file. Any Tropy ingest must supply an explicit output key —
   `<item>/<original filename>_p0007` — rather than relying on the stem.

4. **`filename` preserves the human name.** `photos.filename` holds the
   original (`KV-2-2339_01.pdf`) even though `path` is a checksum. Use it for
   output naming; use `items` + `list_items` for foldering.

5. **Lists are the natural batch unit.** 35 lists over 72 items — a list is
   how the archive is already organised, so "process this list" is the
   selection UI that matches how the material is actually used.


PLANNED SCOPE (Tier 1 only)
---------------------------

`src/ocr_pipeline/tropy.py` — read-only.

  * Open with `sqlite3.connect("file:...?mode=ro&immutable=1", uri=True)`.
    Read-only is not merely polite: it means the tool cannot corrupt a
    project even if Tropy is running with an open WAL.
  * Enumerate items by list / tag / item id; expand to page-level work units.
  * Resolve `assets/` paths relative to the bundle directory.
  * Feed page images to the existing pipeline stages.
  * Write a mirrored output tree:

        out/<Item Title>/<original filename>_p0003/
            raw_ocr.txt  cleaned.txt  translated.txt

  * Emit a `manifest.json` per run mapping each output back to its Tropy
    `photo.id`, `item.id` and page — so a future import path stays possible
    without re-deriving anything.

The GUI side is a source picker in the Main tab: pick a `.tropy` bundle, then
a list or item, and the resulting page units populate the existing queue.
Pause/skip/retry and history then work unchanged — which is why this was
sequenced after the job runner rather than before it.


EXPLICITLY OUT OF SCOPE
-----------------------

* Writing `notes` rows.
* Writing `transcriptions` rows (the empty native table).
* JSON-LD export for re-import.
* A JavaScript Tropy plugin.

If write-back is ever revisited, the non-negotiables are: Tropy closed, a
timestamped copy of `project.tpy` taken first, and dry-run as the default.
