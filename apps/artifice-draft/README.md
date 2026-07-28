# ArtificeDraft

**Precision Copy-Editing & Journal Style Compliance for Academic Historians**

*Part of the [Artifice Suite](../../README.md) — Local-First, Model-Agnostic Software Harnesses for Humanities Research.*

---

## 🏛️ Philosophy: The Software Harness vs. The Chatbot

ArtificeDraft is an editorial software harness built for academic manuscripts (`.docx`). It is engineered around Joseph Weizenbaum’s anti-ELIZA principle: **software should handle deterministic computing tasks, and AI models should be invoked strictly as structured text transformation engines.**

┌────────────────────────────────────────────────────────────────────────┐
│                        ArtificeDraft Harness                           │
│                                                                        │
│   1. Extracts OpenXML paragraph trees & footnote registers             │
│   2. Validates archival citations, footnote gaps, & foreign phrases    │
│   3. Formats structured prompts via packages/model-harness             │
│   4. Re-injects model diffs as native Word Track Changes (<w:ins>/<w:del>)│
└────────────────────────────────────────────────────────────────────────┘

1. **No Ghostwriting or Chat Loops:** ArtificeDraft never "chats" with you about your writing or rewrites whole passages unprompted. It ingests a `.docx` manuscript, applies a target journal style guide, and outputs explicit, granular revisions.
2. **Authorship & Veto Power:** The author retains absolute control over the text. Revisions are injected directly into Microsoft Word's OpenXML structure as native track changes (`<w:ins>` insertions and `<w:del>` deletions) rather than destructive text overwrites.
3. **Local-First & Private:** Unpublished historical research and archival findings never leave your machine to train cloud models. Run entirely offline using local open-weights models via **Ollama** or **LM Studio**, or optionally route through cloud providers using your own API keys.
4. **Editorial Visual Identity:** Built using **The New Masses Design System** (`packages/shared-ui`)—a warm, paper-and-ink interface inspired by 1930s radical editorial design and Soviet Constructivism.

---

## ✨ Key Capabilities

### 1. Multi-Model Pipeline & Journal Style Guides
Processes paragraphs in contextual batches while preserving formatting, bold/italic styles, and footnote anchors.
- **Supported Providers**: Ollama (local default), OpenAI, Anthropic via `packages/model-harness`.
- **Chicago Manual of Style (17th ed.)** — Notes-Bibliography system, Title Case headings, serial comma, date and abbreviation standards.
- **MLA (9th ed.)** — Parenthetical citations, Works Cited formatting, sentence-case titles.
- **APA (7th ed.)** — Author-date citations, Reference List formatting, DOI validation.
- **Custom Style Guides**: Create or import custom JSON rulesets into `packages/model-harness/style_guides/`.

### 2. Specialized Historian Advisories
Beyond basic grammar and typos, ArtificeDraft executes deterministic Python checks against domain-specific historical research conventions:
- **Citation & Footnote Checker**: Detects footnote numbering gaps, orphaned markers/bodies, duplicate markers, and deprecation warnings for Latin abbreviations (`ibid.`, `op. cit.`, `loc. cit.`).
- **Archival Reference Validator**: Inspects archival citations for missing repository names, collection titles, box/folder numbers, and date ranges.
- **Date Standardizer**: Identifies ambiguous M/D/Y formats and normalizes date strings to match journal preferences.
- **Foreign Phrase Inspector**: Checks italicization and consistency of Latin and foreign terms (`et al.` vs `and others`, `sic`, `in situ`).
- **Proper Noun Consistency**: Scans cross-document spelling variants of historical figures, placenames, and archival repositories.

### 3. Native Track Changes & Review Engine
- **Direct OpenXML Injection**: Revisions are written directly to Word XML as native revision elements (`<w:ins>` red insertions and `<w:del>` blue deletions).
- **Interactive Review Mode (Web UI)**: Side-by-side card review powered by `packages/shared-ui`. Approve, reject, or edit individual changes before generating the final file.
- **Statistical Changelogs**: Generates change summaries tracking edit rates, word count deltas, estimated page counts, and categorized breakdowns (grammar, spelling, clarity, style).

---

## 🎨 Design System (`packages/shared-ui`)

