# Artifice Suite — Implementation Plan

**Status as of 2026-07-28 (session 3).** This document records what has been built and
verified, and stages the remaining work. It is the project to-do list; `ARCHITECTURE.md` describes
the system as designed, `CLAUDE.md` governs how agents work on it, and `Design_Philosophy.md` is
the binding design authority.

> **Phase 1 is signed off. Phase 2 is now unblocked.** Both of its prerequisites dissolved under
> audit on 2026-07-28: the canonical web-layer layout had already been settled by commit `0979359`
> and never recorded, and the "fourteen breakpoints in graph" figure was a miscount — there are 7,
> and the `rem` values it listed were element `max-width` rules, not media queries. CORS and both
> HIGH path traversals are also closed. Start from **Part IV**, which was re-derived from
> measurement on that date.
>
> **This plan drifted badly from the tree, and that is the standing risk with it.** Three recorded
> claims were refuted in one audit, two of them gating a phase. Prefer measuring over trusting any
> figure here that carries no verification date — and when you measure, write the date next to
> what you found.

**Reading the status marks:**

| Mark | Meaning |
|---|---|
| **Verified** | Confirmed against the running system or measured output, not inferred from a diff |
| **Landed** | Code is in the working tree, correctness reasoned but not independently confirmed |
| **Open** | Not started |
| **Blocked** | Waiting on a decision or another item |

---

## Part I — Work completed

### I.1 Agent fleet

The orchestrator drives five sub-agents across two runtimes. `security-auditor` moved off Claude
Code to reduce Claude token consumption; it is a safe candidate for a cheaper model because it is
read-only and its findings route through the orchestrator before any code is written. It went to
Gemini first, then to `opencode-go/qwen3.7-max` — Gemini worked but was rate-limited into
uselessness, running **43 minutes at 2.8% CPU** on a real audit without producing anything.

| Agent | Runtime | Model | Status |
|---|---|---|---|
| `lead-engineer` | OpenCode | `opencode-go/deepseek-v4-pro` | **Verified** |
| `tester` | OpenCode | `opencode-go/kimi-k3` | **Verified** |
| `arch-auditor-docs` | OpenCode | `github-copilot/claude-sonnet-4.6` | **Verified** — moved off `glm-5.2` 2026-07-28 for throttling; banner re-asserted after the swap |
| `security-auditor` | OpenCode | `opencode-go/qwen3.7-max` (read-only) | **Verified** on the banner — audit re-dispatched after the Gemini swap |
| `ui-ux` | Claude Code | `sonnet` | **Verified** |

`scripts/smoke-test-agents.sh` asserts registration, model identity and read-only tooling.
Re-run after the Gemini migration: **13 passed, 0 failed** — every agent confirmed answering on its
intended model, so none is silently falling back to the default `build` agent.

### I.2 artifice-graph design pass — **Verified**

Ten defects were identified by reviewing the rendered pages in Chrome at four widths, then fixed
and re-measured. Every "after" figure below came from the live DOM, not from reading source.

| # | Defect | Before | After |
|---|---|---|---|
| 1 | Run button painted over stage description | 11.1px overlap | 26.5px clearance |
| 2 | Five off-scale container radii (3/2/2/2/0px) | ad hoc | all `--radius-lg` |
| 3 | Masthead one step below its assigned size | 44.8px | 84px (`--text-hero`) |
| 4 | Phantom scrollbar inside the tab strip | 15px gutter + arrows | gutter 0 |
| 5 | Stat row orphaned its last tile | 3+1, mixed widths | even at 4 and 5 tiles |
| 6 | Preset grid was not a grid | 231/152/153/235px | 262×4 |
| 7 | Native blue checkboxes on a warm palette | `appearance: auto` | custom, 24×24, accent |
| 8 | About page ran to ~110 characters per line | 940px | 704px (44rem) |
| 9 | Saturated badges; person/event hues 8° apart | solid fills | muted tints, hues respaced, 5.5–7.8:1 |
| 10 | `.foot` defined twice, conflicting | pipeline.css won | single definition |

Two further items were fixed on the same surface: `--error` was warmed from `#dc3545` to `#a8322b`
because the Bootstrap red read as an off-palette alert against the cream ground, and stage badges
now start blank on all five cards rather than one arbitrarily reading "idle".

Before/after screenshots: `~/Pictures/artifice-graph-design-review-2026-07-27/`.

### I.3 Functional repairs — **Verified**

- **`pipeline.js` was missing roughly half its module.** `runStage`, `wireStageButtons`,
  `wireFilePickers`, `setStageState`, `stageCards`, `running` and `clearLog` were referenced in
  `init()` but defined nowhere, so the page threw 22 uncaught exceptions on load. No stage button
  was wired, Run All and Demo did nothing, the SSE log never connected, and the stat tiles showed
  `—` while `/api/state` returned real data. Rebuilt: 346 → 636 lines, console clean, tiles live.
- **`server.py` called an undefined `logger`** in five exception handlers, converting every handled
  error into a `NameError`. Module-level logger added.

### I.4 Design token consolidation — **Verified**

`packages/shared-ui/tokens.css` is now the single source of truth (26 → 56 tokens). The app-local
duplicate is **deleted**, not mirrored: `artifice-graph` serves the canonical file directly through
a `/shared` StaticFiles mount, so there is nothing to keep in sync.

- 30 tokens promoted upstream (shadows, radius, spacing, motion, layout, mono), each matching a
  value already specified in `Design_Philosophy.md`.
- `@media (prefers-color-scheme: dark)` promoted — shared-ui previously could not follow the OS.
- 6 dead `--w-*` "word-status" tokens deleted (LudwigLang residue; zero references).
- `--font-sans` renamed to `--font-label`, no alias. `Design_Philosophy.md` updated to match, and
  §3 now names the token for every font role so the ambiguity cannot recur.

  > **Scope correction, 2026-07-28.** This originally read "across all call sites", which was not
  > true. The rename covered `packages/shared-ui` and `artifice-graph`; `artifice-ocr`,
  > `artifice-draft` and `artifice-transcribe` each kept a local `--font-sans` declaration and
  > between them 18 `var(--font-sans)` call sites, all still present today. It is true **now** —
  > the three apps were reconciled on 2026-07-28, verified by
  > `grep -rnE '(^\s*--font-sans\s*:|var\(\s*--font-sans\s*\))' apps/*/src/*/web/static/css/*.css`
  > returning nothing.
  >
  > The work was real; only its scope was mis-stated. That is the third instance found today of a
  > narrow result recorded as a suite-wide one — see also the canonical-layout prerequisite and the
  > breakpoint count under Phase 2. It also caused a concrete error: a token-retirement brief
  > written on 2026-07-28 instructed an agent to *preserve* `--font-sans` as legitimate app-only
  > vocabulary, because this document implied the rename was already complete everywhere and the
  > canonical file therefore had no counterpart by design. **When recording completed work, state
  > which apps it covered.**
- `--reg-*` and `--type-*` domain colours moved to
  `apps/artifice-graph/src/artifice_graph/web/static/entity-colors.css` (path updated after the
  2026-07-28 layout migration).
  They are deliberately not suite tokens.
- Error states stopped borrowing `--reg-poetic` (a register-taxonomy colour) and use `--error`.

### I.5 Design documentation consolidated — **Verified**

