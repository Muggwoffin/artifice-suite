# OCR Pipeline for Historical Documents

A local-first pipeline for processing, cleaning, and translating historical documents using LM Studio and Ollama.

## Prerequisites

- Python 3.11+
- [LM Studio](https://lmstudio.ai) running locally with `allenai/olmocr-2-7b` loaded
- [Ollama](https://ollama.com) running locally
- Pull the cleanup model: `ollama pull gemma4:12b`
- Pull the translation model: `ollama pull translategemma:4b`

## Structure

- `src/ocr_pipeline` — Core logic and stages.
  - `pipeline.py` — Stage orchestration. `run_ocr_step` / `run_cleanup_step` /
    `run_translate_step` are the shared units the CLI, the batch runner and the
    GUI all call, so there is one implementation of resume/skip behaviour.
  - `jobs.py` — Threaded job runner with pause/skip/cancel, publishing progress
    as events. Knows nothing about tkinter.
  - `history.py` — SQLite store of completed runs.
  - `tropy.py` — Read-only reader for Tropy projects (never writes).
  - `gui/` — Tabbed application (`theme.py`, `views/`, `widgets/`).
- `configs/` — Configuration files.
- `prompts/` — Prompt templates for LLM operations.

## Installation

```bash
pip install -e .
```

## Usage

### CLI

```bash
# OCR stage (requires LM Studio with olmocr-2-7b)
ocr_pipeline ocr path/to/image.png

# Cleanup stage (requires Ollama)
ocr_pipeline cleanup output/raw_ocr/text/<filename>.txt

# Translation stage (requires Ollama)
ocr_pipeline translate output/cleaned/text/<filename>.txt

# Full pipeline: OCR -> Cleanup -> Translate
ocr_pipeline pipeline path/to/image.png

# Skip translation
ocr_pipeline pipeline path/to/image.png --skip-translate
```

### Tropy archives

Pull documents straight out of a [Tropy](https://tropy.org) project. The
project is opened **read-only** and is never modified — output goes to a
folder.

```bash
# list recent projects, or browse one's lists, tags and items
ocr_pipeline tropy-browse
ocr_pipeline tropy-browse "path/to/Archive.tropy"

# preview the work without running it
ocr_pipeline tropy "path/to/Archive.tropy" --list-id 8 --dry-run

# OCR one list (and its sub-lists) into ./output
ocr_pipeline tropy "path/to/Archive.tropy" --list-id 8

# or by tag / specific items, with a cap for a trial run
ocr_pipeline tropy "path/to/Archive.tropy" --tag resistance --limit 25
```

Tropy stores each page of a PDF as a separate photo, so results are keyed by
item and page — `output/raw_ocr/text/<Item Title>/<file>_p0002.txt` — and a
`tropy_manifest.json` maps every output back to its Tropy photo. Translation
is off by default here; pass `--translate` to enable it.

In the GUI, use **Add from Tropy…** on the Main tab. See
[docs/TROPY_INTEGRATION.md](docs/TROPY_INTEGRATION.md) for details.

Supported input formats: `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`

### GUI

```bash
ocr_pipeline_gui
```

A tabbed desktop application over the same pipeline the CLI uses.

| Tab | What it does |
|-----------|--------------|
| Main | Drag-and-drop queue with live per-stage status, progress and log; **Add from Tropy…** pulls pages from a Tropy archive |
| Preview | Raw / Cleaned / Translated side-by-side, with cleanup diffs highlighted |
| History | Past runs from a local SQLite database, with full text comparison |
| Analytics | Throughput, confidence distribution and per-run timing charts |
| Settings | Models, endpoints, document type and a pre-flight health check |

**Batch control.** While a run is in progress you can **Pause** (between
stages — an in-flight model call is allowed to finish), **Stop**, or **Skip**
individual files. **Retry** re-runs the selected files; because completed
stages leave outputs on disk, a retry resumes rather than starting over.

**Persistence.** Settings live in `~/.ocr_pipeline/settings.json` and run
history in `~/.ocr_pipeline/history.db`. Point the history database somewhere
else with the `history_db` config key. Deleting a run from the History tab
removes only the record — output files are left alone.

**Appearance.** The interface uses the design tokens from the
[public_history](https://github.com/Muggwoffin/public_history) site stylesheet
— the same paper/ink palette, green accent and serif display face. Two
variants ship, matching the site's light default and its dark-mode block:

| `gui_theme` | Look |
|-------------|------|
| `paper` (default) | Cream paper, dark ink — the site's light theme |
| `night` | Warm charcoal, light ink — the site's `prefers-color-scheme: dark` block |

Set it in **Settings → Appearance** (applies on restart, since tk widgets take
their colours when they are built). The font chains are the site's own —
Playfair Display / Libre Baskerville / Archivo, falling back to Georgia and
Franklin Gothic Medium. Install those three Google Fonts locally and the
interface picks them up with no code change.

### Programmatic

```python
from src.ocr_pipeline.pipeline import run_pipeline

result = run_pipeline("path/to/image.png", output_dir="output")
# result = {"raw": {...}, "cleaned": {...}, "translated": {...}}
```

## Output Structure

```
output/
  raw_ocr/
    text/<stem>.txt
    json/<stem>.json
  cleaned/
    text/<stem>.txt
    json/<stem>.json
  translated/
    text/<stem>.txt
    json/<stem>.json
```

## Models

| Stage      | Model                    | Engine     |
|------------|--------------------------|------------|
| OCR        | allenai/olmocr-2-7b      | LM Studio  |
| Cleanup    | gemma4:12b               | Ollama     |
| Translate  | translategemma:4b        | Ollama     |
