# Changelog

All notable changes to the Artifice Suite are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Every app and package shares one version; see `ROADMAP.md` for the release policy.

## [Unreleased]

### Changed
- **Transcribe's `api/v1/routes.py` "god router" split into six resource-oriented
  files.** 1,970 lines covering models, health, speakers, config, jobs, and the
  transcription engine in one module, all behind one flat `APIRouter` — now
  `api/v1/{models,health,speakers,config,jobs,transcription}.py`, each with its
  own router, composed in `main.py`, mirroring the pattern `artifice-ocr`
  already used. `routes.py` itself is now 457 lines of private
  helpers and the background worker only, with zero `@router` endpoints left
  on it. Pure code-motion in six independently-reviewed PRs; the one real
  correctness subtlety was that several tests monkeypatch functions
  (`_get_engine`, `_reload_engine`, `_load_inference_config`, `_run_transcription`,
  `pack_embedding`, and the inference-config path constants) by their
  `routes.py` module-attribute path — a plain import into a new module binds a
  stale, unpatchable copy, so every extracted module that still calls back
  into a not-yet-moved helper does it via a module-qualified reference
  (`from artifice_transcribe.api.v1 import routes as _routes`) instead. (#127,
  #128, #129, #130, #131, #132)
- **Shared config systems: unification considered, narrowed to primitive
  extraction only.** `artifice-ocr`'s mutable-dict/YAML config and
  `artifice-transcribe`'s `pydantic_settings` singleton were investigated for
  full unification; neither the API surface nor the file layout will
  converge, because the two are answering genuinely different questions, not
  drifted duplicates of the same one — OCR configures a single image-OCR
  vision-model call, while transcribe configures a document-transcription
  pipeline (ASR engine selection, diarization, an independent chat/inference
  model for summarize/cleanup), each needing its own discrete, independently
  configurable model interaction. Forcing one config shape over both would
  either lose that independence or reintroduce it as a second system anyway.
  Scope narrowed instead to the one piece that *was* genuine, exact
  duplication: a "write private JSON, verify the OS permission restriction
  took effect, retry once, raise on persistent failure" pattern reimplemented
  identically in `artifice-ocr`'s settings save and twice in
  `artifice-transcribe`'s routes (HF token, inference config) — extracted
  into `packages/secure-io` as `write_private_json_verified`. A fourth,
  original copy in the paused `artifice-graph` is deliberately left alone,
  matching this session's existing precedent for paused-app duplication. (#135)
- **OCR's four near-identical batch phase loops (OCR, cleanup, title,
  translate) unified into one `_run_phase` helper.** Each loop in
  `run_pipeline_batch` repeated the same shape — iterate files, time each
  step, collect results, roll up totals — with one real inconsistency between
  them: the OCR phase never zeroed a skipped file's timing while the other
  three did. `_run_phase` applies that zero-on-skip rule uniformly, so OCR's
  timing now matches the others instead of quietly overcounting. `jobs.py`'s
  `JobRunner` was investigated and deliberately left untouched — it solves a
  different problem (interruptible async web-UI runs vs. synchronous CLI
  batches), not the same loop under a different name. (#137)
- **`pipeline._source_identity` and `stages/ocr.py._source_identity_fields`
  unified** — byte-for-byte identical logic (extract `checksum`/`photo_id`
  from a source dict, drop anything falsy) under two names. An earlier note
  claimed unifying them was blocked by a circular import; re-verified
  empirically rather than trusted, since this codebase has a documented
  history of exactly that kind of stale claim surviving past the fix that
  closed it. No cycle exists in either direction — `pipeline.py` already
  imports `stages.ocr` directly, and `stages/ocr.py`'s full import chain
  (including `stages/preprocess.py`) has no reference back to `pipeline`
  anywhere. `pipeline.py` now calls `ocr._source_identity_fields` instead of
  maintaining its own copy. (#141)

### Fixed
- **OCR queue race condition.** `JobRunner` held the exact same list object
  `RunState.items` did, not a copy — reordering, removing, or clearing the
  queue over HTTP while a run was active raced against the runner's own
  background-thread iteration over that list. Concretely reachable via
  ordinary UI actions (drag-reorder a queue row, remove one, hit Clear Queue)
  while OCR was running: clearing the queue mid-run could truncate the
  runner's iteration to nothing, and remove/reorder could cause it to
  silently skip a queued file. `JobRunner` now takes a defensive copy of its
  item list at construction time, and `remove`/`clear`/`reorder` now 409
  while a run is in progress (mirroring the existing "a run is already in
  progress" guard on starting a new one); adding files mid-run stays
  unblocked, since it's harmless once the runner owns its own copy. (#133)
- **A live-interop release-gate test race.** The settings page's "No
  changes" status only proves `setDirty(false)` ran, not that every field
  finished repopulating from the server. Running the LM Studio case
  immediately after Ollama's full OCR pipeline in the same gate could leave
  `#set-max_ocr_workers` reading empty at that point, failing the client-side
  save validator even though the server-side value was already correct.
  Found and fixed while finally running the full live release gate
  (`scripts/interop/run-live-release-gate.sh`) end to end for the first time
  this session — now waits for the field itself, not just the status text.
  (#133)
- **Transcribe's job-delete cascade loaded full transcripts into memory.**
  `TranscriptionJob.segments`/`.speakers` cascaded via SQLAlchemy's ORM layer
  without `passive_deletes=True`, so deleting a job first SELECTed every
  `TranscriptSegment`/`SpeakerMapping` row into memory to stage each for
  individual deletion — for a long oral-history interview, hundreds to
  low-thousands of `Text`-column rows loaded just to delete a job — even
  though the database's own `ON DELETE CASCADE` (already declared on both
  foreign keys, with `PRAGMA foreign_keys=ON` already enabled on every
  connection) was fully capable of doing this with no Python involved.
  `passive_deletes=True` now lets it. A related but distinct issue was found
  and *not* fixed here: `SpeakerEmbedding.job_id` and `SegmentEditVersion.job_id`
  aren't declared as foreign keys at all, so deleting a job never cleans up
  either table — rows accumulate forever. Opposite failure mode, separate
  fix — see below. (#134)
- **`SpeakerEmbedding.job_id` given a real foreign key.** The gap flagged
  above: deleting a `TranscriptionJob` never cleaned up its speaker
  embeddings, which accumulated forever. Verified empirically before
  assuming `SegmentEditVersion.job_id` needed the identical fix — it didn't;
  `SegmentEditVersion.segment_id` already cascades transitively through
  `transcript_segments.id` → `transcription_jobs.id`, confirmed with a
  standalone script proving SQLite honours `ON DELETE CASCADE` across
  multiple FK hops in one statement. `SpeakerEmbedding.job_id` had no FK at
  all and genuinely needed one: now `ForeignKey("transcription_jobs.id",
  ondelete="CASCADE")`, with no new ORM relationship added, so the DB's own
  cascade handles cleanup without risking a repeat of this same bullet's
  over-eager-loading bug. (#140)
- **OCR's repetition-loop guard missed word-level loops with no line
  breaks.** Reported from real archival use: the vision model occasionally
  hits a repetition failure mode on unusual page formatting (suspected
  linked to temperature) that produces 20,000+ characters of looped words or
  short alternating phrases on a single page — text the existing line-based
  repetition check couldn't see, because it never breaks onto new lines.
  Calibrated against real flagged production output (both reconstructed
  patterns and one full verbatim sample) rather than synthetic cases alone:
  genuine archival prose runs ~99.7% unique 4-word windows; the real failure
  patterns run ~0.7–1.0% — roughly a 100x margin. A new word-level check
  (distinct 4-gram ratio below 20%, on text of 40+ words) now runs whenever
  the line-based check doesn't already catch a problem. One tokenization
  pitfall found and fixed during calibration: the existing digit-stripping
  word tokenizer (built for a different, proper-noun-protection check)
  collapsed genuine number-varying text into an apparent short repeating
  cycle, which would have false-flagged real archival content differing only
  by year/quantity — fixed with a separate digit-inclusive tokenizer used
  only by this check. (#138)
- **Async event-loop blocking and an O(N²) SSE regression.** Two upload
  routes and one queue-event poll did blocking file/queue I/O directly on
  the event loop; a per-item finished-state recorder walked the whole queue
  on every event instead of updating the one item that changed. (#116)
- **`InferenceEngine`/`AsyncOpenAI` client leak.** Three transcribe inference
  routes (generate, summarize, cleanup) built a fresh engine per request and
  never closed it — each carries its own `httpx.AsyncClient` connection pool,
  leaking sockets under load. Closed in a `finally`, including inside the
  streaming response's async generator body (which drains lazily, after the
  route function itself has already returned). (#117)
- **OCR confidence scoring routed through the model-harness structured-call
  contract** instead of a bespoke `ollama.Client` call with regex parsing of
  the model's raw text response — the harness path validates against a
  schema and degrades predictably (`StructuredOutputUnsupported`) instead of
  silently misparsing. (#118)
- **Security hardening batch**: transcribe's CLI now refuses to bind
  anything but a loopback host; a URL-userinfo redaction pass strips
  embedded credentials (`https://user:pass@host`) from any error string
  before it reaches a log or response; two previously-swallowed config-load
  exceptions are now logged instead of silently discarded. (#120)
- **`artifice-ocr`'s `history.search_items()`** narrowed from `SELECT *` to
  only the columns the response actually serialises. (#123)

### Performance
- **Uploads stream to a spooled temp file instead of buffering fully in
  memory** before writing to disk — at transcribe's 500 MB cap, two
  concurrent uploads could hold ~1.6 GB in RAM on a machine already running
  Whisper. Bodies under 10 MB still stay in memory; larger ones spill to disk
  transparently. Applied to OCR's and transcribe's upload routes only; the
  shared `read_capped` primitive itself, and its other call sites across the
  paused apps, are untouched. (#126)
- **Five missing indexes added** on FK columns transcribe queries by (job_id
  and segment_id across transcript segments, speaker mappings/embeddings, and
  segment edit versions) — retrofitted onto existing databases at startup,
  since this repo has no migration framework and `create_all(checkfirst=True)`
  skips a table's DDL, including new indexes, once the table already exists
  on disk. (#123)

### Internal
- **Shared `AppLogger` extracted** from two near-identical `_logging.py`
  modules (`artifice-ocr`, `artifice-transcribe`) into `packages/shared-ui`,
  instance-scoped (not a module global) so per-app log configuration stays
  isolated. (#121)
- **BYOM helper functions and `_assert_contained` deduplicated** — the former
  into `packages/model-harness`, the latter into `packages/shared-ui`'s
  `path_validation` module as `assert_contained`, raising a
  framework-agnostic `PathValidationError` rather than `HTTPException`. The
  identical `_assert_contained` copy in the paused `artifice-graph` is left
  untouched. (#122)
- **Six stale references to a nonexistent `OLMOCR2_OPTIMISATION_FINDINGS.md`
  fixed**, redirected to the real
  `docs/superpowers/plans/2026-09-09-olmocr2-optimisation.md` — the original
  findings doc was never checked into version control. Investigated the
  feature the references described (`ocr_prompt_style`) while here: it's
  correctly implemented, safely excluded from the settings API's writable
  keys, and fully tested; the only real gap is an empty `eval_corpus/`, a
  data-curation task, not a code defect. Comment/docstring-only, zero
  behavior change. (#139)
- **The live model-interop release gate re-run to completion** against real
  Ollama, LM Studio, and a real Tropy instance — deferred earlier this
  session pending free local model capacity, now confirmed
  `[live gate] PASS` on all three checks. Closes out the last open item from
  this session's structural audit.
- **OCR's stage-output-writing pattern, a handful of magic numbers, and
  source-identity field logic deduplicated** across the pipeline stages.
  (#125)
- **CORS origins now configurable via an environment variable** in both
  active apps, falling back to the existing hardcoded defaults. (#124)

## [0.4.0] - 2026-09-11

### Added
- **olmOCR-2 inference-side optimisations** (`docs/superpowers/plans/2026-09-09-olmocr2-optimisation.md`).
  Per-page temperature ladder in `_ocr_vision` — a repetition-guard rejection now
  resamples the same page at rising temperature (0.1→0.8) instead of discarding
  the whole document to Tesseract; `ocr_temperature_ladder_enabled` (default on)
  reproduces the exact prior fixed-`0.0` behaviour when off. Near-blank page
  short-circuit (`_blank.py`) skips the model call entirely on a greyscale-variance
  check. Auto-rotation detection (`_rotation.py`) via Tesseract OSD, opt-in and
  only probed when Tropy's own orientation metadata is unset. Defensive YAML
  front-matter stripping in `_normalise.py`, independent of prompt style.
  Configurable per-collection domain instruction prompt (`ocr_prompt_instruction`),
  exposed as a Settings-tab field beside Document type — [CENT] (arXiv:2608.30616)
  measured this taking olmOCR2's field-level exact-match from 30.55% to 74.64%
  with no training. Experimental structured-output prompt style
  (`ocr_prompt_style`), config-file-only, default `"raw"` unchanged — a genuine
  trade the findings doc says needs measurement before any default change. New
  CER-based accuracy/wall-time measurement harness
  (`scripts/measure_ocr_accuracy.py`); `eval_corpus/` ships empty with a README,
  since populating it with real ground-truth pages is a maintainer follow-up.
  Live-tested against a real Ollama endpoint (`richardyoung/olmocr2:7b-q8`) and a
  real, isolated Tropy process, not just the mocked suite. (#101)
- **Tropy write-back is reachable by a user.** `tropy_write.py` had been
  complete, tested and unwired since `eba87a2` — its own commit said "nothing
  wires it to a route, a stage, or a button". Two gated routes
  (`/api/tropy/writeback/preview` and `/commit`, 404 when disabled) and a
  Destination control in the Send to Tropy modal now reach it. The commit route
  recomputes the preview server-side and refuses on any blocker, count mismatch
  or foreign item — never a partial write. **Write-back applies only to photos
  added via Browse project**; a JSON-LD import carries no numeric photo id and
  can never be written back, and the modal says so. (#77)
- **Cross-project write guard.** Photo ids are per-project, so an item browsed
  from project A written into project B lands a transcription on a different
  photo. Items now record `source["tropy_project"]`, and a foreign item is
  refused before the writer opens. (#77)
- **Context size setting** (`context_size`, default `0` = leave it to the
  model). Live for Ollama, which honours `num_ctx` per request; disabled with an
  explanation for LM Studio, which fixes the window when it *loads* a model, and
  for hosted APIs that set it server-side. A context-overflow error is now
  rewritten to name the two token counts and where the limit actually lives.
  (#79, #81)
- **`docs/INSTALL_OCR_WINDOWS.md`** — the frozen-build install route, including
  why SmartScreen blocks an unsigned binary and why the zip should be unblocked
  *before* extracting. **`docs/MAINTAINER_CHECKLIST.md`** — release checks CI
  does not run, and the traps that have cost real time.
- **`artifice-ocr` drag-and-drop upload and native file picker.** New
  `POST /api/queue/upload` staging endpoint; dropzone rework with a file-picker
  fallback using the OS native dialog (replacing a typed-path `prompt()`);
  browser-mode file picker surfaced in the UI. The "Add from Tropy…" modal
  likewise replaced `prompt()` with a native path field and drag-and-drop zone.
- **Deterministic browser UI stress suite** (`ui_stress` pytest marker,
  `ocr-ui-stress` CI job). Eight fixed seeds exercise 30 browser actions each
  against the live OCR interface — queue, review, settings, malformed Tropy
  paths, modal dismissal — with exact seed replay and failure
  traces/screenshots on failure; a scheduled advisory run expands to 50 seeds.
  Kept separate from the unit-test matrix so a missing browser can never turn
  into a silent skip of this gate. (#96, #100)
- **Fabricated OCR result flagging.** A reviewer can mark a transcription as
  containing invented text; flagged items are excluded from Tropy writeback
  automatically and exportable as JSON with model provenance
  (`GET /api/history/fabricated-results`) for guard-rule development. (#95)

### Changed
- **Tropy integration reduced to one supported round trip: browse, OCR, send
  notes back.** The JSON-LD import/export bridge and the direct SQLite
  write-back path (`tropy_write.py`, `tropy_bridge.py`, `tropy_writeback.py`,
  ~1,000 lines) are deleted, not deprecated — all writes now go through
  Tropy's official Developer API (`tropy_api.py`, `tropy_notes.py`).
  **This supersedes the "Tropy write-back is reachable by a user" entry in
  Added, above** — the `tropy_write.py` path it describes no longer exists;
  `apps/artifice-ocr/docs/TROPY_INTEGRATION.md` has the current architecture.
  The cross-project write guard survives unchanged, just against the new
  write mechanism. (#94, #95)
- **History "Send to Tropy" sends every eligible document in the run**, not
  just the one row that happened to be selected — the single-document
  behaviour was a bug, not a design choice. Selecting a run now also opens its
  first document automatically. (#98)
- **Local OCR backend selection now auto-discovers the working address**
  (configured value, plain `localhost`, and the Windows host under WSL)
  instead of requiring an exact manual address; installed models populate
  per-role selectors once a backend is chosen. Hosted backends keep manual
  model-name entry. (#99)
- **`artifice-draft` and `artifice-graph` paused (maintainer decision, 2026-09-09).**
  Current local-model quality for open-ended copy-editing and structured
  knowledge extraction doesn't yet clear this suite's bar; active feature work
  is on hold in favour of `artifice-ocr` and `artifice-transcribe`. Reversible,
  not a removal: both apps stay installable and published, and their existing
  test suites still gate every change. `tests-cross-platform` in
  `.github/workflows/ci.yml` now excludes both from its Windows/macOS legs
  (12→8 combinations); they keep single-platform coverage via `tests`.
  `scripts/check-release-consistency.py` exempts both from the version-lockstep
  gate, so a release no longer needs an empty version bump on either just to
  tag. (#102)
- **Upload guards have one home.** `_read_capped` was copy-pasted into four apps
  and `_sanitise_path_component` into three, with `artifice-draft` missing the
  filename guard entirely. Both now live in `packages/shared-ui`
  (`uploads.read_capped`, `path_validation.sanitise_path_component`) and raise
  domain errors rather than `HTTPException` — shared-ui depends on
  `platformdirs` and `uvicorn` only, and must not gain a web framework. Each
  app's web layer translates, preserving its existing responses exactly. (#78)
- **Docs pass.** Spent working documents moved out of the repository root and
  the app roots into `docs/archive/` — four completed proposals and eight
  session handovers. Every mention of them elsewhere was prose, not a markdown
  link, so nothing broke. `ARCHITECTURE.md` corrected: it said four apps (there
  are five — the Hub is frozen-only, not absent), named a `packages/core-types`
  that does not exist, claimed 90 model-harness tests (265), and listed a
  `package.json` in every app when the suite has no Node toolchain at all.
- **`apps/artifice-ocr/docs/TROPY_INTEGRATION.md` corrected.** The document
  previously stated no code path ever writes to a Tropy `.tpy` database. A
  direct write-back path (`tropy_write.py`, opt-in, default off, not yet wired
  to Settings UI) now exists and has been documented. Sections on removed
  modules, write-path capabilities, and the "What Was Removed" heading were
  updated accordingly.

### Fixed
- **A large Send to Tropy (900+ pages) could hang and appear to crash.**
  `TropyAPIClient` opened a fresh HTTP connection per photo checked, with no
  per-item error isolation, so one slow or flaky response mid-batch discarded
  every other page's already-checked progress with no visible feedback beyond
  a static "Checking…" message. `TropyAPIClient` now reuses one connection for
  a whole batch, `commit` re-verifies the Tropy connection once instead of
  once per note, and per-item failures are recorded and skipped rather than
  aborting the rest. The send modal shows live elapsed time, a batch over 150
  pages asks for confirmation first, and closing the modal cancels an
  in-flight check via `AbortController` instead of leaving it running
  unobserved. Nothing in the suite exercised Tropy at more than a handful of
  items before this — the live interop test sends one photo, and the
  deterministic UI stress harness seeds four and never reaches a live
  backend for Send to Tropy at all. `test_tropy_send_scale.py` and
  `test_tropy_browse_scale.py` now run a synthetic Developer API and a
  synthetic large `.tpy` project at 600-900 items respectively, checking
  wall-clock ceilings, per-item failure isolation, and — structurally, by
  counting the fake server's own accepted connections — that a batch reuses
  one connection instead of opening one per photo. (#106)
- **`window.open()` silently did nothing for "Export flagged OCR" and PDF
  download** in the packaged pywebview desktop app. Nothing in this codebase
  creates a second native window for a script-triggered popup to open into —
  the same category of desktop/browser gap already handled for file and
  folder pickers elsewhere in the app. Both now fetch the bytes and drive a
  `Blob` download, which works identically in a browser tab and the desktop
  shell. (#106)
- Three UI races found by the stress-testing pass: a stale History item
  response could replace a since-selected newer one, Preview's action
  controls stayed enabled while a new item was still loading, and changing
  the Tropy stage dropdown mid-check could let two previews race into the
  same status line. (#100)
- **`backend_name` was passed to the provider SDK**, breaking OCR on every
  backend with `Completions.create() got an unexpected keyword argument`. The
  keyword belongs to our own `_guarded_chat` wrapper; a script adding it to
  eight call sites could not distinguish the wrapper's `model=model,` from the
  provider call's, and tagged both. **799 tests passed over it** — they mock the
  client, and a `MagicMock` accepts any keyword silently. The guard added is a
  test that reads the *source*: it walks the AST and fails if a provider call
  receives a keyword the wrapper owns. (#80)
- **Context-overflow detection could rewrite unrelated errors.** Matching the
  bare phrase "maximum context length" also fired on "maximum context length not
  supported for this model" — a *capability* error — replacing a real failure
  with advice about a limit the user had not hit. Detection now leads with
  machine-stable provider identifiers (`exceed_context_size_error`,
  `context_length_exceeded`), with the prose form requiring the overflow clause
  that follows it. Found by an independent `oss-reviewer` pass. (#81)
- **`artifice-draft` had no filename sanitisation** on upload. Not the traversal
  hole `FOLLOW_UPS.md` described — `Path(filename).name` into a per-upload
  `uuid4` directory already defeated `../../etc/passwd` — but two real gaps:
  backslashes are not separators on POSIX, so a Windows-style name survived
  intact, and `Path(".").name` is `""`, making `doc_dir / ""` the directory
  itself and raising `IsADirectoryError`, a 500 where a 400 belonged. (#78)
- **`tropy_write._display_path` leaked the path it existed to redact**, on
  Windows only. Its home-relative branch emitted the whole tail, disclosing the
  archive location and research topic. It passed on POSIX by accident: pytest's
  `tmp_path` is not under `$HOME` there, so the basename branch ran instead.
  Reproduced on Linux by pointing `HOME` and `TMPDIR` at a shared ancestor. (#76)
- **The write-back gate was invisible to the UI.** `tropy_writeback_enabled` was
  in `PERSISTED_KEYS` but missing from the settings router's `_CONFIG_KEYS`, so
  POST accepted it and GET never returned it — the control read `undefined` and
  stayed hidden even when the feature was on, while every route test passed. A
  test now round-trips the gate through the API. (#79)
- **`artifice-ocr` pipeline end-to-end.** Fixes: doubled `/v1` base URL (the
  404), settings save rejecting unused fields, approved folders for external
  drives, Tropy recent-projects list, tolerant path resolution, nested list
  rendering via recursive CTE, mixed path-separator handling, missing-asset
  preflight, BYOM role picker in the UI, and provider diagnostics output.
- **`artifice-ocr` `python-multipart` declared.** The dependency was absent
  from `pyproject.toml`, so the OCR container could not serve `multipart/form-data`
  upload requests.
- **`artifice-transcribe` no longer refuses roughly one enrolled speaker in 256.**
  The legacy-pickle sniff in `db/models.py` identified a stored embedding as a
  pre-migration pickle from its leading byte alone (`0x80`). A raw float32 vector
  is arbitrary binary, so ~0.4% of perfectly valid embeddings began with that byte
  by chance and were rejected with "the speaker must be re-enrolled". The check now
  requires the full pickle protocol-2+ signature — `0x80`, a protocol byte in 2–5,
  and the trailing STOP opcode — taking the collision rate to ~1 in 4 million while
  still matching every real legacy row. Still a pure byte inspection; `pickle.loads`
  is never called.
- **Reset script detects an installed app by any of its shims.** `scripts/reset-for-first-run.ps1`
  looked only for the bare command name, so an app that also installs a suffixed shim
  (`artifice-ocr-web`) was reported "not installed" while remnants remained on disk.
  It now checks the uv tool directory, `~/.local/bin`, and `PATH`, and judges success
  by what is left on disk rather than by uv's exit code. The early "already clean"
  exit likewise considered only user data and now considers installed programs too.
- **History's `record_finished_items()` re-inserted every already-recorded
  item on every `item_finished` event**, instead of once per item — it looped
  over the whole run's items and re-recorded every `DONE`/`FAILED` one each
  time, an O(n^2) blow-up with no guard against the `history_item_id` field
  that existed for exactly that purpose. On a real 944-file Tropy round trip
  this produced ~108,000 duplicate `run_items` rows in one run alone (~891,000
  on a similar run the day before), compounding across 37 runs into a 14GB
  `history.db` that made the History tab's run-items query effectively hang —
  which is why "Send to Tropy" stayed disabled: the code path that enables it
  never got a chance to run. A stale write from an earlier crash had also
  physically corrupted the single most-recently-inserted row; the history
  store was rebuilt excluding it, recovering a clean 2,922-row database with
  every run's real item count intact. Verified against two real Tropy round
  trips post-fix: a small folder and the full 944-page collection, both
  loading and enabling Send to Tropy correctly. (#111)

## [0.3.0] - 2026-08-24

### Added
- **Auto-generated page titles in `artifice-ocr`.** New optional pipeline stage
  (`stages/title.py`) generates short archival titles (≤120 chars) for each OCR'd
  page using the configured `cleanup_model` via `model_harness.contract` — the
  first OCR-side inference call through the harness contract with a required
  Pydantic schema. Opt-in via `title_enabled` config (default off); length cap
  plus truncation, accent warning, repetition rejection, and provenance marker
  (`generated_by_model: true`) guard every output. Falls back to basename on any
  failure. Titles written to `title/text/` and `title/json/`. The pipeline now
  runs 5 stages: OCR → Cleanup → Title (optional) → Structure → Translate.
- **Live read-only `.tpy` browse in `artifice-ocr`.** New `tropy_db.py` opens
  Tropy `.tpy` SQLite databases in read-only mode (`file:<path>?mode=ro`) with
  short-lived per-query connections. Browse projects, lists, tags, items, and
  photos without modifying database state. Feature-flagged via the persisted
  `tropy_live_browse_enabled` GUI setting (off by default), read per-request so
  the Settings checkbox takes effect with no server restart; the
  `ARTIFICE_OCR_TROPY_LIVE_READ` env var still forces it on. The UI is a
  "Browse project" tab beside the existing JSON-LD import mode, with a two-pane
  list/tag filter, item grid, and enqueue action. Corrected against the
  actual Tropy schema: titles via `metadata`/`metadata_values` join, photo paths
  base-relative, soft-delete filtering via `trash` table. Browse→enqueue maps
  browsed items directly to `JobItem` instances, bypassing manual JSON-LD export.
  Routes: `/api/tropy/browse/projects`, `/lists`, `/tags`, `/items`, `/items/{id}`,
  `/enqueue`.
- **File-bridge UX improvements in `artifice-ocr`.** Inline warning rendering for
  missing photos and pathcheck rejections in the import modal. One-click write-back
  upgraded: tries Tropy's local HTTP import API (`POST /project/import` on port
  2029) first, falls back to "reveal in file manager" plus re-import instructions.
  New `/api/native/reveal` route opens the OS file manager at the exported file's
  location. Workflow memory persists the last Tropy import path and export path in
  user settings.
- **Provenance continuity across `artifice-ocr`, `artifice-graph`, and
  `artifice-draft`.** History UI provenance chips show Tropy item title, group,
  and photo path per history row. LudwigLang export frontmatter extended with
  `tropy_item_id`, `archive_ref`, and `orientation` when Tropy provenance is
  available. Versioned manifest contract: `tropy_manifest.json` carries
  `schema_version: "1.0"` with a documented field shape. Graph manifest consumption
  via new `tropy_import.py` module and `POST /api/tropy/import-manifest` route in
  `artifice-graph`. Draft notes round-trip via new `tropy_notes.py` module and
  `POST /api/tropy/notes/import` and `/export` routes in `artifice-draft`.
- **Security hardening.** `artifice-ocr` and `artifice-graph` servers refuse to
  start when bound to a non-loopback address. `str(e)` reflection fix in graph's
  `api_get_models` returns a generic message and logs detail server-side.
  Resolved-path echo fix in `ludwiglang.py` 404 handler. `tropy_db.py` error
  messages sanitised — never echoes resolved paths or SQLite URI connection
  strings.
- **`artifice-hub` — a fifth app, and the first that is not a harness.** A
  native GUI launcher that installs, updates and launches the other four.
  Deliberately frozen-only: no Dockerfile, no PyPI publish, no
  `uv tool install`. 43 tests.
- **BYOM engine onboarding in `artifice-hub`.** `engine.py` detects Ollama
  (`which` → TCP probe → endpoint probe), reads per-app/per-tier
  recommendations from `model_harness.registry`, and drives an
  allowlist-validated `pull_model_command`. Server routes:
  `GET /api/engine/{slug}`, `POST /api/engine/{slug}/pull` (202 + `job_id`),
  SSE pull progress, and a launch gate. UI: engine modal, missing-model list,
  pull progress, install CTA.
- **Advisory model gate and model picker in `artifice-hub`.** The launch gate
  now checks only `engine_ready` (Ollama installed and running); missing
  *recommended* models became an advisory panel with a picker over the models
  actually installed, matching `model_harness.registry`'s own statement that
  recommendations are "guidance, not requirements". New
  `POST /api/engine/{slug}/models` persists the choice into the target app's
  own config through `config_bridge.py`, which delegates to that app's
  `secure-io`-backed save path so the write keeps the app's own restricted
  file permissions.
- **`packages/shared-ui/shared_ui/window.py`.** The Hub's 182-line `window.py`
  — the only one of the five with maximize/restore/resize — is now the single
  shared module; all five apps' `window.py` collapse to a 23-line re-export.
  The maximize/restore control is wired into the three apps sharing
  `shared_ui/templates/_masthead.html` (ocr, draft, transcribe) and into
  graph's hand-synced inline copy, via
  `shared_ui/assets/window-controls.js`.
- **Native file pickers.** `/api/native/pick-file` and `/api/native/pick-folder`
  use `tkinter.filedialog` for a real platform dialog, with a `prompt()`
  fallback for headless runs. Wired into `artifice-ocr`'s `pickFiles()` /
  `pickFolder()`; added to `artifice-graph` defensively, unused for now. This
  retires the `prompt()`-asks-you-to-type-a-path workaround.
- **`packages/shared-ui/shared_ui/assets/bind.js`.** `onReady` / `bindIfPresent`
  helpers plus an `apiFetch` wrapper that surfaces the server's real error
  message instead of a bare status code.
- **`scripts/frontend-footgun-check.py`**, wired into `ci.yml`: a mechanical
  gate for unguarded top-level `addEventListener` calls, inline-script bindings
  in templates, and empty `.catch()` swallows (with a deliberate exemption for
  `HTMLMediaElement.play().catch()`, which is the standard idiom).
- **Per-app favicons.** Four apps pointed `rel="icon"` at the 1080×1080 product
  lockup — 50–79 KB rendered at 16px, where the fine-line glyph turns to mush —
  and the Hub, being served as static HTML with no `templates/` tree, had none
  at all. Each app now gets a purpose-drawn mark: the serif A traced from the
  logo artwork, knocked out of the app's accent. The hex is literal by
  necessity — an SVG favicon receives no cascade, so `var(--accent)` would
  render it invisible.
- **`scripts/install.sh`** at the repo root, alongside the existing `install.ps1`.

### Changed
- **`build-exe.yml` builds every app on a tag.** The workflow resolved the app
  as `inputs.app || 'artifice-ocr'`, so a tag push built OCR and nothing else —
  draft, graph and hub were never produced. The app is now a matrix dimension:
  four apps on a tag, one on manual dispatch. A new `attach-release` job
  archives each bundle and uploads it to the Release, waiting for `release.yml`
  to create it first (two workflows fire on one tag with no ordering
  guarantee). That job alone holds `contents: write`; the build job stays
  read-only while it freezes third-party code.
- All nine `pyproject.toml` files and `CITATION.cff` cut to `0.3.0`. The
  release gate was failing beforehand: `apps/artifice-hub` sat at `0.1.0`
  against `0.2.0` everywhere else, because a frozen-only app that never ships
  to PyPI is still globbed by `check-release-consistency.py`. Exempt from
  distribution is not exempt from the suite version.
- `scripts/build-wheel.sh` resolved only `apps/`, so it could not build
  `model-harness`, `secure-io` or `shared-ui`. The one tool that exists to
  catch stale-`build/` packaging bugs did not cover the three packages every
  app depends on.
- The `live_smoke` pytest guard moved to the repository root. It lived only in
  `packages/model-harness`, so it applied only when that package was pytest's
  rootdir; any other invocation silently made a live Ollama call. It survived
  CI only because no Ollama exists there — meaning the guard had never actually
  been exercised.
- `artifice-hub` now uses a distinct amber accent (`#F5A845`) instead of
  reusing Graph's blue. Every app's form-control padding — a suite-wide
  hardcoded `0.7rem`/`1rem`, not a token — now reads
  `var(--space-4)`/`var(--space-5)`.
- `docs/TROPY_INTEGRATION.md` rewritten; it still described the removed
  SQLite-write architecture (`tropy_write.py` et al.) rather than the current
  read-only `tropy_jsonld.py` + `tropy_db.py` bridge.
- `CLAUDE.md` recorded four apps; there are five. `IMPLEMENTATION_PLAN.md`
  Part IV gains a dated re-measurement block striking four items that were true
  when written and are not now, and reframes Phase 6's "frozen bundles are
  ruled out" as history rather than policy — that decision was reopened and
  reversed, and a live prohibition already overturned invites someone to undo
  shipped work.
- Consolidated three duplicated subsystems — path validation, local-server
  bootstrap, and legacy-data migration — from per-app copies into two shared
  packages. `packages/shared-ui/shared_ui/path_validation.py` and
  `server_bootstrap.py`, `packages/secure-io/src/secure_io/migration.py`
  (`migrate_legacy_file` / `migrate_legacy_directory` — two functions, not the
  single function originally proposed in `REFACTOR.md`; the three real call
  sites split cleanly into two shapes). Closes a real security gap:
  `artifice-graph`'s path validator previously had no backslash normalisation
  or POSIX Windows-drive-letter rejection. Full detail and every deviation
  from the original proposal in
  `docs/superpowers/plans/2026-08-07-refactor-oss-compliance.md`. PR #62.

### Fixed
- `artifice-ocr`'s `validate_contained()` 500'd on a malformed path (empty
  string, or a Windows-style absolute path on a POSIX host) instead of
  400'ing — the normalisation call sat outside any `try/except`. TDD-verified
  (confirmed the regression test failed against the pre-fix code). Part of PR #62.
- PyInstaller frozen builds on Windows failed native window init with
  `Failed to resolve Python.Runtime.Loader.Initialize`. Affected
  `artifice-ocr`, `artifice-graph` and `artifice-draft`; non-frozen/dev runs
  unaffected. **Took three attempts, and the first two are recorded here
  because each was refuted by a real downloaded build, not by a test.**
  PR #63 set `PYTHONNET_PYDLL`, on the theory that pythonnet could not resolve
  the embedded `pythonXY.dll`; reading pythonnet's and `clr_loader`'s source
  showed pythonnet already defaults to netfx hosting on Windows, so that
  variable configures the opposite embedding direction and the change was a
  no-op. The real cause is Mark-of-the-Web: a file downloaded by a browser, or
  extracted from a downloaded zip, carries a `Zone.Identifier` NTFS
  alternate-data-stream, and .NET Framework's classic assembly loader refuses
  to resolve functions from a tagged assembly (same signature as
  pythonnet/clr-loader#74). PR #66 stripped the stream from pythonnet's own
  assemblies and fixed that DLL — after which the *next* assembly failed the
  same way, from `webview/lib/Microsoft.Web.WebView2.Core.dll`, with a third
  affected location under `clr_loader/ffi/dlls/`. PR #67 stopped enumerating
  subdirectories one bug report at a time and unblocks the entire frozen
  bundle (`_unblock_pythonnet_assemblies` → `_unblock_frozen_bundle`);
  ~1,240 files for ocr, a negligible one-time walk at window startup.
- `artifice-ocr` queue image route returned an opaque 404 and the OCR stage
  raised `FileNotFoundError` for Tropy-imported photos that passed pathcheck
  but did not exist on disk. Both now check file existence first and return
  actionable messages using `Path.name` only (never the resolved path).
- Removed references to retired `tropy.py`, `tropy_read.py`, and
  `tropy_write.py` from the OCR README and ruff baseline.
- **Every installer's uv bootstrap was broken, in two independent ways.**
  `scripts/install.sh` and `install.ps1` shipped
  `EXPECTED_HASH="PLACEHOLDER_SHA256"`, which by design always mismatches, so
  every user without uv was guaranteed a failure;
  `apps/artifice-ocr/scripts/install.sh` was broken differently and already,
  pinning a real hash against the *rolling* `astral.sh/uv/install.sh`, which
  has since been republished. All three now pin the immutable versioned URL
  for uv 0.12.5, so the hash goes stale only when `UV_VERSION` is deliberately
  bumped; the "update before every release" comments are gone, being a promise
  that would be forgotten. Second failure, hidden behind the first: all three
  added `~/.cargo/bin` to `PATH` after installing uv, but uv installs to
  `~/.local/bin` — the installer installed uv and then died saying uv was not
  on `PATH`. Both directories are now prepended, modern first, honouring
  `XDG_BIN_HOME`. `install.ps1` built that prefix with two sequential
  prepends, inverting the order and letting a stale cargo-dir uv shadow the one
  just installed; it now builds the prefix in a single assignment.
- `build-exe.yml`'s smoke test hardcoded `/static/css/app.css` for all three
  apps. ocr and draft serve that path, but graph's own `base.html` references
  `/static/app.css` — graph's `static/` tree has no `css/` subdirectory. Every
  graph build had been failing a check against a URL graph's template never
  generates, regardless of whether the app worked. Per-app `APP_CSS` variable
  now, alongside the existing per-app API path pattern.
- An undocumented commit burst (`0ee8c63`/`1055043`) left `artifice-ocr`'s
  `server.py` calling `open_native_window` twice, with an unreachable dev-mode
  browser fallback behind it, and left unguarded top-level DOM bindings across
  draft, graph, ocr and transcribe — crashing on any page missing the
  referenced element (draft's `/about`, for one). Bindings are now guarded via
  `bind.js`; graph's `library.html` inline bindings moved into
  `static/library.js`; script load order fixed in draft/graph/transcribe/ocr
  `base.html` so `bind.js` and `toast.js` load before the app scripts that
  depend on them.
- `artifice-ocr` `preview.js`: `new FindReplace(container)` ran after the IIFE
  that declared `container` had closed, throwing `ReferenceError` on every page
  load. Moved inside the IIFE with a null guard, since the script loads on
  every route and `#panel-preview` does not exist on all of them.
- `artifice-ocr` `settings.js`: `save()` had no `try`/`catch`, so a failed
  `POST /api/config` — including the default `api_base_url` tripping the
  pre-existing `EndpointPolicy` check — failed completely silently. Now
  toasts. A queue-reorder request in `app.js` swallowed failures via
  `.catch(() => {})`; it now toasts too.
- `artifice-transcribe` `app.js`: `initSettingsPanel()` called
  `loadInferenceConfig()`, a function that was never defined, throwing
  `ReferenceError` every time the settings panel opened. Reconstructed as the
  read-side counterpart to the existing `saveInferenceConfig()`.
- `artifice-hub` `hub.css`, two bugs found by live-testing the model modal
  rather than by reading it: `.modal-overlay[open]` relied on `inset: 0` alone
  to stretch the `<dialog>` to the viewport so its flexbox centring could work,
  but browsers give `<dialog>` an intrinsic width/height that is not literally
  `auto` — the dialog collapsed to its content size, pinned at (0,0), and its
  Close button rendered off-screen at x≈−365, unclickable. And `.btn` carried
  an unconditional `display: inline-flex`, which beats the UA
  `[hidden] { display: none }` rule, so every conditionally-hidden button in
  the suite (Retry, Download Recommended, Launch App, Save Model Choices)
  rendered regardless of its `hidden` attribute.
- `scripts/ruff-baseline.json`'s stale `jobs.py|B023` count (8 → 10). The file
  itself was untouched; the committed baseline simply did not match ruff's
  current count for unchanged code.

### Security
- **CodeQL alert sweep.** SSRF: closed a DNS-rebinding TOCTOU gap in
  `artifice-draft`'s style-guide scraper by pinning the TCP connection to the
  validated IP on every redirect hop, with SNI and certificate checks still
  against the original hostname. Path injection: validated previously
  unchecked user-supplied paths in `artifice-ocr`'s Tropy export/import routes
  and `shared-ui`'s handoff token lookup (UUID-shape check) through the suite's
  existing path-validation machinery. XSS: replaced unescaped `innerHTML`
  interpolation of a user-supplied filename with DOM construction in
  `artifice-draft`'s guide-import UI. Clear-text storage: stopped duplicating
  the plaintext BYOM API key into `localStorage` in `artifice-transcribe`, where
  it is already persisted server-side. Incomplete URL substring check: replaced
  a bypassable `.startswith()` host check in `artifice-graph`'s LLM client with
  an exact hostname comparison. Insecure temp file: `tempfile.mktemp()` →
  `tempfile.mkstemp()` in `artifice-draft`'s track-changes path. Stack-trace
  exposure: across hub/ocr/graph/transcribe's web layers, caught-exception text
  no longer flows into HTTP responses — a `public_message`-carrying exception
  pattern (set from a literal at the raise site, never derived from `str()` on
  a caught exception) replaces two call sites that had wrapped `str(exc)` in a
  new object without actually breaking the taint flow. The remaining open
  alerts — `bad-tag-filter` on the repo's own lint scripts, and
  `EndpointRejected`'s message reaching a response by design — were dismissed
  on GitHub as false positives with justification, not fixed.

## [0.2.0] - 2026-08-06

> **2026-08-06 — 0.1.0 published to PyPI.** Seven distributions (`artifice-model-harness`,
> `artifice-secure-io`, `artifice-shared-ui`, `artifice-ocr`, `artifice-draft`,
> `artifice-graph`, `artifice-transcribe`) shipped to public PyPI in three waves via
> `workflow_dispatch`, each as an sdist and a wheel. All seven verified installable
> into clean environments; the three shared packages resolve from PyPI, not the local
> uv workspace. PR #45 and PR #46 merged.

### Added
- GitHub issue templates (bug report, feature request) and a pull-request template
  to give outside contributors structured filing and a pre-submission checklist.
- Dependabot configuration for the `uv` lockfile and GitHub Actions.
- CI `lint` job: a ruff baseline gate (fails only on **new** violations, not the
  pre-existing backlog), `ruff format --check` on changed files in PRs, `pip-audit`
  for known vulnerabilities, and a dependency-licence gate.
- `scripts/check-release-consistency.py` and a tag-triggered `release.yml` guard so
  tag names, package versions, and `CITATION.cff` cannot drift apart.
- `docs/index.md`, a map of every document in the repository.
- This changelog.
- ASR model consent-and-download flow in `artifice-transcribe`: seven endpoints under
  `/models` (listing with transitive sizes, per-model detail, consent grant/revoke,
  download start, status poll, cancel, SSE progress stream with real byte counts).
  Server-side consent required before any download; HuggingFace token persisted
  through `secure-io`. New module
  `apps/artifice-transcribe/src/artifice_transcribe/services/download.py`; 27 new
  tests (suite: 123 → 150 passed).
- `depends_on` on `model_harness.registry` ASR entries — `pyannote-speaker-diarization`
  now declares its dependency on `pyannote-embedding` explicitly. Transitive download
  size is now the true total (102.3 MB, not the 5.9 MB a single entry would report).
- `github-release` job in `release.yml`, gated on the version-consistency guard,
  creating a GitHub Release on a `v*` tag. Zenodo archives on a published GitHub
  Release; nothing in CI created one before this session.
- `skip-existing` on all four PyPI/TestPyPI upload steps in `publish.yml`. Without it
  no tag could be pushed after the manual first release, since PyPI permanently rejects
  duplicate sdist/wheel uploads.

### Fixed
- `artifice-graph` declared `typer[all]`, an extra removed upstream; every
  `pip install artifice-graph` at 0.1.0 emitted "The package typer==0.27.1 does
  not have an extra named all". Now plain `typer`.
- `README.md` documented the clone-and-bootstrap install as primary and stated "No
  packages are published to any index yet" — inverted the moment 0.1.0 went live.
  PyPI install is now the primary path; clone reframed as development.
- SSE frames in the ASR download endpoints were never terminated. Every yield
  emitted a literal backslash-n rather than a newline; an SSE event is terminated
  by a blank line, so no frame was ever complete and a browser `EventSource`
  received nothing while the server reported healthy. The pre-existing
  summarize/cleanup endpoints in the same module were always correct — a silent
  divergence from a working pattern. Neither the code review nor the 36 tests
  caught it (they assert decoded JSON and manager state, never bytes on the wire).
  Two tests now cover the wire format.
- The same line left a placeholder uninterpolated, so the error told the client
  "No download active for {key}" literally.
- A progress callback captured its loop variables by reference (`ruff B023`) while
  running on a background thread; an event arriving after the loop advanced reported
  the next model's index, key and repo against the current model's byte count.
- `artifice-graph`'s sdist no longer ships `Dockerfile`, three Windows `.bat`
  launchers or `scripts/`. A hatchling sdist includes every git-tracked file in
  its directory; a setuptools one does not, so only graph needed the exclusion.
  Test suites are deliberately still included.

### Known Issues
- `artifice-transcribe --help` starts the web server instead of printing usage.
  (`main.py` `cli()` handles only `--data-dir`; everything else falls through to
  `uvicorn.run`.) Shipped in 0.1.0.
- `artifice-graph` performs a **destructive filesystem operation at import time** —
  `config.py` calls `shutil.move()` on a legacy `~/.callosip` directory at module
  scope. Shipped in 0.1.0.
- A machine-specific WSL2 IP address ships as a fallback in `model-harness`'s
  always-allowed endpoint set, reaching every user of all four apps. Shipped in 0.1.0.
- The `asr` and `asr-cuda` extras of `artifice-transcribe` declare **identical**
  dependency lists. Only `[tool.uv.sources]` distinguishes them, and that is the uv
  workspace configuration which is not carried in the published package — so on PyPI
  the two extras are indistinguishable and the advertised CPU-only PyTorch path does
  not apply. Shipped in 0.1.0.
- Zenodo record `10.5281/zenodo.21707694` (concept DOI `10.5281/zenodo.21621935`)
  is stamped **MIT**. The codebase has been **AGPL-3.0-or-later** since the
  2026-07-30 relicensing. A future tag mints a corrected record but **does not
  retract this one** — it remains unless edited or deleted by the maintainer on
  zenodo.org. (See also "Zenodo licence note" in "Prior pre-release tags" below.)

## Prior pre-release tags (retired)

Two pre-release tags existed and were **removed 2026-08-05** as part of the
2026-07-30 versioning policy (one shared version, `0.1.0`, with tags minted only
at release):

- `v0.1.0-alpha` — created 2026-07-27 at `238b717`; tagged before
  `CITATION.cff` or a `LICENSE` existed.
- `v0.2.0-alpha` — created 2026-07-30 at `6d07380`; tagged while the tree still
  declared an MIT licence.

They were deleted locally and from `origin` because their names contradicted
the shared `0.1.0` version and both predated the 2026-07-30 relicensing to
AGPL-3.0-or-later. Tag/version consistency is now enforced by
`scripts/check-release-consistency.py` for all future tags.

> **Zenodo licence note.** Zenodo record `10.5281/zenodo.21707694` (concept DOI
> `10.5281/zenodo.21621935`) was minted 2026-07-30 from the `v0.2.0-alpha`
> tree, which declared an MIT licence. The codebase is now AGPL-3.0-or-later.
> The published record retains the MIT stamp; this record predates the
> relicensing and has **not** been corrected or deleted on Zenodo as of
> 2026-08-05. A future tag push will mint a corrected record from the current
> `CITATION.cff` (AGPL-3.0-or-later), but the existing MIT-stamped record
> remains unless edited or deleted by the maintainer on zenodo.org.

[Unreleased]: https://github.com/Muggwoffin/artifice-suite/compare/main...HEAD
[0.3.0]: https://github.com/Muggwoffin/artifice-suite/compare/0.2.0...0.3.0
[0.2.0]: https://github.com/Muggwoffin/artifice-suite/compare/0.1.0...0.2.0
