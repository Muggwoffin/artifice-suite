# PersonaeEdit

A Python tool for academic historians that reads a `.docx` file, sends each paragraph to an LLM (Ollama, OpenAI, or Anthropic), and returns a new Word document with copy-edit changes applied as tracked edits (grammar fixes, typos, unclear phrasing, journal style conformance).

## How it works

```
input.docx ──→ GUI / CLI ──→ parse paragraphs ──→ LLM ──→ new_edited.docx
```

- **Drag-and-drop** a `.docx` onto the tkinter window, or run in headless mode with `--headless input.docx [output.docx]`.
- The model is asked to fix grammar, spelling, and unclear phrasing — it returns JSON per paragraph.
- A new `.docx` is written back using `docx-revisions`, so Word shows the changes as tracked insertions/deletions (red/blue marks).
- Select a journal style guide (Chicago, MLA, APA, or custom) to have edits conform to that journal's conventions.

## Requirements

- Python 3.10+
- Ollama running locally with Gemma 4:12b (`ollama pull gemma4:12b`), or an OpenAI/Anthropic API key

## Setup

```bash
pip install -r requirements.txt
```

## Usage

### GUI mode

```bash
python scripts/run_edit.py --gui
```

Drop a `.docx` file onto the window. The result is saved as `<input>_edited.docx`.

#### Desktop shortcut (Windows)

`PersonaeEdit.lnk` in the project root launches the GUI with no console window
— drag it onto your Desktop. To recreate it (after moving the project or
reinstalling Python):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1
powershell -ExecutionPolicy Bypass -File scripts\make_shortcut.ps1 -Desktop   # also place a copy on the Desktop
```

The shortcut runs [`launch_personae.pyw`](launch_personae.pyw), which is
equivalent to `python scripts/run_edit.py --gui`. It sets the working
directory, checks the dependencies, and prefers an interpreter that also has
`tkinterdnd2` so drag-and-drop works — falling back to one without it (file
picker only) rather than refusing to start. Startup failures appear in a
dialog and are logged to `~/.personaeedit/launcher.log` instead of disappearing
silently, which is otherwise what a windowed Python app does.

Regenerate the icon with `py -3.12 scripts/make_icon.py`.

### Web app

A second frontend — FastAPI + vanilla JS, no build step — lives in `src/web/`
and shares the same pipeline (`doc_parser`, `llm_client`, `doc_writer`,
`review`, `changelog`) the tkinter build uses.

```bash
pip install -r requirements.txt -r requirements-web.txt
python -c "from src.web.server import main; main()"          # native window
python -c "from src.web.server import main; main()" --browser  # or a browser tab
```

Drop a `.docx` in, adjust settings, select a journal style guide, click **Start Editing**. If "Review
edits before saving" is on, every suggested change appears on its own card —
approve, reject, or type a replacement — before anything is written to disk.
Settings persist to `~/.personaeedit/web_settings.json` — provider/style/format/batch/temperature/
author/prompt/review-toggle only; API keys stay in environment variables and
are never read from or written to a browser form.

#### Desktop shortcut (Windows)

`PersonaeEdit (Web).lnk` in the project root launches the web build the same
way `PersonaeEdit.lnk` launches the desktop GUI:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_shortcut_web.ps1
powershell -ExecutionPolicy Bypass -File scripts\make_shortcut_web.ps1 -Desktop
```

Runs [`launch_personae_web.pyw`](launch_personae_web.pyw) — same self-healing
interpreter search as the desktop launcher, preferring one with `pywebview`
for a native window and falling back to your default browser without it.
Regenerate the icon with `py -3.12 scripts/make_web_icon.py`.

### CLI / headless mode

```bash
python scripts/run_edit.py --headless input.docx [output.docx]
```

### Default (no arguments)

```bash
python scripts/run_edit.py
```

Launches the GUI.

## Journal Style Guides

PersonaeEdit ships with built-in style guides for the three major academic citation systems:

- **Chicago Manual of Style** (17th ed.) — Notes-Bibliography system, Title Case headings, serial comma
- **MLA** (9th ed.) — Parenthetical citations, Works Cited, sentence-case titles
- **APA** (7th ed.) — Author-date citations, Reference List, DOIs

Custom guides can be created in-app or imported as JSON files from `~/.personaeedit/style_guides/`.

## Configuration

Set these environment variables to override defaults:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `gemma4:12b` | Model name used by Ollama |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `LLM_PROVIDER` | `ollama` | LLM provider: ollama, openai, anthropic |
| `OPENAI_API_KEY` | | API key for OpenAI |
| `ANTHROPIC_API_KEY` | | API key for Anthropic |

## Project structure

```
├── src/
│   ├── __init__.py
│   ├── models.py           # Shared type definitions (ParagraphData)
│   ├── config.py           # Settings (model, batch size, etc.)
│   ├── doc_parser.py       # Read .docx → paragraphs + metadata
│   ├── llm_client.py       # Batch LLM calls
│   ├── doc_writer.py       # Apply edits as track changes
│   ├── _track_changes.py   # Low-level tracked-changes implementation
│   ├── write_utils.py      # Shared plain .docx writing utilities
│   ├── _diff.py            # Word-level diff ranges (web review highlighting)
│   ├── prompts.py          # Editing style presets and system prompt generation
│   ├── changelog.py        # Change summary generation
│   ├── gui.py              # Tkinter GUI with drag-and-drop
│   ├── citation_checker.py # Footnote/citation validation
│   ├── date_standardizer.py# Date format normalization
│   ├── foreign_phrases.py  # Latin/foreign phrase handling
│   ├── archival_refs.py    # Archival reference formatting
│   ├── consistency.py      # Cross-document consistency checks
│   ├── style_guides/       # Journal style guide system
│   │   ├── __init__.py     # Guide registry and loaders
│   │   ├── base.py         # StyleGuide dataclass schema
│   │   ├── chicago.py      # Chicago Manual of Style 17th ed.
│   │   ├── mla.py          # MLA 9th ed.
│   │   └── apa.py          # APA 7th ed.
│   └── web/                # FastAPI + vanilla JS frontend
│       ├── server.py       # HTTP/SSE routes, native-window bootstrap
│       ├── runtime.py      # Adapter over the pipeline (upload/run/review)
│       └── static/         # index.html, css/app.css, js/*.js
├── tests/
│   ├── conftest.py         # Shared test fixtures
│   ├── test_doc_parser.py
│   ├── test_doc_writer.py
│   ├── test_llm_client.py
│   ├── test_revision_xml.py
│   ├── test_diff.py
│   ├── test_prompts.py
│   ├── test_changelog.py
│   ├── test_review.py
│   ├── test_exporters.py
│   ├── test_style_guides.py
│   ├── test_citation_checker.py
│   ├── test_date_standardizer.py
│   ├── test_foreign_phrases.py
│   ├── test_archival_refs.py
│   ├── test_consistency.py
│   └── test_web.py
├── scripts/
│   ├── run_edit.py         # Entry point (GUI or CLI)
│   ├── make_icon.py / make_shortcut.ps1         # Desktop shortcut
│   └── make_web_icon.py / make_shortcut_web.ps1 # Web shortcut
├── requirements.txt
├── requirements-web.txt
├── launch_personae.pyw
├── launch_personae_web.pyw
└── README.md
```

## Running tests

```bash
python -m pytest tests/
```
