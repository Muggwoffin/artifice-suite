# Follow-ups

Work deferred during the OCR repair session. Each entry states what, where,
why it matters, and who owns it. Items are ordered most-consequential first.

> **This file is read as authoritative by every sub-agent briefed from it, so a
> stale entry produces confidently wrong work.** Three entries were found stale
> on 2026-08-26 — one already fixed, one with wrong counts, one with wrong line
> numbers and an understated scope. Resolved items are marked **RESOLVED** in
> place rather than deleted, because the reasoning is worth keeping; live items
> carry no banner. **Re-verify an entry's premises before briefing from it.**

---

## ~~Upload helpers copied three ways — security risk~~ — RESOLVED 2026-08-26 (PR #78)

> **RESOLVED.** Both helpers now live in `packages/shared-ui`:
> `shared_ui.uploads.read_capped` (raises `UploadTooLarge`) and
> `shared_ui.path_validation.sanitise_path_component` (raises
> `PathValidationError`). All four apps call them; no local copy remains outside
> the gitignored `build/`. draft gained the filename guard it never had.
>
> **Two things this entry got wrong, recorded because the mechanism recurs:**
>
> 1. **The counts were stale.** `_read_capped` was in **four** apps, not three —
>    ocr's copy was added by PR #76 *after* this note was written — and
>    `_sanitise_path_component` was in **three**, not two. The duplication was
>    worse than recorded.
> 2. **The severity was overstated.** "draft's filename upload path is
>    unprotected" was not true. `runtime.py` already did
>    `doc_dir / Path(filename).name` into a fresh `uuid4` directory per upload,
>    so `../../etc/passwd` became `passwd` inside a scoped directory — the
>    traversal did not work. The two real gaps were narrower: backslashes are not
>    separators on POSIX (so `..\..\x.docx` survived intact), and `Path(".").name`
>    is `""`, which made `doc_dir / ""` the directory itself and raised
>    `IsADirectoryError` — **a 500 where a 400 belonged.** Both fixed.
>
> Briefing an agent from the entry as written would have produced a confident fix
> for an imagined traversal hole.

### Original entry (historical)

`_read_capped` caps upload size and raises HTTP 413 once exceeded. It exists in
three apps with identical implementations and no shared home:

- `artifice-draft/src/artifice_draft/web/server.py:73`
- `artifice-graph/src/artifice_graph/web/server.py:1274`
- `artifice-transcribe/src/artifice_transcribe/api/v1/routes.py:108`

`_sanitise_path_component` rejects path-traversal characters in filenames. It
exists in two apps and is absent from a third:

- `artifice-graph/src/artifice_graph/web/server.py:1297`
- `artifice-transcribe/src/artifice_transcribe/api/v1/routes.py:128`

`artifice-draft` has `_read_capped` (size cap) but does not have
`_sanitise_path_component` (filename sanitiser). Both functions handle
attacker-controlled input. Three copies mean a fix to one can miss the others;
draft's missing sanitiser means its filename upload path is unprotected.

**Why it matters:** Both functions are the defensive layer between user input
and the filesystem. A path-traversal fix applied to graph and transcribe but
not draft would look like a completed security patch.

**Owner:** `lead-engineer` — candidate for extraction to `packages/shared-ui`.

---

## ~~`python-multipart` undeclared in OCR~~ — RESOLVED (was already fixed)

> **RESOLVED, and it was already fixed before this entry was ever worked.**
> `apps/artifice-ocr/pyproject.toml:51` declares `python-multipart>=0.0.9` under
> the `web` extra, with a comment naming the exact failure it prevents
> ("Form data requires python-multipart"). PR #76 landed it.
>
> The entry was written before that PR and never revisited. Anyone briefing from
> it would have dispatched an agent to fix something already fixed — cheap here,
> but the same pattern applied to the entry above nearly produced a fix for a
> vulnerability that did not exist.

### Original entry (historical)

