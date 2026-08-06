<!--
SPDX-FileCopyrightText: 2026 Maurice Casey
SPDX-License-Identifier: AGPL-3.0-or-later
-->

# Handover — session close, 2026-08-06

**Read this, then `IMPLEMENTATION_PLAN.md`, then `CLAUDE.md`.** Where this file
disagrees with an older block, this one wins.

---

## State at handover — all verified today, 2026-08-06

| | |
|---|---|
| `main` | CI green. PRs #45, #46, #47, #48 all merged |
| Version | `0.2.0` in all nine files; release gate passes for `v0.2.0` |
| Tag | **None. `v0.2.0` is NOT tagged.** No tags exist in the repo at all |
| PyPI | `0.1.0` live for all seven distributions. `0.2.0` not yet published |
| Zenodo | Concept DOI `10.5281/zenodo.21621935`, version `10.5281/zenodo.21707694` — public since 2026-07-30, **stamped MIT while the code is AGPL-3.0-or-later** |

---

## Test baselines — these supersede every earlier figure

| Suite | Count |
|---|---|
| `apps/artifice-ocr` | 489 passed, 1 skipped |
| `apps/artifice-draft` | 227 passed |
| `apps/artifice-graph` | 182 passed |
| `apps/artifice-transcribe` | 168 passed, 4 skipped **without** the `asr` extra |
| `packages/model-harness` | 225 passed, 1 deselected |
| `packages/secure-io` | 18 passed, 1 skipped |

**Transcribe's number depends on the environment and this has now misled twice.**
`uv sync --extra all` omits the `asr` extra, so `pyannote.audio` is absent and
four tests in `tests/test_web_endpoints.py` skip with
`ASR stack not installed (pyannote.audio unavailable)`. **Check the install state
before reporting a regression** — a lower number may be an environment, not a
defect.

> **The `--extra asr` figure is deliberately not stated here.** It was going to
> read "172 passed", arithmetic from 168 + 4 — but nobody ran it, and an
> unmeasured number written down as a baseline is exactly what this file spends
> a section below warning about. Measure it when you next install that extra,
> then record it *with the date and the install state it was measured under*.

---

## YOUR TO-DO LIST

### Maintainer-only — needs credentials or a human decision

1. **Tag `v0.2.0`.** From a WSL terminal (`gh` and `uv` are authenticated there,
   not on the Windows side): `git checkout main && git pull`, then
   `uv run python scripts/check-release-consistency.py --expected v0.2.0`,
   then `git tag v0.2.0 && git push origin v0.2.0`. Run the check **before**
   tagging — a PyPI version is burned permanently.

2. **Correct the Zenodo record.** The published record says MIT. Add a note to
   the old record at zenodo.org (editing metadata does not mint a new DOI);
   the next tag mints a corrected AGPL record under the same concept DOI.
   Zenodo does **not** backfill.

3. **Build the Windows `.exe`.** Actions → *Build standalone executables* →
   Run workflow. This could not be done before #48 merged, because
   `workflow_dispatch` requires the workflow file on the default branch.

4. **Two Dependabot PRs are open and green** (`setup-uv` 5→7,
   `actions/checkout` 4→7). A third Dependabot run **failed** on torchaudio —
   transcribe's torch pins are version-matched pairs, so that needs care.

5. **The `curl | sh` question is still open.** `install.sh:47` and
   `install.ps1:69` fetch and execute the uv installer with no checksum.

6. **Diarization is still unproven end to end** — needs a HuggingFace token.
   Given that the token-leak fixes landed today in exactly that code path, it
   deserves an actual run.

7. **The CUDA install path is unverified.** No NVIDIA GPU on this machine.

8. **macOS signing and notarisation.** Deliberately deferred — the maintainer
   decided on 2026-08-06 to ship Linux and Windows first. `build-exe.yml`
   excludes macOS on purpose, with the reasoning written into the file.

### Ready for the next session to pick up

1. **Freeze the other three apps.** `artifice-ocr` is done and proven;
   `artifice-draft`, `artifice-graph` and `artifice-transcribe` have no spec.
   Note transcribe is the hard one: a frozen bundle has no writable
   `site-packages`, so runtime installation of the ASR stack is impossible inside
   it.

2. **Migrate the other three apps onto the shared toast** in
   `packages/shared-ui/shared_ui/assets/toast.js`. Only `artifice-draft` uses it;
   ocr and transcribe still have their own.

3. **Favicons — no app has one.**

4. **The ASR consent *dialog*.** The backend is complete (seven endpoints, SSE
   progress, consent, transitive size disclosure). No UI exists for it.

