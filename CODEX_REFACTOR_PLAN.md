# Codex Refactor Plan

Status: proposed implementation plan based on the first read-only audit pass  
Audit date: 2026-09-11  
Scope: `artifice-ocr`, `artifice-transcribe`, `model-harness`, `secure-io`,
`output-layout`, and `shared-ui`

## 1. Purpose

This plan converts the verified findings from `CODEX_REFACTOR_BRIEF.md` into an
ordered refactor programme. It is deliberately narrower than a general rewrite:
the first objective is to remove paths that can lose completed work, corrupt
runtime state, or scale with all historical data. The second objective is to
finish the suite's structured-model boundary and make the public interfaces
easier for outside contributors to understand and extend.

The following remain out of scope except where they consume a changed shared
package: `artifice-draft`, `artifice-graph`, `artifice-hub`, `design-system/`,
and agent-tooling configuration. Shared-package changes must retain compatibility
with Draft and Graph even though their app-specific code is not otherwise part of
this programme.

## 2. Verified Baseline

The initial audit established the following facts directly from the current
source rather than relying on historical documentation:

- OCR completion persistence is triggered while an SSE client drains worker
  events. `web/routers/events.py` calls `RunState.record_finished_items()` and
  `RunState.finish_run()`; the worker itself only emits events.
- Transcribe has one module-level ASR engine shared by request-triggered
  background tasks, configuration reloads, preload, and speaker-enrolment paths.
  There is no lock, queue, or semaphore around that engine.
- `shared_ui.uploads.read_capped()` limits input size but returns one complete
  `bytes` value. Transcribe permits 500 MB and then calls `Path.write_bytes()` in
  its async request handler.
- Transcribe's optional text inference uses raw OpenAI-compatible chat
  completions. OCR title generation uses `model_harness.run_structured`, but OCR
  vision, cleanup, structure, and translation do not.
- Transcribe lists all jobs, has no indexes on its frequently filtered foreign
  key columns, and performs per-result job lookups in transcript search.
- The `/api/v1/transcribe/batch` route scans the persistent upload directory and
  creates new jobs for every matching file on every call. The shipped UI does
  not call this route.
- OCR suppresses every exception raised while recording finished history items.
- A single repo-root pytest invocation over all in-scope suites fails collection
  because several test modules share basenames. The same suites pass when run
  separately.

Separate suite baseline on 2026-09-11:

| Suite | Result |
|---|---:|
| Artifice OCR | 893 passed, 27 skipped, 15 deselected |
| Artifice Transcribe | 226 passed, 6 skipped |
| Model Harness | 266 passed, 1 deselected |
| Secure IO | 48 passed, 1 skipped |
| Output Layout | 3 passed |
| Shared UI | 108 passed |

The combined command failed during collection on duplicate modules including
`test_byom`, `test_logging`, `test_resolution`, `test_migration`, and
`test_window`. That failure is part of the baseline, not an implementation
regression.

## 3. Delivery Order

Each phase should land independently and leave all in-scope suites green. Do not
combine the ASR scheduler, SSE/history ownership change, and structured-model
migration in one pull request: each changes a separate reliability boundary and
needs a reviewable rollback point.

### Phase 1: Serialize Transcribe ASR ownership

Severity: high  
Change type: structural; discuss implementation shape before coding

Current failure mode:

- Two upload requests can schedule `_run_transcription` concurrently.
- Both tasks receive the same `_engine` instance and execute `transcribe()` in
  separate worker threads.
- WhisperX mutates shared model options for hotwords and initial prompts.
- Either task may enter `finally` and unload the model while the other task is
  still transcribing, aligning, or diarizing.
- Configuration reload, preload, and speaker-enrolment can also race with an
  active job.
- Real-world outcomes include cross-job vocabulary leakage, duplicate model
  loads, GPU memory exhaustion, use-after-unload failures, and jobs incorrectly
  marked failed.

Implementation:

1. Introduce an application-owned `AsrCoordinator` service. It owns the sole ASR
   engine instance, an `asyncio.Lock`, and engine construction/reload state.
2. Expose explicit async operations: `transcribe`, `preload`, `reload`,
   `health_check`, `extract_speaker_embedding`, and `shutdown`.
3. Run each synchronous engine operation with `asyncio.to_thread()` while
   retaining exclusive ownership for the complete operation, including unload.
4. Serialize jobs in FIFO order. A queued job remains `queued`; only the job that
   acquires the coordinator becomes `processing`.
5. Do not unload between overlapping callers because overlapping callers are no
   longer permitted. Preserve the current policy of unloading after each
   completed transcription unless measurement justifies a separate cache policy.
6. Route config reload, health preload, speaker enrolment, and both ASR backends
   through the coordinator; no route may access the engine singleton directly.
7. Create and dispose the coordinator through FastAPI lifespan so shutdown cannot
   abandon a loaded model or accept new work.

Public behaviour and compatibility:

- Existing HTTP request and response schemas remain unchanged.
- Multiple accepted jobs are processed sequentially instead of contending for
  the same accelerator.
- A configuration update requiring reload returns `409 Conflict` while an ASR
  operation is active, rather than unloading an in-use model. This is preferable
  to silently deferring a settings change whose effective time is unclear.
- Health output should add `busy: bool` and `queued_jobs: int` so the UI can
  distinguish unavailable, idle, and occupied states.

Tests and acceptance:

- Start two transcription tasks against a blocking fake engine; assert the
  second engine call does not begin before the first finishes.
- Give the two jobs different vocabularies and assert each call receives its own
  values with no shared mutation.
- Attempt reload, preload, and speaker enrolment during a blocked transcription;
  assert the documented serialization or `409` behaviour.
- Assert cancellation or failure releases the coordinator and permits the next
  job to run.
- Assert shutdown waits for or explicitly cancels queued work without leaving a
  job marked `processing` indefinitely.

### Phase 2: Separate OCR persistence from SSE delivery

Severity: high  
Change type: structural

Current failure mode:

- `JobRunner` emits `item_finished` and `run_finished` into one `queue.Queue`.
- An SSE connection removes those events and performs the database side effects.
- With no connected browser, completed items are not persisted and the run row
  is not finalized.
- With two browser tabs, clients compete for queue entries, so neither is
  guaranteed a complete event stream.
- A history-write exception is suppressed without a log or visible degraded
  state.

Implementation:

1. Add completion callbacks to `JobRunner`, or an application-owned event
   dispatcher consumed independently of HTTP connections.
2. Make the server-side completion path responsible for recording exactly the
   item that completed. Replace the current scan of all queue items with
   `record_finished_item(item)`.
3. Finalize the run from the worker/dispatcher's `run_finished` lifecycle, not
   from the SSE generator.
4. Make persistence idempotent at the database boundary. Add a stable per-run
   item identity and a unique constraint, or use an upsert keyed by
   `(run_id, item_execution_id)`. The in-memory `history_item_id` remains a cache,
   not the only duplicate guard.
5. Replace the destructive single-consumer SSE queue with a broadcast mechanism.
   Each subscriber gets its own bounded queue and a state snapshot on connect.
6. Define overflow behaviour: if a slow subscriber's queue fills, discard its
   oldest presentation events and send a `resync_required` event. Never discard
   persistence work.
7. On a database error, log the exception with run and item identifiers, mark the
   run as history-degraded, and surface a non-secret warning event. Continue the
   OCR pipeline so a history failure does not destroy generated files.
8. Close the history connection during application shutdown.

Public behaviour and compatibility:

- Preserve current SSE event names and payloads; add only `snapshot`,
  `resync_required`, and a history warning event if needed.
- Preserve history route response shapes.
- Existing databases receive an additive migration for the stable item identity
  and uniqueness rule. The migration must detect legacy duplicates and retain
  them; do not delete historical rows automatically. Apply uniqueness only to
  newly identified executions if legacy data cannot be safely reconciled.

