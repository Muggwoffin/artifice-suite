# Artifice Suite — Implementation Plan

**Status as of 2026-07-27.** This document records what has been built and verified, and stages
the remaining work. It is the project to-do list; `ARCHITECTURE.md` describes the system as
designed, `CLAUDE.md` governs how agents work on it, and `Design_Philosophy.md` is the binding
design authority.

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

The orchestrator drives five sub-agents across two runtimes. `security-auditor` moved from Claude
Code to Gemini via OpenCode to reduce Claude token consumption; it is a safe candidate because it
is read-only and its findings route through the orchestrator before any code is written.

| Agent | Runtime | Model | Status |
|---|---|---|---|
| `lead-engineer` | OpenCode | `opencode-go/deepseek-v4-pro` | **Verified** |
| `tester` | OpenCode | `opencode-go/kimi-k3` | **Verified** |
| `arch-auditor-docs` | OpenCode | `opencode-go/glm-5.2` | **Verified** |
| `security-auditor` | OpenCode | `google/gemini-3.1-pro-preview` (read-only) | **Verified** on the banner — not yet exercised on a real audit |
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
- `--font-sans` renamed to `--font-label` across all call sites, no alias. `Design_Philosophy.md`
  updated to match, and §3 now names the token for every font role so the ambiguity cannot recur.
- `--reg-*` and `--type-*` domain colours moved to `apps/artifice-graph/web/static/entity-colors.css`.
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

---

## Part II — Architectural gaps found while working

These were not the task, but they are load-bearing and should be recorded rather than rediscovered.

**The model harness does not exist.** `CLAUDE.md` requires that "all model interactions must pass
through structured schemas in `packages/model-harness`". In fact `model_harness` is a 29-line
`__init__.py` with **zero imports from any app**, and three apps each carry their own LLM client:

```
apps/artifice-ocr/src/artifice_ocr/_llm.py
apps/artifice-graph/src/artifice_graph/extraction/llm_client.py
apps/artifice-draft/src/artifice_draft/llm_client.py
```

`packages/core-types` is likewise unimported. The harness architecture is currently aspirational.

**Monorepo parity is broken.** `CLAUDE.md` requires identical modular `src/` patterns, but the web
layer sits in a different place in each app — `artifice-graph` has `web/` at the app root, while
`artifice-ocr` and `artifice-draft` nest it under `src/<package>/web/`, and `artifice-transcribe`
uses an `api/v1/` structure instead.

**There is no CI.** `.github/workflows/` does not exist, so the 34 test files are never run
automatically and nothing enforces the parity or security rules on a pull request.

**IDE cruft is committed** — `.idea/` directories in the repo root, `artifice-ocr`,
`artifice-transcribe` and `packages/model-harness`.

**The other three apps do not use the token system.** `packages/shared-ui/README.md` records that
`artifice-ocr`, `artifice-draft` and `artifice-transcribe` each redeclare an identical copy of the
token block at the top of their own `static/css/app.css`. A spot check confirms worse than
redeclaration — `artifice-transcribe/src/artifice_transcribe/static/css/app.css:818,874` hardcodes
`#dc3545` directly for `.health-dot.error` and `.health-status.error`, bypassing tokens entirely
and using the Bootstrap red that was just removed from the design system for being off-palette.
Expect this class of drift throughout Phase 2; it is the reason that phase is a design pass and not
a copy-paste.

---

## Part III — Phased roadmap

### Phase 0 — Settle the current work *(immediate)*

Mostly closed out. One manual step remains, and one new blocker was uncovered.

