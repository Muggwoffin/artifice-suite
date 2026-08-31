# Tropy Integration

**Status: implemented — JSON-LD, live read-only `.tpy` browse, official Developer API note write-back, and an advanced database fallback.**

The architecture described in this document is the one actually in source as of
commit `3d91e7c` ("Redone Tropy integration", 2026-08-09). The old SQLite
read/write modules (`tropy.py`, `tropy_read.py`) were removed; `tropy_write.py` was
restored 2026-08-25, knowingly reversing `ebd89e6`, as an opt-in default-off
write-back alongside the JSON-LD bridge.

There are two independent read paths and two export modes. Normal write-back
uses Tropy's loopback Developer API to attach notes to the original photos.
Direct `.tpy` database write-back is an advanced, **opt-in and default-off**
fallback (`tropy_writeback_enabled: False`).


## Overview

```
Tropy (File → Export)
         │
         ▼ JSON-LD file
    artifice-ocr ──────────────────────────► OCR pipeline
                                              output directory
                                              (tropy_manifest.json)
         │                                          │
         │         artifice-ocr                     │
         │    (JSON-LD export file)                 │
         ▼                           Tropy (File → Import Items…)
  "Send to Tropy…"                  or
  modal ───────────────────────────► Tropy local HTTP API (port 2029)
```

There are **two ways** to read from a Tropy project:

| Mode | Module | Writes to `.tpy`? | Feature flag |
|---|---|---|---|
| JSON-LD file bridge | `tropy_jsonld.py` | Never | None — always available |
| Live read-only browse | `tropy_db.py` | Never | Settings toggle `tropy_live_browse_enabled` |
| Developer API notes | `tropy_api.py` | Through Tropy | Enable Developer API in Tropy |
| Direct write-back | `tropy_write.py` | When enabled | Advanced setting `tropy_writeback_enabled` (default off) |

Both map to the same `JobItem` pipeline entry. The manifest (`tropy_manifest.json`)
is written by the JSON-LD import path and documents provenance for downstream
consumers.


## JSON-LD File Bridge (`tropy_jsonld.py`)

**Portable file integration.** User-initiated and requires no feature flag.

### Import: Tropy → artifice-ocr

1. In Tropy: **File → Export → JSON-LD** (or **File → Export → JSON**).
   Save the file somewhere accessible to artifice-ocr.
2. In artifice-ocr: **Main → Add from Tropy…** opens the import modal.
   Either drop the exported file onto the dropzone, or type/paste a path.
3. artifice-ocr parses the JSON-LD, resolves photo paths, and displays a
   preview. Relative paths are resolved against the export file's directory.
   Absolute paths are validated by `_tropy_pathcheck` before use.
4. The user selects which items to enqueue; missing photos are flagged inline.
5. Items drop into the normal queue. Pause / skip / retry / history all work
   as usual.

### Export: artifice-ocr → Tropy ("Send to Tropy…")

**Main → Send to Tropy…**, available after a run. Only pages processed by
artifice-ocr are eligible.

Two export routes exist:

- **`POST /api/tropy/export`** — exports items currently in the queue.
- **`POST /api/tropy/export/history`** — exports items from the History database
  (for runs already completed and recorded).

The Send to Tropy modal defaults to Developer API note write-back. Tropy must be
running, the target project must be open, and **Preferences → Developer API**
must be enabled. Artifice OCR discovers stable port 2019 and beta port 2029 (or
uses the custom port in Settings), verifies the open project, checks each photo
and parent item, previews blockers and duplicates, and only then enables commit.
Identical notes are skipped, so retrying after a partial failure is safe.

JSON-LD export is the separate choice for creating/importing new items. It
preserves source metadata, photos, page numbers, and existing notes when
provenance is available. The advanced direct-database mode retains its
closed-project check, timestamped backup, preview, and duplicate protection.

### Path validation (`_tropy_pathcheck.py`)

Absolute photo paths in a JSON-LD export (including Windows drive-letter paths)
are validated before the import proceeds. The validator:

