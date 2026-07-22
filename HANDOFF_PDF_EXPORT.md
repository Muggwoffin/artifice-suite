Handoff: Full-Folder Transcription → Readable PDF Export
==========================================================

Read this file before writing any code. It describes the exact state of the
project as of 2026-07-22, what you need to build, and the rules that keep this
feature from becoming the next thing that quietly corrupts archival text —
which has already happened once in this project (see NON-NEGOTIABLE RULES).


PROJECT STATE
--------------

Pipeline: OCR -> Cleanup -> Translate, each stage a module under
`src/ocr_pipeline/stages/`, orchestrated by `pipeline.py`
(`run_ocr_step`/`run_cleanup_step`/`run_translate_step`) and, for batches with
live progress, `jobs.py`'s `JobRunner`. Two complete frontends consume the same
core: a tkinter app (`gui/`) and a FastAPI + vanilla-JS app (`web/`). 164 tests
currently pass (`py -3.12 -m pytest tests/ -q`) — protect that number.

Every stage writes to `<output_dir>/<stage>/text/<stem>.txt` (+ a sibling
`json/<stem>.json` with metadata). `<stem>` is usually a filename, but for
documents pulled from Tropy (`tropy.py`) it is `<Item Title>/<file>_p0003`
(zero-padded to 4 digits) — one subfolder per Tropy item, one file per page.
`tropy_manifest.json`, written at the output root, maps every such stem back
to its `photo_id`/`item_id`/`item_title`/`page_number` — see
`docs/TROPY_INTEGRATION.md` for the full schema.

Real example data already in this repo (from prior sessions — use it for
smoke tests, no OCR run required):

    output/cleaned/text/Fritz Eberhard KV/                    1 page
    output/cleaned/text/Ernest and Walter Lowenheim KV File/   2 pages
    output/cleaned/text/ISK Comms with Switzerland Part I/     4 pages (JPEGs;
                                                                filenames are
                                                                the original
                                                                IMG_NNNN.jpg
                                                                names, no
                                                                page suffix)

`output/tropy_manifest.json` at the repo root has real entries for these.

The cleanup stage (`stages/cleanup.py`) already has a content-preservation
guard (`_guard.py`): it compares the model's output against the source and
rejects (falls back to the source) if words were deleted, the text shrank, a
proper noun changed, or accents appeared that weren't in the source. That
guard was tuned against a 130-page audit of real archival OCR — read the
module docstring before touching it. **Do not weaken or reuse it as-is for
this feature** — see below, its tolerances are wrong for this job.


THE FEATURE
------------

Take everything already transcribed in one folder — one Tropy item's pages,
or any folder of processed `.txt` output — and produce **one continuous,
readable PDF** of the whole thing: a clean reading copy of a 275-page KV file,
not 275 separate scans.

A model pass (reuse `cfg("cleanup_model")` — the user's own framing is "the
cleanup model structures it") adds *reading* structure: paragraph breaks,
plausibly a heading where a letter's salutation/date block sits, sensible
flow. It must not change a single word. This is not the existing cleanup
stage's job (that repairs OCR letter-errors) and it is not a rewrite — it is
pure re-flow of text that is already considered final.


WHAT TO BUILD
--------------

A) `prompts/structure_prompt.txt` — new file, following the existing
   `SYSTEM_PROMPT:` + `{text}`-placeholder convention used by
   `prompts/cleanup_prompt.txt`. The brief must be at least as strict as that
   file's, because this job has *zero* tolerance where cleanup has some:

     - Only insert paragraph breaks, blank lines, and (optionally) a short
       heading line copied verbatim from the text itself (e.g. a date already
       present). Never insert a word that was not there.
     - Never delete, reorder, translate, correct, or modernise anything.
     - Never merge or split words. Whitespace and line breaks are the only
       thing you may add.
     - If you are unsure how to structure a passage, leave it as one
       paragraph. Do not guess at meaning to decide where a break belongs.

   Register it in `_prompts.py` alongside `_CLEANUP_PROMPTS`/
   `_TRANSLATION_PROMPTS`: a `_STRUCTURE_PROMPTS` dict (at minimum a
   `"default"` entry) and a `get_structure_prompt(doc_type)` function mirroring
   `get_cleanup_prompt`.

