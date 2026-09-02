# Maintainer-only checks

Things CI does not do, or cannot do. Everything here needs a human, a Windows
machine, or an account CI does not hold.

---

## Before every release

| # | Check | Command | Why it is yours |
|---|---|---|---|
| 1 | **Build and inspect a wheel** | `bash scripts/build-wheel.sh artifice-ocr`, then read it with `zipfile` | Tests run against `src/` and **cannot see packaging bugs**. Four categories have shipped or nearly shipped this way: fonts resolving outside the package, a stale `build/` resurrecting deleted code, CWD-relative data paths, and prompt templates outside the package. Use the script — it clears `build/` first, without which a deleted module stays in the wheel. `unzip` is not installed; use Python's `zipfile`. |
| 2 | **Version consistency** | `uv run python scripts/check-release-consistency.py` | Globs `apps/*/pyproject.toml`, so **the Hub is gated even though it never publishes** — it was once the sole reason this failed. Its `version` is at **line 7**, not line 3 like the others. |
| 3 | **Secret scan** | `gitleaks detect` | The subcommand is `detect`, not `git`. **Never pipe it** — `gitleaks detect \| tail -3` under `set -e` does not fail the script, and a secret scan that cannot fail is not a gate. |
| 4 | **Dependency audit** | `uv run python scripts/check-dependency-audit.py` | Catches hallucinated imports, undeclared transitive imports, and lockfile drift. Runs in CI too, but worth running before you tag. |
| 5 | **PyPI readiness** | `uv run python scripts/check-pypi-readiness.py` | — |
| 6 | **Publish the GitHub Release** | manual, or `release.yml`'s `github-release` job | Zenodo archives on a published **Release**, not a bare tag. A tag alone fires the gate and `publish.yml` and mints nothing. |

---

## Open items only you can close

| Item | Status |
|---|---|
| **Zenodo record states the wrong licence** | Record `10.5281/zenodo.21707694` is stamped **MIT**; the repo has been **AGPL-3.0-or-later** since the 2026-07-30 relicensing. A public, citable record currently tells the world the wrong licence. Minting a corrected record on the next tag **does not retract it** — it has to be edited or deleted on zenodo.org. Both `v*-alpha` tags were deleted, so the record points at a tree with no tag. |
| **SQLite URI form on Windows** | `tropy_write.py` builds `file:{as_posix()}`; `tropy_db.py` builds `file:{db_path}`. Per the SQLite URI spec, `file:path` without `//` is relative to the CWD, so an absolute Windows path may need `file:///C:/…`. Cannot be settled from WSL — both forms behave identically there. Run `.\scripts\interop\run-live-tropy.ps1 -TempRoot E:\ArtificeInterop` from a native Windows checkout against a real Tropy build. **Do not apply a speculative fix**: `tropy_db.py` works today, and a blind change risks breaking a path that is fine. |
| **Native drag-and-drop (`pywebviewFullPath`)** | Requires `_dnd_state['num_listeners']` to be non-zero, so the listener must be registered from Python via the pywebview DOM API — a JS-only listener silently yields no path. Not verifiable headlessly. |
| **Desktop mode has no drag-and-drop while the browser does** | `app.js` rejects every drop when `isDesktop`. Probably unnecessary — a pywebview window is Chromium, so a drop produces ordinary `File` objects. Needs a real drag in the packaged window. |

---

## Verifications no agent can perform

- **Rendered UI review.** Agents read served bytes; they cannot see pixels, and a
  font silently falling back to a system face looks identical in the markup. One
  session found five defects visible only in a browser — including a deleted
  function header that killed the entire Tropy UI while 791 tests passed, and a
  `<select>` destroyed at runtime by a `textContent` assignment on its parent
  `<label>`.
- **`node --check` on changed JavaScript.** pytest cannot parse JS. It is the
  only thing that catches a syntax error, and a syntax error means the file never
  loads — so *every* control in it dies, not just the one you touched.
- **Frozen-bundle behaviour on Windows.** `build-exe.yml` smoke-tests the binary
  (starts it, fetches the app's API path and its CSS, fails if either does not
  answer), which proves the bundle serves and that `shared_ui` assets resolve
  through `importlib.resources` from inside it. It does not prove anything about
  drag-and-drop, native dialogs, or SmartScreen.

---

## Traps worth knowing

**A dormant lint violation wakes when you touch its file.** The format gate runs
`ruff format --check $CHANGED`. A pre-existing violation sits harmless until an
unrelated change edits that file, then fails the build looking like your
regression. Before blaming your diff:
`git show HEAD:<file> | ruff format --check -`.

**An agent's "verified" is not verification.** Two runs in one session reported
success while stopping mid-checklist, leaving gate failures behind; one reported
a handler "unchanged — OK" that it had in fact deleted. Re-run the gates
yourself.

**`exit=0` from an OpenCode agent is not evidence of work.** Agents have read
every file in a brief and produced nothing, exiting clean. Check `git status`
before believing a report.

**Billing failure is usually silent.** An exhausted tier kills agents with no
error — a banner and then nothing. Diagnose by **CPU time against wall time**:
near-zero CPU over long wall time is a stalled transport, low-but-nonzero is
throttling, and neither will say so. (It can also fail loudly with
`Insufficient balance`; do not assume it will.)

**`$(...)` does not survive `wsl.exe -- bash -lc '...'`.** The file list is
re-parsed as commands and the tool runs with *no arguments*. `ruff format` then
defaults to `.` and reformats the entire repo while reporting success. Write a
script file and use `mapfile`. After any bulk formatter, check
`git status --porcelain | wc -l` against the number of files you meant to touch.

**CodeQL suppression comments do nothing.** GitHub code scanning ignores
`# codeql[rule-id]`; the alert simply moves down with the line. Dismiss via the
API instead — `dismissed_reason` must be one of `false positive` / `won't fix` /
`used in tests`, and `dismissed_comment` is capped at **280 characters**.
