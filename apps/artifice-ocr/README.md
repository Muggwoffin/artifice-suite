# ArtificeOCR

**Local-First Archival OCR, Preservation Cleanup & Translation for Historical Research**

*Part of the [Artifice Suite](../../README.md) — Local-First, Model-Agnostic Software Harnesses for Humanities Research.*

---

## 🏛️ Philosophy: The Software Harness vs. The Chatbot

ArtificeOCR is a local-first pipeline built specifically for processing, cleaning, structuring, translating, and publishing historical documents—engineered for archival research, not demos. It operates around Joseph Weizenbaum’s anti-ELIZA principle: **software should perform deterministic computing tasks, and AI models should be invoked strictly as guarded text transformation engines.**

┌────────────────────────────────────────────────────────────────────────────┐
│                          ArtificeOCR Harness                               │
│                                                                            │
│   1. Vision OCR Extraction (olmocr-2-7b via LM Studio)                     │
│   2. Guarded Text Cleanup (Gemma 4 via Ollama - Capitalisation/Umlaut Guard)│
│   3. Guarded Text Structuring (Gemma 4 via Ollama - Word-for-Word Guard)   │
│   4. Historical Translation (TranslateGemma via Ollama - German to English)│
│   5. Multi-Format Export (PDF / LudwigLang Markdown / Tropy Writeback)     │
└────────────────────────────────────────────────────────────────────────────┘

1. **Deterministic Execution, No Conversational Noise:** ArtificeOCR never "chats" about documents. It processes images or archival manifests through a strict multi-stage pipeline and outputs structured JSON, Markdown, or PDF assets.
2. **Preservation Over Prettiness (The Guard System):** Historical texts—especially fragmentary 1920s–1940s German archival records—contain fragile spellings, capitalized nouns, and OCR artifacts. The cleanup and structuring stages are strictly *guarded*. If a model attempts to alter valid words, capitalized German nouns, or delete text beyond tight thresholds, the modification is rejected and saved as `rejected_*` for review—nothing is silently lost or rewritten.
3. **Local-First & Archival Privacy:** All vision and language models run locally on your GPU via **LM Studio** and **Ollama**. Confidential archival findings and copyright-restricted manuscript photos never leave your hardware.
4. **Editorial Visual Identity:** Built using **The New Masses Design System** (`packages/shared-ui`)—a warm, paper-and-ink interface inspired by 1930s radical editorial design and Soviet Constructivism.

---

## ✨ Core Capabilities

### 1. Guarded 4-Stage Processing Pipeline
Runs entirely on local GPU hardware with complete JSON metadata outputs (prompts, confidence, guard results, timings) at every stage:
* **Stage 1 — Vision OCR:** Converts document scans and photos into raw text using `allenai/olmocr-2-7b` via LM Studio.
* **Stage 2 — Guarded Cleanup:** Repairs OCR artifacts using `gemma4:12b` via Ollama. Guarded against word deletions, umlaut transliteration corruptions (`ueber` $\rightarrow$ `über`), and loss of capitalized German nouns.
* **Stage 3 — Guarded Structuring:** Adds paragraph breaks for human readability using `gemma4:12b` via Ollama. Guarded by **word-for-word equality**—only newline insertions are allowed.
* **Stage 4 — Historical Translation:** Optional translation (e.g., German to English) using specialized models (`translategemma:4b`) via Ollama.