The suite carried **five** copies of the design system: the root document plus a fork in each of the
four apps, and a sixth divergent file. The four app copies were byte-identical to each other
(`cc4cae8f…`) and stale — forks of the root from before the `--font-label` rename. All five are now
deleted; nothing referenced them by path.

`apps/artifice-graph/DESIGN_LANGUAGE.md` was different — a 385-line *"LudwigLang Design Language"*
implementation companion. Its still-accurate component recipes were harvested into §8.9–8.17 (Page
Container, Masthead, Section Heading, List Card, Sort Bar, List Search Input, Stat Row, Progress
Bar, Source Badge), each **verified against the live CSS rather than copied**, because much of that
file had gone stale — it gave `--ink-faint` as `#716c5e` (real: `#635e51`), listed dark-mode values
matching no current palette, used the retired `--font-sans`, and documented a `.lib-folder*`
component that exists nowhere in the codebase.

Root `Design_Philosophy.md` is now 932 → 1202 lines, 13 sections, with zero occurrences of
`--font-sans`, `--w-` or "LudwigLang". §12 mirrors `packages/shared-ui/tokens.css` declaration for
declaration (56 light, 19 dark).

**Not carried across:** the deleted file's engineering conventions — icon-font ban, FastAPI/Jinja2
template conventions, the vanilla-ES5 JS rule, file-naming scheme, and its "Do's and Don'ts". These
are process rules rather than visual design, so they did not belong in `Design_Philosophy.md`. They
remain recoverable from git history and need a home — see Phase 0.

### I.6 Repository hygiene — **Landed**

- **`.gitattributes` created** (67 rules). The repo had none, while two apps carried their own
  nested ones. Committed blobs were LF but working trees were CRLF, so Windows git
  (`core.autocrlf=true`) reported the tree clean while WSL git reported ~65 files modified — the
  same repo giving contradictory answers depending on which shell you stood in. This caused one
  live misdiagnosis. `CONTRIBUTING.md` documents the policy and the one-time normalisation command.
  **The normalisation itself has not been run** — see Phase 0.
- **`scripts/dispatch-opencode.sh` created** to make agent dispatch survive the Windows/WSL
  boundary. See Part V.

### I.7 Session 2 — the pipeline actually runs — **Verified**

Session 1 fixed how `artifice-graph` *looked*. Session 2 found that large parts of it did not
**work**, and that no test or diff would have said so. Every item below was confirmed against the
running system.

**Both `run-all` orchestrators were broken, in unrelated ways** (`4a80524`).

- CLI: `run_all` called the Typer `@app.command()` functions as plain Python, so every unpassed
  parameter kept its `typer.OptionInfo` sentinel. `PipelineConfig` does not validate on assignment,
  so a sentinel landed in an `int` field and detonated in the chunker. Stage 1 died every time.
  Fixed structurally — five plain functions with real typed defaults, Typer commands as thin
  wrappers — rather than by passing more arguments, which would re-break on the next parameter added.
- Web: every stage helper ends in `_log_done` → `_end_run_log` → `_run_active = False`, so ingest
  marked the whole run inactive and stages 2–5 were silently skipped. `_run_active` conflated "the
  SSE stream may close" with "the pipeline should continue"; those are now separate signals.
- `run-all` also exited **0** while printing "0/5 stages completed successfully".

**No control in the web UI had ever worked** (`0c0563b`). `pipeline.js` cached three element ids —
`inputDir`, `outputDir`, `vaultDir` — that have never existed in any template, in any commit.
`collectConfig` dereferenced `.value` on null and threw. Worse, `runStage` set `running = true` and
painted the badge *before* the throw, and `running = false` lived only inside the unreached `.then()`
— so the first click bricked the page until reload and the guard silently refused every later click.
This, not the `_run_active` bug, was the symptom originally observed in the browser.

**Two more dead controls.** The config panel rendered two generations of itself, leaving duplicate
ids where the second copy of each was unreachable (`272721f`); and `btnSaveConfig` had no handler in
any file, ever, so nothing in the panel could be persisted (`e74d243`).

`scripts/audit-controls.py` (`c04e85c`) now finds this class statically across all four apps and
exits non-zero, ready to gate CI. `artifice-graph` is clean.

**The embedder could not be pointed anywhere** (`ca80d63`, `8aa1f8b`). `config.yaml` set
`embedding.base_url: localhost:11434` and nothing could override it, so semantic resolution was
unusable on any machine where the model server is not on localhost. Now configurable per-run and
persistable, and an unreachable embedder fails loudly through `_mark_run_failed` instead of
silently deduplicating nothing.

**The config panel had no stylesheet** (`da6ca9e`). Six structural classes had zero CSS rules and no
`<label>` was styled anywhere, so step headings, field labels and help captions all rendered at 17px
and every caption was `display: inline`. Four levels now separate cleanly, measured from the live
DOM in dark mode: 17px / 12.8px / 12.8px / 11.52px at 13.25:1, 8.42:1, 13.25:1 and 6.14:1. The same
commit fixed an unclosed `<div>` that had made the entire Pipeline Settings block a descendant of
`.configuration-sections`, and themed the top nav — `app.css:87` hardcoded the light paper colour
with no dark override, putting the wordmark at **1.23:1** in dark mode, now **16.24:1**.

**Leaflet was loading from unpkg.com on every Library page view** (`477820a`) — the same local-first
violation as the Google Fonts dependency, in a file nobody had looked at. Now vendored locally
(196K, with images and licence). Map tiles still come from openstreetmap.org but only behind the
"Load Map" click, and now say so.

**Agent infrastructure** (`836b5cc`, `e29e270`). Agents were auto-rejected from `/tmp`, and
`CLAUDE.md` — the only instruction file in the repo, so auto-loaded into every sub-agent —
convinced `lead-engineer` it was the orchestrator, whereupon it wrote its own brief, dispatched
itself, took the resulting error message's advice and SIGTERMed its own process tree. Both fixed;
see Part V.

**End-to-end, from the browser button:** 2 documents → 2 chunks → 42 entities / 28 relationships →
41 canonical → 54 vault notes → 41-node graph, all five export formats. Test suite **47 passed, 0
failed**. Fleet smoke test **13 passed, 0 failed**.

---

## Part II — Architectural gaps found while working

These were not the task, but they are load-bearing and should be recorded rather than rediscovered.

**The model harness does not exist.** `CLAUDE.md` requires that "all model interactions must pass
through structured schemas in `packages/model-harness`". In fact `model_harness` is a 29-line
`__init__.py` with **zero imports from any app**, and **all four** apps carry their own LLM client:

```
apps/artifice-ocr/src/artifice_ocr/_llm.py
apps/artifice-graph/src/artifice_graph/extraction/llm_client.py
apps/artifice-draft/src/artifice_draft/llm_client.py
apps/artifice-transcribe/src/artifice_transcribe/services/inference.py
```

> **Corrected 2026-07-28.** This list previously named three. Transcribe's
> `services/inference.py` is a fourth — it defines `InferenceEngine` and constructs its own
> `AsyncOpenAI` clients; it was missed because it is not named `*_client.py`. OCR is worse
> still: it constructs an `openai.OpenAI` at **six separate sites** (`_llm.py`, `_backend.py`,
> `utils.py`, `stages/ocr.py`, `web/routers/settings.py`, `gui/views/settings_view.py`), so
> there is internal duplication to resolve before any harness migration, not just four clients
> to port.
>
> `uv.lock` installs `model-harness` editable into **every** app's environment. So the package
> is on the path everywhere and imported nowhere — the gap is not "unused", it is "available
> and still bypassed".

