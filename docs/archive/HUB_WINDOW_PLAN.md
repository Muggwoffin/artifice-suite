# Hub Model Registry & Shared Window Management Plan

## Overview

Two related problems: (1) Artifice Hub presents the model-harness registry's
recommendations as mandatory — the user sees "missing" models and is pushed to
`ollama pull` them, when the suite is BYOM and any model the provider serves is
fair game; (2) the Hub's `window.py` has a richer `_WindowApi` (minimize,
maximize, restore, toggle_maximize, resize, destroy) while the other four apps'
`window.py` copies only expose minimize + destroy, and the code is duplicated
across five files with no shared module.

---

## Problem 1: Hub hardcodes registry models and forces installation

### Current state (verified)

**`apps/artifice-hub/src/artifice_hub/engine.py`** is the core issue:

- `get_engine_status(slug, tier)` (line 67) builds a status dict that computes
  `missing = sorted(recommended - installed_models)` and
  `all_satisfied = installed and running and not missing`. The frontend reads
  `all_satisfied` as a gate — if any recommended model is not installed, the
  Hub presents the app as "not ready" and pushes the user to pull models.

- `pull_model_command(slug, tier, model_name)` (line 115) validates the model
  name against the frozen registry before building an `ollama pull` argv. This
  is injection-safe (good), but it means the Hub can *only* offer models the
  registry lists — a user who already has a different model on Ollama cannot
  use it through the Hub's workflow.

**`packages/model-harness/src/model_harness/registry.py`** (line 262):
> "These are guidance, not requirements — the suite is BYOM, and any model the
> provider serves is fair game."

The registry's own docstring says recommendations are guidance. The Hub treats
them as requirements. That is the mismatch.

**`apps/artifice-hub/src/artifice_hub/web/server.py`** (line 29) imports
`HardwareTier` from the registry and calls `get_engine_status` / 
`pull_model_command` from `engine.py`. The server exposes these to the
frontend via routes.

**`apps/artifice-hub/src/artifice_hub/web/static/hub.js`** consumes the
`all_satisfied` / `missing` fields to render the install UI.

### What's wrong

1. **`all_satisfied` is a gate, not guidance.** A user with a working Ollama
   setup running a non-registry model (e.g., their own fine-tune, or a smaller
   quantisation) sees "missing models" and is blocked from launching.

2. **The Hub can only offer `ollama pull` for registry models.** A user who
   wants to use a model not in the registry has no path through the Hub —
   they must install it manually and then the Hub still says it's "missing."

3. **The registry is frozen data, not user-configurable.** There is no
   mechanism for a user to tell the Hub "I'm using this model instead" and
   have the Hub accept it as satisfied.

### Fix approach

**Make recommendations advisory, not mandatory.** The Hub should:

1. **Separate "engine ready" from "models installed."** `all_satisfied` should
   mean "Ollama is installed and running" — not "all recommended models are
   present." A user with Ollama running and zero registry models installed
   should still be able to launch an app.

2. **Show recommended models as suggestions, not requirements.** Change the
   frontend from "missing models" (red/blocking) to "suggested models"
   (blue/informational). The pull button stays — it's useful — but it's an
   opt-in convenience, not a gate.

3. **Detect what's actually installed and let the user pick.** The Hub already
   probes Ollama for installed models (`probe_endpoint` in `engine.py:86`).
   Surface the full installed-model list to the user, not just the intersection
   with the registry. Let the user choose which installed model to use for each
   role (vision, chat, translation, embedding) — and write that choice to the
   app's config.

4. **Add a "skip model installation" path.** A user who already has models
   should be able to dismiss the model suggestions and launch the app
   directly. The `all_satisfied` gate should be removed or replaced with
   `engine_ready = ollama.installed and ollama.running`.

5. **Write the user's model choice to the app's config.** When a user picks
   an installed model for a role, the Hub writes it to the app's
   `~/.artifice_<app>/settings.json` (e.g., `ocr_model`, `cleanup_model`).
   This already works for the OCR app's `PERSISTED_KEYS` — extend it to all
   apps.

### Files to change

- `apps/artifice-hub/src/artifice_hub/engine.py` — decouple
  `all_satisfied` from model presence; add `engine_ready` field; surface full
  installed model list
- `apps/artifice-hub/src/artifice_hub/web/server.py` — pass the new status
  shape to the frontend
- `apps/artifice-hub/src/artifice_hub/web/static/hub.js` — change "missing"
  UI from blocking to advisory; add model-picker for installed models; add
  "skip" path
- `apps/artifice-hub/src/artifice_hub/state.py` — if model choices need
  persisting across Hub sessions, store them here

### What NOT to change

- `packages/model-harness/src/model_harness/registry.py` — the registry is
  correct: it says "guidance, not requirements." The bug is in the Hub's
  interpretation, not the registry.
- The apps' own config systems — they already read model names from config.
  The Hub just needs to write to them.

---

## Problem 2: Window management capabilities are inconsistent and duplicated

### Current state (verified)

**No shared window module exists.** `packages/shared-ui/` has
`server_bootstrap.py` (port discovery, server thread) and `path_validation.py`
but no window management. Every app has its own `window.py`:

| App | `_WindowApi` methods | Lines |
|---|---|---|
| `artifice-hub` | minimize, maximize, restore, toggle_maximize, resize, destroy | 182 |
| `artifice-ocr` | minimize, destroy | 159 |
| `artifice-graph` | minimize, destroy | ~159 |
| `artifice-draft` | minimize, destroy | ~159 |
| `artifice-transcribe` | minimize, destroy | 159 |