B) A **new, stricter** guard. `_guard.check()` deliberately tolerates
   letter-level fixes (`rn`->`m`, hyphen rejoining) — exactly what you do not
   want here, since this stage's input is already-finished text. Do not call
   `_guard.check()`/`_guard.apply()` for this feature. Add a new function,
   e.g. `_guard.check_structure_only(original, structured) -> bool`, that
   strips all whitespace from both strings and requires exact equality (or
   compares the word sequence with a whitespace-insensitive join — same
   effect, pick whichever reads clearer). On failure: keep the original text,
   completely unstructured, rather than a half-trusted rewrite. Put this next
   to `check()` in `_guard.py` rather than in a new module — it is the same
   concern (never trust a content-preservation claim without verifying it),
   and the module docstring already explains why that discipline exists here.

   Write this test first, against the model, before building anything else:
   feed the real text in `output/cleaned/text/Fritz Eberhard KV/Eberhard KV
   3_p0002.txt` through `cfg("cleanup_model")` with your new prompt and
   `think=False` (same throughput lesson as the cleanup stage — see
   `README.md`'s "Why cleanup is fast" section), and confirm your guard
   actually catches it if the model "helpfully" fixes a typo. Do not assume a
   strict prompt is sufficient by itself; the cleanup stage's own history in
   this repo is a worked example of a strict-sounding prompt not being enough
   on its own.

C) `src/ocr_pipeline/stages/structure.py` — new stage module, same shape as
   `stages/cleanup.py`: `perform(text, *, output_dir="output", stem=None) ->
   dict`, using `_llm.chat(ollama.chat, ..., think=cfg("ollama_think"))` and
   `_chunking.py`'s `chunk_text`/`reassemble` if a single page's text is long
   (reuse, don't reinvent — same functions `cleanup.py` uses). Apply
   `check_structure_only()` from (B); on rejection, keep the unstructured
   input verbatim (do **not** fall back to a heuristic paragraph-splitter that
   invents its own breaks — for this stage "untouched" is the only honest
   fallback, since even a heuristic reflow is an edit you did not verify).
   Write output to `<output_dir>/structured/text/<stem>.txt` +
   `structured/json/<stem>.json`, following the exact directory convention
   every other stage uses, including a `guard` field in the JSON like
   `cleanup.py` does. Respect `resume`: skip re-processing a stem whose
   `structured/text/<stem>.txt` already exists, same pattern as
   `_output_exists()` in `pipeline.py`.

   Scope call for you to confirm with the user, not assume: whether this
   becomes a first-class pipeline stage (added to `jobs.STAGES`, wired through
   `pipeline.run_structure_step`, getting pause/skip/resume and GUI/Web
   checkboxes for free) or a simpler standalone loop invoked only from the PDF
   export path in (D), with its own resumability but no `JobRunner`
   integration. The first is more consistent with the rest of the app and
   worth it if folks will often export very large items (275 pages is a real
   example in this archive) and want to watch progress or pause midway. The
   second is less code and lower risk. Recommendation: start with the second
   for a first working version, and only take on `JobRunner` integration if
   the user actually wants live progress for large exports.

D) `src/ocr_pipeline/pdf_export.py` — new module:

   - `collect_folder(folder, *, stage="cleaned", manifest_path=None) ->
     list[PageText]` (a small dataclass: `label`, `text`, `source_path`).
     Ordering priority:
       1. If a `tropy_manifest.json` exists at the output root (check the
          folder's parent chain, or accept an explicit `--manifest` path),
          use its `page_number`/`item_title` to order and label pages
          authoritatively — this is the correct source of truth, not
          filename parsing.
       2. Otherwise, natural-sort the `.txt` filenames (so `page2` sorts
          before `page10`) and use the filename as the label. Note: Tropy's
          own PDF-page filenames are already zero-padded (`_p0001`), so plain
          lexicographic sort happens to already work for those — natural
          sort is for robustness with arbitrarily-named non-Tropy folders,
          not a bug fix for Tropy output.
     `stage` selects which processed text to read for each page —
     "cleaned", "raw_ocr", or "translated" — mirroring the exact fallback
     order already used in `tropy_write.entries_from_items()` (translated >
     cleaned > raw_ocr, falling back to whatever the page actually has).
     Reuse that ordering logic rather than re-deriving it; it is a config
     decision worth keeping in one place.

   - `structure_pages(pages) -> list[PageText]` — calls
     `stages.structure.perform()` per page (or your standalone loop from C),
     logging progress (`log.info("structuring %d/%d", i, n)`), so a long
     compile is not silent.

   - `render_pdf(pages, output_path, *, title=None) -> Path` — lays out a
     continuous, book-like reading document: an optional title page (use the
     Tropy item title when a manifest is present), then flowing paragraphs
     for every page in order, each carrying a small, unobtrusive provenance
     marker (page label — e.g. filename + page number) so a reader can always
     trace a passage back to its source scan, without breaking the reading
     flow into disconnected fragments. **Confirm this "continuous flow" design
     with the user before building it** — the alternative (one rigid PDF page
     per source scan) is equally valid and changes the whole character of the
     output; the user's phrasing ("readable... structures it neatly for
     reading") reads to me as continuous-flow, but it's their call.

     Recommended library: add `reportlab` (pure Python, no system
     dependencies, this project has none of reportlab's GTK-style install
     pain) and use its Platypus layer (`SimpleDocTemplate` + `Paragraph` +
     `PageBreak` flowables) — it handles pagination, headers and font
     embedding for you. A no-new-dependency alternative exists:
     `fitz.Page.insert_textbox()` (PyMuPDF is already a dependency) does
     word-wrapping inside a rect and reports whether it overflowed, but you
     would have to implement pagination (measuring and creating new pages)
     by hand. Recommend `reportlab` unless there's a reason to avoid a new
     dependency.

     If you want the output to look like the rest of this project's design
     work: the desktop/web frontends' palette and type choices come from
     [public_history](https://github.com/Muggwoffin/public_history) (see
     `src/ocr_pipeline/gui/theme.py` and `web/static/css/app.css` for the
     exact tokens — ink `#1b1813`, paper `#f6f3ea`, Playfair Display for
     headings, Libre Baskerville for body text). Embedding those two fonts in
     the PDF (register with `reportlab.pdfmetrics.registerFont`) would make
     the export visually consistent with the rest of the app, but the font
     `.ttf` files are not currently vendored anywhere in this repo — you would
     need to fetch and bundle them (e.g. under `assets/fonts/`) or fall back
     to reportlab's built-in Times-Roman. Treat this as a nice-to-have, not a
     blocker — a correct plain-serif PDF beats a broken fancy one.

E) CLI command in `cli.py`, following the existing `@app.command()` pattern
   (see the `tropy` command for a similar "point at something, process a
   batch, print a summary" shape):

       ocr_pipeline compile-pdf <folder> [--stage cleaned|raw_ocr|translated]
                                         [--output OUT.pdf] [--no-structure]

   `--no-structure` skips step (C) entirely and just concatenates the chosen
   stage's text as-is — useful for a quick sanity check that ordering/layout
   work before trusting the model pass.

F) `tests/test_pdf_export.py` — follow this repo's conventions (see
   `test_guard.py` for the "assert against a known real failure mode" style,
   `test_tropy_write.py` for building a synthetic fixture folder). Cover, at
   minimum:
     - `check_structure_only()` rejects a completion that changed a word,
       accepts one that only added blank lines.
     - `structure.perform()` respects `resume` (second call is a no-op) and
       falls back to the untouched input on guard rejection.
     - `collect_folder()` orders correctly both with a synthetic manifest and
       without one (natural-sort fallback).
     - An end-to-end test with `ollama.chat` mocked: build a small synthetic
       folder (2-3 `.txt` files), run the full `compile-pdf` path, then
       **reopen the produced PDF with `fitz.open(path)`** and assert the
       original words appear in `page.get_text()` for every page — this is
       the test that would have caught a silent content loss, and it costs
       nothing extra since PyMuPDF is already a dependency.
     - A real-data smoke test (no model call, `--no-structure`) against
       `output/cleaned/text/Fritz Eberhard KV/` — it's one real page already
       in this repo, so this test needs no fixture at all.

