Handoff: Surface PDF Export in the GUI and Web UI
====================================================

Read this file before writing any code. It describes the exact state of the
project as of 2026-07-22, what to build, and a threading trap that will make
the UI freeze for minutes on a real archive item if you copy the nearest
"send a batch of stuff somewhere" dialog verbatim — see NON-NEGOTIABLE RULES.


PROJECT STATE
--------------

The PDF export feature itself is **done and working** — this handoff is
*only* about wiring it into the two frontends. It was built per
`HANDOFF_PDF_EXPORT.md` (same folder; read it if you want the full backstory
on the content-preservation guard), and every item in that document's
"WHAT TO BUILD" (A–G) is complete and verified:

  - `prompts/structure_prompt.txt` + `_prompts.py`'s `get_structure_prompt()`
  - `_guard.check_structure_only()` — whitespace-insensitive equality; a
    structuring pass that changes a single word is rejected and the original
    text is kept, never dropped
  - `src/ocr_pipeline/stages/structure.py` — `perform(text, *, source_file="",
    output_dir="output", stem=None) -> dict`, same shape as `cleanup.py`,
    writes `<output_dir>/structured/text|json/<stem>.txt|json`, respects
    `resume`
  - `src/ocr_pipeline/pdf_export.py` — `collect_folder()`, `structure_pages()`,
    `render_pdf()` (see below for exact signatures)
  - CLI: `ocr_pipeline compile-pdf <folder> [--stage cleaned|raw_ocr|translated]
    [--output OUT.pdf] [--no-structure] [--manifest PATH]` in `cli.py`
  - `configs/example.yaml` documents `structure_guard: true`
  - `tests/test_pdf_export.py` — 13 tests, all passing
  - `README.md` has a `### PDF export` section
  - Fonts are bundled: `assets/fonts/{PlayfairDisplay,LibreBaskerville}{,-Italic}.ttf`,
    registered by `pdf_export._register_fonts()`

I ran the full suite (`py -3.12 -m pytest tests/ -q` → **203 passed**) and did
a real smoke test today against actual archive data already in this repo
(`output/cleaned/text/Fritz Eberhard KV`, `--no-structure`) — rendered a
correct PDF, opened it with `fitz`, confirmed the real 1935-era intelligence
text came through untouched with Playfair Display/Libre Baskerville fonts and
a subtle `[Eberhard KV 3_p0002]` provenance marker at the top of the page.
The underlying feature is solid; nobody can reach it except via the CLI.

Two frontends share the rest of this app's core exactly the way they share
everything else: tkinter (`gui/`) and FastAPI + vanilla JS (`web/`). The
closest existing precedent for "point at something, run a batch operation,
show a result" is "Send to Tropy…" (`gui/views/tropy_send.py`,
`web/static/js/tropy.js` + the `modal-tropy-send` block in `index.html`) —
model the new dialog/modal's **visual shape** on that, but see
NON-NEGOTIABLE RULES before copying its execution model.


THE FEATURE
------------