`packages/core-types` is likewise unimported. The harness architecture is currently aspirational.

**~~Monorepo parity is broken, and `artifice-graph` is the one breaking it.~~ — RESOLVED
2026-07-28.** All four apps now use the same web-layer location. Verified: `apps/artifice-graph/web`
does not exist, and `apps/artifice-transcribe/src/artifice_transcribe/static` does not exist.

| app | UI location | form |
|---|---|---|
| `artifice-ocr` | `src/artifice_ocr/web/static/` | one static `index.html`, one `css/app.css` |
| `artifice-draft` | `src/artifice_draft/web/static/` | one static `index.html`, one `css/app.css` |
| `artifice-transcribe` | `src/artifice_transcribe/web/static/` | one static `index.html`, one `css/app.css` |
| `artifice-graph` | `src/artifice_graph/web/` | Jinja2 templates, 4 HTML, 3 app CSS + vendored Leaflet |

Commit `0979359` ("adopt canonical layout and ship web assets in wheels") migrated graph and
transcribe onto the `src/artifice_<slug>/web/` pattern `CLAUDE.md` mandates. **This section
previously described a three-way split that no longer exists, and gated Phase 2 on a decision that
has already been made.**

What remains true: the other three apps are **a single static `index.html` each**, not template
hierarchies. Only graph has a real `templates/` tree (`base.html`, `index.html`, `library.html`,
`about.html`). So Phase 2 is still not "copy graph three times" — there is little structure in the
other three to apply graph's patterns *to* — but the obstacle is thinness, not divergence.

**There is no CI.** `.github/workflows/` does not exist, so the 34 test files are never run
automatically and nothing enforces the parity or security rules on a pull request.

**IDE cruft is committed** — `.idea/` directories in the repo root, `artifice-ocr`,
`artifice-transcribe` and `packages/model-harness`.

**The other three apps do not use the token system.** `artifice-ocr`, `artifice-draft` and
`artifice-transcribe` each redeclare the canonical token block at the top of their own
`web/static/css/app.css`. **Quantified 2026-07-28** — ocr declares 62 local tokens of which 55
shadow a canonical name, draft 61/55, transcribe 54/53. `artifice-graph`'s `entity-colors.css` is
the counter-example and the target state: 13 tokens, **zero** shadowing, pure domain vocabulary.

Worse than redeclaration, and still present:
`artifice-transcribe/src/artifice_transcribe/web/static/css/app.css:818,874` hardcodes `#dc3545`
directly for `.health-dot.error` and `.health-status.error`, bypassing tokens entirely and using
the Bootstrap red removed from the design system for being off-palette. It is not alone — ocr and
draft both carry stock Bootstrap `--success: #28a745` and `--warning: #ffc107` against canonical
`#455f2b` and `#7c5e1a`.

`scripts/token-parity-check.py` now enforces this and **currently exits 1**, reporting 10 drifted
tokens across the three apps. Expect this class of drift throughout Phase 2; it is the reason that
phase is a design pass and not a copy-paste.

---

## Part III — Phased roadmap

### Phase 0 — Settle the current work *(immediate)*

**Phase 0 is closed.**

- [x] ~~Retarget the GitHub default branch to `main`~~ — **done**. `git ls-remote --heads origin`
      now returns `refs/heads/main` and nothing else; `origin/master` has been deleted. This
      mattered: `origin/master` (`238b717`) carried a tree byte-identical to the *pre-conversion*
      TypeScript/pnpm skeleton, so anyone cloning got the abandoned project, and a Zenodo/JOSS tag
      would have minted a DOI for a tree containing neither the software nor `paper.md`. Verified
      safe before deletion — `git rev-list origin/main..origin/master` returned only `238b717`
      itself, a merge commit whose tree already existed on `main`.
      (`gh` is also now installed at `/usr/bin/gh`, so future repository-settings work can be
      scripted; the note below about it being unavailable is obsolete.)
- [x] ~~Reconcile the local branch state~~ — done. Local `master` renamed to `main`,
      fast-forwarded to include both commits from `chore/remove-stray-file`, which was then deleted
      locally and on the remote after confirming `origin/main..origin/chore/remove-stray-file` was
      empty. One local branch remains, tracking `origin/main`
- [x] ~~Commit the remaining uncommitted work~~ — done, in three commits: `4659bdd` (design-doc
      consolidation), `bb40bc3` (implementation plan, smoke-test fix, `.gitignore` for
      `.claude/settings.local.json`), `c7cef6e` (stale-path corrections in `ARCHITECTURE.md` and
      `CONTRIBUTING.md`). WSL git had no `user.name`/`user.email`; set repo-locally to the identity
      already on every commit here
- [x] ~~Run the one-time line-ending normalisation as its own commit~~ — done, and it needed **no
      commit**. `git add --renormalize .` touched zero files: `.gitattributes` had already made the
      blob store canonical (318 `i/lf`, **zero** `i/crlf`, zero mixed). Only the *working tree* was
      stale, at 109 CRLF files — the exact condition that caused a live misdiagnosis and got an
      agent killed. Refreshed via `git rm --cached -r . && git reset --hard`, leaving 313 LF and 5
      CRLF; those five are `.bat` files, CRLF by policy at `.gitattributes:54`, as Windows batch
      requires. Working tree and policy now agree exactly
- [x] ~~Re-run `bash scripts/smoke-test-agents.sh` after the Gemini migration~~ — **13/13**.
      Required a fix first: OpenCode terminates its response banner with a carriage return, which
      sat inside the `${model}$` anchor and failed all four model assertions against banners that
      were in fact correct. `strip_ansi()` now strips CR as well as SGR colour
- [x] ~~**BLOCKER: OpenCode is not installed in WSL at all.**~~ **RESOLVED.** Node 22.22.1 and
      `opencode-ai@1.18.7` installed natively via apt and npm. `command -v opencode` now returns
      `/usr/local/bin/opencode`, and the binary is a genuine `ELF 64-bit LSB executable, x86-64`
      — the `bin/opencode.exe` filename is only the package's naming convention, not a Windows PE.
      `/usr/local/bin` sits at PATH position 2 against `/mnt/c` at position 10, so the shadowing is
      automatic. Credentials live in the Linux store at `~/.local/share/opencode/auth.json` (mode
      `600`), separate from the Windows install's.
      **Verified against the exact failure:** re-dispatching the same 3,958-character brief that
      previously sat at **0.00 CPU seconds for 7 minutes** in `poll_schedule_timeout` now shows
      **3.24 CPU seconds within 5 seconds**, `WCHAN=do_epoll_wait` — an active event loop. Smoke
      test 13/13 on the native install. Long briefs work. The diagnosis below is retained because it
      explains a long series of failures that were repeatedly misattributed to models and briefs:
- [ ] ~~Original diagnosis, retained for the record:~~ Attempting the first real
      `security-auditor` audit exposed the root cause of every prior agent stall. `which opencode`
      resolves to `/mnt/c/Users/mjcas/AppData/Roaming/npm/opencode` — a shim on the *Windows*
      filesystem that launches `opencode.exe` through WSL's Windows-interop layer (`/init`). There
      is no Linux-native `opencode` and no `node` in WSL. Every dispatch has therefore crossed the
      boundary twice, with the whole brief passed as ~4 KB of `argv`. The audit sat for 7 minutes at
      **0.00 CPU seconds**, `WCHAN=poll_schedule_timeout`, log containing only the banner — it never
      received a single token. Short prompts succeed (the smoke test gets a `PONG`), long ones never
      start. This explains the block-buffered logs, the `poll()` stalls, `exit=143`, `exit=1`, and
      the truncated briefs — none of which were model or brief problems. **Fix: install Node and
      OpenCode natively inside WSL** so no interop bridge is involved, then re-authenticate the
      providers. Until then treat OpenCode agents as usable only for short prompts
