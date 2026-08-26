# Design: make Tropy write-back reachable by a user

**Date:** 2026-08-26
**App:** `apps/artifice-ocr`
**Status:** approved, ready for delegation

## The problem

`apps/artifice-ocr/src/artifice_ocr/tropy_write.py` landed in `eba87a2` and is complete and
tested. Its own commit message states the gap plainly:

> It is opt-in and default off (`tropy_writeback_enabled`), and nothing wires it to a route, a
> stage, or a button. The module is defined and tested but cannot yet be triggered by a user.

Today OCR results leave the app only as a JSON-LD file the user must import by hand in Tropy. The
module that writes them straight back into the project exists and cannot be reached.

This project wires it to two routes and one UI control. It adds no capability to the module.

## Verified starting state

Everything below was read from the tree at `735b713`, not assumed.

| Fact | Where |
|---|---|
| Gate `tropy_writeback_enabled`, default `False`, already persisted | `config.py:47`, `config.py:145` |
| `TropyWriter(project_path)` → `.blockers()`, `.backup()`, `.preview(entries, targets)`, `.write(preview, make_backup=True)` | `tropy_write.py:271-470` |
| `Preview.counts()`, `.summary()`, `.insertable()` | `tropy_write.py:109-133` |
| `WriteReport` carries `written` and `errors` | `tropy_write.py:134-141` |
| `entries_from_items(items, stage=...)` builds entries from `JobItem`s | `tropy_write.py:531-566` |
| `TARGET_NOTES = "notes"`, `TARGET_TRANSCRIPTIONS = "transcriptions"` | `tropy_write.py:68-70` |
| Export route reads items via `state.tropy_eligible_items(item_ids)` | `tropy_bridge.py:137-163` |
| Audited project-path resolver: `validate_directory` + `resolve_project_db_path` | `tropy_browse.py:59-64` |
| Send-to-Tropy modal, stat tiles and stage selector | `web/templates/index.html:613-646` |
| Modal controller `openTropyExport()` / `closeTropyExport()` | `web/static/js/tropy.js:821-883` |

**The load-bearing constraint:** `entries_from_items` skips any item without
`source.photo_id`. Only photos that came *from* Tropy can be written back to Tropy. The UI must
say so rather than silently writing nothing.

## Decisions

Settled with the maintainer before this document was written.

1. **Entry point** — a Destination control inside the existing Send to Tropy modal, not a new
   panel. `Save a JSON-LD file` (today's behaviour, stays default) vs `Write into the Tropy
   project`. It reuses the stage selector, stat tiles and status line already there.
2. **Two-step confirm** — preview, then an explicit write. The module already returns counts,
   a summary and blockers; a one-click write would compute all of it and throw it away.
3. **Notes only** — `TARGET_NOTES`. `transcriptions` stays unexposed until the flow is proven.
4. **Two sequential briefs** — routes first, then UI, so the UI brief can cite a working API.

## Architecture

```
tropy.js  ──POST /api/tropy/writeback/preview──▶  tropy_writeback.py
   │                                                     │
   │            ◀── counts, summary, blockers ───────────┤ TropyWriter.preview()
   │                                                     │
   │  (user reads the preview, presses Write)            │
   │                                                     │
   └──POST /api/tropy/writeback/commit──────────▶        │ TropyWriter.write()
                ◀── written, skipped, errors ────────────┘   (backup first)
```

A **new router module** `web/routers/tropy_writeback.py`, not an addition to `tropy_bridge.py`.
The bridge module is already 300+ lines across five routes covering import and export; a mutating
path deserves its own file, its own tests, and a boundary a reviewer can hold in their head.

### Routes

Both routes are gated. When `tropy_writeback_enabled` is false they return **404**, matching the
precedent `tropy_browse._check_enabled()` sets for a disabled feature — an off feature should not
advertise itself.

**`POST /api/tropy/writeback/preview`**

Request: `{ project_path: str | null, stage: str, item_ids: list[str] | null }`
Response: `{ blockers: [...], counts: {...}, summary: str, eligible: int, ineligible: int }`

`project_path` falls back to `config["tropy_last_path"]` when null. It is resolved with the same
`validate_directory` + `resolve_project_db_path` pair `tropy_browse` uses — not a second spelling
of that logic.

`eligible` / `ineligible` split the selected items by whether they carry `source.photo_id`, so
the UI can state "12 of 20 photos came from Tropy" rather than reporting an empty write as
success.

**`POST /api/tropy/writeback/commit`**

Request: as above, plus `expected_write_count: int` from the preview.
Response: `{ written: int, skipped: int, errors: [...], backup_path: str | null }`

**The commit route re-runs `preview()` server-side and never trusts a preview sent by the
client.** If the recomputed insertable count differs from `expected_write_count`, it returns
**409** and writes nothing — the project changed between preview and commit, and the user should
look again. This is the whole point of a two-step flow; skipping it would make the preview
decorative.

Blockers are re-checked at commit. A non-empty blocker list is **409**, never a partial write.

### Errors

`WriteReport.errors` is already sanitised through `_sanitise_error`, and `blockers()` through
`_display_path`. **The route must pass these strings through unchanged** — no re-wrapping in an
f-string that re-introduces the raw exception, which is exactly the leak the redaction exists to
prevent. `tests/test_tropy_write.py:695-752` guards the module; the route needs its own guard.

### UI

The Destination control is a radio pair, defaulting to `Save a JSON-LD file`. Choosing
`Write into the Tropy project` swaps the modal's footer into the two-step flow and reveals a
warning line: this modifies the project, and a timestamped backup is taken first.

States to render, all of which the API already returns:

- **Blocked** — Tropy is running, the database is locked, or it is not writable. Write button
  disabled, blocker text shown verbatim.
- **Nothing to write** — no selected item carries a `photo_id`. Explain that write-back applies
  only to photos imported from Tropy.
- **Ready** — "41 notes will be written, 7 skipped as already present". Write button enabled and
  labelled with the count.
- **Written** — the report, plus the backup location.
- **Failed** — errors verbatim; state that the write was rolled back.

The Destination control is hidden entirely when `tropy_writeback_enabled` is false, so the
default install is visually unchanged.

## Testing

Route tests in `apps/artifice-ocr/tests/test_tropy_writeback.py`, against a fixture project built
the way `test_tropy_write.py:93` builds one:

- gate off → both routes 404
- gate on, blockers present → commit 409, database unmodified
- `expected_write_count` mismatch → 409, database unmodified
- happy path → notes present in the DB afterwards, each carrying the ProseMirror `selection` key
- items without `photo_id` → reported as ineligible, not silently dropped
- an error path asserts no absolute path appears in the response body

That last one matters because the redaction bug fixed in this same PR was invisible on POSIX and
only failed on Windows. A route test that asserts on response *content* rather than status is the
cheap version of that lesson.

## Out of scope

- `TARGET_TRANSCRIPTIONS` — the module supports it; the UI will not expose it yet.
- `repair_missing_selections()` — a maintenance path, not part of the write flow.
- Writing from history rows. Queue items only; history export already has its own route and
  adding a second source doubles the states before the first one is proven.
- Any change to `tropy_write.py` itself. If a route needs something the module does not offer,
  that is a finding to report, not a change to make.