Add a "Compile PDF…" entry point to both frontends that lets the user point
at a folder of already-processed `.txt` output (typically one Tropy item's
worth — `output/cleaned/text/<Item Title>`, though any folder of `.txt` files
works, per `collect_folder()`'s own docstring) and produce one continuous
reading PDF, exactly what `compile-pdf` already does from the CLI.

This is **not** tied to the live queue's current selection — `pdf_export.py`
reads directly from disk (a folder path), not from `item.results` in memory.
A user should be able to compile a folder from a run that finished last week,
same as running the CLI command by hand.


WHAT TO BUILD
--------------

A) **Prerequisite refactor** — `src/ocr_pipeline/pdf_export.py` +
   `src/ocr_pipeline/cli.py`. Right now `cli.py`'s `compile_pdf()` command
   inlines the collect → structure → render sequence itself (lines ~483–524).
   Both new frontends need that exact same sequence, so pull it into one
   function both the CLI and the UI call — "one core, two frontends" is this
   whole project's own stated design, don't let this feature be the
   exception:

       def compile(
           folder: str,
           *,
           stage: str = "cleaned",
           structure: bool = True,
           output: str | Path | None = None,
           manifest_path: str | None = None,
           on_progress: Callable[[str], None] | None = None,
       ) -> Path:
           """Collect, optionally structure, and render one folder into a PDF.

           `on_progress(message)` is called once per major step and, during
           structuring, once per page — a background-thread-friendly
           progress callback, the same convention every other stage's
           `perform()` uses via its own logger, just also handed to a caller
           that wants to show it live instead of only writing it to the log.
           """
           on_progress = on_progress or (lambda msg: None)
           folder_path = Path(folder)

           on_progress(f"Collecting pages from {folder_path}...")
           pages = collect_folder(str(folder_path), stage=stage, manifest_path=manifest_path)
           if not pages:
               raise ValueError(f"No pages found in {folder}")
           on_progress(f"Found {len(pages)} page(s)")

           if structure:
               pages = structure_pages(pages, on_progress=on_progress)

           title = next((p.item_title for p in pages if p.item_title), None)
           if output is None:
               output_dir = Path("output")
               output_dir.mkdir(exist_ok=True)
               output_path = output_dir / f"{folder_path.name}.pdf"
           else:
               output_path = Path(output)

           on_progress("Rendering PDF...")
           result_path = render_pdf(pages, output_path, title=title)
           on_progress(f"Done: {len(pages)} page(s) -> {result_path}")
           return result_path

   Give `structure_pages()` the matching optional parameter (currently it only
   does `log.info("Structuring %d/%d: %s", ...)`  — add `on_progress` calling
   it with the same per-page message, e.g. `f"Structuring {i+1}/{n}: {page.label}"`,
   alongside the existing `log.info` call, not instead of it):

       def structure_pages(pages: list[PageText], on_progress=None) -> list[PageText]:
           on_progress = on_progress or (lambda msg: None)
           ...
           for i, page in enumerate(pages):
               message = f"Structuring {i + 1}/{n}: {page.label}"
               log.info(message)
               on_progress(message)
               ...

   Update `cli.py`'s `compile_pdf()` command to call `pdf_export.compile(...)`
   instead of doing the sequence inline, passing `on_progress=lambda msg:
   typer.echo(msg)` so CLI output is unchanged. This is a pure refactor —
   `tests/test_pdf_export.py`'s existing 13 tests must still pass unmodified
   (its end-to-end test drives the CLI command, so it's already an implicit
   regression check for this refactor).