All visual elements in ArtificeDraft adhere to **The New Masses Design System**:
- **Palette**: Warm cream paper (`#f6f3ea`), deep warm black ink (`#1b1813`), Esperanto green accents (`#2f7d45`), and antique gold highlights (`#bf9b30`). Zero pure blacks or cold grays.
- **Typography**: Playfair Display (Display/Headings), Libre Baskerville (Body text), and Archivo (UI Labels/Buttons).
- **Surface Depth**: Paper-like diffused shadows (`shadow-paper`) and hard-offset tactile button interactions.

---

## 📂 Monorepo Architecture

ArtificeDraft is located at `apps/artifice-draft` within the Artifice Suite monorepo and shares core dependencies with partner applications:

```
artifice-suite/
├── apps/
│   └── artifice-draft/
│       ├── pyproject.toml
│       ├── src/
│       │   └── artifice_draft/
│       │       ├── models.py           # Shared data structures and enums
│       │       ├── doc_parser.py       # .docx paragraph extraction and OpenXML parsing
│       │       ├── doc_writer.py       # OpenXML track changes injector (<w:ins>/<w:del>)
│       │       ├── _track_changes.py   # Low-level XML revision element injection
│       │       ├── _diff.py            # Word-level diff calculation for web review
│       │       ├── citation_checker.py # Footnote & citation validation
│       │       ├── date_standardizer.py# Date format normalization
│       │       ├── foreign_phrases.py  # Latin/foreign phrase italicization & consistency
│       │       ├── archival_refs.py    # Archival reference validation
│       │       ├── consistency.py      # Cross-document proper noun consistency
│       │       ├── changelog.py        # Statistical change summary generation
│       │       ├── cli.py              # `artifice-draft` entry point (GUI / headless)
│       │       └── web/                # FastAPI server, runtime adapter, & static assets
│       ├── tests/                  # Pytest suite
│       └── README.md
└── packages/
    ├── shared-ui/                  # The New Masses CSS design tokens
    └── model-harness/              # Shared BYOM connector config (Ollama/LM Studio/OpenAI)
```

---

## 🚀 Setup & Installation

Ensure **Python 3.11+** is installed. From the monorepo root:

```bash
# Install shared packages and app in editable mode
pip install -e packages/core-types -e packages/model-harness -e packages/shared-ui -e apps/artifice-draft
```

### Configure Local LLM (Default)
Make sure Ollama is running locally with your target model (e.g., `gemma4:12b` or `deepseek-coder`):
```bash
ollama pull gemma4:12b
ollama serve
```

### macOS & Apple Silicon Notes
- Run Ollama natively on macOS to utilize Apple Silicon Metal GPU acceleration.
- When running in Docker containers, configure environment variables to reach host Ollama via `http://host.docker.internal:11434`.

---

## 🖥️ Usage & Interfaces

### 1. Web Application (Recommended)
Launches the FastAPI backend with The New Masses interactive review cards:
```bash
python -m artifice_draft.web --browser
```

### 2. CLI / Headless Mode
Batch process manuscripts directly from the command line:
```bash
python -m artifice_draft.cli \
  --input manuscript.docx \
  --output manuscript_edited.docx \
  --style chicago-17 \
  --provider ollama \
  --model gemma4:12b
```

---

## ⚙️ Configuration

Configure via environment variables or a local `.env` file:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | LLM provider: `ollama`, `openai`, `anthropic` |
| `OLLAMA_MODEL` | `gemma4:12b` | Model name used by local Ollama server |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `OPENAI_API_KEY` | — | API key when using OpenAI provider |
| `ANTHROPIC_API_KEY` | — | API key when using Anthropic provider |

---

## 🛠️ Open-Source Extension Points

We welcome contributions from historians, editors, and software developers!

1. **Custom Style Guides (`packages/model-harness/style_guides/`)**: Add a new `.json` file defining rules for heading cases, citation preferences, date standards, and serial commas for specific academic journals.
2. **Domain Advisories (`apps/artifice-draft/src/artifice_draft/`)**: Implement new deterministic Python validators for historical sub-fields (e.g., medieval date converters, diplomatic transcription checkers).
3. **OpenXML Writers (`apps/artifice-draft/src/artifice_draft/doc_writer.py`)**: Enhance Word XML parsing for complex multi-column tables, figure captions, or margin comment threads.

---

## 🧪 Testing

Run the full pytest suite covering document parsing, OpenXML track changes injection, and historian advisories:
```bash
pytest apps/artifice-draft/tests/
```
