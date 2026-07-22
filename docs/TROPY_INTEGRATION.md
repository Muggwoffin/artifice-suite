Tropy Integration
=================

Status: **implemented — read-only ingest, folder output, and opt-in write-back.**

The original decision of 2026-07-21 was folder-output-only. That was revisited
later the same day and write-back was added, with the safeguards this document
had already set as the price of doing it: Tropy closed, automatic backup,
preview before any change. Reading is still provably separate from writing —
`tropy.py` opens `mode=ro` and never imports the writer.


WHAT IT DOES
------------

Pull documents out of a Tropy archive, OCR them, and write the results to a
folder. Selection is by list, by tag, by item, or the whole project.

    # browse a project (or list recent ones with no argument)
    ocr_pipeline tropy-browse "E:/Tropy/ISK Project Primary Sources.tropy"

    # see what a run would do, without doing it
    ocr_pipeline tropy "E:/Tropy/ISK Project Primary Sources.tropy" \
        --list-id 8 --dry-run

    # OCR one list into ./output
    ocr_pipeline tropy "E:/Tropy/ISK Project Primary Sources.tropy" \
        --list-id 8 --output-dir output --limit 50

In the GUI: **Main → Add from Tropy…** opens a picker (recent projects, the
list/tag tree, item selection with page counts) and drops the chosen pages
into the normal queue, where pause / skip / retry / history all work as usual.

Translation is off by default for Tropy runs (`--translate` to enable) —
these archives are large and translating 1,960 pages by accident is expensive.


READ-ONLY GUARANTEE
-------------------

The connection is opened `file:...?mode=ro`. This is enforced by SQLite, not
by convention: an attempted `INSERT` raises
`sqlite3.OperationalError: attempt to write a readonly database`.

**Do not use `immutable=1`.** An earlier draft of this document recommended
it; that was wrong. `immutable=1` makes SQLite ignore the write-ahead log, so
any edit made in a running Tropy would be invisible, and the file changing
underneath can produce corrupt reads. `mode=ro` respects the WAL and works
while Tropy is open.


THE ARCHIVE, AS VERIFIED
------------------------

Tropy records recent projects in `%APPDATA%/Tropy/state.json`. A `.tropy`
"managed" project is a directory:

    ISK Project Primary Sources.tropy/
      project.tpy      SQLite database
      assets/          content-addressed originals, <checksum>.pdf / .jpg

    ISK Project        72 items    6,070 photos    1,101 notes
    Alpenpost          93 items      552 photos

Both use `base='project'` (paths relative to the bundle) and `store='assets'`.

Four facts drove the design:

1. **Photos are pages, not files.** A 275-page item is 275 rows sharing one
   `assets/<checksum>.pdf`, differing only by the `page` column.

2. **Both path separators occur.** 868 rows in the ISK project use
   backslashes, the rest forward slashes. `resolve_path()` normalises before
   resolving; there is a test for it.

3. **Lists nest.** "KV Files" sits under "National Archives UK". Selecting a
   parent list means everything beneath it, via a recursive CTE.

4. **Mixed media.** 2,333 PDF pages and 3,737 JPEGs. Images are not
   paginated; PDFs are.


THE COLLISION HAZARD
--------------------

This is the thing that would have silently destroyed a run.

`pipeline._output_exists()` keys on `Path(x).stem`. Every page of a Tropy PDF
shares the checksum stem, so all 275 pages of an item would have written to
`output/raw_ocr/text/89bf563c….txt`, each overwriting the last, and `resume`
would have reported pages 2–275 as "already done" after page 1.

The fix is an explicit output key threaded through the stages:

    Max Hodann KV File Part 1/KV-2-2339_01_p0002

`ocr.perform()`, `cleanup.perform()` and `translate.perform()` all accept an
optional `stem` that overrides the filename-derived one and may contain a
subdirectory. `run_ocr_step()` additionally takes `page` to render a single
PDF page rather than all 144. Both are covered by tests
(`test_each_pdf_page_writes_its_own_output`,
`test_page_outputs_resume_independently`).


OUTPUT LAYOUT
-------------

This deviates from the original plan, deliberately. The first sketch proposed
a per-page directory (`out/<Item>/<file>_p0003/raw_ocr.txt`), which would have
forked the output contract that the CLI, resume logic and History tab already
understand. Instead the standard stage-first tree is kept and the *key* is
made unique:

    output/
      raw_ocr/text/Max Hodann KV File Part 1/KV-2-2339_01_p0001.txt
      raw_ocr/json/Max Hodann KV File Part 1/KV-2-2339_01_p0001.json
      cleaned/text/Max Hodann KV File Part 1/KV-2-2339_01_p0001.txt
      translated/...
      tropy_manifest.json

`tropy_manifest.json` maps every output key back to its origin, so the link
from a text file to photo 4 of item 1 survives outside anyone's memory:

    "Max Hodann KV File Part 1/KV-2-2339_01_p0003": {
      "photo_id": 4, "item_id": 1, "page": 2, "page_number": 3,
      "filename": "KV-2-2339_01.pdf",
      "item_title": "Max Hodann KV File Part 1",
      "source_path": "…/assets/89bf563c….pdf"
    }

The manifest merges across runs rather than being overwritten.


WRITING BACK INTO TROPY
-----------------------

**Main tab -> "Send to Tropy…"**, after a run. Only pages that came from Tropy
can be sent; the button says so if none of the queue did.

The dialog previews before it writes. It lists every row it would create, and
the write button stays disabled until that preview is clean:

    PAGE                     TARGET  ACTION         DETAIL
    KV-2-2339_01.pdf  p.1    notes   insert
    KV-2-2339_01.pdf  p.2    notes   duplicate      identical text already attached
    KV-2-2339_01.pdf  p.3    notes   missing-photo  photo 4021 is not in this project

Two targets, selectable per run:

* **Notes** — one note per photo, stored exactly as Tropy's own editor stores
  them: plain `text` plus a ProseMirror document in `state`. Appears in the
  normal note pane.
* **Transcriptions** — rows in Tropy's native `transcriptions` table, tagged
  `config.generator = "ocr_pipeline"` so they are always identifiable as ours.

Both tables carry `AFTER INSERT` triggers maintaining the FTS index, so
inserting is enough to keep Tropy's search working.

Safeguards, all enforced in `tropy_write.py`:

1. **Tropy must be closed.** Checked by process name, plus a `BEGIN IMMEDIATE`
   probe for a held write lock. Writing under a running Tropy means its
   in-memory state diverges and can overwrite what was just written.
2. **Backup first.** A timestamped `project.<stamp>.backup.tpy` beside the
   original, including WAL sidecars. Skippable, but on by default.
3. **One transaction.** Any failure rolls the whole batch back — there is no
   half-written state.
4. **Re-running is safe.** An entry whose text is already attached to that
   photo is reported as a duplicate and skipped.


KNOWN LIMITS
------------

* **Missing assets.** iCloud-backed projects may hold placeholders rather than
  files. `missing_assets()` reports these up front; the CLI warns and the GUI
  offers to skip them.
* **Selections and notes are ignored.** Tropy selections (crops) and existing
  notes are not read. The 1,101 notes in the ISK project are untouched.
* **Write-back creates, never updates.** Sending the same page twice with
  *different* text adds a second note rather than replacing the first. Editing
  or removing what was written is done in Tropy.
* **Transcriptions are an internal schema.** The table shape can change
  between Tropy releases. Notes are the safer of the two targets.