B) **GUI**: new file `src/ocr_pipeline/gui/views/pdf_export_dialog.py`,
   `PdfExportDialog(tk.Toplevel)`, opened from a new "Compile PDF…" button in
   `gui/views/main_view.py`'s toolbar row (next to "Send to Tropy…", same
   `ttk.Button(row, text=..., command=...)` pattern — see line ~98).

   Layout: a folder field + "Browse…" (`filedialog.askdirectory`), a stage
   dropdown (`ttk.Combobox`, values cleaned/raw_ocr/translated, matching
   `tropy_send.py`'s `STAGE_CHOICES` shape), a "Structure text" checkbox
   (default checked), an output-path field + "Browse…" (`filedialog.asksaveasfilename`,
   default extension `.pdf`), a status label, a log/progress area (reuse
   `scrolledtext.ScrolledText` like `main_view.py`'s own log — see its
   `_build_log()`), and Compile/Close/Open-PDF buttons. Match `theme.py`'s
   constants for every color — no new ones, same as every other dialog in
   this app.

   Threading (see NON-NEGOTIABLE RULES for why this matters): own
   `queue.Queue()` + `self.after(POLL_MS, self._pump)` polling loop, the
   *exact* pattern `App`/`gui/app.py` already uses for `JobRunner` events
   (see `gui/app.py`'s `POLL_MS = 80`, `self.events = queue.Queue()`,
   `self.after(POLL_MS, self._pump_events)`) — not a new pattern, the one
   already in this codebase. On "Compile" click: disable the Compile button,
   spawn a `threading.Thread(target=self._run, daemon=True)` that calls
   `pdf_export.compile(..., on_progress=lambda msg: self.queue.put(msg))`
   inside a try/except (put an `("error", str(exc))` tuple on failure, or
   distinguish success/failure/log some other simple way — your call on the
   exact shape, just don't let an exception escape the thread silently, the
   same "surfaced, not swallowed" discipline `server.py`'s
   `_start_server_thread` already established for exactly this class of bug
   in this project). The dialog's `_pump()` drains the queue into the log
   widget and, on completion, re-enables Compile and enables an "Open PDF"
   button (`os.startfile(result_path)` on success — the direct file, not the
   containing folder, since the whole point is showing the reading copy).

C) **Web**: three pieces.

   1. `src/ocr_pipeline/web/runtime.py` — a small state object mirroring
      `RunState`'s own shape but scoped to this one-off operation (deliberately
      *not* wired into `JobRunner`/`jobs.STAGES` — see NON-NEGOTIABLE RULES):

          class PdfExportState:
              def __init__(self):
                  self.lock = threading.Lock()
                  self.status = "idle"  # idle | running | done | error
                  self.error: str | None = None
                  self.output_path: str | None = None
                  self.events: queue.Queue = queue.Queue()
                  self.thread: threading.Thread | None = None

          pdf_export_state = PdfExportState()

          def start_pdf_export(folder, *, stage, structure, output, manifest_path) -> bool:
              """Returns False (caller should 409) if one is already running."""
              with pdf_export_state.lock:
                  if pdf_export_state.status == "running":
                      return False
                  pdf_export_state.status = "running"
                  pdf_export_state.error = None
                  pdf_export_state.output_path = None
                  pdf_export_state.events = queue.Queue()
                  pdf_export_state.thread = threading.Thread(
                      target=_run_pdf_export,
                      args=(folder, stage, structure, output, manifest_path),
                      daemon=True,
                  )
                  pdf_export_state.thread.start()
              return True

          def _run_pdf_export(folder, stage, structure, output, manifest_path):
              from .. import pdf_export

              def on_progress(message):
                  pdf_export_state.events.put({"type": "log", "message": message})

              try:
                  result_path = pdf_export.compile(
                      folder, stage=stage, structure=structure, output=output,
                      manifest_path=manifest_path, on_progress=on_progress,
                  )
                  pdf_export_state.output_path = str(result_path)
                  pdf_export_state.status = "done"
                  pdf_export_state.events.put({"type": "done", "output_path": str(result_path)})
              except Exception as exc:
                  pdf_export_state.status = "error"
                  pdf_export_state.error = str(exc)
                  pdf_export_state.events.put({"type": "error", "message": str(exc)})

   2. `src/ocr_pipeline/web/server.py` — four routes, matching the
      **existing** `/api/events` SSE pattern exactly (`_event_stream()`,
      heartbeat comment lines, `asyncio.to_thread` around the blocking
      `queue.Queue.get`) rather than inventing a second SSE convention:

          class PdfExportRequest(BaseModel):
              folder: str
              stage: str = "cleaned"
              structure: bool = True
              output: str | None = None
              manifest: str | None = None

          @app.post("/api/pdf-export/start")
          def pdf_export_start(req: PdfExportRequest) -> dict:
              started = start_pdf_export(req.folder, stage=req.stage,
                                         structure=req.structure, output=req.output,
                                         manifest_path=req.manifest)
              if not started:
                  raise HTTPException(status_code=409, detail="A PDF export is already running")
              return {"ok": True}

          @app.get("/api/pdf-export/status")
          def pdf_export_status_route() -> dict:
              return {"status": pdf_export_state.status, "error": pdf_export_state.error,
                     "output_path": pdf_export_state.output_path}

          @app.get("/api/pdf-export/events")
          async def pdf_export_events():
              async def gen():
                  while True:
                      try:
                          event = await asyncio.to_thread(pdf_export_state.events.get, True, 1.0)
                      except queue.Empty:
                          yield ": heartbeat\n\n"
                          continue
                      yield f"data: {json.dumps(event)}\n\n"
                      if event.get("type") in ("done", "error"):
                          break
              return StreamingResponse(gen(), media_type="text/event-stream",
                                       headers={"Cache-Control": "no-cache",
                                               "X-Accel-Buffering": "no"})

          @app.get("/api/pdf-export/download")
          def pdf_export_download():
              if not pdf_export_state.output_path:
                  raise HTTPException(status_code=404, detail="No PDF has been compiled yet")
              path = Path(pdf_export_state.output_path)
              return FileResponse(path, media_type="application/pdf", filename=path.name)

      Import `start_pdf_export`, `pdf_export_state` from `.runtime` in the
      existing import block near the top of `server.py` (same place
      `render_page_image`/`save_raw_text` were added for the Preview image
      feature — follow that precedent).

   3. `static/index.html` + new `static/js/pdf_export.js`. Button next to
      `btn-send-tropy` (line ~74): `<button class="btn" id="btn-compile-pdf">Compile
      PDF&hellip;</button>`. New modal block (copy `modal-tropy-send`'s
      structure/CSS classes, not its content) with: a folder input + Browse
      button (reuse `pickFolder("folder")` from `app.js`, which already
      handles the native-vs-browser-prompt fallback), a stage `<select>`, a
      "Structure text" checkbox, an output-path input, a status line, a log
      div, and Start/Download/Close buttons. `pdf_export.js` follows
      `tropy.js`'s "own `els` lookup object, own module, loaded after
      `app.js`" shape, but its Start handler opens an `EventSource` against
      `/api/pdf-export/events` (see `app.js`'s own `connectEvents()` for the
      `EventSource` pattern already in this codebase) instead of doing a
      synchronous `POST` + rendering a response, for the same threading
      reason as (B).

