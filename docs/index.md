# Artifice Suite — Documentation Index

This repository deliberately keeps most of its documentation at the root, so
the index exists to say where things are rather than to duplicate them.

## For users

| Document | What it covers |
|---|---|
| [README.md](../README.md) | What the suite is, quick start, app table |
| [INSTALL_OCR_WINDOWS.md](INSTALL_OCR_WINDOWS.md) | Installing Artifice OCR on Windows from the frozen build — including the SmartScreen prompt and why it appears |
| Each app's own `README.md` | Setup and entry points for that app (e.g. [`apps/artifice-ocr/README.md`](../apps/artifice-ocr/README.md)) |
| [Design_Philosophy.md](../Design_Philosophy.md) | The New Masses design system — tokens, typography, motion, anti-patterns |

## For contributors

| Document | What it covers |
|---|---|
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Setup, conventions, PR process |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Monorepo layout and the model-harness contract |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Contributor Covenant 2.1 |
| [SECURITY.md](../SECURITY.md) | Reporting a vulnerability |
| [ROADMAP.md](../ROADMAP.md) | Direction, release cadence, and the explicit out-of-scope list |
| [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) | The working task list and operational history (large, maintainer-facing) |
| [MAINTAINER_CHECKLIST.md](MAINTAINER_CHECKLIST.md) | Release checks CI does not run, open items only the maintainer can close, and the traps that have cost real time |
| [FOLLOW_UPS.md](../FOLLOW_UPS.md) | Deferred work. **Read the header** — it is treated as authoritative by sub-agents, and stale entries have produced confidently wrong work |

## Governance and release

| Document | What it covers |
|---|---|
| [CITATION.cff](../CITATION.cff) | How to cite the suite (Zenodo DOI) |
| [paper.md](../paper.md) | The JOSS submission paper |
| [CHANGELOG.md](../CHANGELOG.md) | Curated release history |

## Code layout

```
apps/                        # the four desktop applications
packages/                    # shared, version-locked packages
design-system/               # The New Masses design specification (reference only)
scripts/                     # dev tooling: audits, checks, agent dispatch
```

All four apps keep an identical internal layout. See [ARCHITECTURE.md](../ARCHITECTURE.md) for the
full map, and [CONTRIBUTING.md](../CONTRIBUTING.md) for the conventions a change must obey.

## Not documentation

`CLAUDE.md` at the root, and the per-app `CLAUDE.md` / `HANDOFF.md` files, are agent-orchestration
context for the maintainer's sub-agent fleet, not user or contributor documentation. Read them if
you are working on the tooling; ignore them otherwise.