- [ ] Exercise `security-auditor` on a real audit. The transport blocker above is fixed, and the
      first attempt then failed for a second, unrelated reason: on `google/gemini-3.1-pro-preview`
      it ran **43 minutes at 2.8% CPU** — alive but rate-limited into uselessness — and produced
      nothing. Now on `opencode-go/qwen3.7-max`, the same tier as the rest of the fleet.
      **Diagnostic lesson:** `0.00` CPU means a stalled transport; low-but-nonzero CPU across a long
      wall time means throttling. Two different faults with the same symptom of a silent log
- [x] ~~Decide where the engineering conventions from the deleted `DESIGN_LANGUAGE.md` should
      live~~ — done. Each convention was checked against the current code first, because that
      document was demonstrably unreliable (it misstated `--ink-faint`, listed dark values matching
      no current palette, and documented a component that exists nowhere). Roughly half survived:
      - **Kept, in `CONTRIBUTING.md` → "Frontend conventions"**: template structure and blocks,
        the `?v={{ asset_v }}` cache-buster, `data-theme`/`data-reduce-motion` middleware stamping,
        the global `[hidden]` rule, and the file/naming table (corrected — `tokens.css` is no
        longer app-local). All verified present in code
      - **Kept, with its rationale written down for the first time**: the vanilla, ES5-compatible,
        IIFE-wrapped, no-build-step JavaScript rule. Verified exactly true — **zero** uses of
        `let`, `const` or `=>` across the apps' JS, and every JS file IIFE-wrapped. It had read as
        arbitrary taste; it actually follows from the local-first guarantee (no Node toolchain
        required to run the software), from auditability (`security-auditor` must review what
        actually executes, not compiled output), and from the fact that harness UIs have never
        needed more
      - **Kept, going to `Design_Philosophy.md` §8**: the icon rules — no icon fonts, no emoji in
        chrome, inline SVG with `aria-hidden="true"` and a fixed attribute set. Verified followed:
        10 inline SVGs, 11 `aria-hidden`, **zero** icon-font links
      - **Discarded — animations (§6)**: `state-pulse-flash`, `ink-dry` and `ink-create` appear in
        **zero files**. LudwigLang reading-view residue, same category as the `--w-*` tokens
      - **Discarded — breakpoints (§7)**: the table named three; the code did not match. It
        described a discipline that does not exist. *(The "fourteen" figure recorded here was
        itself wrong — remeasured 2026-07-28 as **7**, the rest being element `max-width` rules
        counted as media queries. See Phase 2.)*
      - **Nothing went to `ARCHITECTURE.md`** — that describes system structure, not code style
- [ ] Delete committed `.idea/` directories and add them to `.gitignore`

### Phase 1 — Finish artifice-graph

The reference implementation. Nothing should roll out to the other three apps until this is signed
off, because every pattern here becomes the template.

**Gate status: the ten-defect visual list is signed off; the gate stays closed.** Those defects
were fixed and each re-measured from the live DOM, so that work is settled. But two open items
below would change the template that Phase 2 copies four times over, and both are cheaper to
resolve once than to unpick from four apps:

- **Dark mode has never been looked at.** Every measurement in Part I was taken in light mode. The
  token file declares 19 dark-mode values that no one has seen rendered. Rolling out first would
  propagate any dark-mode defect ×4.
- **`base.html` fetches fonts from `fonts.googleapis.com`.** That is an architectural violation of
  the local-first guarantee, not a cosmetic one, and it sits in the very file every other app is
  about to copy. It also makes the UI depend on a network the product promises not to need.

Both were fixed, and a third of the same kind was found and fixed afterwards (`library.html` loading
Leaflet from unpkg). **The gate is now open — see the sign-off below.**

- [x] ~~Full pipeline run against a live local LLM~~ — run end to end **from the browser Run All
      button**, not by curl: 2 documents → 2 chunks → 42 entities / 28 relationships → 41 canonical
      → 54 vault notes → 41-node graph, all five export formats written. Also verified via the CLI,
      which additionally exits non-zero on failure now
- [x] ~~Audit the remaining stage states (`running`, `done`) in the browser~~ — all four states seen
      rendered. `error` in particular had **never been reachable**: nothing in `pipeline.js` called
      `setStageState(key, "error")`, which an audit had flagged as dead styling. The `runStage`
      unwind added in `0c0563b` is the path that reaches it
- [ ] Re-check entity badge scanability — hues are now ~34° apart, but at 14% tint all five
      converge toward cream. Consider raising the tint rather than moving hues further
- [x] ~~Dark mode has not been reviewed at all~~ — reviewed by measurement from the live DOM.
      **Dark mode is in good shape**; three findings, only one of which matters:
      - Core text passes comfortably: `--ink` 14.32:1, `--ink-soft` 9.1:1, `--ink-faint` 6.64:1,
        `--error` 5.3:1, `--warning` 9.47:1 against `--paper` `#161310`
      - Entity badges pass: rendered contrast 5.08–6.65:1 (Concept 5.16, Event 5.08, Location 5.13,
        Person 6.65). `entity-colors.css` has no dark block and does not need one — the badges are
        built with `color-mix()` against `--paper`/`--ink`, so they re-derive per theme. Measuring
        the raw `--type-*` tokens against `--paper` suggests four of five fail AA; that measurement
        is wrong, because it is not how the badges render. The rendered figure is the real one
      - The dark palette is declared twice — under `@media (prefers-color-scheme: dark)` and under
        `[data-theme="dark"]` — and the two agree exactly, 19 declarations each, no drift
- [x] ~~`--success` and `--warning` are still raw Bootstrap in light mode~~ — warmed and verified
      from the live DOM. `--success` `#28a745` → `#256b39` (2.82:1 → **5.84:1**), `--warning`
      `#ffc107` → `#7c5e1a` (1.47:1 → **5.45:1**). Both now pass AA against `--paper`
- [x] ~~`--accent` and `--success` are the identical `#4aa066` in dark mode~~ — `--success` given
      its own dark value `#67a04b`, a moss/olive ~40° off the accent's forest green. Verified
      distinct: ΔE 16.3 normal vision, 17.1 simulated deuteranopia
- [x] ~~`app.css:523` keys its only dark rule to `@media (prefers-color-scheme: dark)`~~ — a
      `[data-theme="dark"]` twin now accompanies it, following the `tokens.css` pattern
- [x] ~~Vendor the Google Fonts locally~~ — `packages/shared-ui/fonts/` now holds all three
      families with per-family OFL licence files, declared in a sibling `fonts.css` and served
      through the existing `/shared` mount; no `server.py` change was needed. `base.html` makes
      **zero** requests to `googleapis.com`/`gstatic.com`. Verified rendered: `document.fonts.status`
      is `loaded`, all three families resolve, and the variable-font weight ranges are correct
      (Archivo 400–700, Libre Baskerville 400–700, Playfair Display 400–900), italics included.
      Caveat: only Archivo is woff2. The two TTFs could not be converted — `fontTools` is present in
      `.venv` but its woff2 support needs the `brotli` extension, which is not installed. Total font
      payload is **940 KB**; `pip install brotli` and re-running the conversion would roughly halve
      it. Local-first, so this costs page weight rather than network