D) `tests/test_pdf_export.py` — add tests for the two additive changes in
   (A): `structure_pages()` calls `on_progress` once per page in order, and
   `pdf_export.compile()` end-to-end (mirroring the existing
   `test_compile_pdf_end_to_end`/`test_compile_pdf_smoke_no_structure` tests,
   just calling the new function instead of driving it through the CLI
   runner). `tests/test_web.py` — add tests for the four new routes following
   this file's own `client` fixture (see NON-NEGOTIABLE RULES on
   `_SETTINGS_PATH`): missing-folder 404/400 on start, 409 on concurrent
   start, the SSE stream emits `log` then `done` for a small real folder with
   `--no-structure`-equivalent (`structure=False`, no model call needed),
   and `download` 404s before anything has been compiled.

E) `README.md`'s existing `### PDF export` section — add one line each for
   the GUI button and the web button/modal, matching how the Tropy section
   documents both entry points already.


NON-NEGOTIABLE RULES
---------------------

- **Do not copy `tropy_send.py`'s or `tropy.js`'s synchronous execution
  model.** Both of those run their preview/write calls directly on the
  Tk main thread / inside a single `fetch()`, with `self.update_idletasks()`
  calls papering over the pause — that's fine there because a Tropy DB write
  is fast (no model calls). Structuring calls the LLM once per page and a
  real item in this exact repo (per `HANDOFF_PDF_EXPORT.md`) is 275 pages —
  copying the Tropy pattern here would freeze the GUI's Tk main loop or hang
  a browser tab's request for however long that takes, with zero visible
  progress. Use the threaded + queue-drained pattern in (B)/(C) instead —
  it already exists twice in this codebase (`JobRunner`'s events queue on the
  GUI side, `/api/events`'s SSE stream on the web side); this feature gets a
  third, smaller copy of the same idea, not a new architecture.
- A page whose structuring is rejected must still appear in the final PDF —
  this is already guaranteed by `structure.perform()`'s own guard fallback
  (see `HANDOFF_PDF_EXPORT.md`); don't add UI logic that could skip or drop
  a page on a warning. Surfacing *which* pages fell back is a nice-to-have
  (a `warning`-tagged log line is enough) — see SCOPE CALLS below.
- Do not touch `_guard.py`, `jobs.py`'s `STAGES` tuple, or `JobRunner` for
  this pass. `structure` stays a standalone loop invoked from `pdf_export.py`,
  not a first-class pipeline stage — that was an explicit, still-current
  scope decision in `HANDOFF_PDF_EXPORT.md`, not something this pass
  reopens.
- Keep `pdf_export.compile()`'s `on_progress` addition backward compatible —
  it must default to a no-op so the existing CLI call site and
  `tests/test_pdf_export.py`'s current 13 tests keep passing unmodified
  after the refactor in (A).
- Reuse `pickFolder()` (web) / `filedialog.askdirectory()` (GUI) — do not
  build a second file-path-entry mechanism; both already exist and both
  already handle the native-vs-browser distinction for you.
- Match existing tokens only: `theme.py` constants for tkinter, `app.css`
  classes for the web modal. No new colors — this dialog is chrome, not the
  PDF's own content styling (which is already correct and untouched by this
  pass).
