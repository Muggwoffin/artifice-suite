# Follow-ups

Work deferred during the OCR repair session. Each entry states what, where,
why it matters, and who owns it. Items are ordered most-consequential first.

---

## Upload helpers copied three ways — security risk

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

## `python-multipart` undeclared in OCR

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

## Dead `import ollama`, four files

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

## Stale model placeholders in OCR templates

The settings form in `apps/artifice-ocr/src/artifice_ocr/web/templates/index.html`
contains two placeholder values that no known local provider serves:

- Line 317: `e.g. gemma4:12b`
- Line 326: `e.g. translategemma:4b`

A user who copies either placeholder gets `CONFIGURED_MISSING` and a 409
response at runtime. A third stale placeholder was already removed; these two
remain.

**Why it matters:** A user following the UI's own hint is rewarded with a
hard failure and no actionable message.

**Owner:** `ui-ux`.

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

*Last verified: 2026-08-25. Items marked UNVERIFIED could not be confirmed from
within the repo and are recorded as maintainer actions only.*
