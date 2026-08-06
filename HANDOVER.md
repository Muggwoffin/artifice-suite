<!--
SPDX-FileCopyrightText: 2026 Maurice Casey
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Handover — session close, 2026-08-06

**Read this, then `IMPLEMENTATION_PLAN.md` § "PICK UP HERE — Phase 6", then
`CLAUDE.md`.** Where this file disagrees with an older block, this one wins.

---

## State at handover

| | |
|---|---|
| `main` | **CI green** — first green run on `main` since 2026-08-05 |
| PR #45 | **merged** — CI fixes + install-script fixes |
| PR #46 | **open, awaiting review** — draft UI, ASR test coverage, PyPI readiness |
| PyPI | **7/7 distributions verified publishable.** Nothing published. Account setup outstanding |

### Current suite baselines — these supersede every earlier figure

| Suite | Count |
|---|---|
| `apps/artifice-ocr` | 489 passed, 1 skipped |
| `apps/artifice-draft` | 227 passed |
| `apps/artifice-graph` | 171 passed |
| `apps/artifice-transcribe` | **123** passed (was 116; +7 new) |
| `packages/model-harness` | 222 passed, 1 deselected |
| `packages/secure-io` | 18 passed, 1 skipped |

Transcribe's count **depends on the environment** — without the ASR extra some
tests skip. Check before reporting a regression that is only an install state.

---

## YOUR TO-DO LIST

### Only you can do these — they need credentials or a human decision

1. **Review and merge PR #46.** CI should be green; check before merging.

2. **Create the PyPI accounts and pending publishers.**
   Full walkthrough: **`docs/PYPI_PUBLISHING.md`**. Summary below.

3. **Decide the `curl | sh` question.** `install.sh:47` and `install.ps1:69`
   fetch and execute the uv installer with no checksum. `security-auditor`
   rated it MEDIUM and noted it is the standard pattern for uv, rustup and pip
   over HTTPS. Either pin a checksum or require uv pre-installed. Deliberately
   left to you.

4. **Diarization is still unproven end to end** — it needs a HuggingFace token.
   Transcription itself was run through the API on CPU with the `tiny` model
   and works.

5. **The CUDA install path is unverified.** No NVIDIA GPU on this machine.
   `--extra asr-cuda` resolves, but its size and whether it actually gets GPU
   torch are unmeasured.

### Ready for the next session to pick up

6. **Step 5 — the ASR consent-and-download flow.** Not started. Its PyTorch
   prerequisite is done, and the distribution decision (uv primary) unblocks
   tier 3 runtime install, which a frozen bundle would have denied.

7. **Step 9 remainder** — favicons (no app has one) and a shared toast
   (implemented three times, missing from draft). Draft's theme toggle,
   shortcuts and dark accent block are **done** in PR #46.

8. **`typer[all]` is stale.** `uv tool install` warns that `typer==0.27.1` has
   no extra named `all`. Something still requests it. One-line fix, not yet
   traced to which pyproject.

9. **The `.callosip` migration has never run against a real directory.** The
   `shutil.move` + `ensure_restricted` path is not hit by any test. Your own
   `~/.callosip` is the natural first case — back it up first.

10. **Consider upper bounds on the internal pins.** `>=0.1.0` is loose once
    these names are public; `~=0.1.0` would stop a future 2.0 being pulled into
    an old app. Do this *before* first publish if you want it in 0.1.0.

11. **`README.md` still tells users to clone the workspace.** Once published,
    `uv tool install artifice-<app>` is the real install story.

12. **Fix the agent smoke gate.** `scripts/smoke-test-agents.sh` is flaky —
    `mode=all` failed on different agents across two runs while every direct
    check passed. Most likely concurrent `opencode` invocations. It is the
    check that exists to catch silent agent fallback, so it needs to be
    trustworthy.

---

## PyPI — what you need to do, in order

Full detail in `docs/PYPI_PUBLISHING.md`. This is the short version.

### The one thing to get right

Every app declares the three shared packages by name. Locally
`[tool.uv.sources]` resolves them from the workspace; **on PyPI there is no
workspace.** Publish the apps first and `pip install artifice-graph` fails for
everyone, because its dependencies are not on the index yet.

> **Shared packages first. Then the apps.** `publish.yml` enforces this with
> `needs: shared-packages`, but the same order applies when you register the
> pending publishers.

### Step 1 — accounts

- Register at <https://pypi.org/account/register/>.
- **Enable 2FA immediately** — required to own a project, and you cannot create
  publishers without it.
- **Save the recovery codes somewhere you will still have them in two years.**
- Do the same at <https://test.pypi.org/> — a **separate account**, separate
  2FA, not linked.

### Step 2 — seven pending publishers

None of the seven names exist yet (all 404, re-confirmed 2026-08-06). A
*pending* publisher claims a name that has never been uploaded.

PyPI → *Your projects* → *Publishing* → *Add a new pending publisher* →
**GitHub**, once per name. Owner `Muggwoffin`, repository `artifice-suite`,
workflow `publish.yml` every time — but **a different environment each time**.

**Register three, publish them, then register the next three.** PyPI allows at
most three pending publishers per account, and a pending publisher only frees
its slot once its project has actually been published.

| Wave | `stage` input | PyPI Project Name | Environment name |
|---|---|---|---|
| 1 | `wave-1-shared` | `artifice-model-harness` | `pypi-artifice-model-harness` |
| 1 | | `artifice-secure-io` | `pypi-artifice-secure-io` |
| 1 | | `artifice-shared-ui` | `pypi-artifice-shared-ui` |
| 2 | `wave-2-apps` | `artifice-ocr` | `pypi-artifice-ocr` |
| 2 | | `artifice-draft` | `pypi-artifice-draft` |
| 2 | | `artifice-graph` | `pypi-artifice-graph` |
| 3 | `wave-3-apps` | `artifice-transcribe` | `pypi-artifice-transcribe` |

