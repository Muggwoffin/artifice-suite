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
  - `tropy_write.py` — Writes OCR results back into Tropy as notes/transcriptions.
  - `_guard.py` — Content-preservation guard for the cleanup stage.
  - `_diff.py` — Diff/marker highlighting, shared by both frontends.
  - `gui/` — Tkinter application (`theme.py`, `views/`, `widgets/`).
  - `web/` — FastAPI + vanilla-JS application (`server.py`, `runtime.py`, `static/`).
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

In the GUI, use **Add from Tropy…** on the Main tab. After a run, **Send to
Tropy…** writes the results back as Tropy notes and/or native transcriptions.
That write previews everything first, requires Tropy to be closed, and takes a
timestamped backup before it touches anything. See
[docs/TROPY_INTEGRATION.md](docs/TROPY_INTEGRATION.md) for details.

### Cleanup guard

Cleanup asks a model to rewrite archival text, and over 130 real pages it both
repaired genuine OCR errors *and* damaged some pages — corrupting words that
were already correct, and on fragmentary pages deleting clauses it could not
parse. The guard makes that failure mode safe: if the output looks lossy or has
altered a capitalised word, the raw text is kept instead, so a page is either
cleaned or untouched — never quietly truncated. The rejected version is stored
in the stage JSON as `rejected_cleaned_text` so it can still be reviewed.

| key | default | meaning |
|---|---|---|
| `cleanup_guard` | `true` | Enable the guard |
| `cleanup_guard_max_deleted_words` | `2` | Words that may vanish before rejecting |
| `cleanup_guard_min_length_ratio` | `0.97` | Minimum share of source **letters** kept |
| `cleanup_guard_protect_nouns` | `true` | Reject any change to a capitalised word |

Note that German capitalises every noun, so `cleanup_guard_protect_nouns`
effectively forbids the model from editing German nouns at all. That blocks
`Elsass` → `Elass`, but also blocks the wanted `Narnen` → `Namen`. Turn it off
if you would rather have the noun repairs and review them yourself.

Supported input formats: `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`

### GUI

```bash
ocr_pipeline_gui
```