**Two colour problems remain in the status triad, found by verification rather than by the change
itself.** Neither renders anywhere today — `--success` and `--warning` are still unreferenced in
`artifice-graph` — but Phase 2 wires real UI to them, so both should be fixed before rollout:

- [ ] **Dark `--warning` and `--error` collapse together for red–green colour blindness.** They are
      far apart to normal vision (ΔE 61.7) but converge to ΔE **8.4** under simulated deuteranopia —
      `#d9b64a` → `#cdcf78` and `#e06060` → `#bdc560`, both muddy olive. Roughly 6% of men could not
      tell a warning from an error in dark mode. Light mode is fine at ΔE 21.4. Either separate the
      two by lightness as well as hue, or guarantee status is never carried by colour alone
      (WCAG 1.4.1) — an icon or text label alongside would also resolve it
- [ ] **Light `--success` and `--accent` are nearly the same colour.** `#256b39` vs `#2f7d45` is
      ΔE **7.6** to normal vision and 5.7 under deuteranopia — below the threshold where two colours
      read as distinct. The dark-mode collision was fixed; light mode was left, and is now the worse
      of the two. `ui-ux` flagged this itself as a design call it would not make unilaterally, which
      was the right instinct. Apply the same hue separation used in dark
- [ ] Accessibility pass: keyboard traversal, focus order, screen-reader labelling on the stage
      cards now that they are `div` containers rather than buttons

#### Phase 1 sign-off — 2026-07-27

**Signed off. The design gate is open; Phase 2 may proceed on the other three apps.**

Verified at sign-off, all against the running system:

| Check | Result |
|---|---|
| Test suite | 47 passed, 0 failed |
| Control bindings (`scripts/audit-controls.py`) | `artifice-graph` clean |
| External network refs in templates | openstreetmap only, and only behind the Load Map click |
| `node --check` on both JS files | pass |
| Agent fleet smoke test | 13 passed, 0 failed |
| Pipeline, browser-driven | all five stages, all four stage states rendered |
| Themes | light and dark, contrast measured from the live DOM |

**Known and accepted at sign-off** — recorded so they are not rediscovered as surprises:

- Three literal colours remain in graph stylesheets: `app.css:405` `rgba(27, 24, 19, 0.5)` (that is
  `--ink` at 50%, so it will not re-derive in dark mode) and `pipeline.css:377,578`
  `rgba(0,0,0,0.0x)` — **pure black, which `Design_Philosophy.md` forbids**. All three are
  sub-visible alpha values, which is why they did not block; fix them before Phase 2 copies them.
  The twelve literals in `entity-colors.css` are token *definitions* and are correct.
- `index.html:203` has a bare `<h3 style="margin-top: 2rem;">Pipeline Settings</h3>` that renders
  19.89px serif and now reads inconsistently against the new sans uppercase step markers.
- `.rule` and `.muted` have no CSS rules anywhere.
- The Vision Support field nests two `<label>` elements pointing at the same checkbox; a screen
  reader may announce it twice.
- `pipeline.js:49` uses an ES6 default parameter against the vanilla-ES5 rule in `CONTRIBUTING.md`.
- Font payload is 940 KB because only Archivo is woff2 — `brotli` is now installable (see Part V)
  and would roughly halve it.
- [ ] Decide whether Google Fonts should be vendored locally — `base.html` currently fetches from
      `fonts.googleapis.com`, which contradicts the local-first, offline guarantee

### Phase 1.5 — Security remediation *(blocks the public release, not the design rollout)*

First full security audit run 2026-07-27 by `security-auditor`. **13 findings.** Most sit in
`artifice-ocr`, `artifice-draft` and `artifice-transcribe`, so the fixes land in apps otherwise
frozen behind the design gate — security work is not design work and the gate does not apply, but
it does mean these touch frozen code.

> **Deliberately non-specific.** This repository is **public**. Full findings, with reproduction
> steps, are kept locally in `.security/` (gitignored, mode 0600) and must stay there until fixed.
> Publishing reproduction steps for unpatched vulnerabilities in software people may already be
> running is publishing an attack guide. Move detail here only after the fix ships.

- [x] **CORS — DONE, all four apps.** Verified 2026-07-28. Each server registers `CORSMiddleware`
      with an explicit loopback origin allowlist, `allow_credentials=False`, an enumerated method
      list and no wildcard: `artifice-ocr/web/server.py:31`,
      `artifice-draft/web/server.py:382`, `artifice-graph/web/server.py:49`,
      `artifice-transcribe/main.py:44`. This was the highest-leverage fix in the backlog and it
      closed the escalation path that made several findings below worse than they read
- [x] **Two HIGH path-traversals in `artifice-transcribe` — DONE.** Verified 2026-07-28. Both
      sites now route through `_sanitise_path_component`: audio upload at
      `api/v1/routes.py:639` and speaker enrollment at `:1224`. The helper does **not** simply
      call `.name` — `routes.py:86` documents that `Path("..").name` returns `".."`, so `.name`
      alone is insufficient, and it normalises separators first (`:93`). That is the correct
      handling of the trap the original finding pointed at
- [ ] Audit `ocr` and `graph` for the same path-construction shape, now that the pattern to apply
      is established in transcribe
- [ ] **Credentials returned in API response bodies** (medium, `artifice-transcribe` and
      `artifice-ocr`) — config endpoints echo HuggingFace tokens and API keys back to the client.
      Redact on the way out; the client does not need the value it just set
- [ ] **SSRF via user-controlled model endpoints** (medium, `artifice-graph` and
      `artifice-transcribe`) — the base URL for model calls is taken from request bodies and
      fetched server-side, with responses returned to the caller. Constrain to a scheme/host
      allowlist consistent with the local-first guarantee: loopback and the WSL host gateway
- [ ] **User-supplied directories used for reads and writes** (medium/low, `artifice-graph`) —
      `input_dir`, `output_dir` and `vault_dir` arrive in POST bodies and are used directly.
      Validate against an allowlist
- [ ] **Secrets persisted world-readable** (low, `artifice-ocr` and `artifice-transcribe`) —
      tokens are written to disk with default permissions. Write mode `0600`, and reconsider
      whether the key needs persisting at all
- [ ] **`apps/artifice-draft/src/artifice_draft/write_utils.py:36`** hardcodes a Windows temp path
      containing a specific username. It will fail on macOS, Linux, and any other Windows account.
      Use `tempfile.gettempdir()`. This one is safe to fix immediately — it is a portability bug
      with an incidental information leak, not an exploitable vulnerability
- [ ] Confirm the `pickle.loads()` calls in `artifice-transcribe` deserialize only
      database-internal, model-generated data and never anything user-supplied

**Resolved during the audit — F1, "GitHub PAT in `.mcp.json`", is contained.** Verified by the
orchestrator, since the auditor is read-only and could not run `git`: the file was **never
committed** (zero commits touch it, zero objects in history carry the name), it is correctly
ignored at `.gitignore:31`, and **no credential-shaped string appears in any tracked file** or in
the last 60 commits. The live exposure was file permissions only — it sat at `0644`. Remediation is
`chmod 600 .mcp.json`; no token rotation is required on the evidence, because the credential never
entered the repository.

