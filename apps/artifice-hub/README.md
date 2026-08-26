# Artifice Hub

Native launcher and installer for the [Artifice Suite](https://github.com/Muggwoffin/artifice-suite) — a lightweight, PyInstaller-frozen PyWebView Python app that acts as a GUI for [uv](https://docs.astral.sh/uv/).

## What the Hub Does

- **Discovers** which of the four Artifice apps (OCR, Draft, Graph, Transcribe) you have installed via `uv tool`.
- **Installs** missing apps with one click (handles the 5.8 GB PyTorch CUDA pack for Transcribe natively).
- **Updates** outdated apps.
- **Launches** installed apps in their own windows or browser tabs.

## Why It Exists

Using Artifice Suite from the command line works, but a graphical launcher lowers the barrier for academic historians who do not want to think about `uv tool install` and extras syntax. The Hub is the single download that gets them started.

## Deliberate Omissions

- **No Dockerfile** — the Hub is a GUI application. Running it inside a container is meaningless (it needs a display, a webview backend, and access to the host's `uv` installation).
- **No PyPI publish** — the Hub ships as a frozen executable, not as a pip-installable package. The `pyproject.toml` exists for development and for the workspace resolver.
- **No model calls** — the Hub makes zero model interactions. It is purely a launcher and installer. The [harness architecture mandate](../../CLAUDE.md) does not apply here.
- **Onefile, not onedir** — every other app ships as `onedir` (a folder). The Hub is a single double-clickable `.exe`/`.app` because it is a tiny launcher (fastapi + pywebview, no model libraries) and onefile is the expected UX for a launcher.

## Building

From the repo root:

```bash
uv run --with pyinstaller pyinstaller apps/artifice-hub/artifice-hub.spec
```

The output is a single executable in `dist/artifice-hub` (or `dist/artifice-hub.exe` on Windows).

## Development

```bash
# From the repo root — add the Hub to the workspace resolver:
uv sync

# Start in dev mode (opens a browser):
uv run artifice-hub

# Start server-only (no window/browser):
uv run artifice-hub --no-window

# Run tests:
uv run pytest apps/artifice-hub/tests/ -x -q
```

## Architecture

- **`src/artifice_hub/registry.py`** — frozen app registry. The injection-safety boundary — app names are constants, never user input.
- **`src/artifice_hub/uv_backend.py`** — subprocess layer for `uv` commands. All calls use list-form argv (`shell=False`). Progress is streamed over SSE.
- **`src/artifice_hub/hardware.py`** — GPU/OS probe (detects NVIDIA CUDA, Apple Silicon, or CPU).
- **`src/artifice_hub/state.py`** — persistent JSON state via `platformdirs`.
- **`src/artifice_hub/web/server.py`** — FastAPI app + `main()` bootstrap (port discovery, server thread, native window/browser launch).
- **`src/artifice_hub/web/window.py`** — pywebview native window wrapper.
- **`src/artifice_hub/web/static/`** — vanilla HTML/CSS/JS dashboard. No frameworks, no build step.

## License

AGPL-3.0-or-later
