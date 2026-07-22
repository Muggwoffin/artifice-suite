Handoff: Preview Tab Source-Image Pane + Editable Raw OCR Text
================================================================

Read this file before writing any code. It describes the exact state of the
project as of 2026-07-22, what to build, and the scope calls that need
confirming with the user before you start — this feature touches a shared
renderer used by two tabs, and it is easy to accidentally widen its blast
radius past what was asked for.


PROJECT STATE
--------------

Pipeline: OCR -> Cleanup -> Translate. Two frontends share the same core:
tkinter (`gui/`) and FastAPI + vanilla JS (`web/`). 166 tests currently pass
(`py -3.12 -m pytest tests/ -q`) — protect that number. No JS build step or
package.json exists; every `web/static/js/*.js` file is plain, dependency-free
JS loaded via `<script src>` tags in `index.html`. Follow that convention —
do not introduce a bundler or an npm dependency for this feature.

The Preview tab (`web/static/index.html`, `#panel-preview`) and the History
tab (`#panel-history`) both render their three-pane Raw/Cleaned/Translated
comparison through **one shared function**, `renderCompare(container, data)`
in `app.js`, writing into a `.compare-panes` grid (`app.css`, 3 equal columns).
Preview's data comes from `GET /api/queue/{id}/preview`
(`serialize_item_preview` in `runtime.py`, in-memory, live queue items only).
History's comes from a per-item detail endpoint reading the SQLite
`run_items` table (`serialize_history_item_detail`). This sharing is
deliberate — "one renderer, two sources, no drift" per `app.js`'s own comment
— and is exactly why this feature must be added carefully: **the image pane
and the editable textarea are Preview-only** per the user's request. Do not
let either leak into the History tab's rendering just because the code is
shared; see NON-NEGOTIABLE RULES.

Each queue item is a `JobItem` (`jobs.py`): `item.path` is the source file
(`.jpg .jpeg .png .tif .tiff .pdf`, see `SUPPORTED_EXTENSIONS`), `item.page` is
the 0-based PDF page index when the item is one page of a shared PDF (Tropy
items; see `docs/TROPY_INTEGRATION.md`), and `item.stem` is the output-file key
used everywhere on disk. Raw OCR output already lives at
`<output_dir>/raw_ocr/text/<stem>.txt` + a sibling
`<output_dir>/raw_ocr/json/<stem>.json` (see `stages/ocr.py`'s `perform()`,
lines ~160-190) — the JSON carries `extracted_text` plus provenance
(`source_file`, `engine`, `model`, `ocr_prompt`, `timestamp`, `page`,
`total_pages`). `RunState` (`web/runtime.py`) tracks the output dir of the
most recent run at `state.runner.output_dir` (or `cfg("output_dir")` if
nothing has run yet this session).

PyMuPDF (`fitz`) is already a **required** dependency (not optional) and can
open and rasterize `.pdf` pages *and* plain raster files including `.tif`.
`stages/ocr.py` already has `_pdf_single_page_image()` (renders one PDF page
to a temp PNG at 200 dpi) — that helper is OCR-specific (writes to a temp
file, expects the caller to delete it) and should not be reused as-is; write a
small, image-serving-specific equivalent instead (see WHAT TO BUILD, part A).
**Pillow is not a project dependency** — it's only used by the standalone
`scripts/make_icon.py`/`make_web_icon.py` icon generators. Do not add it for
this feature; `fitz.Pixmap` covers every format this app accepts as input.


THE FEATURE
------------

In the Preview tab only: add a source-image pane to the left of the existing
Raw/Cleaned/Translated panes, showing the actual scanned page the raw OCR text
came from, with the ability to zoom in close enough to check individual
words. Make the Raw OCR pane's text directly editable, so a user looking at a
blurry or ambiguous word in the image can correct the transcription right
there, without switching to a text editor and hunting for the file on disk.

This is a manual, human-directed correction — the user *is* the verifier.
Nothing here should invoke a model or touch `_guard.py`; that machinery exists
for *automated* stage output, which is a different trust problem (see
NON-NEGOTIABLE RULES).


WHAT TO BUILD
--------------