**Clean surfaces, recorded so they are not re-audited without cause.** All six `subprocess.run()`
calls across the suite use list-form arguments — no `shell=True`, no string concatenation, no shell
injection vector. No secrets in tracked markdown, scripts, TOML or YAML; the `hf_...` strings in
`HANDOFF.md` are documentation of a placeholder.

### Phase 2 — Design system rollout

**Both prerequisites have dissolved. Phase 2 is unblocked as of 2026-07-28.** Audited by
`arch-auditor-docs` and independently re-verified by the orchestrator. Both are kept here, struck
through rather than deleted, because each was wrong in an instructive way.

- [x] ~~**PREREQUISITE: settle the canonical web-layer layout first.**~~ **Already done.** Commit
      `0979359` migrated graph and transcribe onto `src/artifice_<slug>/web/`. All four apps now
      agree. Verified: `apps/artifice-graph/web` does not exist. The plan gated Phase 2 on a
      decision that had already been made and not recorded — see Part II.
- [x] ~~**PREREQUISITE: consolidate the responsive breakpoints — graph declares fourteen.**~~
      **The count was wrong.** `artifice-graph` declares **7 distinct `@media` width breakpoints**,
      all in `px`, **zero in `rem`**: 520, 600, 700, 720, 800, 960, 1050. Nine declarations, since
      720 appears three times in `pipeline.css`.

      The "580px plus seven more in `rem`" figures were **element `max-width` / `max-height`
      declarations miscounted as media queries** — e.g. `44rem` is a prose measure
      (`.page.page-prose`), `72rem` a layout cap (`.read-layout .page`), `580px` a single
      element's width. A `max-width` in a rule body is not a breakpoint.

      For comparison, measured the same way: **ocr 3** (1100, 900, 600), **transcribe 4** (900,
      860, 700, 600), **draft 0** — draft has no width breakpoints at all, only
      `prefers-color-scheme` and `prefers-reduced-motion`. Graph is not the outlier the plan
      described, and nothing approaches fourteen.

      **The lesson worth keeping:** a metric quoted in a plan and never re-derived becomes
      folklore. This one blocked a whole phase for two sessions. Re-measure before treating a
      recorded number as a constraint.

      Genuinely remaining: the three parallel `720px` blocks in `pipeline.css` could merge. That
      is a tidy-up, not a prerequisite.
- [ ] Apply the graph patterns to `artifice-ocr`, then `artifice-draft`, then `artifice-transcribe`
- [ ] **Retire the app-local token blocks that already exist.** This is not a forward-looking
      constraint — it is remediation. Measured 2026-07-28 against the 56 canonical tokens in
      `packages/shared-ui/shared_ui/assets/tokens.css`:

      | App | Local tokens | Shadow a canonical name | Of those, value drifts |
      |---|---|---|---|
      | `artifice-ocr` | 62 | 55 | 6 (4 real, 2 quoting-only) |
      | `artifice-draft` | 61 | 55 | 4 |
      | `artifice-transcribe` | 54 | 53 | 2 |
      | `artifice-graph` (`entity-colors.css`) | 13 | **0** | 0 |

      All three re-declare essentially the whole canonical set inside their own
      `web/static/css/app.css`. `CONTRIBUTING.md:238,248` already forbids this; the apps avoided
      the *filename* `tokens.css`, not the practice. `artifice-graph` is the counter-example and
      the target state: 13 tokens, zero shadowing, pure domain vocabulary.

      The value drift itself is narrow and specific:
      - `--success: #28a745` and `--warning: #ffc107` in **ocr** and **draft** are **stock
        Bootstrap 4/5 defaults, unmodified**, against canonical `#455f2b` olive and `#7c5e1a`
        ochre. Saturated cold green and amber in a warm paper-and-ink palette — the most
        visually wrong values in the token layer, and the reason this is a design pass and not
        a find-and-replace.
      - `--error: #9a3324` in **all three** apps against canonical `#a8322b`. The apps agree
        with each other and `tokens.css` is the outlier, so decide by eye which is correct —
        this one may be a fix to *canonical*, not to the apps.
      - `--font-mono` differs everywhere: apps lead with Cascadia Mono / Consolas (Windows
        first), canonical with SFMono-Regular (macOS first). A genuine cross-platform question
        given the suite targets Windows 11 and Apple Silicon equally, not drift to be flattened.
      - ocr's `--font-body` / `--font-display` differ **only in quoting** (`'Georgia'` vs
        `Georgia`). Not drift. Any tooling that reports them is miscalibrated.
- [ ] Per-app domain colours follow the `entity-colors.css` precedent
- [ ] Rendered review of every app at desktop, ~900px and ~600px before sign-off

### Phase 3 — Make the harness real

The largest correctness item in the project, and the one the architecture claims is already done.

- [ ] Design the schema contract in `packages/model-harness` — structured request/response, no
      freeform chat, explicit provider abstraction
- [ ] Port `artifice-graph` first (its extraction schemas are the most developed)
- [ ] Port `artifice-ocr` and `artifice-draft`; retire the three duplicate LLM clients
- [ ] Establish what `packages/core-types` is for, or remove it
- [ ] Enforce `host.docker.internal` / `localhost` routing in one place rather than per app

### Phase 4 — Structural parity

- [x] ~~Choose one canonical web-layer location and migrate all four apps to it~~ — **done in
      commit `0979359`**, verified 2026-07-28. All four apps use `src/artifice_<slug>/web/`
- [ ] Align `pyproject.toml` definitions and Docker configuration across apps
- [x] ~~Commission `arch-auditor-docs` for a full parity audit once the above lands~~ — **run
      2026-07-28.** Findings folded into Part II and Part IV. Two of its six checks refuted a
      recorded claim; the orchestrator independently re-verified every consequential finding, and
      corrected two the auditor got wrong (`Zone.Identifier` files and `build/lib/` directories
      are present on disk but **not tracked in git**, so neither is a repository problem)
- [ ] Remaining parity gap: only `artifice-graph` has a `templates/` tree. The other three are a
      single static `index.html` each — thinness, not divergence

### Phase 5 — Engineering quality gates

- [ ] CI on pull request: `uv sync --extra all`, run all 34 test suites, lint
- [ ] `gitleaks` in CI, per the Zero Secrets Policy
- [ ] Cross-platform CI matrix — Windows, WSL2 and macOS are all supported targets
- [ ] Full `security-auditor` sweep of every ingestion surface (OCR upload, audio upload, graph
      import, document ingest) for path traversal, zip-slip and decompression bombs
- [ ] Test coverage for the restored `pipeline.js` and the SSE log broker, which have none

### Phase 6 — Academic release

- [ ] Verify `CITATION.cff` is current
- [ ] Confirm the Zenodo integration mints a DOI on a `v*.*.*` tag
- [ ] Finish `paper.md` / `paper.bib` for JOSS submission
- [ ] Write user-facing documentation for each app

---

## Part IV — Consolidated to-do list

Phase 1 is closed. **Re-derived 2026-07-28** — the previous list's top two items were already
fixed, and its items 4 and 5 were blockers that did not exist. In priority order from here:

1. **Repair `artifice-ocr`'s test suite** — 79 failed / 91 errors, and **all 170 are one bug**:
   every failure is `ModuleNotFoundError: No module named 'src'`, because 27 test files write
   their `patch()` targets as `src.artifice_ocr.…` while the package installs as `artifice_ocr`
   (112 occurrences). Measured 2026-07-28: exactly 170 occurrences of that error and **zero**
   missing-dependency errors of any kind. Highest return in the project — one mechanical change
   takes the suite from 148/319 to near-green.

   This plan had never recorded a cause for OCR's failures; the working assumption in session 3
   was that they came from missing optional dependencies (`fpdf2`, tropy). That assumption was
   wrong, and it is written down here because it is the kind of plausible guess that becomes
   folklore if the first person to check does not record what they actually found.
2. **Add CI** (Phase 5) — 34 test files exist and nothing runs them. Now cheap to make meaningful:
   `scripts/audit-controls.py`, `scripts/token-parity-check.py` and `scripts/smoke-test-agents.sh`
   all exit non-zero on failure and can gate a PR on day one. Note `token-parity-check.py`
   **currently exits 1** on the real tree, so landing it as a gate means either fixing the 10 token
   drifts first or knowingly admitting a failing check.
3. **Finish Phase 1.5** — remaining: credentials echoed in config response bodies, SSRF via
   user-supplied model endpoints, user-controlled directories in graph, secrets written at default
   permissions. CORS and both HIGH path traversals are done.
4. **Phase 2 design rollout** — genuinely unblocked, both prerequisites having dissolved. The
   measured work is the 10 token drifts, led by the stock Bootstrap `#28a745` / `#ffc107` in ocr
   and draft.
5. **Make the model harness real** (Phase 3) — the architecture's central claim is still untrue,
   and larger than recorded: four per-app clients rather than three, and six `openai.OpenAI`
   construction sites inside ocr alone. Nothing else depends on it, which is why it sits below
   work that gates other work.
6. **Delete the committed `.idea/` directories** — 8 files still tracked. Trivial, and it has
   survived several sessions on this list.

> **On the two items removed from this list:** both were true when written. Neither was
> re-derived before being treated as a constraint, and between them they blocked Phase 2 for two
> sessions. When an item here gates a phase, re-measure it before acting on it — and when it turns
> out to be stale, record that in the plan rather than quietly dropping it.

**Do not re-litigate these** — they were settled by measurement this session and the reasoning is
recorded above: dark mode is sound; entity badges pass AA as rendered (measuring the raw `--type-*`
tokens gives a wrong answer); generated pipeline output is deliberately untracked; and both
`run-all` orchestrators work.

---

## Part V — Operational notes

Hard-won during this session; ignoring these costs real time.

**Run everything through WSL.** The orchestrator's shell tools are Windows-side over a UNC mount
and cannot see `uv` or the Linux `.venv`. Use `wsl.exe -d Ubuntu -- …`.

**Long-running processes need `Start-Process`, not `&`.** A backgrounded job inside
`wsl.exe -- bash -lc "… &"` dies when that invocation returns — silently, leaving an empty log and
no process. This cost real time twice in one session, once for a dev server and once for an agent
dispatch, and in the server case the port answered anyway because a *stale process from an earlier
session* was still listening, so `HTTP 200` proved nothing. Launch detached instead:

```powershell
Start-Process -FilePath "wsl.exe" `
  -ArgumentList "-d","Ubuntu","--","bash","/tmp/serve-app.sh" -WindowStyle Hidden