- Rejects UNC paths (`//…`) unconditionally.
- Rejects paths under protected system directories: `/etc`, `/usr`, `/bin`,
  `/sbin`, `/lib`, `/var`, `/sys`, `/proc`, `/dev`, `/boot`, `/root`, `/run`,
  `/private/etc`, `/private/var` on POSIX; `C:/Windows`, `C:/Program Files`,
  `C:/Program Files (x86)`, `C:/ProgramData`, `C:/$Recycle.Bin`,
  `C:/System Volume Information` on Windows.
- Rejects paths resolving into protected subdirectories under `$HOME`:
  `.ssh`, `.gnupg`, `.aws`, `.azure`, `.kube`, `.docker`, `AppData`.
- Allows only `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.pdf` suffixes.
- Follows symlinks (the resolved target is checked against the blocklist);
  a warning is added when a symlink was followed so the user knows.
- Reports a missing file rather than failing — the photo is flagged as missing
  and the import continues.

The `ARTIFICE_OCR_TROPY_RELATIVE_ONLY=1` environment variable reverts to rejecting
all absolute paths outright (the pre-pathcheck behaviour).

### Manifest (`tropy_manifest.json`)

Written to the output directory after every JSON-LD import. Maps each output
stem back to its source photo. This is the documented contract for
`artifice-graph` and any other downstream consumer.

Schema version: `1.0`. The manifest merges across runs (it is never overwritten;
existing entries are updated or preserved).

    {
      "schema_version": "1.0",
      "export": { "name": "export.jsonld", "imported": "2026-08-09T…" },
      "output_layout": "<stage>/text/<item title>/<file>_p<page>.txt",
      "pages": {
        "Max Hodann KV File Part 1/KV-2-2339_01_p0002": {
          "photo_id": null,
          "page": 1,
          "page_number": 2,
          "source_path": "…/assets/89bf563c….pdf",
          "mimetype": "application/pdf",
          "orientation": 1,
          "filename": "KV-2-2339_01.pdf",
          "item_title": "Max Hodann KV File Part 1",
          "checksum": "89bf563c…",
          "photo_path_rel": "KV-2-2339_01.pdf",
          "tropy_group": "a1b2c3d4e5f6:0"
        }
      }
    }

`photo_id` is `null` for JSON-LD imports (Tropy IDs are not preserved in the
export format). It is populated only for live-read items.


## Live Read-Only Browse (`tropy_db.py`)

**Opt-in, feature-flagged.** Enable via the Settings UI toggle
`tropy_live_browse_enabled` (takes effect immediately, no restart required).
The environment variable `ARTIFICE_OCR_TROPY_LIVE_READ=1` also works as a
fallback override for advanced/CI use. When disabled, the browse routes
return 404.

Opens `.tpy` SQLite databases in `file:<path>?mode=ro` — SQLite enforces
read-only at the connection level. A running Tropy instance holds a write
lock; `tropy_db` handles `SQLITE_BUSY` with a clean error message telling the
user to close Tropy and retry. Connections are short-lived and per-query.

### Browse routes

All mounted at `/api/tropy/browse/` when enabled:

| Route | What it returns |
|---|---|
| `POST /projects` | The single `project` row (name, base path) |
| `POST /lists` | All lists except ROOT (`list_id != 0`) |
| `POST /tags` | All tags |
| `POST /items?list_id=N` | Items in a list (recursive via join on `list_items`) |
| `POST /items?tag=name` | Items with a given tag |
| `POST /items` | All non-trashed items |
| `POST /items/{item_id}` | Single item with its photos |
| `POST /enqueue` | Map selected items to `JobItem` and add to queue |

The **Add from Tropy…** modal shows a live-browse tab when the
settings toggle `tropy_live_browse_enabled` is on (or
`ARTIFICE_OCR_TROPY_LIVE_READ=1` is set). Selecting items and clicking
**Add to Queue** bypasses the JSON-LD export/import round-trip entirely.


## Output Layout

All output goes into the standard stage-first tree. The unique output key
prevents PDF page collision:

    output/
      raw_ocr/text/Max Hodann KV File Part 1/KV-2-2339_01_p0001.txt
      raw_ocr/json/Max Hodann KV File Part 1/KV-2-2339_01_p0001.json
      cleaned/text/Max Hodann KV File Part 1/KV-2-2339_01_p0001.txt
      translated/…
      tropy_manifest.json