Tests and acceptance:

- Complete a run with no SSE client and verify every item and final run totals
  are persisted.
- Connect two clients and verify both observe the same ordered completion events.
- Disconnect and reconnect a client; verify the snapshot reflects current state
  and history contains no duplicates.
- Invoke the persistence callback twice for one item and verify one row exists.
- Inject `sqlite3.OperationalError`; verify it is logged and surfaced while the
  worker still reaches a terminal state.
- Re-run the historical O(n^2) regression with at least 1,000 fake items and
  assert one persistence call per completion, rather than rescanning all items.

### Phase 3: Stream uploads to disk with a shared capped-copy API

Severity: high for Transcribe; medium for OCR  
Change type: shared-package API addition

Current failure mode:

- `read_capped()` stores all chunks and then allocates a joined buffer.
- The route subsequently writes that complete buffer synchronously.
- A valid 500 MB Transcribe upload can therefore require substantially more than
  500 MB of transient process memory before ASR begins. Concurrent requests
  multiply that pressure on ordinary laptops.
- A write error after the Transcribe job row is committed leaves an orphaned
  queued job.

Implementation:

1. Add `shared_ui.uploads.copy_capped(upload, destination, limit, *, chunk_size)`.
   It streams fixed-size chunks directly to a temporary sibling file, tracks the
   total, flushes and closes the file, then atomically replaces the destination.
2. On oversize input, cancellation, or write failure, close and remove only the
   temporary file and raise a typed domain exception. Never expose a partial
   destination.
3. Keep `read_capped()` for compatibility with Draft and Graph, but document it
   as an in-memory convenience for small payloads. Migrate OCR and Transcribe to
   the new API.
4. Perform blocking file writes with `asyncio.to_thread()` or implement the
   helper so asynchronous upload reads and synchronous disk writes are cleanly
   separated without blocking the event loop.
5. In Transcribe, validate the filename and reserve the destination before
   inserting the database row. If the database commit fails, remove the staged
   file. If final promotion fails, roll back the row.
6. Preserve OCR's per-file batch result semantics and collision-safe filenames.

Public API:

```python
async def copy_capped(
    upload: ReadableUpload,
    destination: Path,
    limit: int,
    *,
    chunk_size: int = 64 * 1024,
) -> int:
    """Atomically copy an upload to destination and return bytes written."""
```

Tests and acceptance:

- Verify maximum-sized input is accepted and maximum-plus-one is rejected while
  reading, without a completed destination.
- Use a recording fake to prove reads are bounded by `chunk_size`.
- Inject a disk-write failure and cancellation; assert temporary files are
  removed and an existing destination is untouched.
- Assert Transcribe creates no database job for an invalid filename or failed
  upload.
- Add a memory-oriented test or benchmark demonstrating peak Python-owned upload
  buffering remains near one chunk rather than the configured upload limit.

### Phase 4: Repair Transcribe history scaling and query shape

Severity: medium-high  
Change type: additive database migration and HTTP pagination

Implementation:

1. Add indexes for the actual query patterns:
   - `transcription_jobs(created_at)`;
   - `transcript_segments(job_id, start_time)`;
   - `speaker_mappings(job_id, speaker_label)` with uniqueness where existing
     data permits;
   - `speaker_embeddings(job_id, speaker_label)`;
   - `segment_edit_versions(segment_id, edited_at)`;
   - `segment_edit_versions(job_id)` if job-wide maintenance retains that field.
2. Add a small, explicit schema-version migration runner. `create_all()` creates
   tables but does not add indexes or columns to existing user databases.
   Migrations must be additive, transactional, and covered against a copied
   legacy schema.
3. Paginate `GET /api/v1/jobs` using stable cursor pagination ordered by
   `(created_at DESC, id DESC)`. Default to 50 and cap page size at 200.
4. Return a page envelope rather than an unbounded list:

   ```json
   {"items": [], "next_cursor": null}
   ```