A) **Image-serving endpoint** — `web/runtime.py` (new function) +
   `web/server.py` (new route):

       GET /api/queue/{item_id}/image

   Resolve `item = state.get(item_id)` (404 if missing, matching the existing
   `/preview` endpoint's pattern). Then, based on `Path(item.path).suffix`:

     - `.jpg` / `.jpeg` / `.png`: these are natively browser-renderable —
       return them as-is via `FileResponse(item.path)`. Do not decode/re-encode;
       it's wasted work for the common case.
     - `.tif` / `.tiff`: browsers cannot render TIFF. Convert with
       `fitz.Pixmap(item.path)` then `.tobytes("png")`, and return via
       `Response(content=png_bytes, media_type="image/png")`.
     - `.pdf`: render the single page this item represents —
       `fitz.open(item.path)[item.page].get_pixmap(dpi=DPI)`, then
       `.tobytes("png")`. `item.page` is already 0-based and already the
       exact page this JobItem was OCR'd from — do not re-derive it, and do
       not render every page of the PDF (this is exactly the mistake
       `_pdf_single_page_image`'s own docstring warns against for a
       275-page Tropy item).

   Pick `DPI` higher than OCR's own 200 — this pane exists specifically so a
   user can zoom in past what's needed for machine OCR. 300 is a reasonable
   default; consider capping the long edge (e.g. ~3000px) so an oversized
   scan doesn't produce an unreasonably large PNG. No server-side caching is
   needed for v1: an `<img>` element only fetches its `src` once per load, so
   repeated zoom/pan on the client causes zero extra requests.

B) **CSS layout change, scoped to Preview only** — `app.css` +
   `index.html`. Do **not** change the shared `.compare-panes` rule (3 equal
   columns), since History uses that same class unmodified. Instead, give
   Preview's compare-card a modifier, e.g.:

       <div class="card compare-card compare-card--with-image">
         <div class="image-pane" id="preview-image-pane"> ... </div>
         <div class="compare-bar"> ... </div>
         <div class="compare-panes"> ... (unchanged, 3 columns) ... </div>
       </div>

   with a `.compare-card--with-image` rule in `app.css` that lays the new
   `.image-pane` and the existing `.compare-panes` side by side (CSS grid,
   something like `grid-template-columns: minmax(320px, 1fr) 2fr;`), leaving
   `.compare-panes` itself untouched so History's copy is unaffected. Match
   existing tokens (`--paper`, `--rule`, `--ink-soft`, etc. — see
   `app.css`'s `:root` block) rather than inventing new colors.

C) **Zoom/pan, vanilla JS, no new dependency** — new
   `web/static/js/preview_image.js` (own file, following `tropy.js`'s pattern
   of a self-contained module with its own `els` lookup), added to
   `index.html`'s script list next to `preview.js`. Structure:
   an outer `overflow: hidden` viewport `<div>` containing the `<img>`,
   transformed with `transform: translate(Xpx, Ypx) scale(S)`:

     - Mouse wheel over the image: zoom in/out, keeping the point under the
       cursor stationary (standard "zoom toward cursor" math — adjust the
       translate offset by the scale delta times the cursor's offset from the
       image's current transform origin).
     - Click-and-drag: pan (track pointer delta between `pointerdown` and
       `pointermove`, update translate).
     - Double-click (or a small "Reset" button): return to a fit-to-pane
       scale.
     - A minimal zoom-percentage readout is a nice-to-have; not required.

   Use Pointer Events (`pointerdown`/`pointermove`/`pointerup`), not
   deprecated mouse-event-only handling, so it also works with touch on a
   tablet without extra code.

D) **Editable Raw pane.** In `renderCompare()` (`app.js`), the raw pane is
   currently:

       el.innerHTML = highlightRanges(text, ranges);

   This must not change for History's raw pane (still read-only, still
   diff-highlighted). For Preview specifically, replace the raw pane's
   content with an editable control instead of highlighted `innerHTML` —
   simplest correct approach: a `<textarea>` holding the plain (unhighlighted)
   raw text, shown only in Preview's copy of the raw pane. This does mean
   Preview's raw pane temporarily loses the diff-highlight marks against
   cleaned text while it is the editable one — that's an acceptable, honest
   trade (you can't both edit plain text in a textarea and show inline
   `<mark>` highlighting in the same control without a contenteditable div and
   considerably more complexity). Confirm this trade-off with the user if you
   want to instead attempt a `contenteditable` div that preserves highlight
   marks — more work, and editing inside highlighted spans is fiddlier to get
   right (caret placement, paste stripping marks, etc.) — but flag it as an
   option rather than silently picking the harder path.

   Add a small save affordance near the raw pane header (a "Save correction"
   button, enabled only when the textarea's content differs from what was
   loaded — track a simple dirty flag) plus a `Ctrl+S`/`Cmd+S` keyboard
   shortcut scoped to the textarea. Do **not** autosave on every keystroke —
   that would hammer disk I/O on every character (see part E) for no benefit,
   since a scan-correction session is a deliberate, occasional action, not a
   live-typing document.

