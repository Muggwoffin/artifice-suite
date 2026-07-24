# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Copy Editor — Gemma 4:12b

A Python tool that reads a `.docx` file, sends each paragraph to Ollama running **Gemma 4:12b**, and returns a new Word document with copy-edit changes applied as tracked edits (grammar fixes, typos, unclear phrasing).

Requires Python 3.10+.

## Entry Point

Run `scripts/run_edit.py`:

- **GUI mode**: `python scripts/run_edit.py --gui`
- **Headless/CLI mode**: `python scripts/run_edit.py --headless input.docx [output.docx]`

Environment variables: `OLLAMA_MODEL`, `OLLAMA_URL`. Default model is `gemma4:12b`.

## Architecture

The pipeline has three stages. Each stage is a separate module in `src/`:

1. **Parse** (`src/doc_parser.py`) — reads a `.docx` with `python-docx`, extracts paragraphs as dicts (typed as `ParagraphData` in `src/models.py`) containing text, style name, bold/italic flags, and indent level. Empty paragraphs are skipped.

2. **LLM call** (`src/llm_client.py`) — batches the paragraph dicts into chunks of N (default 5), sends each chunk to Ollama's `/api/generate` endpoint with a system prompt + user prompt, parses JSON responses, and returns `LLMEdit` dataclasses per paragraph. `LLMEdit.to_edits_dict()` converts results to the edits mapping. Handles invalid JSON by marking all paragraphs as unchanged; handles single-object responses by wrapping in a list.

3. **Write** (`src/doc_writer.py`) — takes the original paragraphs plus an `edits` mapping (index → edited text or None) and writes either a plain `.docx` (no changes) or one with track changes applied via `src/_track_changes.py`. The `_track_changes.py` module uses `docx_revisions.RevisionDocument.find_and_replace_tracked()` to produce `<w:ins>/<w:del>` revision elements. Plain docx writing is shared via `src/write_utils.py`.

The GUI (`src/gui.py`) is a Tkinter window with a file picker button and optional drag-and-drop (if `tkinterdnd2` is installed); processing runs in a background thread.

Configuration (`src/config.py`) uses a dataclass with a `from_env()` classmethod. The `ollama_generate_url` property appends `/api/generate` to the base URL.

## Running tests

```bash
python -m pytest tests/
```
