# OSS Compliance & Maintainability Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: This repo's own orchestration model
> (see `CLAUDE.md` → "Sub-Agent Fleet") governs execution, not
> `superpowers:subagent-driven-development`. Tasks below are dispatched to the
> OpenCode fleet (`lead-engineer` implements, `tester` verifies, `code-reviewer` /
> `security-auditor` audit) via `scripts/dispatch-opencode.sh`, one task per
> dispatch, on branch `refactor/oss-compliance`. Steps use checkbox (`- [ ]`)
> syntax for tracking.

> **STATUS 2026-08-07: All 9 tasks complete.** All committed on
> `refactor/oss-compliance`, not merged to `main` — awaiting the
> maintainer's go-ahead per this plan's own "Do not merge" rule.
> `REFACTOR.md` (the original hand-written proposal) was never a tracked
> file — it existed only as an untracked scratch doc in the `main`
> checkout's working directory and never propagated into this branch's
> worktree, so this plan document is the only tracked record of what
> shipped. Three deviations from REFACTOR.md's literal proposal, beyond
> the five already logged in "Verified deviations" above, emerged during
> implementation and are worth a future reader knowing without
> re-deriving them:
>
> 1. **`migrate_legacy_directory`'s two independent try/except blocks**
>    (`_migrate_whole_dir`, fixed mid-Task-9). The first committed version
>    put `shutil.move` and `ensure_restricted` in one try block, so a
>    restrict-hardening failure after a successful move would make the
>    function claim the data was still at `legacy_path` — provably false.
>    Unreachable via the real `ensure_restricted` today (it already
>    swallows its own exceptions by contract) but was a real latent
>    defect. Split into two blocks; a restrict failure now returns
>    `default_path` regardless.
> 2. **One pre-existing, out-of-scope bug found and fixed on request**
>    (not part of REFACTOR.md, not part of this plan's original task
>    list): `artifice-ocr`'s `validate_contained()` called
>    `normalise_path` outside any try/except, so a malformed path 500'd
>    instead of 400'ing. Fixed with TDD (confirmed the regression test
>    failed against the pre-fix code before trusting the fix).
> 3. **Mock-patch-target corrections were a recurring theme, not a
>    one-off.** Every app migrated to a shared module needed at least one
>    test's `mock.patch(...)` target corrected from "where the function
>    is defined" to "where it's looked up" — a module-level `from X import
>    Y` in the new shared module creates a separate binding from
>    whatever the old per-call local import bound. This bit
>    `artifice-graph`'s `ensure_restricted` tests specifically (Task 9)
>    and is worth watching for in any future shared-module extraction.
>
> **Verified clean** by an `arch-auditor-docs` dangling-reference sweep
> covering all six deleted-name/deleted-body search patterns across all
> four apps: no orphaned duplicate implementations, no dangling private-name
> imports, no leftover module-level state. Full test suite green across
> all four apps and three shared packages (3 pre-existing, unrelated
> `artifice-draft` failures — missing optional `readability-lxml`
> dependency, confirmed present before this branch existed).

**Goal:** Consolidate three duplicated subsystems (path validation, local-server
bootstrap, legacy-data migration) into shared packages, closing a real security
gap in the process, with zero behavior change to any app's happy path.

**Architecture:** Extract to `packages/shared-ui/shared_ui/` (path validation,
server bootstrap — both already-shared, `src/`-less packages every app depends
on) and `packages/secure-io/src/secure_io/` (migration — already has a `src/`
layout and already owns `ensure_restricted`, which one of the two migration call
sites already uses). Each app's own module becomes a thin wrapper or is deleted
outright once the shared call site is proven equivalent by tests.

**Tech Stack:** Python 3.11+, pytest, hatchling (both shared packages), FastAPI
(graph, ocr, draft's web layers), pydantic-settings (transcribe, graph configs).

## Global Constraints

- **No breaking changes.** Every app must behave identically post-refactor on
  its happy path. Where the refactor closes a real gap (see Task 1), that is a
  narrowly-scoped exception, called out explicitly, never silent.
- **Backward compatibility.** Existing configs, env vars, and on-disk layouts
  (legacy paths, default paths, env var *names*) are unchanged.
- **Correct package layout.** `packages/shared-ui/shared_ui/<file>.py` — **no**
  `src/` level. `packages/secure-io/src/secure_io/<file>.py` — **has** a `src/`
  level. These two packages are NOT laid out the same way; do not "fix" one to
  match the other.
- **No new dependencies.** All four apps already depend on
  `artifice-shared-ui>=0.2.0` and `artifice-secure-io>=0.2.0` via the uv
  workspace (`pyproject.toml` `[tool.uv.sources]`). No app-level `pyproject.toml`
  edits are needed to consume new modules in these packages.
- **Every task ends with the full test suite green** for every app it touches,
  run via `uv run pytest` from that app's directory (each app's
  `[tool.pytest.ini_options]` sets `testpaths = ["tests"]`), plus the shared
  package's own new unit tests.
- **Deprecation, not deletion, until the owning app's tests are green against
  the shared call.** Once green, delete the old implementation — REFACTOR.md's
  "mark deprecated but leave intact" was written before this plan verified each
  call site line-by-line; leaving dead duplicate code behind is itself the kind
  of maintenance burden this refactor exists to remove. State this explicitly
  to the maintainer if it's contentious — it isn't blocking, just flagged.

## Verified deviations from REFACTOR.md (read before dispatching any task)

1. **Path.** REFACTOR.md says `packages/shared-ui/src/shared_ui/path_validation.py`.
   The real layout has no `src/` (`packages/shared-ui/shared_ui/__init__.py`,
   confirmed by `[tool.hatch.build.targets.wheel] packages = ["shared_ui"]`).
   Use `packages/shared-ui/shared_ui/path_validation.py`.
2. **Path-validation security gap is real, not hypothetical.** `artifice-ocr`'s
   `validation.py` normalises backslashes and rejects a POSIX-hosted server
   being handed a Windows-style absolute path (`C:/Windows`) before `resolve()`
   can misinterpret it as relative-to-cwd and admit it. `artifice-graph`'s
   `_validate_directory()` (`apps/artifice-graph/src/artifice_graph/web/server.py:193`)
   has neither check — it passes `raw` straight to `Path(raw)`. Both platforms
   (native Windows, WSL2 Ubuntu) are supported per `CLAUDE.md`, so a
   POSIX-hosted `artifice-graph` server is a real deployment target, and this
   gap is closed by the consolidation, not introduced by it.
3. **Signatures in REFACTOR.md are aspirational, not measured.** Real function
   names: `_normalise` (ocr, not `_normalise_path`), `_build_allowed_roots()`
   (ocr, zero args — the env var name `ARTIFICE_OCR_ALLOWED_ROOTS` is
   hardcoded inside it; graph hardcodes `ARTIFICE_GRAPH_ALLOWED_ROOTS` the same
   way). Task 1's target signature below parametrises the env var name so one
   function serves both.
4. **Server bootstrap duplication is partial, not uniform.** `_free_port` and
   `_wait_for_server` are duplicated verbatim across all three apps'
   `web/server.py`. `_start_server_thread`, `_report_startup_failure`, and
   `_ensure_std_streams` exist in `artifice-ocr` and `artifice-graph` but
   **not** in `artifice-draft` — draft starts its thread inline in `main()`
   (`apps/artifice-draft/src/artifice_draft/web/server.py:546-550`), has no
   error-dialog function (a `_wait_for_server` failure just prints a warning
   and continues), and does the `sys.stdout is None` guard inline rather than
   as a named function. `_port_available` exists in ocr
   (`apps/artifice-ocr/src/artifice_ocr/web/server.py:446`) — check whether
   graph/draft have it too before assuming three-way parity; REFACTOR.md's
   "17 occurrences" figure is unverified and should not be treated as a target
   to hit.
5. **The three "migration functions" are not one shape.** REFACTOR.md's
   proposed single signature
   (`migrate_legacy_path(legacy_path, default_path, user_override_signal,
   collision_strategy, apply_restrictions=False) -> Path`) does not fit what
   the code actually does:
   - `artifice-transcribe._migrate_legacy_db` — single file, `shutil.move`,
     collision → keep existing + `logger.warning`.
   - `artifice-transcribe._migrate_legacy_uploads` — directory, **file-by-file**
     move (subdirectories under legacy `uploads/` are silently left behind —
     an existing quirk, preserve it, do not "fix" it), collision → keep
     existing + `logger.warning` per file, plus cleanup of an empty legacy dir.
   - `artifice-graph._resolve_user_data_dir` — whole-directory `shutil.move`,
     collision → **silent skip, no warning** (different from transcribe's
     warn-on-collision), symlink refusal on the legacy path, re-applies
     `secure_io.ensure_restricted` to the migrated `config.json`, and falls
     back to the legacy dir on any exception so the app never fails to start.

   Forcing these into one five-parameter function is itself the kind of
   over-engineering REFACTOR.md says it wants to eliminate. **Task 7 below
   specifies two functions instead — `migrate_legacy_file` and
   `migrate_legacy_directory`** — matching the two real shapes. This is a
   deliberate, documented departure from REFACTOR.md's literal proposal;
   flag it to the maintainer as a design call, not an oversight.

---

## Dispatch mechanics (applies to every task)

For each task:
1. Write the OpenCode brief to a scratch file (objective / scope / constraints
   / deliverable, per `CLAUDE.md` → "Task brief format") and dispatch with
   `bash scripts/dispatch-opencode.sh lead-engineer <brief-file>`.
2. Poll `--status` for completion; on `exit=137`/`143`, read the log before
   re-dispatching — work often survives a kill.
3. Dispatch `tester` with a brief naming the exact test commands to run (the
   app(s) touched, plus the shared package's own tests). Do not let it infer
   scope.
4. For Tasks 1 and 7 (security-relevant: path validation, permission
   re-application) additionally dispatch `security-auditor` (read-only) before
   the task is considered done. Route findings back to the maintainer before
   any follow-up code changes, per `CLAUDE.md` → "Escalation".
5. Dispatch `code-reviewer` with the exact two-or-three files changed (its
   large-brief failure mode returns nothing — keep briefs small, per memory
   `oss-reviewer-needs-tiny-briefs` / the `code-reviewer` incident in
   `CLAUDE.md`).
6. Commit only after tester is green and code-reviewer's findings (if any)
   are resolved or explicitly deferred to the maintainer.

---

### Task 1: Implement `path_validation.py` shared utility

**Files:**
- Create: `packages/shared-ui/shared_ui/path_validation.py`
- Test: `packages/shared-ui/tests/test_path_validation.py` (new `tests/` dir —
  none exists yet for this package)

**Interfaces:**
- Produces:
  ```python
  def normalise_path(raw: str, field_name: str) -> str: ...
  def build_allowed_roots(env_var: str) -> list[Path]: ...
  def validate_path(raw: str, field_name: str, *, allowed_roots_env_var: str) -> str: ...
  ```
  `validate_path` raises `ValueError` (no web-framework dependency — copy
  ocr's framework-agnostic approach, since graph's caller already wraps
  exceptions in `HTTPException` and can keep doing so at the call site).
  Behavior is the union of ocr's `_normalise`/`_build_allowed_roots`/
  `validate_path` (backslash normalisation, POSIX Windows-drive rejection,
  hidden-component rejection) — this is the stricter of the two existing
  implementations and becomes the one shared baseline.

- [ ] **Brief `lead-engineer`:** implement the three functions above in the new
  file, ported from `apps/artifice-ocr/src/artifice_ocr/validation.py` verbatim
  in logic (rename `_normalise`→`normalise_path`, `_build_allowed_roots()`→
  `build_allowed_roots(env_var)` taking the env var name as a parameter instead
  of hardcoding it, `validate_path` gains the `allowed_roots_env_var` keyword
  and calls `build_allowed_roots(allowed_roots_env_var)`). Preserve every
  docstring's reasoning (the POSIX drive-letter comment, the hidden-component
  comment). Write `packages/shared-ui/tests/test_path_validation.py` covering:
  empty string, backslash normalisation, POSIX Windows-drive rejection
  (`os.name == "posix"` gated — skip or mock on Windows CI), path outside all
  allowed roots, path inside `Path.cwd()`, hidden-component rejection below the
  matched root, and the `allowed_roots_env_var` parameter actually changing
  which env var is read (set two different env vars, confirm each only takes
  effect when named).
- [ ] **Verify:** `cd packages/shared-ui && uv run pytest tests/test_path_validation.py -v` — all pass.
- [ ] Dispatch `security-auditor`: read `packages/shared-ui/shared_ui/path_validation.py`
  only, confirm it does not weaken any check present in either original
  implementation.
- [ ] Dispatch `code-reviewer` on the one new file + its test.
- [ ] Commit: `feat(shared-ui): add shared path_validation utility`

---

### Task 2: Migrate `artifice-ocr` to shared path validation

**Files:**
- Modify: `apps/artifice-ocr/src/artifice_ocr/validation.py` (replace body with
  a thin re-export, or delete and update its one import site — check
  `apps/artifice-ocr/src/artifice_ocr/web/server.py` and any other importer
  first with `grep -rn "from .*validation import\|from artifice_ocr.validation"`)
- Modify: `apps/artifice-ocr/src/artifice_ocr/web/validation.py:18` — found by
  Task 1's security-auditor pass, not in REFACTOR.md's original scope:
  `validate_contained()` imports the *private* name `_normalise` directly
  (bypassing `validate_path` entirely, since containment-within-an-arbitrary-directory
  is a different check from allowed-roots validation). Once
  `artifice_ocr/validation.py` stops defining `_normalise` locally, update this
  import to the shared module's public `normalise_path`. `validate_directory()`
  in the same file calls `validate_path(raw, field_name)` (2-arg) — that stays
  compatible unchanged as long as `artifice_ocr.validation.validate_path` keeps
  its existing 2-arg public signature as a thin wrapper (see Interfaces below).
- Test: existing `apps/artifice-ocr/tests/test_web.py` path-validation cases
  must still pass unmodified (they exercise behavior, not the internal module
  path) — do not edit test expectations, only the import if it references
  `artifice_ocr.validation` internals directly.

**Interfaces:**
- Consumes: `shared_ui.path_validation.validate_path(raw, field_name, allowed_roots_env_var="ARTIFICE_OCR_ALLOWED_ROOTS")` from Task 1.

- [ ] **Brief `lead-engineer`:** grep every import of `artifice_ocr.validation`
  across `apps/artifice-ocr/src` and `apps/artifice-ocr/tests`. Replace the
  three functions in `validation.py` with calls into
  `shared_ui.path_validation`, preserving `validation.py`'s existing public
  names (`validate_path`, etc.) as thin wrappers so no call site needs to
  change — this keeps the change backward-compatible at the import level, not
  just behaviorally. Pass `allowed_roots_env_var="ARTIFICE_OCR_ALLOWED_ROOTS"`
  at the wrapper boundary.
- [ ] **Verify:** `cd apps/artifice-ocr && uv run pytest tests/ -v` — full suite green, not just the validation tests.
- [ ] Manual check (per REFACTOR.md's own validation step): start the ocr
  server, exercise a directory-selection path in the browser — reject-outside-root
  and accept-inside-root both still work. Use the Chrome tooling per
  `CLAUDE.md`'s design-director loop if a UI path is involved; otherwise
  `curl` the endpoint directly.
- [ ] Dispatch `code-reviewer` on the modified `validation.py` + any import-site diffs.
- [ ] Commit: `refactor(ocr): use shared path_validation utility`

---

### Task 3: Migrate `artifice-graph` to shared path validation

**Files:**
- Modify: `apps/artifice-graph/src/artifice_graph/web/server.py:193-239`
  (`_validate_directory`)

**Interfaces:**
- Consumes: `shared_ui.path_validation.validate_path(raw, field_name, allowed_roots_env_var="ARTIFICE_GRAPH_ALLOWED_ROOTS")`.
- `_validate_directory` keeps its name and `HTTPException`-raising signature
  (callers at lines 275/277/279/885/887/889 are unchanged) — it becomes a
  4-line wrapper: call `shared_ui.path_validation.validate_path`, catch
  `ValueError`, re-raise as `HTTPException(status_code=400, detail=str(exc))`.

- [ ] **Brief `lead-engineer`:** implement the wrapper exactly as specified
  above. This is the task that closes the real gap in deviation #2 above —
  graph gains backslash normalisation and POSIX Windows-drive rejection it
  didn't have. Note this explicitly in the commit message since it's a
  behavior change, even though it's a strictly-more-correct one.
- [ ] **Verify:** `cd apps/artifice-graph && uv run pytest tests/ -v` — full
  suite green, specifically `tests/test_web_security.py` and
  `tests/test_regression.py`.
- [ ] Dispatch `security-auditor`: confirm the new gap-closing behavior doesn't
  reject any previously-valid graph input (e.g. a legitimate Windows path on a
  native Windows deployment — `_normalise`'s POSIX gate must not fire there).
- [ ] Dispatch `code-reviewer` on the modified section.
- [ ] Commit: `refactor(graph): use shared path_validation utility, close POSIX Windows-path gap`

---

### Task 4: Implement `server_bootstrap.py` shared utility

**Files:**
- Create: `packages/shared-ui/shared_ui/server_bootstrap.py`
- Test: `packages/shared-ui/tests/test_server_bootstrap.py`

**Interfaces:**
- Produces:
  ```python
  def free_port() -> int: ...
  def port_available(port: int) -> bool: ...
  def wait_for_server(port: int, *, timeout: float = 10.0) -> bool: ...
  def start_server_thread(app, port: int) -> tuple[threading.Thread, list[BaseException]]: ...
  def report_startup_failure(app_name: str, port: int, thread, errors: list[BaseException]) -> None: ...
  def ensure_std_streams() -> None: ...
  ```
  `start_server_thread` takes the FastAPI/ASGI `app` object as a parameter
  (each app's is different) and runs `uvicorn.run(app, host="127.0.0.1",
  port=port, log_level="warning")` in a daemon thread, exactly as ocr and
  graph do today. `report_startup_failure` gains an `app_name: str` parameter
  so the message/dialog title is per-app (was hardcoded `"ArtificeOCR"` in
  ocr's version) — this is the one signature change from the as-is code,
  needed to make the function shared at all.

- [ ] **Brief `lead-engineer`:** port from `apps/artifice-ocr/src/artifice_ocr/web/server.py:440-518`
  (the fuller of the two ocr/graph implementations), parametrising `app_name`
  into `report_startup_failure` and `app` into `start_server_thread`. Write
  `packages/shared-ui/tests/test_server_bootstrap.py` covering: `free_port`
  returns a bindable port, `port_available` true/false around an actually-bound
  socket, `wait_for_server` true when something listens within timeout and
  false when nothing does, `start_server_thread` returns a running thread for
  a trivial ASGI app and populates `errors` when the app raises on startup,
  `ensure_std_streams` replaces `None` streams and leaves real ones alone.
- [ ] **Verify:** `cd packages/shared-ui && uv run pytest tests/test_server_bootstrap.py -v`.
- [ ] Dispatch `code-reviewer` on the one new file + its test.
- [ ] Commit: `feat(shared-ui): add shared server_bootstrap utility`

---

### Task 5: Migrate `artifice-ocr` to shared server bootstrap

**Files:**
- Modify: `apps/artifice-ocr/src/artifice_ocr/web/server.py:440-518` (delete
  the six local functions, call the shared ones)

**Interfaces:**
- Consumes: all six functions from Task 4. `report_startup_failure(app_name="ArtificeOCR", ...)`.

- [ ] **Brief `lead-engineer`:** replace the local definitions with imports
  from `shared_ui.server_bootstrap`; update `main()` call sites to pass `app`
  and `app_name="ArtificeOCR"` where the new signatures need them. ocr's
  tkinter-messagebox fallback behavior in `_report_startup_failure` must be
  preserved verbatim in the shared version (Task 4 already specifies this) —
  confirm the ported version still shows the dialog.
- [ ] **Verify:** `cd apps/artifice-ocr && uv run pytest tests/ -v`, then
  manually start the server (`uv run artifice-ocr` or equivalent per that
  app's entry point) and confirm it still opens on a free port and the window/
  browser opens.
- [ ] Dispatch `code-reviewer` on the modified `server.py` section.
- [ ] Commit: `refactor(ocr): use shared server_bootstrap utility`

---

### Task 6: Migrate `artifice-graph` and `artifice-draft` to shared server bootstrap

**Files:**
- Modify: `apps/artifice-graph/src/artifice_graph/web/server.py:1407-1477+`
- Modify: `apps/artifice-draft/src/artifice_draft/web/server.py:440-585`

**Interfaces:**
- Same as Task 5, `app_name="ArtificeGraph"` / `app_name="ArtificeDraft"`.
- **Draft-specific:** draft has no existing `_start_server_thread`,
  `_report_startup_failure`, or `_ensure_std_streams` — it inlines a
  `threading.Thread(...)` call and a bare `print()` warning on
  `_wait_for_server` failure (no dialog). When migrating draft, **do not
  introduce a dialog it never had** — call `shared_ui.server_bootstrap.start_server_thread`
  for the thread, but keep draft's own `print`-only failure path rather than
  wiring in `report_startup_failure`'s tkinter dialog. This preserves draft's
  existing UX; adding a dialog it never showed would be an undocumented
  behavior change, exactly what the Global Constraints forbid.

- [ ] **Brief `lead-engineer` (graph):** same pattern as Task 5, `app_name="ArtificeGraph"`.
- [ ] **Verify (graph):** `cd apps/artifice-graph && uv run pytest tests/ -v`.
- [ ] **Brief `lead-engineer` (draft):** replace `_free_port`/`_wait_for_server`
  with the shared versions; replace the inline `threading.Thread` construction
  with `shared_ui.server_bootstrap.start_server_thread(app, port)`; leave the
  `_wait_for_server`-failure branch's `print()`-and-continue behavior
  untouched.
- [ ] **Verify (draft):** `cd apps/artifice-draft && uv run pytest tests/ -v`.
- [ ] These two are independent (different apps, no shared state) — dispatch
  both `lead-engineer` briefs in parallel per `CLAUDE.md`'s two-in-parallel
  precedent (path-validation phase 2/3), then both `tester` verifications in
  parallel.
- [ ] Dispatch `code-reviewer` twice, once per app, small briefs each.
- [ ] Commit (two commits, one per app): `refactor(graph): use shared server_bootstrap utility` / `refactor(draft): use shared server_bootstrap utility`

---

### Task 7: Implement `migration.py` shared utility

**Files:**
- Create: `packages/secure-io/src/secure_io/migration.py`
- Test: `packages/secure-io/tests/test_migration.py`

**Interfaces:**
- Produces (see "Verified deviations" #5 for why this is two functions, not REFACTOR.md's one):
  ```python
  def migrate_legacy_file(
      legacy_path: Path,
      default_path: Path,
      *,
      user_overrode_default: bool,
      logger: logging.Logger,
  ) -> None:
      """Move legacy_path -> default_path if the user hasn't overridden the
      default and default_path doesn't already exist. Logs a warning (does
      not raise) if both exist; keeps the existing default in place."""

  def migrate_legacy_directory(
      legacy_path: Path,
      default_path: Path,
      *,
      user_overrode_default: bool,
      move_mode: Literal["whole_dir", "files_only"],
      collision_is_silent: bool,
      refuse_symlink: bool = False,
      restrict_filename: str | None = None,
      cleanup_empty_legacy: bool = False,
      logger: logging.Logger,
  ) -> Path:
      """Move legacy_path -> default_path per move_mode. whole_dir uses
      shutil.move on the directory; files_only moves only files directly
      under legacy_path (subdirectories are left behind, matching
      transcribe's existing uploads-migration behavior). collision_is_silent
      controls whether an existing default_path is a silent skip (graph's
      current behavior) or a logged warning (transcribe's current behavior)
      — this parameter exists specifically because the two apps disagree
      today and neither call site's behavior may change. refuse_symlink
      refuses (logs + returns default_path unmoved) if legacy_path is a
      symlink. restrict_filename, if set, calls
      secure_io.ensure_restricted(default_path / restrict_filename) after a
      successful whole_dir move. Returns default_path always — on any
      exception during the move, logs a warning and returns legacy_path as a
      fallback (the app must still start)."""
  ```

- [ ] **Brief `lead-engineer`:** implement both functions. `migrate_legacy_file`
  ports `artifice-transcribe`'s `_migrate_legacy_db` body exactly (collision →
  warn + keep existing, always). `migrate_legacy_directory` must reproduce,
  parametrised, **both** graph's `_resolve_user_data_dir` (`move_mode="whole_dir"`,
  `collision_is_silent=True`, `refuse_symlink=True`, `restrict_filename="config.json"`,
  exception fallback to `legacy_path`) and transcribe's `_migrate_legacy_uploads`
  (`move_mode="files_only"`, `collision_is_silent=False`, `cleanup_empty_legacy=True`).
  Write `packages/secure-io/tests/test_migration.py` with one test class per
  function, and within `migrate_legacy_directory`'s tests, one subtest per
  parameter combination actually used by a real call site (don't test the
  full combinatorial space — only what Tasks 8 and 9 will call with) plus the
  symlink-refusal and exception-fallback paths explicitly, since those are the
  security-relevant branches.
- [ ] **Verify:** `cd packages/secure-io && uv run pytest tests/test_migration.py -v`.
- [ ] Dispatch `security-auditor`: focus on `refuse_symlink` and
  `restrict_filename` — confirm the symlink check happens before any
  filesystem mutation (TOCTOU: check-then-move must not leave a window), and
  that `ensure_restricted` is called on the *destination* path, never the
  legacy one.
- [ ] Dispatch `code-reviewer` on the one new file + its test.
- [ ] Commit: `feat(secure-io): add shared legacy-path migration utilities`

---

### Task 8: Migrate `artifice-transcribe` to shared migration utilities

**Files:**
- Modify: `apps/artifice-transcribe/src/artifice_transcribe/config.py:44-121+`
  (`_migrate_legacy_db`, `_migrate_legacy_uploads`)

**Interfaces:**
- Consumes: `secure_io.migration.migrate_legacy_file` and
  `secure_io.migration.migrate_legacy_directory` from Task 7, called with the
  exact parameters listed in Task 7's brief for transcribe's two call sites.

- [ ] **Brief `lead-engineer`:** replace both methods' bodies with calls into
  `secure_io.migration`, passing `user_overrode_default=(self.database_url !=
  _DEFAULT_DB_URL)` / `(self.upload_dir != str(_DEFAULT_UPLOAD_PATH))` exactly
  as the current `if` guards do. Keep the methods as thin wrappers on
  `Settings` (they're called from `model_post_init`) rather than inlining the
  shared calls directly into `model_post_init` — smaller diff, same test
  surface.
- [ ] **Verify:** `cd apps/artifice-transcribe && uv run pytest tests/test_migration.py tests/test_security.py -v`, then full suite `uv run pytest tests/ -v`.
- [ ] Dispatch `code-reviewer` on the modified `config.py` section.
- [ ] Commit: `refactor(transcribe): use shared migration utilities`

---

### Task 9: Migrate `artifice-graph` to shared migration utilities

**Files:**
- Modify: `apps/artifice-graph/src/artifice_graph/config.py:193-243`
  (`_resolve_user_data_dir`)

**Interfaces:**
- Consumes: `secure_io.migration.migrate_legacy_directory(move_mode="whole_dir", collision_is_silent=True, refuse_symlink=True, restrict_filename="config.json", ...)`.

- [ ] **Brief `lead-engineer`:** replace `_resolve_user_data_dir`'s body with
  a call into `secure_io.migration.migrate_legacy_directory`, keeping the
  function's own signature (`() -> Path`) and its call site in
  `_get_user_data_dir` (line 259) unchanged.
- [ ] **Verify:** `cd apps/artifice-graph && uv run pytest tests/test_config_migration.py -v`, then full suite `uv run pytest tests/ -v`.
- [ ] Dispatch `security-auditor` a second time on this specific call site:
  confirm the symlink-refusal and post-move `ensure_restricted` behavior is
  bit-for-bit preserved through the parametrised call (this is the app that
  currently protects `~/.callosip`, real secret-bearing config).
- [ ] Dispatch `code-reviewer` on the modified section.
- [ ] Commit: `refactor(graph): use shared migration utilities`

---

## Final validation (after Task 9)

- [ ] Run the full test suite for all four apps plus both shared packages
  from the workspace root: `uv sync --extra all` then `uv run pytest` per app
  directory (no root-level aggregate runner exists — confirm this remains
  true rather than assuming one was added).
- [ ] Dispatch `arch-auditor-docs`: confirm no dangling references to the
  deleted local implementations remain anywhere in `apps/*/src`, `apps/*/tests`,
  or docs (`grep -rn "_migrate_legacy_db\|_resolve_user_data_dir\|_validate_directory\|_normalise\b"`
  across the repo, expecting only the new shared-module definitions and the
  thin-wrapper call sites to remain).
- [ ] Update `CLAUDE.md`'s harness-mandate correction block (the one dated
  2026-07-29) is unrelated to this refactor — do not touch it. Do add a short,
  dated note to `REFACTOR.md` itself recording what shipped vs. what
  REFACTOR.md originally proposed (the two-function migration API instead of
  one, the corrected shared-ui path), so the next reader doesn't rediscover
  deviations #1–#5 from scratch.
- [ ] Report status table to the maintainer per `CLAUDE.md` → "Task Completion
  Checklist": task / status / evidence (test output, commit SHA) for all 9
  tasks plus final validation.
- [ ] Do **not** merge to `main` without the maintainer's explicit go-ahead —
  offer the branch for review; per `CLAUDE.md` this is the maintainer's call,
  not the orchestrator's.
