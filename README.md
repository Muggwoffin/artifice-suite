<img width="960" height="540" alt="Readme Logo (1)" src="https://github.com/user-attachments/assets/4a68238d-20b1-4461-9cdb-eba2aed69bfc" />
<h1 align="center"> OCR | Transcribe Speech | Visualise Data | Copy Edit </h1>

<p align="center">
  <a href="https://doi.org/10.5281/zenodo.21621935">
    <img src="https://img.shields.io/badge/DOI-10.5281%2Fzenodo.21621935-blue.svg" alt="DOI">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/Licence-AGPL--3.0--or--later-blue" alt="Licence: AGPL-3.0-or-later">
  </a>
  <a href=".github/workflows/ci.yml">
    <img src="https://img.shields.io/badge/CI-four%20apps%20%C3%97%20three%20platforms-blue" alt="CI">
  </a>
  <a href="pyproject.toml">
    <img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11+">
  </a>
</p>

A collection of local-first and open-source tools that place a user-friendly interface over models. Buttons, forms, and human-in-the-loop checks create predictable results rather than open-ended chatbot surprises. Designed to support digital humanities research.

## Applications

| App | What it does | Model backends |
|---|---|---|
| 🖥️ **Artifice Hub** | Native GUI launcher and installer. Manages installation, updating, and launching of all four apps. Handles the PyTorch CUDA hardware probe natively. Ships frozen only (not on PyPI). | — |
| 📷 **Artifice OCR** | Local-first OCR processing: edit raw OCR output, clean up text, auto-generate archival page titles (optional), and translate documents in one workflow. Integrates with Tropy via JSON-LD and live read-only `.tpy` browse; previewed Developer API write-back attaches notes to original photos. | Ollama, LM Studio, OpenAI-compatible, Hugging Face |
| 🎧 **Artifice Transcribe** | Oral history transcription with a speech-to-text model of your choice, coupled with pyannote diarization for speaker labels. Produces OHMS- and TEI-compliant transcripts. | Whisper / Parakeet, pyannote |
| 🗺️ **Artifice Graph** | Knowledge graph creator extracting entities and relationships into a variety of formats. Integrated with Obsidian for navigable graphs. | Ollama, LM Studio, OpenAI-compatible |
| 📝 **Artifice Draft** | Copy and paste an academic journal style guide for precise edits of your writing. Outputs a track-changed Word file: you veto any change. | Ollama, LM Studio, OpenAI-compatible, Anthropic |

## Quick start