**Desktop shortcut (Windows).** `OCR Pipeline.lnk` in the project root launches
the GUI with no console window — drag it onto your Desktop. To recreate it
(after moving the project or reinstalling Python):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1
powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1 -Desktop   # also place a copy on the Desktop
```

The shortcut runs [launch_ocr_pipeline.pyw](launch_ocr_pipeline.pyw), which
sets the working directory, verifies the dependencies, and — if the
interpreter it was started with cannot import them — finds one that can and
re-launches itself. Startup failures are reported in a dialog and logged to
`~/.ocr_pipeline/launcher.log` rather than disappearing silently, which is the
usual failure mode for a windowed Python app.

The icon is generated from the same design tokens as the interface:
`py -3.12 scripts/make_icon.py`.

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

### Web frontend

```bash
pip install -e ".[web]"
ocr_pipeline_web              # opens a native window
ocr_pipeline_web --browser    # opens in the default browser instead
```

A full second frontend over the same pipeline, all five tabs at parity with
the desktop build (Main, Preview, History, Analytics, Settings — plus both
Tropy dialogs, "Add from…" and "Send to…"). It started as a spike to test
whether the interface could look like an actual piece of editorial design
rather than a tkinter window — the desktop GUI's palette above is a
hand-translated approximation of the
[public_history](https://github.com/Muggwoffin/public_history) site tokens,
because Playfair Display, Libre Baskerville and Archivo aren't installed as
system fonts. On the web, [`static/index.html`](src/ocr_pipeline/web/static/index.html)
just links the real Google Fonts URL the site itself uses, and dark mode comes
free from `prefers-color-scheme` — no second palette to maintain by hand.
Analytics draws its charts as inline SVG rather than a hand-drawn `tk.Canvas`.

Nothing about the pipeline changed to make this possible. Every module the
web build touches — `jobs`, `pipeline`, `history`, `tropy`, `tropy_write`,
`config` — is exactly what the tkinter build already used; the shared
diff/marker-highlighting logic was lifted out of `gui/widgets/compare_view.py`
into [`_diff.py`](src/ocr_pipeline/_diff.py) so both frontends compute
identical highlights from one implementation, not two that could drift.
[`web/runtime.py`](src/ocr_pipeline/web/runtime.py) is a thin adapter over the
same `JobRunner` the tkinter build uses; progress reaches the browser as
Server-Sent Events over the same `queue.Queue` the runner already published to.
The desktop GUI is untouched and still a complete, independent build.

Native file/folder dialogs need [pywebview](https://pywebview.flowrl.com/)
(installed by the `web` extra). Without it — or with `--browser` — file and
folder pickers fall back to typing a path, because a browser tab is not
allowed to learn the real filesystem path of a dropped or selected file; that
boundary is enforced by the browser itself, not something this app can work
around.

`launch_ocr_pipeline_web.pyw` follows the same self-healing pattern as the
desktop launcher: it finds a Python with the web dependencies if the one that
started it lacks them, and prefers an interpreter that also has pywebview.
There is no desktop-shortcut script for it yet.

**Known limitation:** the SSE stream serves one browser tab per run. Two tabs
open at once would each receive only some of the events, since reading a
`queue.Queue` removes what it reads. Fine for one person in one tab; a
multi-tab build would need to fan events out to a queue per connection.

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

### Why cleanup is fast (`ollama_think`)

`gemma4:12b` is a reasoning model: left alone it emits a chain-of-thought block
before answering. On mechanical OCR repair that is almost pure waste. Measured
on a real archival page (1,769 characters):

| | wall clock | tokens generated |
|---|---|---|
| reasoning on | 104.5 s | 7,664 |
| reasoning off | 8.0 s | 569 |

Same model, same GPU, output identical in length — about **13x**, or 8.3 hours
versus 26 minutes over a 286-page batch. `ollama_think` therefore defaults to
`false`.

The saving is not free, though, and the two halves go together. Part of what
the reasoning was doing was deliberating over whether to modernise the text.
With it off and the old loose prompt, the model silently "improved" the source:
`ueber` → `über`, `Marz` → `März`, and — worse — `Pans` → `Paris`,
`Landon` → `London`. Inferring place names is exactly the corruption an
archival transcription must not make.

`prompts/cleanup_prompt.txt` is therefore written as a mechanical repair brief
rather than an editing brief: it enumerates the artifacts to fix, forbids
touching umlaut transliterations and proper nouns, and says to leave anything
uncertain alone. **If you rewrite that prompt, keep the prohibitions** — they
are what makes running without reasoning safe.

Turn reasoning back on in **Settings → Model reasoning**, or with
`ollama_think: true`.

## Hardware requirements

The pipeline runs four models across two engines sequentially (OCR → Cleanup → Translate → Structure). Only one model is active per engine at a time, but LM Studio and Ollama each keep their own model in VRAM concurrently.

### Recommended

| Component | Requirement |
|---|---|
| GPU VRAM | 16 GB (e.g. RTX 4060 Ti 16 GB, RTX 4070+) |
| System RAM | 32 GB |
| Disk | 40 GB free on SSD |
| CPU | 8+ cores (Intel i7 / AMD Ryzen 7) |
| Mac | Apple Silicon M3/M4 Pro with 24 GB unified memory |

This comfortably fits both engines' largest models simultaneously with room for context windows. At default quantization (Q4_K_M), the models use ~5.5 GB (olmocr) + ~6.6 GB (gemma4) + ~2.9 GB (translategemma) during operation — about 12–15 GB combined — leaving headroom on a 16 GB card.

### Minimum (GPU)

| Component | Requirement |
|---|---|
| GPU VRAM | 12 GB (e.g. RTX 3060 / 4070) |
| System RAM | 16 GB |
| Disk | 20 GB free on SSD |
| CPU | 6+ cores |

Works, but tight. You may need to unload models between stages to fit within VRAM. Expect occasional out-of-memory errors on long context windows.

### Minimum (CPU-only)

Both LM Studio and Ollama can run without a GPU. Expect 5–10× slower inference.

| Component | Requirement |
|---|---|
| System RAM | 32 GB (all model weights live in RAM) |
| Disk | 20 GB free on SSD |
| CPU | 8+ cores (Intel i7 / AMD Ryzen 7) |

A 275-page archive would take several hours instead of ~30 minutes.

### Mac (Apple Silicon)

Unified memory is shared between CPU and GPU — the numbers below are system RAM, not VRAM.

| Tier | Chip | Memory | Notes |
|---|---|---|---|
| Minimum | M1 Pro | 16 GB | Workable; models compete for the same pool |
| Recommended | M3/M4 Pro | 24 GB | Comfortable headroom for context windows |
| Ideal | M4 Pro | 48 GB | Best consumer option |
| Avoid | Intel Mac | — | No Metal acceleration; CPU-only fallback is slow |

### Lower-powered configurations

You can substitute lighter models to run on less capable hardware:

| Stage | Lightweight alternative | VRAM saved | Trade-off |
|---|---|---|---|
| OCR | `allenai/olmocr-2b` (~2 GB) | ~3.5 GB | Lower accuracy on dense/historical layouts |
| OCR | `Qwen2.5-VL-3B-Instruct` GGUF (~2.5 GB) | ~3 GB | Good general OCR, less tested on archival fonts |
| Cleanup | `gemma4:9b` (~5 GB at Q4_K_M) | ~1.6 GB | Slightly less capable at complex repairs |
| Cleanup | `llama3.1:8b` (~4.9 GB at Q4_K_M) | ~1.7 GB | Adequate for English-only cleanup |
| Translate | `llama3.2:3b` (~2.2 GB at Q4_K_M) | ~0.7 GB | Adequate for short passages; worse on long-form |
| Translate | `qwen2.5:7b` (~4.4 GB at Q4_K_M) | — (larger) | Better translation quality than translategemma if you have the VRAM |

You can also trade quality for size by adjusting quantization across *any* model:

| Quantization | Relative size | Typical VRAM multiplier | Quality impact |
|---|---|---|---|
| Q4_K_M (default) | 1.0× | baseline | None visible |
| Q3_K_S / Q3_K_M | ~0.75× | −25% | Slight perplexity increase; fine for OCR/cleanup |
| Q2_K | ~0.55× | −45% | Noticeable degradation on reasoning tasks; avoid for structure |
| Q5_K_M | ~1.15× | +15% | Negligible gain over Q4 for these tasks |
| Q8_0 | ~1.5× | +50% | Near-lossless; useful if you have the VRAM |
| FP16 | ~2.0× | +100% | Full precision; no practical benefit over Q8 for inference |

The models are configured in `configs/default.yaml` (or set them per-session via the Settings tab in either frontend).

### How to reduce VRAM usage

1. **Run models one at a time.** Use the CLI to run each stage separately instead of `pipeline`, so models unload between stages.
2. **Lower context window.** Set `max_output_tokens` in config or reduce Ollama's `num_ctx` (default 2048) in the model's Modelfile.
3. **Use CPU offloading.** Both LM Studio and Ollama let you offload some layers to CPU. Set `--num-gpu-layers` to a lower value in Ollama's Modelfile (`ollama show` to see the default; typical default is full offload for 12B models).
4. **Pick a less quantized GGUF.** In LM Studio, choose a Q3_K_M GGUF of olmocr instead of Q4_K_M.

### PDF export

Compile a folder of processed text files into a single readable PDF. The output
is a continuous-flow reading document — one continuous document for a multi-page
KV file, not 275 separate page images.

```bash
# Quick check: concatenate cleaned text as-is (no model call)
ocr_pipeline compile-pdf output/cleaned/text/Fritz\ Eberhard\ KV --no-structure