```

Two things the wrapper script must do itself: `export PATH="$HOME/.local/bin:$PATH"`, because
`bash script.sh` is non-login and `uv` is not on the plain `PATH`; and redirect its **own** output,
because `Start-Process` discards the child's stdout. Before trusting a port, check `pgrep -af` for
the process you actually expect.

**Write scripts to files; never inline shell in the tool call.** PowerShell mangles quoting on the
way to WSL — `$(…)`, `${var}`, nested quotes and `2>/dev/null` all break, sometimes into a
PowerShell parse error and sometimes into a subtly different command. Use the Write tool to create
`/tmp/foo.sh`, then run `wsl.exe -d Ubuntu -- bash /tmp/foo.sh`. This recurred perhaps six times in
one session despite being known.

**Dispatch OpenCode agents with `scripts/dispatch-opencode.sh`.** Hand-rolled invocations fail four
ways, each silently: quoted briefs arrive truncated to one word; `$var` is eaten before WSL sees
it; backgrounded agents are reaped when the invocation returns; and `pkill -f <agent>` matches the
caller's own wrapper, killing the wrapper while leaving the agent running. That last one produced
two agents racing on the same files.

**~~OpenCode agents hang after finishing.~~ Fixed — do not act on this any more.** The cause was
never the provider: `which opencode` resolved to a Windows npm shim under `/mnt/c/…`, so every
"agent" was launching `opencode.exe` back across the interop boundary and blocking in `poll()`
forever. A native Linux install fixed it outright — the same 3,958-character brief went from
**0.00 CPU over 7 minutes** to **3.24 CPU-seconds in 5 seconds**, and `WCHAN` from
`poll_schedule_timeout` to `do_epoll_wait`. Agents now complete and report normally.

The diagnostic technique remains useful even though the bug is gone: **judge liveness by CPU time
against wall time**, not by the log, which block-buffers when redirected and freezes early. Near-zero
CPU over minutes means stalled; 35–55% sustained means working.

**Sub-agents inherit the orchestrator's persona from `CLAUDE.md`, and will act on it.** `CLAUDE.md`
is the only instruction file in the repo, so OpenCode auto-loads it into every sub-agent — ten
kilobytes of "you oversee… delegate to specialized sub-agents" against a six-line agent definition.
`lead-engineer` read its brief, correctly diagnosed all three bugs, then wrote *its own* brief and
ran `dispatch-opencode.sh lead-engineer` — dispatching itself. The script refused, advised `--stop`,
and the agent followed that advice and SIGTERMed its own process tree: `exit=143`, log ending
mid-sentence, nothing implemented. Every `.opencode/agents/*.md` now opens with an explicit "you are
a sub-agent, not the orchestrator" block, and GUARD 6 refuses to stop the caller's own agent. **Keep
both when editing agents** — a near-empty agent definition is not neutral, it cedes the agent's
identity to whatever else is in context.

**Agents report static checks as though they were runtime ones unless told not to.** They have no
browser. One reported that "a save-then-reload round trip preserves both values", reasoning
correctly from the persistence code — while the actual failure was one layer earlier at a button
that had never been wired. Brief them to say plainly when they could not exercise something; they
comply when asked, and an honest "I verified statically" is worth more than a confident inference.

**Verify rendered, not from the diff.** This caught, in one session: the above; an entire UI whose
buttons had never worked despite looking correct; and three of the orchestrator's *own* false
alarms — a "stage 3 card is styled differently" that was a JPEG artifact, a "helper text is in small
type" assumption that was never true, and five "dead controls" that were bound in an inline
`<script>` the audit had not scanned.

**~~OpenCode agents have no browser.~~ Superseded 2026-07-28 — they can fetch, but still cannot
see.** A self-hosted Firecrawl instance is wired as an MCP server and granted to `lead-engineer`
and `tester`. Proven the same day: `tester` scraped a running `artifice-graph` at
`http://host.docker.internal:8766/` and returned its title, headings and markup, `exit=0`.
Firecrawl's own container log recorded the scrape and the app logged the request arriving from
`172.18.0.4` — a container IP on the local bridge, which is what proves the self-hosted route
rather than a cloud round trip.

Rendered, visual confirmation is **still the orchestrator's job**. Firecrawl returns text and
markup, never pixels; the design-director loop in `CLAUDE.md` is unchanged. What changed is that
structural checks — is the control in the DOM, does it carry the right `id`, did the route return
200 — can now be delegated. That is the exact gap behind the "five dead controls bound in an inline
`<script>`" miss.

Setup, for reproduction:

```bash
scripts/firecrawl.sh up        # start; also asserts the loopback binding
scripts/firecrawl.sh status    # service table + binding check
scripts/firecrawl.sh prune     # after an audit run — clears stale Chromium
scripts/firecrawl.sh down
```

The checkout lives at `~/tools/firecrawl` (outside this repo, deliberately). Three deviations from
upstream were necessary and will be lost if it is re-cloned:

1. **`extra_hosts` added to `playwright-service`.** Upstream sets it only on the
   `x-common-service` anchor, which `playwright-service` does not use. Without it the renderer
   cannot resolve `host.docker.internal`, and **every scrape of a host-served app returns a bare
   404 while the api container reaches the same URL fine** — a genuinely confusing failure, because
   the 404 looks like an application bug rather than a DNS one.
2. **Port republished as `127.0.0.1:3002`,** not `0.0.0.0`. The instance runs unauthenticated
   (`USE_DB_AUTHENTICATION=false`), so a default bind would expose it to the LAN.
3. **Prebuilt `ghcr.io/firecrawl/*` images** substituted for the `build:` stanzas, avoiding a long
   Playwright build.

Three traps worth carrying forward:

- **`firecrawl-mcp` silently falls back to the Firecrawl cloud when `FIRECRAWL_API_URL` is unset.**
  It logs "running in keyless mode… against the Firecrawl cloud" and continues. Nothing errors. If
  that variable is ever dropped from `opencode.json`, a local-only tool becomes an egress path with
  no signal at all.
- **Firecrawl's URL validator rejects raw IPs** — "URL must have a valid top-level domain or be a
  valid path". Always brief the hostname, never `172.x.x.x`.
- **A `127.0.0.1` bind makes an app invisible to the agents.** The Phase 1.5 hardening changed
  `artifice-graph`'s default host from `0.0.0.0` to `127.0.0.1`, which is correct for a local-first
  app — and it silently removed the fleet's ability to verify it. Measured directly: host-local
  `curl` returns 200 while the same URL from inside the Firecrawl container is **unreachable**, and
  the scrape fails with status 594. Loopback does not include the docker bridge.

  To serve an app *for agent verification*, set the host explicitly:

  ```bash
  CALLOSIP_HOST=0.0.0.0 uv run python -m web.server
  ```

  Keep the shipped default at `127.0.0.1`. Widening the bind is a deliberate, temporary act for a
  verification session, never a committed change. Expect this to recur for every app as the same
  hardening rolls out to `ocr`, `draft` and `transcribe` — a verification brief that "just stops
  working" after a security pass is this, not a Firecrawl fault.

**Canonical web layout: `apps/<app>/src/artifice_<slug>/web/static/`.** Decided 2026-07-28 and
**migration completed the same day** in commit `0979359`. All four apps conform:

| App | Location | Status |
|---|---|---|
| `artifice-draft` | `src/artifice_draft/web/static/` | conforms |
| `artifice-ocr` | `src/artifice_ocr/web/static/` | conforms |
| `artifice-graph` | `src/artifice_graph/web/` | conforms — migrated |
| `artifice-transcribe` | `src/artifice_transcribe/web/static/` | conforms — migrated |

Verified 2026-07-28: `apps/artifice-graph/web` and
`apps/artifice-transcribe/src/artifice_transcribe/static` no longer exist.

The reason it mattered: assets outside the package are dropped from a wheel and are only findable
by a CWD-relative path, which breaks as soon as the server starts from anywhere but the app root.
The migration moved `StaticFiles` mounts, Dockerfile `COPY` lines and `pyproject.toml` package-data
rules together.

**Still outstanding from that migration:** `artifice-graph` carries the signed-off Phase 1 design
work and has had a green test run (47/47) but **not** a rendered re-check since it moved. A test
pass does not confirm that stylesheets still resolve in the browser. Do that before Phase 2 treats
graph as the reference.

**`git status` means different things in different shells** until the line-ending normalisation is
run. Always `git diff --ignore-cr-at-eol` before concluding anything about what changed.

**~~Developer tooling the fleet assumes but WSL does not have.~~ Installed — do not re-install.**
The gap this note described is closed. Verified present in WSL as of 2026-07-28:

| Tool | Version | Path |
|---|---|---|
| `ripgrep` | 15.1.0 | `/usr/bin/rg` |
| `ffmpeg` | 8.0.1-3ubuntu2 | `/usr/bin/ffmpeg` |
| `brotli` | 1.2.0 | `/usr/bin/brotli` |
| `jq` | 1.8.1 | `/usr/bin/jq` |
| `shellcheck` | 0.11.0 | `/usr/bin/shellcheck` |

`gitleaks` and `node` were already installed. The `uv` symlink still matters and is unrelated to
the above — it is the fix for the non-login `PATH` problem, and it removes a whole class of
"command not found" failures from scripts and agents alike:

```bash
sudo ln -s "$HOME/.local/bin/uv" /usr/local/bin/uv     # see the PATH note above
```

Two consequences worth acting on rather than just noting:

- **`brotli` unblocks the font payload.** §II and `packages/shared-ui/README.md:76` both record the
  vendored fonts shipping as TTF at **940 KB** because woff2 conversion needed `brotli` and it was
  absent. That blocker is gone; re-running the conversion should roughly halve the payload. Not yet
  done — it is a real task, not a footnote.
- **`ffmpeg` is now the *Linux* build.** `apps/artifice-transcribe/HANDOFF.md:100` records an
  `ffmpeg.exe` at a Windows path, which Whisper and pyannote under WSL cannot use. That note is now
  stale for WSL work; the native package at `/usr/bin/ffmpeg` is what transcribe will pick up.

`CONTRIBUTING.md` carries the developer-tooling list, which closes the documentation gap this note
used to flag.

---

## Part VI — Starting a fresh session

Read in this order: this document's status block and §I.7, then Part V, then `CLAUDE.md`.

**Confirm the environment before trusting anything:**

```bash
wsl.exe -d Ubuntu -- bash -lc "cd ~/projects/artifice-suite && \
  uv run python scripts/audit-controls.py && \
  bash scripts/smoke-test-agents.sh | tail -2 && \
  (cd apps/artifice-graph && uv run pytest tests/ -q | tail -2)"
```

Expected: `artifice-graph: clean`, `13 passed, 0 failed`, `47 passed`. Anything else means the
environment has drifted, not that the code has regressed — check Part V first.

**To serve `artifice-graph`** (port 8766), write a wrapper script and launch it detached per Part V;
do not background it inside `wsl.exe`.

**Local model topology on this machine** — worth knowing before debugging a connection failure.
Ollama is reachable from WSL only via the Windows gateway `172.21.176.1:11434`, never `localhost`.
LM Studio is not reachable from WSL at all (it binds localhost; "Serve on Local Network" would need
enabling). Installed models: `gemma4:12b` (tools + vision), `translategemma:4b`, `bge-m3:latest`,
`sematre/orpheus:de`. `config.yaml` names `gemma2:27b`, which is **not installed** — that default is
deliberate and portable, so override per-run rather than committing a machine-specific value.

**Unpushed work.** Check `git status -sb`; session 2 ended with several commits ahead of origin and
nothing was pushed without being asked.