5. Update the UI library view to append or replace pages intentionally; do not
   keep an unbounded DOM table.
6. Replace search's per-segment `db.get(TranscriptionJob, ...)` calls with one
   joined projection containing all `SearchMatch` fields.
7. Retain the 100-result cap as a quick guard. Treat SQLite FTS5 as a later
   structural option, not part of the initial query-shape fix. Leading-wildcard
   `LIKE` will still scan transcript text, but it should issue one query rather
   than up to 101.
8. Add pagination to segment edit history if real datasets show it growing
   materially; the index is required now regardless.

Compatibility and rollout:

- The `/jobs` response change is intentionally versioned under the existing v1
  route only if no external consumer depends on the list shape. Before merging,
  search the repository and release notes and ask the maintainer to confirm
  whether third-party API compatibility is promised.
- If compatibility is required, add `/api/v2/jobs` with the page envelope and
  retain a deprecated, capped v1 list temporarily.
- Back up the SQLite file before the first migration and leave a clear log entry
  recording schema version and outcome.

Tests and acceptance:

- Migrate a legacy database and assert every expected index exists via
  `PRAGMA index_list`/`index_info`.
- Compare query plans and assert job-scoped lookups use the new indexes.
- Populate more than 200 jobs with equal timestamps; traverse cursors and assert
  no duplicate or missing IDs.
- Count SQL statements during a 100-result search and assert the route performs
  one result query rather than N+1 job lookups.
- Verify the library UI remains usable with at least 10,000 synthetic jobs.

### Phase 5: Remove or redesign the unsafe batch-directory route

Severity: medium; potentially high if external callers use it  
Change type: quick removal if unused, structural redesign otherwise

The current UI implements batch upload by sending each selected file to the
normal `/transcribe` endpoint. No shipped caller uses `/transcribe/batch`, and
the route is absent from the documented endpoint table. Nevertheless, it is
discoverable through OpenAPI and requeues all retained audio files on every
invocation.

Decision and implementation:

1. Confirm with the maintainer whether `/api/v1/transcribe/batch` has an external
   consumer. Repository evidence indicates it does not.
2. Default action: remove the route and add a regression test that the supported
   UI batch flow continues to call `/transcribe` per file.
3. If an external directory-watcher workflow exists, replace the route with an
   explicit inbox service. Atomically claim each file by moving it from
   `incoming/` to `processing/`, store a unique source identity, and move it to
   `completed/` or `failed/`. Repeated scans must not create another job for a
   claimed identity.
4. Never use the persistent audio-retention directory as an input inbox.

Acceptance:

- Repeating a batch request cannot create a second job for the same source.
- Files retained for audio playback are never interpreted as new work.
- The supported route surface and README endpoint table agree.

### Phase 6: Complete structured model-harness adoption

Severity: high architectural non-conformance  
Change type: staged structural migration

This phase must preserve task-specific behaviour. "Structured" means every
model interaction declares and validates an output contract; it does not mean
forcing naturally long text into a single impractical JSON field without
chunking or degradation handling.

Implementation sequence:

1. Define app-owned Pydantic response schemas for OCR outputs:
   - vision OCR: extracted text plus optional model metadata;
   - cleanup: cleaned text;
   - structure: whitespace-only structured text;
   - translation: detected/source language and translated text;
   - confidence/self-assessment: numeric score and bounded rationale fields.
2. Reuse the existing title-stage integration as the reference for provider
   lifetime and `run_structured()` invocation.
3. Extend `model-harness` providers only where an existing OCR backend cannot be
   represented. Avoid retaining a parallel `_backend.py` contract after all
   callers migrate; provider configuration and endpoint policy should have one
   owner.
4. Preserve OCR's deterministic guards after schema validation. Schema-valid
   text may still be historically unsafe, so model-harness validation does not
   replace cleanup, structure, translation, or hallucination guards.
