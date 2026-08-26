Handoff: Source-Image Pane in the Web UI's History Tab
=======================================================

Read this before writing code. It records why the History image pane in the
**web** frontend "isn't loading" (diagnosis), and the plan to build it. Dated
2026-07-22.


THE REPORT
-----------

"The image pane is not loading in the History view on the Web UI."


DIAGNOSIS — it was never built there
-------------------------------------

There is nothing broken to repair: the web History view has **no image pane at
all**. The source-scan pane exists only in the web **Preview** tab. It was
deliberately scoped to Preview in the original build (see
`HANDOFF_PREVIEW_IMAGE_EDIT.md`, "NON-NEGOTIABLE RULES" — "Do not add the image
pane or the editable textarea to the History tab").

The expectation almost certainly comes from the **desktop (tkinter) build**,
whose History tab *did* recently gain a source-image pane + editable raw
correction (`gui/widgets/image_pane.py`, `gui/widgets/compare_view.py`'s
`with_image`/`editable_raw` options, wired in `gui/views/history_view.py`). The
web build's History tab never received the equivalent, so the two frontends are
now out of parity.

Concretely, four independent gaps mean no image can appear in web History:

1. **No markup.** `web/static/index.html` — the Preview panel (line ~105) is
   `<div class="card compare-card compare-card--with-image">` and contains
   `<div class="image-pane">…<img id="preview-image">…`. The History panel
   (line ~177) is a plain `<div class="card compare-card">` with only the
   `.compare-panes` 3-column grid. No image element exists to populate.

2. **No backend route for history images.** The only image route is
   `GET /api/queue/{item_id}/image` (`web/routers/queue.py`). It resolves
   `state.get(item_id)` — a **live, in-memory `JobItem`** keyed by `id(item)`.
   A History item is a **SQLite row** keyed by its `item_id` primary key; it is
   not in the live queue, so that route can't serve it. There is no
   `/api/history/items/{id}/image` equivalent.

3. **The detail serializer doesn't emit what a client would need.**
   `serialize_history_item_detail` (`web/serializers.py`) returns `source_file`
   but no image URL and no `page`. `history.js`'s `selectItem()` calls
   `renderCompare(container, {...})` with title/raw/cleaned/translated only —
   `renderCompare` itself (`app.js`) has *no* image handling; the image is
   driven entirely separately by `preview.js` calling
   `window.PreviewImage.load(...)`.

4. **`PreviewImage` is a hardcoded singleton.** `web/static/js/preview_image.js`
   binds by fixed element IDs — `getElementById("image-viewport")`,
   `"preview-image"`, `"image-empty"`, `"btn-image-reset"`,
   `"image-zoom-readout"`. It cannot drive a second image pane in another panel
   without being generalised. The CSS is also partly ID-bound: `#preview-image`
   is an ID selector (`app.css` ~581), though `.compare-card--with-image`,
   `.image-pane`, `.image-viewport`, `.image-empty` are all reusable classes.


THE CRITICAL DATA CAVEAT (read this — it changes the plan)
-----------------------------------------------------------

A naive "render `source_file` at page `page`" route would show the **wrong
image** for the overwhelming majority of existing history, confidently.

Measured against the real DB (`~/.ocr_pipeline/history.db`, 239,271 rows):

  - **221,585 rows (93%) have a `.pdf` `source_file`** — these are Tropy items,
    where *many pages share one PDF path* (one asset PDF, 113 distinct
    page-items in the largest single case).
  - **`page` is NULL for 100% of existing rows.** The `page` column was only
    added in the recent schema migration and is populated by `record_item`
    **only for runs recorded from now on**. Every historical row predates it.

So `render_page_image(source_file, page or 0)` renders **page 0 of the shared
PDF for every page-item of that PDF** — e.g. page 1 of a 200-page Tropy asset
shown identically for documents that were actually pages 3, 4, 5…

**The page index is recoverable, though.** The `name` column already encodes a
1-based page label:

    name = "Eberhard KV 3.pdf  p.3"   ->  page label 3  ->  page_index = 2

A `p\.(\d+)\s*$` match on `name` recovers it. Plain single-image items (jpg/
png/tif) have no `p.N` suffix and don't need one. **The route must prefer the
`page` column when present and fall back to parsing `name`**, or it will serve
wrong pages for all existing Tropy history.


WHAT TO BUILD
--------------

A) **History image route** — `web/routers/history.py` (+ a render helper).

       GET /api/history/items/{item_id}/image

   Steps:
     1. `row = state.history.get_item(item_id)`; 404 if None (mirror the
        existing `history_item_detail` pattern).
     2. Resolve the page index:
          - if `row["page"]` is not None, use it;
          - else parse `p\.(\d+)` from `row["name"]` and subtract 1;
          - else 0.
     3. `source = row["source_file"]`. If the file no longer exists on disk
        (Tropy projects move; history outlives them), return **404**, not 500 —
        the client already has an `onerror` fallback ("(image unavailable)").
     4. Dispatch on suffix exactly like `queue_item_image`:
          - `.jpg/.jpeg/.png` -> `FileResponse(source, media_type=…)`
            (browser-native, no re-encode);
          - `.tif/.tiff` / `.pdf` -> PNG bytes via the render helper below,
            `Response(content=…, media_type="image/png")`.

   Refactor `render_page_image` (`web/runtime.py`) so the PDF/TIFF rendering is
   callable **without a `JobItem`** — it currently takes `item` and reads
   `item.path`/`item.page`. Extract a `render_page_image_from(path: str,
   page: int | None) -> bytes` core and have the existing
   `render_page_image(item)` delegate to it (`item.path`, `item.page`). Keep
   the DPI cap logic (`IMAGE_DPI`, `IMAGE_MAX_LONG_EDGE`) unchanged. Do **not**
   render the whole PDF — one page only, same waste warning as everywhere else
   in this codebase.

