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
| 📷 **Artifice OCR** | Local-first OCR processing: edit raw OCR output, clean up text and translate documents in one workflow. Integrates with Tropy to import archival photographs and send transcriptions back. | Ollama, LM Studio, OpenAI-compatible, Hugging Face |
| 🎧 **Artifice Transcribe** | Oral history transcription with a speech-to-text model of your choice, coupled with pyannote diarization for speaker labels. Produces OHMS- and TEI-compliant transcripts. | Whisper / Parakeet, pyannote |
| 🗺️ **Artifice Graph** | Knowledge graph creator extracting entities and relationships into a variety of formats. Integrated with Obsidian for navigable graphs. | Ollama, LM Studio, OpenAI-compatible |
| 📝 **Artifice Draft** | Copy and paste an academic journal style guide for precise edits of your writing. Outputs a track-changed Word file: you veto any change. | Ollama, LM Studio, OpenAI-compatible, Anthropic |

## Quick start

The suite is a [uv](https://docs.astral.sh/uv/) workspace. No Node toolchain
is required anywhere.

### Install (primary: `uv`)

Clone the repo and run the bootstrap script from the repo root:

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

The script installs `uv` for you if it is missing, then runs
`uv tool install --editable` from the local workspace. No packages are
published to any index yet — the install relies on the cloned repo.

For `artifice-transcribe` the default is a **CPU-only torch stack**
(~1.6 GB download). Pass `--cuda` (or `-Cuda` on PowerShell) to opt into
the CUDA build (~7.2 GB).

### Install (development, within the workspace)

```bash
uv sync --extra all      # all four apps + shared packages, editable
uv run artifice-ocr      # or artifice-draft / artifice-graph / artifice-transcribe
```

### Install (Docker)

Each app has its own `Dockerfile`:

```bash
cd apps/artifice-ocr
docker build -t artifice-ocr .
docker run -p 8000:8000 artifice-ocr
```

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
| OCR | `artifice-ocr` | `artifice-ocr`, `artifice-ocr-web` | `~/.artifice_ocr/` |
| Draft | `artifice-draft` | `artifice-draft` | `~/.artifice_draft/` |
| Graph | `artifice-graph` | `artifice-graph`, `artifice-graph-web` | platformdirs(`artifice-graph`, `ArtificeSuite`) |
| Transcribe | `artifice-transcribe` | `artifice-transcribe` | platform-dependent (see `artifice-transcribe --data-dir`) |

> **Note:** ArtificeGraph stores its data under the platform-conventional
> user-data directory (was `~/.callosip/` prior to v0.1.1 — migrated
> automatically on first launch). The uninstaller reports this explicitly
> so you do not mistake it for a directory belonging to another application.

## What makes this suite different

- **Bring Your Own Model.** Use a model on your machine, a cloud model, or one your university hosts on a local network — your credentials, your endpoint.
- **Data privacy.** Artifice never connects to the internet unless you permit it. By default none of your research material leaves your machine.
- **Digital sovereignty.** Built from the ground up to work with open models, reducing dependency on corporations for digital tools and data storage.
- **Minimal computing.** Artifice never uses an LLM where a straightforward script achieves the same result.
- **Harness architecture, not chat.** All model interactions pass through a schema-validated contract in `packages/model-harness` — structured data in, structured data out. There is deliberately no chat interface anywhere in the suite.

## Repository layout

```
apps/                        # the four desktop applications
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
