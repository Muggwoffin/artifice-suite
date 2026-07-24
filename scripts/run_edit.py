"""Main entry point — launch GUI or run CLI mode."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def _ensure_project_root_in_path():
    """Add the project root to sys.path so ``from src.X import Y`` works."""
    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


_ensure_project_root_in_path()


def _cli_progress(progress):
    """Print progress updates to the console."""
    bar_len = 40
    filled = int(bar_len * progress.percentage / 100)
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stderr.write(f"\r  [{bar}] {progress.percentage:5.1f}%  {progress.message}")
    sys.stderr.flush()
    if progress.percentage >= 100:
        sys.stderr.write("\n")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Usage: python scripts/run_edit.py [options]")
        print()
        print("Options:")
        print("  --gui                  Launch the drag-and-drop GUI")
        print("  --headless FILE [OUT]  Edit FILE, save to OUT (or _edited.docx)")
        print("  --styles               List available editing styles")
        print("  --help                 Show this help message and exit")
        print()
        print("Environment variables:")
        print("  LLM_PROVIDER           ollama | openai | anthropic")
        print("  OLLAMA_MODEL           Ollama model name (default: gemma4:12b)")
        print("  OLLAMA_URL             Ollama base URL")
        print("  OPENAI_API_KEY         API key for OpenAI")
        print("  OPENAI_MODEL           OpenAI model name (default: gpt-4o)")
        print("  OPENAI_BASE_URL        OpenAI-compatible base URL")
        print("  ANTHROPIC_API_KEY      API key for Anthropic")
        print("  ANTHROPIC_MODEL        Anthropic model name")
        print("  EDITING_STYLE          academic | creative | concise | business | custom")
        print("  CUSTOM_SYSTEM_PROMPT   Custom system prompt (when style=custom)")
        print("  EXPORT_FORMAT          docx_track_changes | docx_plain | markdown | html | plain_text")
        print("  BATCH_SIZE             Paragraphs per LLM call (default: 5)")
        print("  TEMPERATURE            LLM temperature (default: 0.3)")
        print("  ENABLE_REVIEW          Enable human-in-the-loop review (true/false)")
        print("  AUTHOR_NAME            Author name for tracked changes")
        print("  LOG_LEVEL              Logging level (default: INFO)")
        print("  LOG_FILE               Path to log file for rotation")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--styles":
        from src.prompts import list_styles
        print("Available editing styles:")
        for s in list_styles():
            print(f"  - {s}")
        return

    from src.config import AppConfig

    cfg = AppConfig.from_env()

    from src.log_setup import setup_logging
    setup_logging(level=cfg.log_level, log_file=cfg.log_file)

    if len(sys.argv) > 1 and sys.argv[1] == "--gui":
        from src.gui import EditGUI

        app = EditGUI()
        app.root.mainloop()
    elif len(sys.argv) > 1 and sys.argv[1] == "--headless":
        from src.changelog import format_change_log, generate_change_summary
        from src.doc_parser import parse_docx
        from src.doc_writer import apply_edits
        from src.llm_client import LLMEdit, call_ollama
        from src.review import apply_decisions, cli_review, create_review_items

        if len(sys.argv) < 3:
            print("Usage: python scripts/run_edit.py --headless input.docx [output.docx]")
            sys.exit(1)

        inp = sys.argv[2]
        out = sys.argv[3] if len(sys.argv) > 3 else None

        print(f"Parsing '{inp}'...")
        paragraphs = parse_docx(inp)
        print(f"Found {len(paragraphs)} paragraphs.")

        print(f"Sending to {cfg.active_model} ({cfg.llm_provider.value}) "
              f"with style '{cfg.editing_style.value}'...")
        edits_list = call_ollama(
            paragraphs=paragraphs,
            batch_size=cfg.batch_size,
            config=cfg,
            on_progress=_cli_progress,
        )

        if cfg.enable_review:
            items = create_review_items(edits_list, paragraphs)
            decisions = cli_review(items)
            edits_dict = apply_decisions(edits_list, decisions)
        else:
            edits_dict = LLMEdit.to_edits_dict(edits_list)

        summary = generate_change_summary(edits_list, paragraphs)
        print(format_change_log(summary))

        from src.models import ExportFormat

        fmt = cfg.export_format
        if out:
            output_path = out
        else:
            base, _ext = Path(inp).stem, Path(inp).suffix
            ext_map = {
                ExportFormat.DOCX_TRACK_CHANGES: "_edited.docx",
                ExportFormat.DOCX_PLAIN: "_edited.docx",
                ExportFormat.MARKDOWN: "_edited.md",
                ExportFormat.HTML: "_edited.html",
                ExportFormat.PLAIN_TEXT: "_edited.txt",
            }
            output_path = str(Path(inp).parent / (Path(inp).stem + ext_map.get(fmt, "_edited.docx")))

        actual = apply_edits(
            input_path=inp,
            paragraphs=paragraphs,
            edits=edits_dict,
            output_path=output_path,
            export_format=fmt,
            author=cfg.author_name,
        )
        print(f"Saved to '{actual}'")
    else:
        from src.gui import EditGUI

        app = EditGUI()
        app.root.mainloop()


if __name__ == "__main__":
    main()
