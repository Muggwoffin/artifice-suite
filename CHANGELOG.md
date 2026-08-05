# Changelog

All notable changes to the Artifice Suite are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Every app and package shares one version; see `ROADMAP.md` for the release policy.

## [Unreleased]

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