5. Preserve chunking and reassembly. Each chunk is a separate structured call,
   and its validated payload feeds the existing guard.
6. Define schemas for Transcribe summary and cleanup results. A summary should
   return explicit overview, topics, notable material, and action-item fields.
   Cleanup should return ordered speaker/timestamp segments rather than an
   unvalidated prose transcript.
7. Route non-streaming generation through `run_structured()`.
8. Do not retain token streaming merely for cosmetic progress if it bypasses the
   contract. Emit coarse SSE lifecycle events (`started`, `validating`, `done`,
   `error`) and return the validated result at completion. If structured
   streaming becomes a real requirement, add it to model-harness as a framed,
   schema-aware protocol in a separate proposal.
9. Close provider clients deterministically with async context managers.
10. After every app path is migrated, remove raw freeform chat helpers that have
    no remaining caller.

Public API changes:

- Transcribe summary and cleanup SSE payloads change from arbitrary text chunks
  to lifecycle events plus one typed result event. Version or compatibility
  handling must be chosen using the same v1 policy decision as Phase 4.
- Direct `/inference/generate` is a generic freeform surface and conflicts with
  the harness mandate. Remove it unless a concrete structured use case owns it;
  do not expose a schema-less public model proxy.

Tests and acceptance:

- Assert every in-scope model call reaches `run_structured()`; add a static audit
  test that rejects direct app imports or calls to provider chat-completion APIs.
- Exercise native schema, tool-call, prompted-JSON, and unsupported degradation
  paths using fake providers.
- Feed malformed, truncated, and prose-only outputs into every new schema and
  assert no unvalidated content reaches an output file or API result.
- Re-run OCR preservation guards against the existing fixtures and confirm raw
  fallback behaviour is unchanged.
- Test long chunked documents and transcripts near the configured context limit.

### Phase 7: Contributor and package-surface cleanup

Severity: medium/low  
Change type: quick wins followed by small package refactors

Implementation:

1. Make a combined in-scope pytest invocation collect safely. Prefer
   `--import-mode=importlib` in the root pytest configuration; if any suite
   relies on prepend-mode imports, package each test directory with
   `__init__.py` and use unique module paths instead.
2. Add the combined command to CONTRIBUTING and CI after it passes locally.
   Retain per-app matrix jobs for failure isolation and cross-platform signal.
3. Remove bare `pip install` and bare `pytest` setup instructions from
   CONTRIBUTING. Use `uv sync` and `uv run pytest` consistently with the stated
   workspace policy.
4. Correct stale documentation:
   - record that OCR title generation already uses `run_structured`;
   - list all supported Transcribe API routes or clearly identify OpenAPI as the
     canonical exhaustive surface;
   - update Transcribe's platformdirs-based database/upload defaults;
   - remove references to per-app `CLAUDE.md` files that do not exist;
   - update shared-package and application counts.
5. Bring `packages/output-layout/pyproject.toml` up to the suite metadata
   baseline: SPDX license expression, `license-files`, README, authors,
   classifiers, keywords, and project URLs. Add a package README describing its
   stable public API and path guarantees.
6. Move the near-identical OCR and Transcribe rotating-file logging setup into a
   small shared runtime module with app name, environment variable, filename,
   and data directory supplied as configuration. Keep app-local wrappers so
   import paths remain compatible.
7. Evaluate retry helpers separately. Their sync/async behaviour and exception
   sets differ, so share a tested policy or utility only if doing so makes those
   differences explicit; do not force them into one opaque decorator.

Tests and acceptance:

- One root command collects and runs all in-scope suites without module mismatch.
- CI retains Linux, Windows, and macOS coverage for OCR and Transcribe.
- Documentation commands execute as written from the documented directory.
- Built metadata for every in-scope wheel declares AGPL-3.0-or-later and includes
  its declared README/license files.
- REUSE, dependency audit, Ruff baseline, and changed-file format gates remain
  green.

### Phase 8: Move blocking export work off the event loop