### 2. Deep Tropy Archive Integration
Directly connects to [Tropy](https://tropy.org) historical research archives:
* **Read-Only Browsing:** Inspect Tropy projects, lists, tags, items, and photos directly from the CLI or UI without modifying database state.
* **Manifest Processing:** Ingest items by list ID, tag, or item ID, mirroring Tropy's item/page structure on disk.
* **Safe Writeback:** Writes cleaned, structured, or translated texts back into Tropy as *notes* or native *transcriptions* with preview verification and automatic timestamped project backups.

### 3. Multi-Format Publishing Exports
* **Typeset PDF Compilation:** Generates continuous reading PDFs with section headings per item, provenance page markers (`[page1]`), and Playfair/Libre Baskerville typography.
* **LudwigLang Markdown Export:** Exports cleaned and structured text as `.md` files pre-configured with front-matter metadata for the LudwigLang editorial web publisher.
* **Structured JSON Data:** Full audit logs for every page, preserving raw OCR text, accepted cleanup, rejected model attempts, and guard status logs.

---

## 🛡️ The Guard System (Preservation Details)

| Stage | Guard Implementation | Protection Objective |
| :--- | :--- | :--- |
| **Cleanup** | `_guard.check_cleanup` | Protects German capitalized nouns, forbids umlaut transliteration (`ueber` $\rightarrow$ `über`), enforces word deletion thresholds (default $\le$ 2 words), and maintains length ratios ($\ge$ 97% letters retained). |
| **Structure** | `_guard.check_structure_only` | Enforces **word-for-word equality**—only newlines may be added. Any word alteration triggers a rejection, retaining raw text and saving the attempt as `rejected_structured_text`. |

---

## 🎨 Design System (`packages/shared-ui`)

All visual interfaces in ArtificeOCR adhere to **The New Masses Design System**:
* **Palette:** Warm cream paper (`#f6f3ea`), deep warm black ink (`#1b1813`), Esperanto green accents (`#2f7d45`), and antique gold highlights (`#bf9b30`).
* **Typography:** Playfair Display (Display/Headings), Libre Baskerville (Body/Manuscripts), and Archivo (UI Labels/Buttons).
* **Surface Depth & Motion:** Paper-like diffused shadows (`shadow-paper`), card lifts (4px), rule draw-in animations, and tactile button presses.

---

## 📂 Monorepo Architecture

ArtificeOCR is located at `apps/artifice-ocr` within the Artifice Suite monorepo and shares core dependencies with partner applications:

```
artifice-suite/
├── apps/
│   └── artifice-ocr/
│       ├── src/
│       │   ├── cli.py                 # Typer CLI entry point
│       │   ├── pipeline.py            # Stage orchestration (shared by CLI/GUI/Web)
│       │   ├── jobs.py                # Threaded JobRunner with pause/cancel
│       │   ├── history.py             # SQLite run history
│       │   ├── tropy.py               # Read-only Tropy archive parser
│       │   ├── tropy_write.py         # Tropy notes/transcriptions writeback
│       │   ├── pdf_export.py          # PDF compilation with structuring
│       │   ├── export_ludwiglang.py   # LudwigLang Markdown export
│       │   ├── _guard.py              # Content preservation guards
│       │   ├── _diff.py               # Diff & marker highlighting
│       │   ├── stages/                # OCR, Cleanup, Structure, Translate modules
│       │   └── web/                   # FastAPI server & vanilla JS SPA
│       ├── tests/                     # Pytest suite
│       └── README.md
└── packages/
    ├── shared-ui/                     # The New Masses CSS tokens & web components
    ├── model-harness/                 # BYOM connectors (Ollama/LM Studio)
    └── core-types/                    # Shared TypeScript & Python data interfaces
```

---

## 🚀 Setup & Hardware Requirements

### Prerequisites & Dependencies
Ensure **Python 3.11+** is installed. From the monorepo root:

```bash
# Install shared packages and app in editable mode
pip install -e packages/core-types -e packages/model-harness -e packages/shared-ui -e apps/artifice-ocr[web]
```

### Engine Setup & Model Provisioning
- **LM Studio**: Launch LM Studio locally on port `1234` and load `allenai/olmocr-2-7b`.
- **Ollama**: Launch Ollama locally on port `11434` and pull required models:
  ```bash
  ollama pull gemma4:12b
  ollama pull translategemma:4b
  ```

### Cross-Platform & macOS Apple Silicon Notes
- **Linux / Windows (CUDA)**: Native GPU acceleration via CUDA drivers.
- **macOS (Apple Silicon Metal)**: Run **LM Studio** and **Ollama** natively on the host to leverage Apple Metal Performance Shaders (MPS) and Unified Memory. If running containers via Docker, connect to host models using `http://host.docker.internal:1234/v1` and `http://host.docker.internal:11434`.

### Hardware Recommendations
| Tier | GPU VRAM | System RAM | Notes |
| :--- | :--- | :--- | :--- |
| **Recommended** | 16 GB (RTX 4060 Ti 16G / 4070+) | 32 GB | All models resident simultaneously. |
| **Minimum (GPU)** | 12 GB (RTX 3060 / 4070) | 16 GB | Requires sequential model offloading between stages. |
| **Apple Silicon** | 24 GB Unified (M3/M4 Pro) | — | Unified memory handles vision and LLM weights comfortably. |

---

## 🖥️ Usage & Interfaces

### 1. CLI Commands
```bash
# Process single image through full pipeline:
artifice-ocr pipeline path/to/document.png --skip-translate

# Execute individual processing stages:
artifice-ocr ocr path/to/image.png
artifice-ocr cleanup output/raw_ocr/text/file.txt
artifice-ocr structure output/structured/text/file.txt
artifice-ocr translate output/structured/text/file.txt

# Tropy Archive Workflows:
artifice-ocr tropy-browse "path/To/Archive.tropy"
artifice-ocr tropy "path/To/Archive.tropy" --list-id 3 --tag resistance

# Export Compilation:
artifice-ocr compile-pdf output/cleaned/text/Collection --stage cleaned
artifice-ocr export-md output/cleaned/text/Collection --author "Fritz Eberhard" --date "1936-1939"
```

### 2. Web UI (Recommended)
Launches the FastAPI server with The New Masses editorial layout, real Google Fonts, and Server-Sent Events (SSE) live progress tracking:
```bash
python -m artifice_ocr.web
# → Access at http://127.0.0.1:8765
```

---

## ⚙️ Configuration
Set defaults via `configs/default.yaml` or environment variables:

| Variable / Key | Default | Description |
| :--- | :--- | :--- |
| `lmstudio_base_url` | `http://localhost:1234/v1` | LM Studio vision OCR endpoint |
| `ollama_host` | `http://localhost:11434` | Ollama LLM endpoint |
| `ocr_model` | `allenai/olmocr-2-7b` | Vision model used for OCR stage |
| `cleanup_model` | `gemma4:12b` | Model used for guarded cleanup |
| `translate_model` | `translategemma:4b` | Model used for translation |
| `cleanup_guard` | `true` | Enable German noun / umlaut protection guard |
| `structure_guard` | `true` | Enable word-for-word equality guard |
| `ollama_think` | `false` | Disable reasoning tokens (13× speedup during cleanup) |

---

## 🛠️ Open-Source Extension Points

We welcome contributions from historians, archivists, and software engineers!

1. **Custom Stage Guards (`apps/artifice-ocr/src/_guard.py`)**: Implement specialized content-preservation rules for specific languages or historical writing styles (e.g., Fraktur font artifacts, early modern orthography).
2. **Archival Exporters (`apps/artifice-ocr/src/`)**: Add writeback connectors for other archival software (e.g., Omeka, Arches, or custom IIIF manifests).
3. **Vision OCR Connectors (`apps/artifice-ocr/src/stages/ocr.py`)**: Extend vision stage adapters to support additional local vision-language models.

---

## 🧪 Testing

Run the full pytest suite covering CLI commands, guard validation logic, Tropy read/write, and export compilers:
```bash
pytest apps/artifice-ocr/tests/
```