- Run `py -3.12 -m pytest tests/ -q` before and after; keep it at 203 passed
  or higher. Use `py -3.12` explicitly — `python` on PATH on this machine is
  3.14 and lacks the project's dependencies.
- Any test touching `config.save_user_settings()`/`load_user_settings()` must
  `monkeypatch.setattr(config, "_SETTINGS_PATH", tmp_path / "settings.json")`
  first — see `tests/test_web.py`'s `client` fixture for the pattern. A test
  in this exact project once skipped this and overwrote the developer's real
  `~/.ocr_pipeline/settings.json`.


SCOPE CALLS TO CONFIRM WITH THE USER (don't assume)
-----------------------------------------------------

1. **Web download UX** — I've assumed a `/api/pdf-export/download` route
   (`FileResponse`) plus a Download button that appears once the SSE stream
   reports `done`, rather than just showing the on-disk path as text. This
   is a small amount of extra code for a much better result (the browser and
   the server are typically the same machine here, but the user shouldn't
   have to go hunt for the file). Recommendation: build the download route.
2. **Smart folder defaults** — should the dialog pre-fill the folder field
   based on the currently selected queue item (e.g. derive
   `output/<stage>/text/<parent-of-its-stem>` from the selection), or always
   start blank and require Browse? The former is a nicer first-run
   experience; the latter is less code and less likely to guess wrong for a
   non-Tropy folder. Recommendation: start blank (manual browse only) for a
   first version.
3. **Surfacing guard rejections in the UI** — beyond a plain log line (which
   this handoff already asks for), should a completed export show a
   summary like "2 of 12 pages kept their original (unstructured) text"? The
   guard already protects correctness either way; this is purely about user
   awareness. Recommendation: skip it for v1 — the log line is enough, and a
   dedicated summary UI is easy to add later once someone actually asks for
   it.


FILES TO CHANGE
-----------------

  File                                            Action
  ------------------------------------------------ ---------------------------
  src/ocr_pipeline/pdf_export.py                    Add compile(); add
                                                     on_progress to
                                                     structure_pages()
  src/ocr_pipeline/cli.py                           compile_pdf() calls
                                                     pdf_export.compile()
  src/ocr_pipeline/gui/views/pdf_export_dialog.py   New — PdfExportDialog
  src/ocr_pipeline/gui/views/main_view.py           New "Compile PDF…" button
  src/ocr_pipeline/web/runtime.py                   PdfExportState,
                                                     start_pdf_export()
  src/ocr_pipeline/web/server.py                    4 new routes (start/
                                                     status/events/download)
  src/ocr_pipeline/web/static/index.html            New button + modal block
  src/ocr_pipeline/web/static/js/pdf_export.js       New — mirrors tropy.js's
                                                     module shape, SSE instead
                                                     of sync fetch
  tests/test_pdf_export.py                          New tests for (A)
  tests/test_web.py                                 New tests for the 4 routes
  README.md                                         Document both new
                                                     entry points


VALIDATION COMMANDS
---------------------

  py -3.12 -m pytest tests/ -q                              # baseline: 203 passed
  py -3.12 -m pytest tests/test_pdf_export.py -v
  py -3.12 -m pytest tests/test_web.py -v -k pdf_export

  # Manual smoke test once wired up — real data already in this repo, no
  # model call needed if you leave "Structure text" unchecked / structure=False:
  py -3.12 launch_ocr_pipeline.pyw
  #  -> Main tab -> "Compile PDF…" -> browse to
  #     output/cleaned/text/Fritz Eberhard KV -> Compile -> confirm the PDF
  #     opens and reads correctly.

  py -3.12 launch_ocr_pipeline_web.pyw --browser
  #  -> "Compile PDF…" -> same folder -> confirm the progress log streams
  #     live and the Download button produces the same PDF.

  # With structuring, against a slightly bigger real folder (4 real pages,
  # a genuine LLM call per page — needs Ollama running with cleanup_model):
  #     output/cleaned/text/ISK Comms with Switzerland Part I


END OF HANDOFF
