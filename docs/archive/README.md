# Archive

Working documents that have served their purpose. They are kept, not deleted,
because the *reasoning* in them explains why parts of the codebase look the way
they do — but they are no longer current, and none of them should be read as
instructions.

**Nothing here is a live plan.** If a document here contradicts `CLAUDE.md`,
`README.md`, or an app's own `README.md`, those win.

Moved out of the repository root and the app roots on 2026-08-26. Every mention
of these files elsewhere was prose (`` `REFACTOR.md` says… ``), not a markdown
link, so no link was broken by the move — checked before moving.

## Completed proposals

| Document | Why it is here |
|---|---|
| `REFACTOR.md` | OSS compliance refactor. Its own header records the outcome: all three items shipped in PR #62. The full record, with every deviation, is `docs/superpowers/plans/2026-08-07-refactor-oss-compliance.md`. |
| `HUB_WINDOW_PLAN.md` | Hub native-window plan. Nothing referenced it. |
| `TROPY_INTEGRATION_PLAN.md` | Superseded by `apps/artifice-ocr/docs/TROPY_INTEGRATION.md`, which describes what was actually built. |
| `PLAN_PersonaeEdit.md` | `artifice-draft` feature plan from 2026-07-27. |
| `PLAN_graph.md` | `artifice-graph` plan from 2026-07-27 (was `apps/artifice-graph/PLAN.md`). |

## Session handovers

`handoffs/` holds one-shot briefs written for a specific session and never
updated afterwards. They are the most misleading documents in the repository if
read as current: several name models the suite no longer uses, describe stages
as "STUB — your job" that have since shipped, and give line numbers that have
moved.

They are kept because they record *why* a thing was built the way it was.

## A caution, from experience

`FOLLOW_UPS.md` is treated as authoritative by sub-agents, and on 2026-08-26
three of its entries were found stale — one already fixed, one with wrong counts,
one whose central claim was false. An agent briefed from a stale entry produces
confident, wrong work.

The same applies here, more so. **Verify a premise from this directory against
the code before acting on it.**