`python-multipart` is required for FastAPI to parse `multipart/form-data`
uploads. It is listed as a dependency in all three other apps but is absent
from `artifice-ocr/pyproject.toml`.

`artifice-graph/pyproject.toml:63` records that its own prior omission meant
"the container has never served a request; no test caught it because no test
starts a container." The same pattern applies to OCR.

**Why it matters:** Without this dep, the OCR container silently accepts
zero uploads. A user deploying the container has no indication that file
upload is broken.

**Owner:** `lead-engineer` — already fixing OCR's declaration. Broader check
for other undeclared direct imports (e.g. FastAPI route decorators, Starlette
types) belongs in the same pass.

---

## ~~Dead `import ollama`, four files~~ — REFUTED 2026-08-26. Do not delete them.

> **REFUTED. These imports are load-bearing for the test suite. Deleting them
> breaks 792 passing tests.**
>
> An agent tried the deletion, watched the suite fail, worked out why, and
> reverted its own edits. The mechanism:
>
> ```python
> @patch("artifice_ocr.stages.cleanup.ollama.Client")    # test_cli.py:152, 191, 682
> @patch("artifice_ocr.stages.translate.ollama.Client")  # test_cli.py:384, 395
> ```
>
> `import ollama` binds the shared module object into each module's namespace,
> so `cleanup.ollama` **is** `_backend.ollama` — the same object. Patching
> `cleanup.ollama.Client` therefore patches the global `ollama.Client` that
> `_backend.OllamaBackend.chat` actually calls. Remove the import and `patch`
> cannot resolve the target: `AttributeError`, at collection time.
>
> **How this entry came to be wrong, because the mechanism will recur.** The
> claim was verified by grepping for `ollama.` usage *in the source tree*, which
> correctly found it only in `_backend.py`. That verification was real, and too
> narrow: it never looked at test patch targets. "Unused in `src/`" is not the
> same as "unused". This is the same narrow-result-recorded-as-general failure
> `CLAUDE.md` documents, committed while quoting it.
>
> **If the startup cost is worth reclaiming**, the fix is to re-point the tests
> at `artifice_ocr._backend.ollama.Client` first, then delete the imports — two
> changes, in that order, not one. Not currently judged worth the churn.

### Original entry (historical — its premise is false)

These files import `ollama` but never reference it:

- `apps/artifice-ocr/src/artifice_ocr/stages/cleanup.py:10`
- `apps/artifice-ocr/src/artifice_ocr/stages/translate.py:10`
- `apps/artifice-ocr/src/artifice_ocr/stages/structure.py:21`
- `apps/artifice-ocr/src/artifice_ocr/_confidence.py:14`

`_backend.py` in the same package also carries `import ollama` at line 10; that
one IS used (`ollama.Client`, `ollama.ResponseError`) and is not dead.

**Why it matters:** `ollama` is a heavy optional dependency. Importing it at
module level costs startup time and memory in every process that loads these
modules, even when Ollama is not the configured backend.

**Seed discrepancy — noted:** The original brief listed four files but I found
five total, with one (`_backend.py:10`) live. The four dead files above are
correct as verified.

**Owner:** `lead-engineer`.

---

## Stale model names — wider than "two placeholders"