5. **`security-auditor` finding F5 follow-ups** and the remaining "note only"
   items from the 2026-08-06 audit.

---

## What changed today, and why it matters

Seven distributions were published to PyPI at `0.1.0` and then verified
installable from the real index into clean environments. This was the load-bearing
test: the shared packages had to resolve *from PyPI*, not the local uv
workspace. If that had failed, `pip install artifice-graph` would have broken for
every user on the index — and only a real install into a clean environment could
confirm it.

A pre-tag audit sweep found four tag-blocking issues. The most serious: a
token-redaction helper existed in `download.py` but was applied nowhere else.
When an HF API call returns a 401, the response echoes the bearer token in
plain text. That token was going into the logs, into **SQLite via
`job.error_message`**, and back out through `GET /api/v1/jobs/{id}` and
`GET /health/detailed`. It was never in a chat UI — but it was in the job
history and the health endpoint, both reachable by design.

`artifice-ocr` now freezes into a standalone executable. The blocker was a
live packaging bug: a `configs/` directory sat outside the package tree and was
loaded with `Path(__file__).parent.parent.parent`, which resolved to the
working directory at runtime and to nothing in a wheel. It shipped in no wheel
at all in both 0.1.0 and 0.2.0. The OCR prompt templates — which users see on
every job — were silently absent from the installed package.

An undisclosed network egress was closed. `artifice-graph` was sending entity
names extracted from the user's documents to OpenStreetMap's Nominatim API,
with no consent mechanism and no way to disable it. The README promised
local-first processing. The egress is now default-off.

---

## Lessons worth keeping

- **A measurement is only as wide as the path you point it at.** Three separate
  claims were refuted today, and two of the corrections were *themselves* wrong
  for the same reason: an audit scoped to a file list that excluded
  `CHANGELOG.md` concluded no Zenodo DOI existed (one did); a grep scoped to
  `apps/` concluded three apps lacked the BYOM button (it was in
  `packages/shared-ui`). When a search comes back negative, widen the path
  before believing it.

- **A citation is not evidence of currency.** Stale plan entries cite real line
  numbers and read as verified. The line numbers are real; the condition they
  describe may have changed.

- **Tests assert on meaning; bugs live in what is emitted.** Every SSE frame in
  the new download endpoints was malformed — a literal backslash-n instead of a
  newline — so no event would ever have reached a browser. A code review and 36
  tests missed it because they all asserted on decoded JSON and object state.
  A line-length warning caught it.

- **A fix can be right and still incomplete on the path that matters.** The
  cancel guard registered its thread only on the success path, so the cancel
  case — the only one it existed for — was still broken.

- **Agents killed mid-task still produce value.** Two runs were killed
  (`exit=137`, `exit=143`) after starting servers inside their shell tool and
  hanging on cleanup; their findings were salvaged from the logs. Start
  long-running servers with `setsid nohup ... < /dev/null &`, never a bare `&`.

- **`code-reviewer` returns nothing on a large brief.** It read nine files and
  produced no report at all, exit 0. Re-scoped to two files it produced the best
  review of the day. Keep its briefs small.

---

## Environment notes

- **Run apps and `uv` through `wsl.exe -d Ubuntu`.** The Bash tool is
  Windows-side and has no `uv`.
- **Check `/tmp` first** — it is a 7.6 GB tmpfs, and a leftover ASR venv once
  filled it, producing 148 failures that read `OSError: [Errno 28]` and looked
  exactly like a code regression.
- **Servers:** harness-backgrounded ones get reaped; `setsid nohup` survives.
- **Quoting across the Windows/WSL boundary breaks constantly.** Write a script
  file and run that rather than fighting inline quoting.
- **`gh` is authenticated inside WSL only.** Running it Windows-side fails with
  "please run gh auth login". The Claude Code `!` prefix runs Windows-side —
  use `!wsl.exe -d Ubuntu -- bash -lc "gh ..."`.
- **Backticks in a heredoc are command-substituted across the boundary.** A PR
  body written inline was silently gutted. Write the body to a file and use
  `--body-file`.
- **`gh pr edit` can fail on an unrelated Projects-classic GraphQL deprecation.**
  `gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -F body=@file` works.
- **`dispatch-opencode.sh --status` is machine-wide, not repo-scoped.** It
  reported an unrelated project's agent as if it were this repo's.
- **GitHub Actions can fail with "The job was not acquired by Runner of type
  hosted".** That is infrastructure, not code. `gh run rerun <id> --failed`.