B) **Emit `page` (and keep `source_file`) in the detail payload** —
   `serialize_history_item_detail` (`web/serializers.py`). Add `page` so the
   client and any future consumer can see it; the image URL itself is
   constructible client-side from `item_id`, so it need not be in the payload,
   but exposing `page` keeps the serializer honest about what's known.

C) **Generalise the image viewport module** — `web/static/js/preview_image.js`.
   Two options; pick one and note it:
     - *Preferred:* turn the IIFE singleton into a small factory
       `createImageViewport(ids)` (or accept a root element) so it can bind a
       second set of elements, then instantiate one for Preview
       (`window.PreviewImage`) and one for History (`window.HistoryImage`).
       Generalise the `#preview-image` CSS selector to a shared class
       (e.g. `.source-image`) applied to both `<img>`s.
     - *Simpler but lower-quality:* a second near-duplicate module bound to
       History's IDs. Discouraged — it duplicates the pan/zoom math the desktop
       build already had to keep in one place.

D) **History panel markup** — `web/static/index.html`. Give the History
   `.compare-card` the `compare-card--with-image` modifier and add an
   `.image-pane` block mirroring Preview's (viewport, `<img>`, empty-state
   element, Reset button, zoom readout) with History-specific IDs (or a shared
   class per option C). The `.compare-card--with-image` grid rule is already
   generic (`app.css` ~546) and needs no change; only `#preview-image`'s ID
   selector needs generalising if you share styling.

E) **Wire History selection to the image** — `web/static/js/history.js`.
   In `selectItem()`, after `renderCompare(...)`, call the History viewport's
   `.load('/api/history/items/${id}/image')`. In `renderItems()`/`refresh()`
   where `clearCompare(...)` runs, also clear the History image
   (`.clear()`), so switching runs/items doesn't leave a stale scan.

F) **Tests** — `tests/test_web.py` (has the `client` fixture pattern; note its
   `monkeypatch.setattr(config, "_SETTINGS_PATH", …)` requirement). Cover:
     - `GET /api/history/items/{id}/image` returns `image/png` for a `.pdf`
       source and renders the **page parsed from `name`** when the `page`
       column is NULL (assert on pixmap dimensions or that two different
       `p.N` items yield different bytes — this is the regression that proves
       the wrong-page bug is fixed).
     - honours the `page` column when it *is* populated (page column beats the
       name parse).
     - passes a `.jpg` through unchanged.
     - 404 for an unknown item id, and 404 (not 500) when `source_file` no
       longer exists on disk.
     - `serialize_history_item_detail` includes `page`.

   Run `py -3.12 -m pytest tests/ -q` before and after — baseline is **246
   passed**; keep it there or higher. Use `py -3.12` explicitly (the `python`
   on PATH is 3.14 and lacks the project's deps).


SCOPE CALLS TO CONFIRM (don't assume)
--------------------------------------

1. **Editable raw correction too, or image only?** The desktop History tab got
   *both* image pane and an editable Raw-OCR "Save correction" surface (writing
   via `HistoryStore.update_raw_text`, a route the web build would also need:
   `POST /api/history/items/{id}/raw-text`). The report only names the image
   pane. Recommend shipping **image-only** first (this handoff), and treating
   editable History raw text as a separate follow-up so the web matches the
   desktop fully. Flag, don't silently do both.

2. **Backfill the `page` column, or parse `name` at request time?** Parsing
   `name` per-request (part A) needs no migration and fixes all existing rows
   immediately — recommended. A one-off backfill UPDATE (regex `name` ->
   `page`) is optional polish, not required, and touches 200k+ real rows, so
   leave it out of v1 unless asked.


FILES TO CHANGE
----------------

  File                                       Action
  -----------------------------------------  ---------------------------------
  src/ocr_pipeline/web/runtime.py            Extract render-from-(path,page)
  src/ocr_pipeline/web/routers/history.py    New GET …/{id}/image route
  src/ocr_pipeline/web/serializers.py        Add `page` to detail payload
  src/ocr_pipeline/web/static/index.html     History image-pane markup
  src/ocr_pipeline/web/static/css/app.css    Generalise #preview-image selector
  src/ocr_pipeline/web/static/js/preview_image.js  Factory / second instance
  src/ocr_pipeline/web/static/js/history.js  Load/clear the History image
  tests/test_web.py                          New tests (see part F)


VERIFY LIVE
------------

  py -3.12 -m pytest tests/ -q                       # baseline 246 passed
  py -3.12 -m pytest tests/test_web.py -v -k image

  # Manual: launch the web build, open History, pick a run whose items are
  # Tropy PDF pages, and confirm consecutive p.N items show *different* pages
  # (the wrong-page regression), that zoom/pan works, and that an item whose
  # source_file was moved shows "(image unavailable)" rather than erroring.


END OF HANDOFF
