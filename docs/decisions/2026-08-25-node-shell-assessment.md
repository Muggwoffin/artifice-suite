# Node / Electron Shell Assessment

**Date:** 2026-08-25
**Decision:** Do not migrate to Electron. Fix the existing pywebview app.
**Status:** Decision stands. Phase 1 largely shipped 2026-08-26 — see below.

> ## Outcome, recorded 2026-08-26
>
> The recommendation was followed and **the diagnosis held**: all four failures
> were application bugs, none of them a WebView permission problem. Verified
> against the tree rather than assumed:
>
> | Phase 1 item | State |
> |---|---|
> | 1. Approved-folder model for external drives | **Shipped.** `approved_folders` in config, validated on save, granted through the native folder dialog (#76) |
> | 2. Truthful drag-and-drop | **Shipped.** The `"Drag-and-drop isn't supported in the browser"` string no longer exists; the dropzone is capability-detected per mode (#76) |
> | 3. Tropy diagnostics | **Partly.** The browse path works and Tropy write-back now exists (#77); the failure-class split described below was not implemented as such |
> | 4. Endpoint / 404 classification | **Partly.** The specific doubled-`/v1` 404 was fixed (`fd07569`), and context-overflow errors are now classified and rewritten with actionable guidance (#79, #81). General per-run provider logging was not added |
> | 5. Regression tests | **Shipped.** artifice-ocr went from 770 to 803 passing |
>
> **Phase 2 was never triggered** — no native capability was proven unreliable on
> pywebview. Phase 3 remains a fallback, not a plan.
>
> The open questions at the foot of this document were answered: the 404 was the
> doubled `/v1`; browser mode stays supported; approved folders are managed in
> the UI; and the no-Node-toolchain policy is still in force.

## Origin of the question

The suite's apps surfaced repeated failures during ordinary use, recorded in
[the original bug report](../archive/2026-08-25-ocr-issues-report.md):

1. Saving settings fails with "Could not save settings", asking to permit
   endpoints outside the user's own network.
2. Tropy "Browse Project" reports that the server is not permitted to access
   the directory.
3. A Tropy JSON-LD export imports successfully, but the pipeline then returns
   a **404** even though Ollama and the OCR model were connected.
4. The queue dropzone advertises drag-and-drop, but dropping a file prints
   "Drag-and-drop isn't supported in the browser".

The hypothesis under test was that these are WebView permission failures that a
Node (Electron) application would fix by being a "real" native app.

## Findings

### 1. The reported failures are four distinct problems, not one WebView problem

None of the four is caused by the WebView lacking OS permissions. Each has a
different root cause in application code:

| Failure | Root cause | WebView-related? |
|---|---|---|
| Save-settings error | Endpoint policy in `apps/artifice-ocr/src/artifice_ocr/_backend.py` rejects an endpoint the user configured (public endpoints require the deliberate `ARTIFICE_ALLOW_PUBLIC_MODELS` opt-in) | No |
| Tropy Browse Project | The path is on the user's **E: drive**, which is not in the allowed-roots set built by `packages/shared-ui/shared_ui/path_validation.py:67-86` (`Path.home()`, temp dirs, `cwd`, plus an env-var escape hatch) | No — this is backend validation |
| Pipeline 404 | Provider/model resolution or routing failure; the exact request URL is not yet captured | No |
| Drag-and-drop message | Deliberate no-op: `apps/artifice-ocr/src/artifice_ocr/web/static/js/app.js:284-293` discards the browser drop event and logs the warning | Partially — the UI advertises a feature it does not implement in any mode |

The E: drive detail is decisive for item 2: the maintainer's Tropy project
lives on a secondary drive, and the validator only trusts `home`, temp, and
`cwd` by default. A native shell wrapping the *same* Python backend would fail
identically, because the Python layer would still refuse the path.

### 2. Browsers are not innately incapable of drag-and-drop

A browser drop event carries file **contents**, not filesystem paths
(`app.js:289-293` documents this). The app could already accept dragged files
by uploading their contents to the local server — the Tropy JSON-LD import
modal's content-based path (`tropyImportSource.type === "content"`,
`apps/artifice-ocr/src/artifice_ocr/web/static/js/tropy.js:149`) proves the
backend supports content uploads. The queue dropzone simply never wires the
browser path. The current UX is wrong in both directions: the UI promises a
feature it does not provide, and the failure message blames the browser for a
gap in the application.

### 3. PyWebView already provides a native bridge and native dialogs

- `packages/shared-ui/shared_ui/window.py` exposes a JS API
  (`window.pywebview.api.*`) with minimize/maximize/restore/resize/destroy.
- `packages/shared-ui/shared_ui/filedialog.py` provides file/folder/save
  dialogs with a precedence ladder (live pywebview window → tkinter → explicit
  "unavailable"), and the OCR server exposes them at
  `/api/native/pick-file` and `/api/native/pick-folder`
  (`apps/artifice-ocr/src/artifice_ocr/web/server.py:177-219`).

So native dialogs exist today. What does not exist is (a) native *drag-and-drop*
wiring, and (b) a user-facing way to approve paths outside the default allowed
roots.

### 4. Electron would not automatically grant better permissions

Electron's renderer is sandboxed by default. Privileged filesystem access there
also requires deliberately exposed main-process APIs plus an IPC bridge plus
validation — the same engineering the pywebview bridge needs. Electron would
still have to hand the Python backend a path, and the backend allowlist would
still reject `E:\...` unless the allowlist changes. Moving shells changes the
bridge technology, not the permission model.

Additionally:

- A full Node rewrite of the processing layers is not viable. The load-bearing
  Python surfaces — whisperx/pyannote diarization in transcribe, `python-docx`/
  `docx-revisions` tracked changes in draft, PyMuPDF/reportlab PDF in OCR,
  networkx/BGE embeddings in graph, and the schema-validated
  `packages/model-harness` contract — have no equivalent in the Node ecosystem
  at the fidelity this project depends on.
- The project documents reject a required frontend build step and Node
  toolchain (`ROADMAP.md:107-109`; `README.md:33` "No Node toolchain is
  required anywhere"). A Node conversion is a policy reversal, not just an
  engineering choice.
- The distribution pipeline is Python-shaped end to end: PyPI trusted
  publishing, `uv tool install`, PyInstaller frozen builds, per-app
  Dockerfiles. Electron would add a second runtime and a second packaging
  pipeline for each app.

### 5. What "better standalone functionality" is actually missing

The concrete gaps, in priority order:

1. **External-drive access** — no user-facing approval mechanism for `E:\`
   (or any drive outside home/temp/cwd).
2. **Truthful UI** — dropzone advertises drag-and-drop that no mode provides.
3. **Actionable error messages** — endpoint rejection, path rejection, and
   provider 404s surface raw reasons instead of diagnostics with next steps.
4. **Native drag-and-drop wiring** — a real feature, implementable in both
   pywebview and (later) Electron.
5. Everything else an Electron shell would bring (menus, shortcuts, file
   associations, single-instance, crash recovery) is secondary to the above.

## Recommendation

**Do not migrate to Electron now.** Fix the four failures in the existing
pywebview app. The evidence shows missing capability wiring and an
over-restrictive backend policy — not a WebView limitation.

Electron should only be reconsidered if, after the fixes below, a concrete
native capability is *proven* unreliable on pywebview on Windows 11. Even then,
the defensible shape is a thin native shell over the **unchanged** Python
backend, not a rewrite (see "Fallback path" below).

## Path forward

### Phase 1 — Fix the existing app (no new runtime)

1. **Approved-folder model for external drives.**
   - Replace the implicit roots-only rule with an explicit, user-approved
     folder list: the native folder picker selects a folder (e.g.
     `E:\Projects\Tropy`), the choice is persisted in OCR settings, and
     validation checks against approved folders plus the current defaults.
   - Keep the existing protections (traversal, hidden sensitive directories,
     POSIX drive-letter rejection) and keep `ARTIFICE_OCR_ALLOWED_ROOTS` as a
     working escape hatch.
   - Error messages must name the rejected path and explain how to approve a
     folder — never leak server filesystem layout.
   - Add regression tests for non-C-drive paths (Windows) and approved-folder
     persistence.

2. **Implement drag-and-drop where it is possible.**
   - Browser mode: read dropped file contents and upload them
     (`/api/queue` content upload, mirroring the Tropy JSON-LD content path).
     Folder drops in browser mode: detect and explain they need the desktop
     app, rather than failing silently.
   - pywebview mode: wire the window bridge to accept dropped paths and submit
     them through the existing queue endpoints, subject to the approval model
     above.
   - Until both exist, make the UI truthful: capability detection at runtime,
     and per-mode copy ("Drop files here" only where it works; otherwise
     "Use Browse Files").

3. **Tropy diagnostics.**
   - Split the failure classes: `.tpy` file missing/inaccessible, SQLite
     schema unreadable, photo paths unresolvable, `project.base` resolution
     wrong, Tropy local API down, Tropy API 404.
   - Ensure E-drive `.tpy` paths flow through the same approval mechanism as
     every other external path.
   - Add fixture-based integration tests with a `.tpy` database outside the
     default roots.

4. **Endpoint and provider 404 classification.**
   - Record provider, base URL, resolved model and route (redacting keys)
     for every pipeline run.
   - Preflight before a run: distinguish endpoint unreachable, endpoint
     rejected by policy, model missing, wrong provider route, provider 404.
   - The maintainer's third screenshot should be re-captured with the exact
     failing URL/model once logging exists — the 404's URL decides whether the
     fix is model resolution, an Ollama route, or a different provider.

5. **Regression tests for every fix**, including an end-to-end OCR run with
   files on a secondary drive and a live Tropy import/export.

### Phase 2 — Gated reconsideration of a native shell

Only if Phase 1 exposes a native capability pywebview genuinely cannot deliver
on Windows 11 (e.g. drag-and-drop paths, or dialog parenting). Criteria to
record before starting: the specific failing capability, the pywebview
evidence, and the minimum shell that fixes it.

### Phase 3 — Fallback path: thin shell over unchanged Python backend

If a native shell is ever adopted:

- Shell technology: Electron only if "Node application" is a hard requirement;
  otherwise evaluate Tauri/Neutralino on size and system-webview reuse.
- The shell owns: window, menus, dialogs, drag-and-drop, backend lifecycle,
  startup diagnostics, logging, single-instance.
- Python keeps: all processing, Tropy integration, model-harness policy, PDF
  export, storage.
- Define a formal HTTP/SSE backend contract with pytest contract tests before
  any shell code; pilot on `artifice-ocr`; dual-track releases alongside the
  pywebview build until parity is proven on real Windows 11 and macOS hardware.
- Amend `README.md`, `ROADMAP.md` and `ARCHITECTURE.md` in the same commit
  that lands the first Node artifact — the "no Node toolchain" statements
  become stale constraints the moment Node appears.

## Open questions for the maintainer

1. Exact text/URL of the pipeline 404 (decides the model-resolution fix).
2. Should browser mode remain a supported fallback, or is the desktop window
   the only mode that must stay polished?
3. Should approved folders be managed in the UI (recommended) or remain an
   environment-variable concern?
4. Is the no-Node-toolchain policy (`ROADMAP.md:107-109`) still in force?
   This assessment assumes yes.
