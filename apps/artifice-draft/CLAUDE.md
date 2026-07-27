# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: ArtificeDraft

A Python tool for academic historians that reads a `.docx` file, sends each paragraph to an LLM (Ollama, OpenAI, or Anthropic), and returns a new Word document with copy-edit changes applied as tracked edits (grammar fixes, typos, unclear phrasing, journal style conformance).

Requires Python 3.10+.

## Entry Point

Run the installed `artifice-draft` command (`src/artifice_draft/cli.py`):

- **GUI mode**: `artifice-draft --gui`
- **Headless/CLI mode**: `artifice-draft --headless input.docx [output.docx]`

Environment variables: `OLLAMA_MODEL`, `OLLAMA_URL`, `LLM_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. Default model is `gemma4:12b`.

## Architecture

The pipeline has three stages. Each stage is a separate module in `src/artifice_draft/`:

1. **Parse** (`src/artifice_draft/doc_parser.py`) — reads a `.docx` with `python-docx`, extracts paragraphs as dicts (typed as `ParagraphData` in `src/artifice_draft/models.py`) containing text, style name, bold/italic flags, and indent level. Empty paragraphs are skipped.

2. **LLM call** (`src/artifice_draft/llm_client.py`) — batches the paragraph dicts into chunks of N (default 5), sends each chunk to the LLM with a system prompt + user prompt, parses JSON responses, and returns `LLMEdit` dataclasses per paragraph. `LLMEdit.to_edits_dict()` converts results to the edits mapping. Handles invalid JSON by marking all paragraphs as unchanged; handles single-object responses by wrapping in a list.

3. **Write** (`src/artifice_draft/doc_writer.py`) — takes the original paragraphs plus an `edits` mapping (index → edited text or None) and writes either a plain `.docx` (no changes) or one with track changes applied via `src/artifice_draft/_track_changes.py`. The `_track_changes.py` module uses `docx_revisions.RevisionDocument.find_and_replace_tracked()` to produce `<w:ins>/<w:del>` revision elements. Plain docx writing is shared via `src/artifice_draft/write_utils.py`.

The GUI (`src/artifice_draft/gui.py`) is a Tkinter window with a file picker button and optional drag-and-drop (if `tkinterdnd2` is installed); processing runs in a background thread.

Configuration (`src/artifice_draft/config.py`) uses a dataclass with a `from_env()` classmethod. The `ollama_generate_url` property appends `/api/generate` to the base URL.

### Style Guide System

`src/artifice_draft/style_guides/` contains the journal style guide system:

- `base.py` — `StyleGuide` dataclass schema
- `chicago.py`, `mla.py`, `apa.py` — built-in guides for Chicago 17th, MLA 9th, APA 7th
- `__init__.py` — `list_guides()`, `load_guide(name)`, `load_guide_by_path(path)`

Custom guides are stored as JSON in `~/.artifice_draft/style_guides/`.

### Historian Features

- `citation_checker.py` — footnote/citation validation against journal rules
- `date_standardizer.py` — date format normalization per journal preference
- `foreign_phrases.py` — Latin/foreign phrase italicization and consistency
- `archival_refs.py` — archival citation format validation
- `consistency.py` — cross-document proper noun and naming consistency

## Running tests

```bash
python -m pytest tests/
```