The Hub's `window.py` is the superset — it has `maximize()`, `restore()`,
`toggle_maximize()`, and `resize()` that the others lack. The other four are
near-identical copies (same `_unblock_frozen_bundle`, same
`open_native_window` signature, same `frameless=True`, `resizable=True`,
`min_size=(640, 480)`).

All five use the same pywebview pattern:
- `frameless=True` — custom title bar in HTML/JS
- `easy_drag=False` — window-wide drag would hijack page interactions
- `js_api=_WindowApi()` — exposes methods to JS as `window.pywebview.api.*`
- `webview.start(gui=None)` — auto-detect backend

The Hub's frontend (`hub.js`) calls `window.pywebview.api.toggle_maximize()`,
`resize()`, etc. The other apps' frontends can only call `minimize()` and
`destroy()` — they lack the JS API methods for maximize/restore/resize.

### Fix approach

**Extract a shared `open_native_window` into `packages/shared-ui/`** with the
Hub's full `_WindowApi` (the superset), then have all five apps import it
instead of carrying their own copies.

### Files to change

1. **New: `packages/shared-ui/shared_ui/window.py`** — extract the Hub's
   `window.py` as a shared module. Contains:
   - `WindowResult` class
   - `WindowApi` class (renamed from `_WindowApi` — the underscore is
     invisible to pywebview's introspection, but a public name in a shared
     module is cleaner) with all 6 methods: minimize, maximize, restore,
     toggle_maximize, resize, destroy
   - `_unblock_frozen_bundle()` helper
   - `open_native_window(url, *, title, width, height)` function
   - The `title` parameter defaults to "Artifice" — each app passes its own
     title (e.g., "ArtificeOCR")

2. **Delete: each app's `window.py`** — replace with a thin import:
   ```python
   from shared_ui.window import open_native_window, WindowResult
   ```
   Or keep a 3-line shim file if the import path needs to stay local for
   frozen-bundle resolution. (Check whether `importlib.resources` is needed
   for the shared import in a frozen bundle — the `server_bootstrap.py`
   pattern already works this way, so the import path is proven.)

3. **Update each app's `server.py` `main()`** — the `open_native_window`
   call site stays the same (same signature), just the import source changes.

4. **Update each app's frontend JS** — add window control buttons that call
   the pywebview API methods. The Hub's `hub.js` already has this pattern;
   copy it to the other apps' frontends. Specifically:
   - Add a window control bar (or extend the existing masthead) with
     minimize, maximize/restore, and close buttons
   - Wire each button to `window.pywebview.api.minimize()`,
     `window.pywebview.api.toggle_maximize()`, `window.pywebview.api.destroy()`
   - The close button calls `destroy()` which exits the app

5. **Test: `packages/shared-ui/tests/test_window.py`** — test that
   `open_native_window` returns `WindowResult(opened=False)` when pywebview
   is not installed (the headless/CI path). Test that `WindowApi` methods
   are no-ops when `_window is None`.

### Constraints

- **Frozen-bundle safety.** The `_unblock_frozen_bundle` helper must stay in
  the shared module — it runs before `import webview` and is needed on Windows
  frozen builds. All five apps need it.
- **Lazy pywebview import.** The `import webview` must stay inside
  `open_native_window()`, not at module top level — users without pywebview
  can still import the shared module for `WindowResult`.
- **Backend auto-detection.** `webview.start(gui=None)` stays — let pywebview
  pick the backend (WebView2 on Windows, WKWebView on macOS, WebKitGTK on
  Linux).
- **Design system.** The window control buttons must use The New Masses
  Design System tokens — no hardcoded colors. The Hub's existing window
  controls are the reference pattern.
- **The `frameless=True` + `easy_drag=False` pattern stays.** All apps use
  a frameless window with a custom HTML title bar. The drag region is
  scoped to the title bar, not the whole window.

---

## Delegation plan

### Lane 1: Hub model registry fix (fixer)
- `engine.py`: decouple `all_satisfied` from model presence; add
  `engine_ready`; surface full installed model list
- `server.py`: pass new status shape
- `hub.js`: change "missing" UI to advisory; add model-picker; add skip path
- `state.py`: persist user model choices if needed

### Lane 2: Shared window module (fixer)
- New `packages/shared-ui/shared_ui/window.py` (Hub's superset)
- Delete/replace each app's `window.py` with import from shared
- Update each app's `server.py` import
- New `packages/shared-ui/tests/test_window.py`

### Lane 3: Window controls in app frontends (ui-ux)
- Add window control buttons (minimize, maximize/restore, close) to each
  app's masthead or a new title bar
- Wire to `window.pywebview.api.*` methods
- Follow the Hub's existing pattern in `hub.js`
- Use design tokens, no hardcoded colors

### Dependencies
- Lane 2 must complete before Lane 3 (the JS API methods must exist before
  the frontend can call them)
- Lane 1 is independent of Lanes 2 and 3

### Verification
- `uv run pytest` across all apps + shared-ui
- `ruff check` on all new/modified Python files
- `node --check` on all modified JS files
- `gitleaks detect` on all new/modified files
- Build wheel for shared-ui and verify `window.py` is packaged
- Verify the Hub's model UI no longer blocks app launch when models are
  "missing"
- Verify all four non-Hub apps have working minimize/maximize/restore/close
  buttons in the native window