Wave 1 being the shared packages is not a coincidence — they must reach the
index before any app regardless. Wave 3 has one project only because seven does
not divide by three.

**A shared environment name does not work, and the failure is silent until the
second registration.** A pending publisher is identified only by
`(owner, repository, workflow, environment)` until its project exists, and PyPI
requires that tuple to be unique. Owner, repo and workflow are fixed for a
monorepo, so the environment is the only field that can vary. Reusing one name
fails with *"A pending trusted publisher matching this configuration has already
been registered for a different project name."*

These must match the `environment:` values in `publish.yml` exactly. A mismatch
surfaces at publish time as what looks like a permissions error.

### Step 3 — rehearse on TestPyPI

Actions → *Publish to PyPI* → *Run workflow* → target `testpypi`.

**Rehearse properly.** A version number on PyPI is burned permanently — you
cannot re-upload `0.1.0` after deleting it. A bad first upload costs you the
version, not just time.

### Step 4 — publish

**First release: wave by wave, manually.** Actions → *Publish to PyPI* →
*Run workflow* → target `pypi`, stage `wave-1-shared`. When it succeeds,
register wave 2's publishers, run `wave-2-apps`, then the same for wave 3.

A tag (`git tag v0.1.0 && git push origin v0.1.0`) publishes everything at once
and also fires the Release Gate and Zenodo DOI minting — correct from the
**second** release onward, once all seven publishers are active.

### Never

**Do not create a PyPI API token.** Trusted Publishing needs no stored
credential — the only arrangement compatible with the Zero Secrets Policy. If
anything asks you to paste a token into an Actions secret, the setup above has
gone wrong.

### Re-check readiness any time

```bash
uv run python scripts/check-pypi-readiness.py
```

---

## What changed this session, and why it matters

### Three CI failures, all pre-existing, all the same shape

The recent ruff work did not cause any of them — it unblocked the steps that
expose them. **A gate that has never executed is not a passing gate.**

- **Dependency audit reported a ghost that was correctly declared.**
  `pyannote.audio` sits behind transcribe's `asr` extra, which `--extra all`
  omits, so CI locks it but never installs it — and the fallback compared an
  import root against distribution names. `IMPORT_ROOT_TO_DIST` teaches the
  fallback the name; it is **not** an exemption list.
- **The `ruff format` gate had never once run.** Shallow clone, so the PR base
  commit was unreachable: `fatal: bad object`, on every PR, regardless of
  content. Fixed with `fetch-depth: 0`.
- **The Windows failures were never about admin ACEs.** The check was made to
  say *why* it failed, and the runner answered: `Get-Acl`'s
  `Microsoft.PowerShell.Security` module would not load, so **the ACL was never
  read at all.** The standing test comment blaming "implicit admin ACEs the
  runner retains" was a plausible guess and wrong.

  This was a **live user-facing defect**, not a CI artefact: on any Windows
  machine where that module will not autoload, the apps cannot save settings.

### The install scripts had never been executed

Three defects, all found by running them, none visible in source review:

- **`uninstall.ps1` aborted before its own disclosure.** PowerShell 5.1 wraps
  native stderr in a terminating `ErrorRecord` under `$ErrorActionPreference =
  "Stop"`, and uv writes its *success* message to stderr. The script died after
  a successful removal, before printing the block that tells the user their data
  is still on disk **and may contain an API key**.
- **`uninstall.ps1` returned a stale exit code** — success reported as failure.
- **`install.ps1` installed uv in response to a typo** — validation ran after
  the uv bootstrap.

> **`2>&1` on a native command in PowerShell 5.1 is a trap.** It corrupts both
> error handling and `$LASTEXITCODE`. It bit the scripts, and then bit the
> test harness measuring them — a clean run reported `-1`. If you measure a
> PowerShell exit code, do not merge stderr.

### Lessons worth keeping

- **A verification that only tests the success case proves almost nothing.**
  Unchanged from last session and it earned its place again.
- **Brief agents to disagree.** Both sub-agents corrected a false premise in
  their brief this session — one found the toggle already existed and was
  switched off; the other found graph has no keyboard shortcuts to copy. Both
  flagged it instead of half-applying the instruction.
- **Scope a brief tightly, but be ready to widen it.** `ui-ux` hit a boundary I
  drew too tightly, worked around it, and flagged the workaround as worse than
  the fix. Widening the scope was correct; accepting the workaround would have
  left draft carrying graph's duplicated nav.
- **The rendered page still finds what source review cannot.** The toggle
  measured 44.00 × 44.00 with 0.00px centre offset — confirmable only in a
  browser, and the agent correctly declined to claim it.

---

## Environment notes

- **Run apps and `uv` through `wsl.exe -d Ubuntu`.** The Bash tool is
  Windows-side and has no `uv`.
- **Check `/tmp` first** — it is a 7.6 GB tmpfs, and a leftover ASR venv once
  filled it, producing 148 failures that read `OSError: [Errno 28]` and looked
  exactly like a code regression.
- **Servers:** harness-backgrounded ones get reaped; `setsid nohup` survives.
- **uv is NOT installed on native Windows.** It was installed accidentally this
  session by the `install.ps1` typo path, then removed at the maintainer's
  request (~410 MB reclaimed). `install.ps1` will bootstrap it if you test
  those scripts again.
- Quoting across the Windows/WSL boundary breaks constantly. **Write a script
  file and run that** rather than fighting inline quoting.
