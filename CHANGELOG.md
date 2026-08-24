# Changelog

All notable changes to the Artifice Suite are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Every app and package shares one version; see `ROADMAP.md` for the release policy.

## [Unreleased]

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
