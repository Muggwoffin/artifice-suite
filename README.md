# ArtificeOCR

A local-first pipeline for processing, cleaning, structuring, translating, and publishing historical documents — built for archival research, not demos.

Runs entirely on your hardware via **LM Studio** (OCR) and **Ollama** (cleanup, translation, structuring). No cloud APIs, no data leaves your machine.

---

## What It Does

| Stage | Model (default) | Engine | Purpose |
|-------|-----------------|--------|---------|
| **OCR** | `allenai/olmocr-2-7b` | LM Studio | Image → raw text |
| **Cleanup** | `gemma4:12b` | Ollama | Repair OCR artifacts (no rewriting) |
| **Structure** | `gemma4:12b` | Ollama | Add paragraph breaks for reading (guarded: never rewrites) |
| **Translate** | `translategemma:4b` | Ollama | German → English (optional) |

**Outputs at every stage:** raw text + structured JSON with model, prompt, confidence, guard results, timings.

**Export formats:**
- **PDF** — continuous reading document with section headings, provenance markers, Playfair/Libre Baskerville typesetting
- **LudwigLang Markdown** — front-matter + body for the [LudwigLang](https://github.com/Muggwoffin/public_history) editorial web publisher
- **Tropy** — write results back as notes/transcriptions into your Tropy archive (with preview + backup)

---

## Design Philosophy

**ArtificeOCR is not a generic OCR tool.** It is built for historical research on German-language archival material (1920s–40s), with three non-negotiable constraints:

1. **Local-first, always.** Models run on your GPU via LM Studio/Ollama. No API keys, no uploads.
2. **Preservation over prettiness.** The cleanup and structure stages are *guarded*: if the model alters a word that should stay intact (capitalised nouns, umlaut transliterations, proper nouns), the original is kept. The model's attempt is saved as `rejected_*` for review — nothing is silently lost.
3. **Editorial design, not app chrome.** Both frontends (Tkinter desktop, FastAPI+Vanilla JS web) implement the **New Masses** design system — warm paper/ink palette, Playfair Display + Libre Baskerville + Archivo, Soviet Constructivist editorial layout, editorial motion (rule draw-in, card lift, star settle). No framework chrome, no generic UI kit.

---

## Quick Start

### Prerequisites
- Python 3.11+
- [LM Studio](https://lmstudio.ai) running locally with `allenai/olmocr-2-7b` loaded
- [Ollama](https://ollama.com) running locally
- Models: `ollama pull gemma4:12b` && `ollama pull translategemma:4b`

### Install
```bash
pip install -e .              # CLI + desktop GUI
pip install -e ".[web]"       # + web frontend
```

---

## Interfaces

| Interface | Command | What You Get |
|-----------|---------|--------------|
| **CLI** | `ocr_pipeline` | Scriptable, scriptable, scriptable |
| **Desktop GUI** | `ocr_pipeline_gui` | Tkinter app, 5 tabs, drag-drop queue, Tropy import/export |
| **Web UI** | `ocr_pipeline_web` | FastAPI + vanilla JS at `http://127.0.0.1:8765`, full parity + real fonts + dark mode |

**Both GUIs share the exact same pipeline modules** (`pipeline`, `jobs`, `history`, `tropy`, `tropy_write`, `_diff`, `_guard`, `pdf_export`, `export_ludwiglang`). The web build is not a rewrite — it's the same Python core with a thin SSE adapter.

---

## CLI Usage

```bash
# Single stages
ocr_pipeline ocr path/to/image.png
ocr_pipeline cleanup output/raw_ocr/text/file.txt
ocr_pipeline structure output/cleaned/text/file.txt
ocr_pipeline translate output/structured/text/file.txt

# Full pipeline (OCR → Cleanup → Structure → Translate)
ocr_pipeline pipeline path/to/image.png
ocr_pipeline pipeline path/to/image.png --skip-translate

# Tropy archive integration (read-only browse, then process)
ocr_pipeline tropy-browse                    # list recent .tropy projects
ocr_pipeline tropy-browse "path/Archive.tropy" --list-id 3
ocr_pipeline tropy "path/Archive.tropy" --list-id 3 --limit 10 --dry-run
ocr_pipeline tropy "path/Archive.tropy" --tag resistance --translate

# PDF compilation (from any stage folder)
ocr_pipeline compile-pdf output/cleaned/text/My\ Collection --stage cleaned
ocr_pipeline compile-pdf output/structured/text/My\ Collection --structure

# LudwigLang Markdown export (for web publishing)
ocr_pipeline export-md output/cleaned/text/My\ Collection \
  --medium print --author "Fritz Eberhard" --date "1936-1939"
```

---

## Tropy Integration

**Read-only browse:** `ocr_pipeline tropy-browse` lists projects, lists, tags, items, photos — never writes.

**Process from Tropy:** Pull items by list ID, tag, or item IDs. Output mirrors Tropy's item/page structure:
```
output/raw_ocr/text/<Item Title>/<photo>_p0001.txt
output/tropy_manifest.json   # maps every output file → Tropy photo UUID + page number
```

**Write back to Tropy:** GUI → **Send to Tropy…** writes cleaned/structured/translated text as Tropy *notes* and/or native *transcriptions*. Preview-first, requires Tropy closed, writes timestamped backup first. See [docs/TROPY_INTEGRATION.md](docs/TROPY_INTEGRATION.md).

---

## The Guard System (Preservation Over Prettiness)

Both **Cleanup** and **Structure** stages are guarded:

| Stage | Guard | What It Protects |
|-------|-------|------------------|
| Cleanup | `_guard.check_cleanup` | Capitalised nouns (German nouns), umlaut transliterations (`ueber`→`über` forbidden), word deletion threshold (default ≤2 words), length ratio (≥97% letters retained) |
| Structure | `_guard.check_structure_only` | **Word-for-word equality** — only newlines may be added. Any word change → original kept, rejected version saved as `rejected_structured_text` |

**Config keys** (in `configs/default.yaml` or Settings tab):
```yaml
cleanup_guard: true
cleanup_guard_max_deleted_words: 2
cleanup_guard_min_length_ratio: 0.97
cleanup_guard_protect_nouns: true   # German nouns = capitalised → protected
structure_guard: true
```

> **Why this matters:** On 130+ real archival pages, the cleanup model *both* fixed real OCR errors **and** corrupted correct words (deleting clauses on fragmentary pages, "correcting" `Elsass`→`Elass`, `Narnen`→`Namen`). The guard makes that failure mode safe: a page is either cleaned *or* left raw — never silently mangled.

---

## PDF Export

**GUI:** Main tab → select queue items → **Compile PDF…** → single combined PDF with section headings per item, provenance markers (`[page1]`), structured text if enabled.

**CLI:**
```bash
ocr_pipeline compile-pdf output/cleaned/text/Collection --stage cleaned --structure
ocr_pipeline compile-pdf output/structured/text/Collection --output out.pdf
```

**Web:** Same modal, folder picker (path input), progress via SSE, **Download** button when ready.

Typography: Playfair Display (headings), Libre Baskerville (body), provenance markers per page.

---

## LudwigLang Markdown Export

Export cleaned/structured text as a single `.md` with LudwigLang front matter for the [public_history](https://github.com/Muggwoffin/public_history) publisher:

```bash
ocr_pipeline export-md output/cleaned/text/Collection \
  --medium print --author "Fritz Eberhard" --date "1936–1939" \
  --page-markers --skip-language-gate
```

**Front matter fields:** `title`, `date`, `author`, `medium` (`typed|handwritten|print`), `language` (de/en), `tags`, `source` (Tropy UUID), `page_markers`.

**GUI:** **Export → LudwigLang…** tab — preview, configure, export, drag `.md` onto `http://localhost:8765/import`.

**Web:** Full parity, same modal.

---

## Dual Frontend Architecture

| Layer | Desktop (Tkinter) | Web (FastAPI + Vanilla JS) |
|-------|-------------------|----------------------------|
| Pipeline core | `pipeline.py`, `jobs.py`, `stages/*` | **Identical** |
| Tropy read/write | `tropy.py`, `tropy_write.py` | **Identical** |
| History (SQLite) | `history.py` | **Identical** |
| Diff/highlight | `_diff.py` (lifted from GUI) | **Identical** |
| Guards | `_guard.py` | **Identical** |
| PDF export | `pdf_export.py` | **Identical** |
| LudwigLang export | `export_ludwiglang.py` | **Identical** |
| UI framework | Tkinter + `theme.py` (tokenised) | FastAPI + `static/index.html` (CSS tokens) |
| Progress/events | `queue.Queue` → Tk callbacks | Same `queue.Queue` → SSE |
| Fonts | System fonts (fallback stack) | Google Fonts CDN (real Playfair/Libre/Archivo) |
| Dark mode | Two token sets (`paper`/`night`) | `prefers-color-scheme` (native) |

**Why two?** The web build started as a spike to prove the design system works with real web fonts and native dark mode. It stayed because it's genuinely useful — zero-config sharing, mobile access, no Python install for collaborators.

---

## Configuration

`configs/default.yaml` (or Settings tab in either GUI):

```yaml
# Engines
lmstudio_base_url: "http://localhost:1234/v1"
ollama_host: "http://localhost:11434"

# Models
ocr_model: "allenai/olmocr-2-7b"
cleanup_model: "gemma4:12b"
translate_model: "translategemma:4b"

# Guard thresholds
cleanup_guard: true
cleanup_guard_max_deleted_words: 2
cleanup_guard_min_length_ratio: 0.97
cleanup_guard_protect_nouns: true
structure_guard: true

# Performance
ollama_think: false        # disables reasoning tokens (13× speedup on cleanup)
chunk_max_tokens: 2048
chunk_overlap_tokens: 128
max_output_tokens: 4096

# Output
output_dir: "output"
resume: true               # skip stages with existing output
history_db: "~/.ocr_pipeline/history.db"
```

---

## Output Structure

```
output/
  raw_ocr/
    text/<stem>.txt
    json/<stem>.json
  cleaned/
    text/<stem>.txt
    json/<stem>.json          # includes guard result, rejected_cleaned_text if any
  structured/
    text/<stem>.txt
    json/<stem>.json          # includes guard result, rejected_structured_text if any
  translated/
    text/<stem>.txt
    json/<stem>.json
  structured/                 # cached structured text for PDF re-exports
  tropy_manifest.json         # when processing from Tropy
```

---

## Hardware Requirements

| Tier | GPU VRAM | System RAM | Notes |
|------|----------|------------|-------|
| **Recommended** | 16 GB (RTX 4060 Ti 16G / 4070+) | 32 GB | All models resident, comfortable headroom |
| **Minimum (GPU)** | 12 GB (RTX 3060 / 4070) | 16 GB | May need model offloading between stages |
| **CPU-only** | — | 32 GB | 5–10× slower; viable for small batches |
| **Apple Silicon** | Unified: 24 GB (M3/M4 Pro) | — | M1 Pro 16 GB works but tight |

**Default quantization:** Q4_K_M (~12–15 GB combined VRAM). Drop to Q3_K_M (−25%) or Q2_K (−45%) if needed.

**VRAM-saving levers:**
1. Run stages separately via CLI (`ocr` → `cleanup` → `structure` → `translate`) so models unload between stages
2. Lower `max_output_tokens` / Ollama `num_ctx`
3. CPU offload layers in Ollama Modelfile
4. Use lighter models (see `configs/example.yaml` for alternatives)

---

## Design System: The New Masses

Both frontends implement a cohesive editorial design system derived from the *New Masses* (1920s–30s radical magazine) filtered through Soviet Constructivism (Lissitzky) and the personal site of Dr Maurice J. Casey.

| Token Category | Light (`paper`) | Dark (`night` / Lamplight Archive) |
|----------------|-----------------|-------------------------------------|
| **Paper** | `#f6f3ea` (cream) | `#161310` (warm black-brown) |
| **Ink** | `#1b1813` (warm black) | `#e8e2d3` (warm off-white) |
| **Accent** | `#2f7d45` (Esperanto green) | `#4aa066` (lifted green) |
| **Gold** | `#bf9b30` (antique) | `#bf9b30` (unchanged) |

**Typography:** Playfair Display (display, 700/900), Libre Baskerville (body, 400/700), Archivo (UI, 500/600/700). Fluid `clamp()` scale.

**Motion:** Editorial, not decorative. Single easing `cubic-bezier(0.22, 0.61, 0.36, 1)`. Card lift (4px), rule draw-in, star settle, modal rise. Full `prefers-reduced-motion` support.

**Components:** Cards (12px radius, paper shadows), buttons (hard-offset shadow, green-on-hover), inputs (4px radius, recessed paper), chips (uppercase Archivo 600), modals (16px, green top border), nav (pinned, frosted blur).

See [Design_Philosophy.md](Design_Philosophy.md) for the full specification.

---

## Project Structure

```
src/ocr_pipeline/
├── cli.py                 # Typer CLI entry point
├── pipeline.py            # Stage orchestration (shared by CLI/GUI/Web)
├── jobs.py                # Threaded JobRunner (pause/skip/cancel, event queue)
├── history.py             # SQLite run history
├── config.py              # YAML + env + defaults
├── tropy.py               # Read-only Tropy archive reader
├── tropy_write.py         # Write results back to Tropy (notes/transcriptions)
├── pdf_export.py          # PDF compilation with structuring
├── export_ludwiglang.py   # LudwigLang Markdown export
├── _guard.py              # Cleanup/Structure content-preservation guards
├── _diff.py               # Diff/marker highlighting (shared)
├── _chunking.py           # Token-aware chunking for long texts
├── _llm.py                # Unified LM Studio / Ollama client
├── _prompts.py            # Prompt template loader
├── stages/
│   ├── ocr.py             # LM Studio vision call
│   ├── cleanup.py         # Ollama repair (guarded)
│   ├── structure.py       # Ollama paragraphing (guarded)
│   └── translate.py       # Ollama translation
├── gui/                   # Tkinter desktop app
│   ├── theme.py           # Design tokens → Tk styles
│   ├── app.py             # Main window, tab orchestration
│   ├── views/             # Main, Preview, History, Analytics, Settings, Tropy pickers
│   └── widgets/           # Queue table, image pane, compare view
└── web/                   # FastAPI + vanilla JS
    ├── server.py          # FastAPI app, static files, SSE
    ├── runtime.py         # JobRunner → SSE adapter
    ├── routers/           # run, queue, history, analytics, settings, tropy, pdf, ludwiglang
    └── static/
        ├── index.html     # SPA shell
        ├── app.js         # View router, SSE client, components
        └── style.css      # Design tokens + components (CSS custom properties)
```

---

## Testing

```bash
pytest tests/ -v
```

Tests cover: CLI commands, guard logic, Tropy read/write, PDF export, LudwigLang export, web endpoints, GUI smoke tests.

---

## License

MIT — see `LICENSE`.

---

## Acknowledgements

- **Models:** AllenAI (olmOCR), Google (Gemma), Google (TranslateGemma)
- **Engines:** LM Studio, Ollama
- **Archive platform:** [Tropy](https://tropy.org)
- **Design system:** Derived from [public_history](https://github.com/Muggwoffin/public_history) (Maurice J. Casey)
- **Fonts:** Playfair Display (Claus Eggers Sørensen), Libre Baskerville (Impallari Type), Archivo (Omnibus-Type) — all SIL OFL