Severity: medium  
Change type: quick performance fix

Transcribe's async export route loads the complete transcript, constructs PDF or
XML in process, writes an archive copy synchronously, and returns the complete
body. Long transcripts can block unrelated health, polling, and SSE requests.

Implementation:

1. Keep async database loading in the request task.
2. Convert exporters into pure synchronous renderers that accept detached data
   transfer objects, then invoke CPU-heavy PDF/XML rendering with
   `asyncio.to_thread()`.
3. Write the optional archive copy in the same worker thread using an atomic
   temporary file.
4. Log archive-write failure with job and destination context. Continue serving
   the requested download, preserving current user-visible behaviour.
5. For formats whose output can realistically exceed tens of megabytes, write to
   a temporary file and return `FileResponse` rather than retaining duplicate
   response buffers.

Acceptance:

- A deliberately slow fake renderer does not delay a concurrent health request.
- Archive failure is logged and the HTTP download still succeeds.
- Existing JSON, SRT, VTT, TXT, Markdown, PDF, OHMS, and TEI golden-output tests
  remain byte- or semantics-equivalent as appropriate.

## 4. Cross-Cutting Rules

- Preserve local-first behaviour and endpoint-policy validation. No refactor may
  introduce an undisclosed network call.
- Treat generated documents, audio, transcripts, API keys, and tokens as
  sensitive. Errors sent to logs or SSE must use existing token redaction.
- Use `pathlib.Path` and platformdirs-derived roots; test Windows path forms and
  macOS/Linux paths.
- Use additive, backed-up SQLite migrations. Never delete or rewrite user history
  merely to simplify a uniqueness constraint.
- Keep public domain errors independent of FastAPI in shared packages. Web routes
  translate typed errors into HTTP responses.
- Do not move FastAPI or Starlette into `shared-ui` solely for upload helpers.
- Preserve Draft and Graph compatibility for every shared-package API. Run their
  suites when a shared package changes even though their app code is outside the
  audit scope.
- Land instrumentation with structural changes: queue depth, operation duration,
  migration outcome, and history-persistence failure should be visible in local
  logs without recording document contents.

## 5. Definition of Done

The refactor programme is complete when all of the following are true:

1. Transcribe cannot execute two operations concurrently against one ASR engine,
   and queued work has explicit observable state.
2. OCR records and finalizes completed runs without any browser connection, and
   multiple SSE clients receive independent streams.
3. OCR and Transcribe uploads are streamed atomically to disk with bounded memory.
4. Transcribe job/history queries are indexed and paginated, and transcript
   search has no N+1 job lookup.
5. Repeating any supported batch operation cannot enqueue retained audio again.
6. Every in-scope model interaction is schema-declared and validated through
   model-harness, or has a documented non-generative reason for exemption.
7. No expected history, config, or archive failure is silently suppressed without
   a diagnostic and defined user-visible outcome.
8. One documented root test command runs all in-scope suites successfully, while
   per-app cross-platform CI remains green.
9. Public API and configuration documentation matches the shipped routes and
   platform-specific defaults.
10. Benchmarks or stress tests demonstrate linear completion persistence,
    bounded upload memory, responsive async endpoints during exports, and usable
    history views at the agreed scale fixtures.

## 6. Open Decisions Requiring Maintainer Confirmation

Only three product-level decisions remain; implementation must not silently pick
them:

1. Whether any external consumer relies on the undocumented
   `/api/v1/transcribe/batch` route. The default recommendation is removal.
2. Whether Transcribe's v1 HTTP response shapes carry a compatibility promise.
   If yes, introduce paginated and structured-result surfaces under v2; if no,
   update v1 and the shipped UI together.
3. Whether OCR should retain every legacy duplicate history row. The safe default
   is to preserve all existing rows, prevent new duplicates, and provide a
   separate opt-in repair tool rather than cleaning user data during migration.

These decisions do not block Phases 1-3, which can proceed without changing a
documented public response shape or deleting historical data.