The key format is `<Item Title>/<file>_p<page:04d>` for PDFs, or
`<Item Title>/<file>` for images. This is the same naming used by `tropy_db`.

`ocr.perform()`, `cleanup.perform()` and `translate.perform()` all accept an
optional `stem` parameter that overrides the filename-derived key and may contain
a subdirectory. `run_ocr_step()` additionally takes `page` to render a single
PDF page rather than all pages of an item.


## The Tropy Archive, As Verified

These are properties of Tropy's own data model, confirmed by the schema
comments in `tropy_db.py`.

**A `.tropy` "managed" project is a directory:**

    ISK Project Primary Sources.tropy/
      project.tpy      SQLite database
      assets/          content-addressed originals, <checksum>.pdf / .jpg

The `project` table holds `base='project'` (paths relative to the bundle) and
`store='assets'`.

Four structural facts shaped the design:

1. **Photos are pages, not files.** A 275-page item is 275 rows sharing one
   `assets/<checksum>.pdf`, differing only by the `page` column. The output
   key's per-page suffix (`_p0001`, `_p0002`, …) prevents all 275 pages from
   writing to the same `.txt` file.

2. **Both path separators occur.** Tropy stores paths as-is; backslash and
   forward-slash both appear in the database. `tropy_jsonld` normalises
   backslashes to forward slashes before resolving; `_resolve_photo_path`
   in `tropy_db` does the same.

3. **Lists nest.** A parent list includes everything beneath it via a
   recursive CTE-style join on `list_items`.

4. **Mixed media.** Photos may be PDFs (paginated, one row per page) or images
   (JPEG, PNG, TIFF — unpaginated, one row per file). The `mimetype` column
   distinguishes them.


## What Was Removed

The 2026-08-09 rewrite deleted:

- **`tropy.py`** — `mode=ro` live database reader. Replaced by `tropy_db.py`
  (still read-only, but a separate, simpler library module).
- **`tropy_read.py`** — the old 7-route import/preview/browse/write FastAPI
  module. Replaced by `tropy_bridge.py` (import/export, JSON-LD only) and
  `tropy_browse.py` (live browse, read-only).

**`tropy_write.py`** was removed in the 2026-08-09 rewrite and **restored
2026-08-25** — knowingly reversing `ebd89e6` — as an opt-in default-off write-back
alongside the JSON-LD bridge. It is not yet wired to any Settings UI control.

The following capabilities from the old doc **do not exist** in the JSON-LD bridge
(default path):

- **Notes and Transcriptions as write targets.** The JSON-LD bridge writes
  no `.tpy` tables. The separate `tropy_write.py` write-back path (opt-in,
  default off) does write notes and transcriptions with duplicate-text skip,
  timestamped backup, and a ProseMirror `selection` key on every note.
- **Tropy-must-be-closed probe.** The live-read connection uses `mode=ro`
  and catches `SQLITE_BUSY` at the library level; there is no proactive probe.
- **Automatic timestamped backup.** The JSON-LD export is a new file the user
  owns; artifice-ocr never touches the `.tpy` file via this path.
- **`immutable=1` connection flag.** The current `mode=ro` is correct; the old
  doc warned against `immutable=1` and that warning still applies if anyone
  tried it, but the current code uses `mode=ro` only.
- **Inline pre-write preview dialog.** The JSON-LD export modal shows item/photo
  statistics but does not enumerate rows or flag duplicates before writing.


## Known Limits

- **Selections (crops) are not read.** Tropy's `selections` table is not
  queried by either `tropy_db` or `tropy_jsonld`.
- **Existing notes are not read.** Neither module reads the `notes` table.
- **Write-back creates, never updates.** Re-exporting the same item with
  changed text and re-importing into Tropy adds a second Note rather than
  replacing the first. Edit or remove notes in Tropy.
- **Missing assets.** iCloud-backed projects may hold placeholder paths
  rather than files. Both modules mark missing photos and report them in the
  import preview. For JSON-LD imports the user can see which items are
  affected before enqueueing; for live browse the `missing` flag is surfaced
  in the items response.
- **Live browse requires Tropy to not be open** for write operations, because
  Tropy holds a write lock. Read operations get `SQLITE_BUSY` and ask the user
  to close Tropy. This is unavoidable for live read — it is why the
  JSON-LD file bridge is the default.
