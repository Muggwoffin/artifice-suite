# ArtificeDraft

**Precision Copy-Editing & Journal Style Compliance for Academic Historians & Scholars**

ArtificeDraft is an advanced desktop and web application designed specifically for academic historians, researchers, and rigorous writers. It reads a `.docx` manuscript, analyzes each paragraph against scholarly editing standards and specific journal style guides, and returns a new Word document with copy-edit changes applied as **native Word Track Changes** (`<w:ins>` / `<w:del>`), alongside automated historian advisories for citations, archival references, foreign phrases, and document consistency.

---

## 🏛️ Philosophy

1. **Scholarly Rigor & Authorship Control**: AI should serve as an editorial assistant, not a ghostwriter. ArtificeDraft preserves original voice, tone, footnotes, citations, bold/italic formatting, and document structure.
2. **Native Track Changes**: Edits are rendered as native Microsoft Word revisions (red insertions and blue deletions) rather than opaque, destructive text replacements. You retain absolute veto power over every suggestion.
3. **Flexible Architecture**: Run entirely offline and locally using open-weights models via **Ollama** (e.g., Gemma 4), or leverage cloud power via **OpenAI** and **Anthropic**.
4. **Domain-Specific Awareness**: Beyond basic grammar and typos, ArtificeDraft understands the nuances of historical writing—validating footnote sequences, archival citations, Latin phrasing, and naming consistency.

---

## ✨ Key Features

### 1. Multi-Model LLM Pipeline
- **Providers**: Ollama (local), OpenAI, Anthropic.
- **Smart Chunking**: Paragraphs are parsed, batched, and reviewed contextually while preserving structural integrity.
- **Editing Styles**: Academic, Creative, Concise, Business, Journal Style, or Custom Prompts.

### 2. Journal Style Guide System
Ships with built-in rulesets for major academic standards:
- **Chicago Manual of Style** (17th ed.) — Notes-Bibliography system, Title Case headings, serial comma, date/abbreviation preferences.
- **MLA** (9th ed.) — Parenthetical citations, Works Cited formatting, sentence-case titles.
- **APA** (7th ed.) — Author-date citations, Reference List, DOIs.
- **Custom Guides**: Create or import custom journal JSON guides into `~/.artifice_draft/style_guides/`.

### 3. Specialized Historian Tools & Advisories
ArtificeDraft scans your manuscript for common scholarly pitfalls:
- **Citation Checker**: Detects footnote numbering gaps, orphaned footnote markers or bodies, duplicate markers, and deprecation warnings for Latin abbreviations (`ibid.`, `op. cit.`, `loc. cit.`).
- **Date Standardizer**: Identifies ambiguous M/D/Y dates and normalizes date formatting to match journal preferences.
- **Foreign Phrase Inspector**: Checks italicization and consistency of Latin and foreign terms (`et al.` vs `and others`, `sic`, etc.).
- **Archival Reference Validator**: Validates archival citations for missing repositories, box/folder numbers, and date ranges.
- **Consistency Checker**: Flags inconsistent capitalization of proper nouns and variant spellings of personal names across the document.

### 4. Interactive Review & Change Summaries
- **Web App Review Mode**: Approve, reject, or type custom replacements for every suggested change card-by-card before saving.
- **Changelog & Statistics**: Generates detailed change summaries tracking edit rates, word count deltas, estimated page counts, and categorized change breakdowns (grammar, spelling, clarity, style).

---

## 🖥️ Flexible Interfaces

### Desktop GUI (Tkinter)
Clean desktop application featuring drag-and-drop support, background thread processing, and native Windows desktop shortcuts (`ArtificeDraft.lnk`).
```bash
python scripts/run_edit.py --gui
```

### Web Application (FastAPI + Vanilla JS)
Modern browser/native window UI featuring interactive side-by-side review cards, live diff highlighting, and settings persistence.
```bash
pip install -r requirements.txt -r requirements-web.txt
python -c "from src.web.server import main; main()" --browser
```

### CLI / Headless Mode
Batch process manuscripts directly from the command line:
```bash
python scripts/run_edit.py --headless input.docx [output.docx]
```

---

## 🚀 Setup & Installation

Requires **Python 3.10+**.

```bash
git clone https://github.com/your-username/ArtificeDraft.git
cd ArtificeDraft
pip install -r requirements.txt
```

### Ollama Setup (Default Local LLM)
Make sure Ollama is running locally with the default model (`gemma4:12b`):
```bash
ollama pull gemma4:12b
ollama serve
```

---

## ⚙️ Configuration

Configure via environment variables:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_MODEL` | `gemma4:12b` | Model name used by Ollama |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |
| `LLM_PROVIDER` | `ollama` | LLM provider: `ollama`, `openai`, `anthropic` |
| `OPENAI_API_KEY` | — | API key for OpenAI |
| `ANTHROPIC_API_KEY` | — | API key for Anthropic |

---

## 📂 Project Structure

```
├── src/
│   ├── models.py           # Shared data structures and enums
│   ├── config.py           # Configuration and environment loaders
│   ├── doc_parser.py       # .docx paragraph extraction and metadata
│   ├── llm_client.py       # Batch LLM interaction and JSON parsing
│   ├── doc_writer.py       # Track changes document generation
│   ├── _track_changes.py   # Low-level XML revision element injection
│   ├── write_utils.py      # Plain .docx writing utilities
│   ├── _diff.py            # Word-level diff calculation for web review
│   ├── prompts.py          # Editing style presets and journal system prompts
│   ├── changelog.py        # Statistical change summary generation
│   ├── gui.py              # Tkinter desktop interface
│   ├── citation_checker.py # Footnote & citation validation
│   ├── date_standardizer.py# Date format normalization
│   ├── foreign_phrases.py  # Latin/foreign phrase italicization & consistency
│   ├── archival_refs.py    # Archival reference validation
│   ├── consistency.py      # Cross-document proper noun consistency
│   ├── style_guides/       # Chicago, MLA, APA rules and registry
│   └── web/                # FastAPI server, runtime adapter, and static assets
├── tests/                  # Comprehensive pytest test suite
├── scripts/                # Entry points and shortcut generators
└── requirements.txt
```

---

## 🧪 Running Tests

```bash
python -m pytest tests/
```
