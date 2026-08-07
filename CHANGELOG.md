# Changelog

All notable changes to the Artifice Suite are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Every app and package shares one version; see `ROADMAP.md` for the release policy.

## [Unreleased]

### Changed
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
  `Failed to resolve Python.Runtime.Loader.Initialize` — pywebview's
  pythonnet backend couldn't resolve the embedded `pythonXY.dll` because
  `PYTHONNET_PYDLL` was unset and `_internal/` (`sys._MEIPASS`) wasn't on
  `%PATH%`. Affected `artifice-ocr`, `artifice-graph`, and `artifice-draft`
  (byte-identical `window.py` copies). Non-frozen/dev runs unaffected. PR #63.

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
[0.2.0]: https://github.com/Muggwoffin/artifice-suite/compare/0.1.0...0.2.0
