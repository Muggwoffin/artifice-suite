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

## [0.1.0-alpha] - 2026-07-27

First tagged release. See the [git tag `v0.1.0-alpha`](https://github.com/Muggwoffin/artifice-suite/tree/v0.1.0-alpha)
for the state of the tree at this point.

## [0.2.0-alpha]

Second tagged pre-release. See the [git tag `v0.2.0-alpha`](https://github.com/Muggwoffin/artifice-suite/tree/v0.2.0-alpha).

> Note: package metadata and `CITATION.cff` currently declare `0.1.0` while these
> two pre-release tags exist. Keeping tag names and package versions in lockstep
> is now enforced by `scripts/check-release-consistency.py` for future tags.

[Unreleased]: https://github.com/Muggwoffin/artifice-suite/compare/v0.2.0-alpha...HEAD
[0.1.0-alpha]: https://github.com/Muggwoffin/artifice-suite/releases/tag/v0.1.0-alpha
[0.2.0-alpha]: https://github.com/Muggwoffin/artifice-suite/releases/tag/v0.2.0-alpha