G) `README.md` — add a `### PDF export` section under `### Usage`, matching
   the style of the existing `### Tropy archives` / `### Cleanup guard`
   sections (what it does, the one command to run, the config keys, the one
   thing to know about the guard).

H) Optional, explicitly out of scope unless the user asks for it now: GUI and
   Web buttons. If asked, the natural spots are the toolbar row in
   `gui/views/main_view.py` (next to "Send to Tropy…") and, for the web build,
   a new button beside `btn-send-tropy` in `static/index.html` plus a new
   `static/js/pdf_export.js` following `tropy.js`'s structure (its own `els`
   lookup, its own modal, reusing `api()`/`escapeHtml()` from `app.js`). Don't
   start this without confirming scope — it roughly doubles the size of the
   change for a feature that works fine from the CLI first.


NON-NEGOTIABLE RULES
---------------------

- The structuring pass must never be trusted to have preserved content just
  because the prompt says so — verify with `check_structure_only()`, every
  time, no exceptions. This project already shipped a cleanup guard *because*
  a strict-sounding prompt alone let a reasoning model quietly delete clauses
  and corrupt an already-correct word on real archival pages (see
  `_guard.py`'s docstring and `README.md`'s cleanup-guard section for the
  full story). Assume the same failure mode here unless proven otherwise.