> **Corrected 2026-08-26. The line numbers below are stale and the scope is
> understated. Read this before briefing.**
>
> - The placeholders are at **`index.html:351` and `:360`**, not 317 and 326.
> - **The maintainer confirmed they do not use these models at all.** The
>   approach is model-agnostic; the docs should guide users toward openly
>   provenanced models.
> - **They are not only in `index.html`.** `gemma4:12b` / `translategemma:4b`
>   also appear in `apps/artifice-ocr/README.md` (~7 places, including the
>   `ollama pull` block a new user follows), `scripts/install.sh:287-288`, and
>   `src/artifice_ocr/configs/example.yaml:10-11`. Fixing only the two
>   placeholders leaves the installer and README still instructing users to pull
>   models that do not exist — a narrow fix that would read as complete.
> - The ~40 occurrences under `apps/artifice-ocr/tests/` are **fine and should
>   stay**: a test needs *a* model name, not a real one.
>
> **Replacements come from `packages/model-harness/src/model_harness/registry.py`,
> not from invention** — it is the single source of truth and already carries
> `ethos_badges`. Sourcing from it keeps docs and runtime recommendations from
> drifting apart, which is how they diverged in the first place:
>
> | Role | Model | Badges |
> |---|---|---|
> | OCR / vision | `richardyoung/olmocr2:7b-q8` | Strict Open Data · Transparent Training · Allen AI Open Science |
> | Translation (laptop) | `aya-expanse:8b` | Open Science Lab |
> | Translation (desktop) | `aya-expanse:32b` | Open Science Lab |
>
> Note the config defaults are **empty strings** (`config.py:31-33`), so these
> were never the runtime defaults — purely advisory, which supports the original
> diagnosis below.

### Original entry

The settings form in `apps/artifice-ocr/src/artifice_ocr/web/templates/index.html`
contains two placeholder values that no known local provider serves.

A user who copies either placeholder gets `CONFIGURED_MISSING` and a 409
response at runtime. A third stale placeholder was already removed; these two
remain.

**Why it matters:** A user following the UI's own hint is rewarded with a
hard failure and no actionable message.

**Owner:** `ui-ux` for `index.html`; `lead-engineer` for README, installer and
example config.

---

## `_redact_url` leaks credentials on scheme-less URLs

`_resolution.py:125` — the function strips userinfo from logged URLs using
`urlsplit`/`urlunsplit`. It correctly handles `http://user:pass@host/path`
(authority is parsed) and `//user:pass@host/path` (same, explicit netloc).

For a scheme-less URL such as `user:hunter2@localhost:11434/v1`, `urlsplit`
places everything in `path` because there is no `//` prefix to trigger
authority parsing. `parts.hostname` is `None`, so `host=""`, and
`urlunsplit` returns the path unchanged — credentials survive into the log
line.

**Why it matters:** The function's documented purpose is defence in depth:
credentials must not reach logs even if a user pastes a URL without the
required scheme prefix. The current implementation fails that contract
silently.

**Owner:** `lead-engineer`.

---

## Native drag-and-drop deferred (Stage 4c)

pywebview 6.2.1 can supply real filesystem paths on Windows via
`CoreWebView2File.Path` injected as `pywebviewFullPath`. The mechanism is
documented in pywebview's own source (`platforms/edgechromium.py:233`).

The critical constraint: `_dnd_state['num_listeners']` must be non-zero, so the
drop listener must be registered from Python via the pywebview DOM API. A
JS-only listener silently yields no path. This cannot be verified headlessly
and was not implemented in this session.

**Why it matters:** The current dropzone in the OCR UI is a JS-only fallback
that cannot return a real path. A native drop is required for the
filesystem-picker workflow to work on Windows.

**Owner:** `lead-engineer` (requires Windows or a pywebview expert to
verify).

---

## Desktop mode now has NO drag-and-drop, while the browser does

`app.js:444-448` rejects every drop when `isDesktop`:

```js
if (isDesktop) {
  log("Drag-and-drop is not available in desktop mode — use Browse Files.", "warning");
  return;
}
```

That inversion is almost certainly unnecessary. A pywebview window is Chromium,
so a drop there produces ordinary `File` objects — pywebview's own handler
iterates `event['dataTransfer'].get('files', [])` (`webview/util.py:292`) and
*augments* those files with `pywebviewFullPath`, which only makes sense because
the `File` objects already exist. The `POST /api/queue/upload` path should
therefore work unchanged in the desktop window.

Native paths (the item above) are needed only to avoid copying the user's file
into `~/.artifice_ocr/uploads/` — they are an optimisation, not a prerequisite
for drag-and-drop working at all.