# Full: structure for reading, then render to PDF
ocr_pipeline compile-pdf output/cleaned/text/ISK\ Comms\ with\ Switzerland\ Part\ I \
    --output isk_comms.pdf

# Choose which stage to read from
ocr_pipeline compile-pdf output/cleaned/text/My\ Item --stage translated
```

The structuring pass (enabled by default) asks a model to add paragraph breaks
and blank lines for readability. It does **not** change any words — a strict
guard verifies word-for-word equality of the original text, and if the model
alters anything the page appears unstructured in the final PDF.

In the GUI, click **Compile PDF…** on the Main tab to open a dialog: pick a
folder of processed text files, choose a stage and output path, and watch live
progress while the PDF compiles. A "Guard rejected" line reports pages whose
structuring was skipped; the **Open PDF** button opens the result once done.

In the web UI, the same **Compile PDF…** button opens a modal with folder
browsing, stage selection, and a progress log streamed via Server-Sent Events.
Click **Download** when the status shows it is complete to retrieve the PDF.

| key | default | meaning |
|---|---|---|
| `structure_guard` | `true` | Enable the word-preservation guard |

The PDF uses Playfair Display (headings) and Libre Baskerville (body text) for
visual consistency with the rest of the app. Each page section carries a small
provenance marker (e.g. `[page1]`) so passages can be traced back to their
source scan.

When a `tropy_manifest.json` is present in the folder's parent chain, pages are
ordered by their manifest `page_number` and the item title is used as the PDF
title.