- Do not touch `_guard.py`'s existing `check()`/`apply()` thresholds — they
  are tuned against a 130-page audit for a different job (OCR repair) with
  deliberately looser tolerances than this feature needs. Add new logic
  alongside it.
- A page whose structuring is rejected must still appear in the final PDF
  (unstructured). Never drop a page from the compiled output.
- Reuse `cfg("cleanup_model")` for the structuring pass — no new required
  model config, per the user's own framing of the feature.
- Every model call must pass `think=cfg("ollama_think")` via `_llm.chat()`
  like every other stage does. This is not optional politeness — see
  `README.md`'s "Why cleanup is fast" section for the measured ~13x cost of
  getting this wrong.
- Follow the existing `<output_dir>/<stage>/text|json/<stem>.txt` convention
  for any new stage output. Do not write into `cleaned/` — add `structured/`.
- Run `py -3.12 -m pytest tests/ -q` before and after your changes; keep it
  at 164 passed or higher. Use `py -3.12` explicitly — the `python` on PATH on
  this machine is 3.14 and lacks the project's dependencies (collection fails
  immediately, which looks like broken tests rather than a wrong interpreter).
- Any test that touches `config.save_user_settings()`/`load_user_settings()`
  must first `monkeypatch.setattr(config, "_SETTINGS_PATH", tmp_path /
  "settings.json")`. This is not a style preference: a test in this project
  once wrote real content into the developer's actual
  `~/.ocr_pipeline/settings.json` by skipping this, and it wasn't caught
  until a live run downstream failed with a genuinely confusing error. See
  `tests/test_web.py`'s `client` fixture for the pattern to copy.
- Do not import `tropy_write.TropyWriter` for this feature — you only need
  read-only context (the manifest file, which is plain JSON, not even a
  Tropy DB connection). If you find yourself wanting to open the `.tpy`
  database at all, stop and reconsider — the manifest already has everything
  this feature needs.
- Don't wire GUI/Web buttons without confirming the user wants that now (see
  (H) above).


FILES TO CHANGE
----------------

  File                                     Action
  ----------------------------------------  ------------------------------
  prompts/structure_prompt.txt              New
  src/ocr_pipeline/_prompts.py              Add _STRUCTURE_PROMPTS + getter
  src/ocr_pipeline/_guard.py                Add check_structure_only()
  src/ocr_pipeline/stages/structure.py      New stage module
  src/ocr_pipeline/pdf_export.py            New — collect/structure/render
  src/ocr_pipeline/cli.py                   New `compile-pdf` command
  src/ocr_pipeline/config.py                Any new keys (see below)
  configs/example.yaml                      Document new keys
  pyproject.toml                            Add `reportlab` (if used)
  tests/test_pdf_export.py                  New
  README.md                                 New "### PDF export" section
  gui/views/main_view.py, web/static/...    Only if (H) is in scope

  Config keys to consider adding (keep minimal — only add what you use):
  `structure_guard` (bool, default true, mirrors `cleanup_guard`'s escape
  hatch), and possibly `pdf_font` if you go with the embedded-fonts route.
  Do not add a `structure_model` key — reuse `cleanup_model`.


VALIDATION COMMANDS
--------------------

  py -3.12 -m pytest tests/ -q                          # baseline: 164 passed
  py -3.12 -m pytest tests/test_pdf_export.py -v
  py -3.12 -m src.ocr_pipeline.cli compile-pdf --help

  # Real smoke test against data already in this repo, no OCR/model call:
  py -3.12 -m src.ocr_pipeline.cli compile-pdf \
      "output/cleaned/text/Fritz Eberhard KV" --no-structure \
      --output /tmp/smoke.pdf

  # With structuring, against a slightly bigger real folder (4 real pages):
  py -3.12 -m src.ocr_pipeline.cli compile-pdf \
      "output/cleaned/text/ISK Comms with Switzerland Part I" \
      --output /tmp/isk_comms.pdf


END OF HANDOFF