**Why it matters:** the packaged desktop app is the shipped product, and it
currently offers strictly less than the browser it embeds.

**UNVERIFIED** — cannot be confirmed headlessly; needs a real drag in the
packaged window on Windows.

**Owner:** `ui-ux`, after a maintainer confirms the behaviour in the desktop
window.

---

## Zenodo record misstates the licence (UNVERIFIED)

`CITATION.cff:17` and the repository root state `AGPL-3.0-or-later`. The
published Zenodo record `10.5281/zenodo.21707694` is stated to be stamped MIT.
This discrepancy was recorded in `CLAUDE.md` but has not been verified by
checking the live record on zenodo.org.

**Why it matters:** A public, citable, archived record currently tells the
world the wrong licence. Minting a corrected record on the next tag does not
retract the existing one.

**Owner:** Maintainer — requires direct access to zenodo.org to verify and
correct.

---

## Packaging checks not run this session

CI (`.github/workflows/ci.yml:290`) has a `wheel-contents` job that asserts
font files, templates, and static assets are present in each app's built
wheel. No wheel was built or inspected during this session.

Tests run against `src/` and cannot reach packaging faults. Four categories of
bug have shipped or nearly shipped this way: fonts resolved outside the
package, stale `build/` resurrecting deleted code, CWD-relative data paths,
and prompt templates resolving outside the package.

**Why it matters:** The session may have closed with packaging defects that
tests did not and could not catch.

**Owner:** Maintainer to verify: `bash scripts/build-wheel.sh` per app, then
`python3 -c "import zipfile; z = zipfile.ZipFile('dist/*.whl'); print(z.namelist())"`.

---

## Deferred UI defects (separate brief exists)

The queue action row contains 11 buttons of equal visual weight that wrap to
an orphan on smaller viewports. `#log` and `#queue-body` both render with
empty content and no empty-state copy.

These are acknowledged as a separate brief to `ui-ux`.

**Owner:** `ui-ux`.

---

## SQLite URI construction may be wrong on Windows (UNVERIFIED)

The two Tropy modules build their SQLite URIs differently:

- `apps/artifice-ocr/src/artifice_ocr/tropy_write.py:203` —
  `file:{self.db_path.as_posix()}` → on Windows, `file:C:/Users/name/project.tpy`
- `apps/artifice-ocr/src/artifice_ocr/tropy_db.py:82` —
  `file:{db_path}` → on Windows, backslashes inside the URI

Per the SQLite URI specification, `file:path` without `//` is interpreted
relative to the current working directory. An absolute Windows path may require
`file:///C:/Users/name/project.tpy`.

**Why it matters:** if SQLite treats `file:C:/…` as relative, the connection
fails or silently resolves against the wrong directory — on the *write* path,
against the user's research database.

The inconsistency between the two modules is itself the strongest signal that
neither was exercised on Windows. `tropy_db.py` is committed and apparently
working, so SQLite may be lenient here.

**UNVERIFIED** — cannot be settled from Linux/WSL, where both forms behave the
same. Needs a run on native Windows against a real `.tropy` project. Found by
`security-auditor` on 2026-08-25, which correctly declined to assert it as a
bug. Do **not** apply a speculative fix: a blind change risks breaking a path
that currently works.

**Owner:** maintainer (Windows verification), then `lead-engineer`.

---

---

## Install docs are wrong in three ways that break a fresh install

Found 2026-08-26 while writing an install guide. All three verified against the
tree:

1. **`apps/artifice-ocr/README.md` tells the user to install a package that does
   not exist.** Its setup block runs
   `pip install -e packages/core-types -e packages/model-harness -e packages/shared-ui -e apps/artifice-ocr[web]`.
   **There is no `packages/core-types`** — the workspace has `model-harness`,
   `secure-io`, `shared-ui`. The command fails outright. The same README's
   directory tree also lists `core-types/`.