E) **Save endpoint** — `web/runtime.py` + `web/server.py`:

       POST /api/queue/{item_id}/raw-text
       body: {"text": "<corrected text>"}

   1. `item = state.get(item_id)` — 404 if missing.
   2. Update in-memory: `item.results.setdefault("raw", {})["extracted_text"]
      = req.text`. This is what makes the correction visible immediately if
      the item is later included in a Tropy write-back or a subsequent
      cleanup/translate run (which read from `item.results["raw"]`, per
      `jobs.py`'s `_phase_cleanup`).
   3. Persist to disk, if a run has actually produced output for this stem:
      resolve `output_dir = state.runner.output_dir if state.runner else
      cfg("output_dir")`, then check whether
      `<output_dir>/raw_ocr/text/<item.stem>.txt` exists. If it does:
        - Overwrite that `.txt` file with the corrected text.
        - Load the sibling `.json`, update only its `extracted_text` field,
          and add `"edited": true` + `"edited_at": <ISO timestamp>` — do
          **not** touch `engine`/`model`/`ocr_prompt`/`timestamp`, which
          record what the *original* OCR pass actually did. Silently
          rewriting those to look like the model produced the corrected text
          would be dishonest provenance — same principle `_guard.py`'s
          docstring argues for automated corrections, applies just as much to
          manual ones.
      If no on-disk output exists yet (item added to the queue but never
      run), only update the in-memory copy — this is not an error condition,
      just nothing to persist yet.
   4. Return the same shape `serialize_item_preview()` produces (recomputed
      diff ranges included), so the client can re-render all three panes in
      one round-trip rather than issuing a second GET.

   Client-side (`preview.js`): on successful save, re-render the
   Raw/Cleaned/Translated panes from the response (refreshes the diff
   highlighting in the Cleaned pane against the now-corrected Raw text) and
   clear the dirty flag.


NON-NEGOTIABLE RULES
---------------------

- Do not add the image pane or the editable textarea to the History tab.
  `.compare-panes` and `renderCompare()` are shared — change only what's
  additive and clearly scoped to Preview (see part B/D). If you find yourself
  editing `.compare-panes` itself or `renderCompare()`'s raw-pane branch
  unconditionally, stop — you're about to change History's behavior too.
- Do not call `_guard.check()`/`_guard.apply()` or invoke any model for this
  feature. A user manually correcting a word they can see with their own eyes
  in the zoomed image is not the same trust problem the guard exists for —
  don't bolt on unrelated verification machinery.
- Never overwrite `cleaned/` or `translated/` output from this feature —
  only `raw_ocr/text/<stem>.txt` and `raw_ocr/json/<stem>.json`, and only
  the `extracted_text` field (+ new `edited`/`edited_at`) of the JSON.
  Leave every other provenance field in the JSON untouched.
- Do not add Pillow as a dependency. `fitz` already handles every raster
  format this app accepts as input (`SUPPORTED_EXTENSIONS`); use it for the
  TIFF→PNG conversion in part A.
- Do not render every page of a multi-page PDF when serving the image for one
  `JobItem` — `item.page` already identifies the single page. Rendering the
  whole document for one preview request is the exact waste
  `_pdf_single_page_image`'s docstring already warns about.
- No new JS dependency, no bundler, no `package.json`. Match the existing
  vanilla-JS, `<script src>`-per-file convention.
- Scope editing to the **Raw OCR** pane only, per the user's request. Do not
  also make Cleaned/Translated editable in this pass — that's a materially
  different feature (editing model output, not correcting a transcription
  against source) and should be its own decision if wanted later.
- Scope this feature to **live queue items only** (the same "in-memory only"
  boundary `/api/queue/{id}/preview` already documents in its own docstring).
  Do not extend editing to completed runs in the History tab/SQLite
  `run_items` table in this pass — that's a real feature (retroactively
  correcting historical, already-archived runs) with its own questions
  (should it rewrite history rows? does that break provenance/audit trail for
  a run that's supposed to be a record of what happened?) that the user
  should decide explicitly, not inherit as a side effect of this change.
- Run `py -3.12 -m pytest tests/ -q` before and after; keep it at 166 passed
  or higher. Use `py -3.12` explicitly — `python` on PATH is 3.14 and lacks
  the project's dependencies.
- Any new test that touches `config.save_user_settings()`/
  `load_user_settings()` (unlikely for this feature, but if you end up near
  `output_dir` resolution) must `monkeypatch.setattr(config,
  "_SETTINGS_PATH", tmp_path / "settings.json")` first — see
  `tests/test_web.py`'s `client` fixture for the pattern.


SCOPE CALLS TO CONFIRM WITH THE USER (don't assume)
-----------------------------------------------------

1. **Textarea vs. contenteditable for the raw pane** (part D) — textarea is
   simpler and loses inline diff-highlighting while editing; contenteditable
   preserves highlighting but is meaningfully more work and fiddlier to get
   right. Recommendation: start with the textarea.
2. **Render DPI / max dimension for the image pane** (part A) — 300 dpi with
   a ~3000px long-edge cap is a reasonable starting point; the user may want
   it higher if their scans have genuinely tiny handwriting that needs more
   resolution to read even at max zoom.
3. **Whether to extend this to the History tab later** — flagged above as
   explicitly out of scope for this pass, but worth surfacing as a likely
   next ask once this ships, since the underlying data (source_file column
   already exists in `run_items`) is already there.


FILES TO CHANGE
-----------------

  File                                          Action
  --------------------------------------------  ---------------------------
  src/ocr_pipeline/web/runtime.py                Add image-render helper +
                                                  raw-text save logic
  src/ocr_pipeline/web/server.py                 Add GET .../image and
                                                  POST .../raw-text routes
  src/ocr_pipeline/web/static/index.html         Preview markup: image pane,
                                                  script tag for new JS file
  src/ocr_pipeline/web/static/css/app.css        .compare-card--with-image,
                                                  .image-pane, zoom viewport
  src/ocr_pipeline/web/static/js/preview_image.js New — zoom/pan module
  src/ocr_pipeline/web/static/js/preview.js      Wire save button, dirty
                                                  flag, re-render on save
  src/ocr_pipeline/web/static/js/app.js          renderCompare(): Preview-only
                                                  branch for editable raw pane
  tests/test_web.py                              New tests (see below)


VALIDATION COMMANDS
---------------------

  py -3.12 -m pytest tests/ -q                          # baseline: 166 passed
  py -3.12 -m pytest tests/test_web.py -v -k "image or raw_text"

  # Manual smoke test once wired up:
  py -3.12 launch_ocr_pipeline_web.pyw --browser
  # -> add a real file from output/cleaned/text/Fritz Eberhard KV/ or any
  #    source scan you have, run it, open Preview, confirm the image loads,
  #    zooms, pans, and a raw-text edit survives a page reload.

Cover in `tests/test_web.py` at minimum:
  - `GET /api/queue/{id}/image` returns `image/png` for a `.tif` source
    (conversion path) and passes a `.jpg` through unchanged.
  - `GET /api/queue/{id}/image` for a PDF-page item renders only the one
    page `item.page` points at (assert on returned pixmap dimensions or page
    count, not just "it returns 200").
  - `GET /api/queue/{id}/image` 404s for an unknown item id.
  - `POST /api/queue/{id}/raw-text` updates `item.results["raw"]
    ["extracted_text"]` in memory even when no on-disk output exists yet.
  - Same endpoint, when `raw_ocr/text/<stem>.txt` already exists (build via a
    real or fake prior run in a `tmp_path`), overwrites the `.txt` and updates
    only `extracted_text`/`edited`/`edited_at` in the `.json`, leaving
    `engine`/`model`/`ocr_prompt`/`timestamp`/`source_file` untouched.
  - Saving does not write anywhere under `cleaned/` or `translated/`.


END OF HANDOFF