- [ ] **Retarget the GitHub default branch to `main` — the one remaining manual step.**
      `origin/master` (`238b717`) has a tree byte-identical to `d6f80ca`, the *pre-conversion*
      TypeScript/pnpm skeleton (`package.json`, `pnpm-workspace.yaml`, `src/index.ts`; no
      `pyproject.toml`, no `uv.lock`, no `paper.md`). **Anyone cloning today gets the abandoned
      skeleton**, and the Zenodo/JOSS path would mint a DOI for a tree containing neither the
      software nor `paper.md`. This cannot be scripted here: `gh` is installed on neither Windows
      nor WSL, and the GitHub MCP tools expose no repository-settings operation. Do it in the web
      UI — *Settings → General → Default branch → switch to `main`* — then delete `origin/master`
      with `git push origin --delete master`. Verified safe: `git rev-list origin/main..origin/master`
      returns only `238b717` itself, a merge commit whose tree already exists on `main`, so nothing
      unique is lost
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
- [ ] **BLOCKER: OpenCode is not installed in WSL at all.** Attempting the first real
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
- [ ] Exercise `security-auditor` on a real audit — blocked on the item above, not on the agent
      itself. It is correctly registered, read-only, and answers on `gemini-3.1-pro-preview`
- [ ] Decide where the engineering conventions from the deleted `DESIGN_LANGUAGE.md` should live —
      `ARCHITECTURE.md` or `CONTRIBUTING.md`. Recover with
      `git show 73d8d4d:apps/artifice-graph/DESIGN_LANGUAGE.md`
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

Fix those two, then open the gate. The remaining four items are refinements that can proceed in
parallel with rollout without contaminating the template.

- [ ] Full pipeline run against a live local LLM — the restored `pipeline.js` has been verified for
      wiring and clean console, but not by running all five stages end to end
- [ ] Audit the remaining stage states (`running`, `done`) in the browser; only `idle` and `error`
      have been reviewed
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
- [ ] Decide whether Google Fonts should be vendored locally — `base.html` currently fetches from
      `fonts.googleapis.com`, which contradicts the local-first, offline guarantee

### Phase 2 — Design system rollout

- [ ] Apply the graph patterns to `artifice-ocr`, then `artifice-draft`, then `artifice-transcribe`
- [ ] Each app serves `packages/shared-ui/tokens.css` via its own `/shared` mount; no app-local
      token copies are recreated
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

- [ ] Choose one canonical web-layer location and migrate all four apps to it
- [ ] Align `pyproject.toml` definitions and Docker configuration across apps
- [ ] Commission `arch-auditor-docs` for a full parity audit once the above lands

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

Phase 0 items are listed above and are the immediate queue. The highest-value items beyond them,
in priority order:

1. **Make the model harness real** (Phase 3) — the architecture's central claim is currently untrue
2. **Add CI** (Phase 5) — 34 test files exist and nothing runs them
3. **Finish graph, including dark mode and accessibility** (Phase 1)
4. **Vendor the fonts** (Phase 1) — a network fetch on every page load contradicts local-first
5. **Structural parity** (Phase 4) — cheap to fix now, expensive after three more design passes

---

## Part V — Operational notes

Hard-won during this session; ignoring these costs real time.

**Run everything through WSL.** The orchestrator's shell tools are Windows-side over a UNC mount
and cannot see `uv` or the Linux `.venv`. Use `wsl.exe -d Ubuntu -- bash -lc '…'` — and note the
`-l`, because a non-login shell has no `uv` on `PATH`.

**Dispatch OpenCode agents with `scripts/dispatch-opencode.sh`.** Hand-rolled invocations fail four
ways, each silently: quoted briefs arrive truncated to one word; `$var` is eaten before WSL sees
it; backgrounded agents are reaped when the invocation returns; and `pkill -f <agent>` matches the
caller's own wrapper, killing the wrapper while leaving the agent running. That last one produced
two agents racing on the same files.

**OpenCode agents hang after finishing.** Observed repeatedly across two models: the agent
completes its file edits, then blocks in `poll()` waiting on a provider response that never
arrives, with no client-side timeout. Diagnose with `/proc/<pid>/stat` — near-zero cumulative CPU
over many minutes means hung, not thinking. Judge progress by file mtimes and `git diff`, never by
the log, which block-buffers to a file and freezes early. **Expect to kill agents and read their
output rather than wait for their reports.**

**OpenCode agents have no browser.** Never brief one to verify anything visually. Rendered
confirmation is the orchestrator's job, per the design-director loop in `CLAUDE.md`.

**`git status` means different things in different shells** until the line-ending normalisation is
run. Always `git diff --ignore-cr-at-eol` before concluding anything about what changed.