The suite is a [uv](https://docs.astral.sh/uv/) workspace. No Node toolchain
is required anywhere.

### Install from PyPI (primary)

All four apps are published at `0.3.0` (the Hub ships frozen only, never to
PyPI). Install one or more with:

```bash
uv tool install "artifice-ocr[web]"              # OCR pipeline
uv tool install "artifice-draft[web]"             # copy editing
uv tool install "artifice-graph[web]"             # knowledge graph
uv tool install "artifice-transcribe[asr-cuda]"   # speech-to-text + CUDA
```

On Windows PowerShell:

```powershell
uv tool install "artifice-ocr[web]"
uv tool install "artifice-transcribe[asr-cuda]"
```

**`artifice-transcribe[asr-cuda]` includes the full CUDA-enabled PyTorch stack.**
The `[web]` extra gates FastAPI and Uvicorn — all four apps need them. The `[asr-cuda]`
extra gates the speech-recognition stack (Whisper/Parakeet + pyannote). Artifice Hub
handles the CUDA hardware probe natively when launched from the Hub; on bare installs
the first transcription attempt triggers the prompt.

> **Note on size.** `[asr-cuda]` resolves PyTorch from default PyPI, which bundles
> the CUDA runtime — several gigabytes. The workspace pins a CPU-only PyTorch index,
> but that pin is uv workspace configuration and **is not carried in the published
> package**, so it does not apply to a PyPI install. If you want a CPU-only stack,
> select a CPU PyTorch index yourself, or install from a clone (below), where the pin
> applies.

### Install from a clone (development)

If you are working on the suite itself, clone the repo and run the
bootstrap script from the repo root:

```bash
git clone https://github.com/Muggwoffin/artifice-suite.git
cd artifice-suite
bash scripts/install.sh artifice-ocr        # install one app
bash scripts/install.sh artifice-ocr artifice-draft artifice-graph  # several
```

On Windows PowerShell:

```powershell
.\scripts\install.ps1 artifice-ocr
.\scripts\install.ps1 artifice-transcribe -Cuda   # GPU stack
```

This installs `uv` if it is missing, then runs `uv tool install --editable`
from the local workspace — it keeps the apps linked to your clone for
development. Uninstall with `bash scripts/uninstall.sh <app>`.

### Install (Docker)

Each app has its own `Dockerfile`:

```bash
cd apps/artifice-ocr
docker build -t artifice-ocr .
docker run -p 8000:8000 artifice-ocr
```

### Build Artifice Hub (frozen)

Artifice Hub is a native PyWebView GUI that manages installation, updating, and
launching of all four apps. It ships frozen only — no Dockerfile, no PyPI publish.

```bash
uv run pyinstaller apps/artifice-hub/artifice-hub.spec
```

The spec produces a single-file executable (deviation from the suite's onedir
pattern — a GUI launcher is a single entry point). Run the resulting
`dist/artifice-hub` directly; there is no `uv tool install` for the Hub.

### Uninstall

```bash
bash scripts/uninstall.sh artifice-ocr
```

The uninstaller removes the programs but **leaves your data in place**. It
prints the exact path and warns that it may contain an API key. It never
deletes your data automatically.

Each app documents its own setup and entry points in its own `README.md`.

### Supported apps

| App | Install name | Commands after install | Data directory |
|---|---|---|---|
| Hub | — (frozen only) | `artifice-hub` (after building) | — |
| OCR | `artifice-ocr[web]` | `artifice-ocr`, `artifice-ocr-web` | `~/.artifice_ocr/` |
| Draft | `artifice-draft[web]` | `artifice-draft`, `artifice-draft-web` | `~/.artifice_draft/` |
| Graph | `artifice-graph[web]` | `artifice-graph`, `artifice-graph-web` | platformdirs(`artifice-graph`, `ArtificeSuite`) |
| Transcribe | `artifice-transcribe[asr-cuda]` | `artifice-transcribe` | platform-dependent (see `artifice-transcribe --data-dir`) |

> **Note:** ArtificeGraph stores its data under the platform-conventional
> user-data directory (was `~/.callosip/` prior to v0.1.1 — migrated
> automatically on first launch). The uninstaller reports this explicitly
> so you do not mistake it for a directory belonging to another application.

### Frameless window mode

All four apps run in frameless PyWebView windows — no OS window borders or native
title bar. The shared masthead (`_masthead.html`) acts as the draggable title bar.
Minimize and Close buttons are inline SVG, hidden by default and revealed by the
`pywebviewready` event. This is the expected appearance; do not report it as a
layout bug.

### Send To (inter-app handoff)

Apps can send extracted text and data to each other via a file-based handoff using
a platformdirs shared directory (e.g., OCR → Draft, OCR → Graph). The mechanism is
documented in each app's own README.

## What makes this suite different

- **Bring Your Own Model.** Use a model on your machine, a cloud model, or one your university hosts on a local network — your credentials, your endpoint.
- **Data privacy.** Artifice never connects to the internet unless you permit it. By default none of your research material leaves your machine.
- **Digital sovereignty.** Built from the ground up to work with open models, reducing dependency on corporations for digital tools and data storage.
- **Minimal computing.** Artifice never uses an LLM where a straightforward script achieves the same result.
- **Harness architecture, not chat.** All model interactions pass through a schema-validated contract in `packages/model-harness` — structured data in, structured data out. There is deliberately no chat interface anywhere in the suite.

## Repository layout

```
apps/                        # five applications (four desktop apps + Hub launcher)
  artifice-hub/              #   native GUI launcher and installer (frozen/PyInstaller only)
  artifice-ocr/              #   OCR pipeline (Tropy integration, PDF export)
  artifice-draft/            #   copy editing with tracked changes
  artifice-graph/            #   knowledge graph + Obsidian export
  artifice-transcribe/       #   speech-to-text + diarization API
packages/                    # shared, version-locked packages
  model-harness/             #   structured model-interaction contract
  shared-ui/                 #   design tokens, fonts, shared templates
  secure-io/                 #   OS-appropriate access control for secret files
design-system/               # The New Masses design specification (reference only)
scripts/                     # dev tooling: audits, checks, agent dispatch
```

All four apps keep an identical internal layout (`src/<package>/`, `tests/`, `pyproject.toml`, `Dockerfile`, `README.md`). See [ARCHITECTURE.md](ARCHITECTURE.md).

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — monorepo layout and the model-harness contract
- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, conventions, and how to submit a PR
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — Contributor Covenant 2.1
- [SECURITY.md](SECURITY.md) — how to report a vulnerability
- [ROADMAP.md](ROADMAP.md) — where the project is going, and what is deliberately out of scope
- [Design_Philosophy.md](Design_Philosophy.md) — The New Masses design system
- [docs/index.md](docs/index.md) — a map of every document in the repository

## Licence

Artifice Suite is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version. See [LICENSE](LICENSE) for the full terms.

Bundled third-party components carry their own licences (BSD-2-Clause for
Leaflet, OFL-1.1 for fonts). Every file's licence is machine-checked by
[REUSE](https://reuse.software/) in CI.