2. **That command violates the suite's own rule.** `CLAUDE.md`: *"Use `uv`
   workspace commands exclusively... Do not run bare `pip install`."* The app
   README is the first place a new user looks, and it teaches the forbidden path.
3. **Root `README.md:38` says the apps are published at `0.1.0`.** Every
   `pyproject.toml` in the workspace is at **`0.3.0`**.

**Why it matters:** a new user following the documentation cannot install the
app. Nothing in CI reads prose, so none of this fails a gate.

**Owner:** `lead-engineer` — in flight as at 2026-08-26.

---

## `_backend.py`'s four `chat` methods have diverged into copy-paste

Raised by `oss-reviewer` (Mistral) on 2026-08-26, reviewing the file after it
took four changes in a day and shipped a regression.

`OllamaBackend`, `OllamaOpenAIBackend`, `LMStudioBackend`, `HuggingFaceBackend`
and `ApiKeyBackend` each repeat: build a client, validate the URL, log the base
URL once, map `num_predict` to `num_predict` or `max_tokens`, call
`_guarded_chat`, and unwrap the response into `_SimpleResponse`.

What genuinely differs is small: client construction, where `num_ctx` goes
(`options` vs `extra_body` vs nowhere), `think` handling (Ollama only), and
response extraction.

**Why it matters, concretely.** `backend_name` was added to eight call sites by
one script. Because the same `model=model,` shape appears twice per backend —
once in the provider call, once in the wrapper around it — it landed in four
*provider* calls too, and broke OCR on every backend at once
(`Completions.create() got an unexpected keyword argument 'backend_name'`, fixed
in #80). One place to edit is one place to get wrong.

**Not done now, deliberately.** Refactoring five backend classes immediately
after shipping a regression in that exact file, with no independent reviewer
available, trades a known-good state for a larger unreviewed change. The AST
test added in #80 guards the specific failure; the duplication is the standing
risk.

**Owner:** `lead-engineer`, with a `code-reviewer` pass, once the fleet has
credit. Extract the shared kwargs construction; keep the per-backend
differences explicit rather than behind flags.

---

## draft has a flaky wall-clock test that fails on Windows CI

`apps/artifice-draft/tests/test_byom.py:396` asserts:

```python
assert elapsed < 0.5, f"GET / took {elapsed:.3f}s, root must not probe"
```

It failed PR #77 at `0.942s` on `windows-latest` while ubuntu, macOS and the
plain draft job all passed. A re-run went green — it is timing, not behaviour.

The test has a **second** assertion that actually proves the property:

```python
assert not httpx_mock.get_requests(), "root route made a network request"
```

That one cannot be fooled by a slow machine. The wall-clock line is a redundant
proxy that fires *first* and masks it, so a slow runner fails the build without
the route ever having probed anything.

**Why it matters:** an unrelated PR gets a red build and someone re-runs CI until
it passes — which trains the habit of ignoring red.

**Fix:** drop the timing assertion, or raise it to something a shared Windows
runner can actually hit. Keep the mock assertion.

**Owner:** `lead-engineer`. Small.

---

## Packaging checks — partially addressed

The original entry (above) said no wheel was built or inspected. Still true for
**wheels**. But note that `build-exe.yml` *does* smoke-test the frozen bundle on
both Windows and Linux before uploading: it starts the binary, fetches the app's
API path and its CSS, and fails the build if either does not answer. A green
`build-exe` run therefore proves the frozen bundle serves and that `shared_ui`
assets resolve through `importlib.resources` from inside it.

That covers the *frozen* artifact, not the wheel. `scripts/build-wheel.sh` +
`zipfile` inspection is still a maintainer action.

---

*Last verified: 2026-08-26. Items marked UNVERIFIED could not be confirmed from
within the repo and are recorded as maintainer actions only. Entries marked
**RESOLVED** are kept for their reasoning, not as live work.*
