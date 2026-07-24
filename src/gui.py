"""Tkinter GUI with drag-and-drop, settings panel, and review workflow.

Falls back to a file picker button when tkinterdnd2 is not installed.
"""

from __future__ import annotations

import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.config import AppConfig
from src.models import (
    EditingStyle,
    ExportFormat,
    LLMProvider,
    PipelineProgress,
)

logger = logging.getLogger(__name__)


class EditGUI:
    """Main GUI window for the copy-edit tool."""

    def __init__(self):
        self.root = tk.Tk()
        self.canvas = None
        self._drop_file_path: str | None = None
        self._result_path: str | None = None
        self._cfg = AppConfig.from_env()
        self._edit_items: list[dict] = []
        self._paragraphs: list[dict] = []

        self._build_ui()
        self.root.title("Copy Editor")
        self.root.minsize(700, 500)

    def _build_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)

        self._build_drop_zone(main_frame)
        self._build_status_bar(main_frame)
        self._build_settings_panel(main_frame)

    def _build_drop_zone(self, parent):
        self.canvas = tk.Canvas(parent, width=800, height=300, bg="#f0f4f8")
        self.canvas.pack(fill="x", padx=20, pady=(15, 5))

        self.canvas.create_rectangle(
            50, 30, 750, 270,
            outline="#b0c4de", width=2, dash=(6, 4),
            tags="drop_zone",
        )
        self.canvas.create_text(
            400, 150,
            text="Drop a .docx file here\nor click Browse below",
            fill="#607080", font=("Segoe UI", 14),
            tags="drop_label",
        )

        self._dnd_available = False
        try:
            self.root.update_idletasks()
            self._setup_dnd()
            self._dnd_available = True
        except Exception:
            pass

    def _build_status_bar(self, parent):
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill="x", padx=20, pady=(5, 0))

        self.status_label = ttk.Label(
            status_frame, text="Select a .docx file to start editing"
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.browse_btn = ttk.Button(
            status_frame, text="Browse...", command=self._browse_file
        )
        self.browse_btn.pack(side="left", padx=(0, 10))

        self.progress_bar = ttk.Progressbar(
            status_frame, length=250, mode="determinate"
        )
        self.progress_bar.pack(side="left", padx=10)

        self.open_btn = ttk.Button(
            status_frame, text="Open result", command=self._open_result
        )
        self.open_btn.pack(side="right", padx=(0, 10))
        self.open_btn.config(state="disabled")

    def _build_settings_panel(self, parent):
        settings_frame = ttk.LabelFrame(parent, text="Settings", padding=10)
        settings_frame.pack(fill="x", padx=20, pady=10)

        row1 = ttk.Frame(settings_frame)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="Provider:").pack(side="left")
        self.provider_var = tk.StringVar(value=self._cfg.llm_provider.value)
        provider_combo = ttk.Combobox(
            row1, textvariable=self.provider_var,
            values=[p.value for p in LLMProvider],
            state="readonly", width=12,
        )
        provider_combo.pack(side="left", padx=(5, 20))

        ttk.Label(row1, text="Editing Style:").pack(side="left")
        self.style_var = tk.StringVar(value=self._cfg.editing_style.value)
        style_combo = ttk.Combobox(
            row1, textvariable=self.style_var,
            values=[s.value for s in EditingStyle],
            state="readonly", width=12,
        )
        style_combo.pack(side="left", padx=(5, 20))

        ttk.Label(row1, text="Export Format:").pack(side="left")
        self.export_var = tk.StringVar(value=self._cfg.export_format.value)
        export_combo = ttk.Combobox(
            row1, textvariable=self.export_var,
            values=[f.value for f in ExportFormat],
            state="readonly", width=18,
        )
        export_combo.pack(side="left", padx=(5, 0))

        row2 = ttk.Frame(settings_frame)
        row2.pack(fill="x", pady=2)

        ttk.Label(row2, text="Batch Size:").pack(side="left")
        self.batch_var = tk.IntVar(value=self._cfg.batch_size)
        batch_spin = ttk.Spinbox(
            row2, from_=1, to=20, textvariable=self.batch_var, width=5
        )
        batch_spin.pack(side="left", padx=(5, 20))

        ttk.Label(row2, text="Temperature:").pack(side="left")
        self.temp_var = tk.DoubleVar(value=self._cfg.temperature)
        temp_spin = ttk.Spinbox(
            row2, from_=0.0, to=2.0, increment=0.1,
            textvariable=self.temp_var, width=5,
        )
        temp_spin.pack(side="left", padx=(5, 20))

        self.review_var = tk.BooleanVar(value=self._cfg.enable_review)
        ttk.Checkbutton(
            row2, text="Review edits before saving",
            variable=self.review_var,
        ).pack(side="left", padx=(10, 0))

        row3 = ttk.Frame(settings_frame)
        row3.pack(fill="x", pady=2)

        ttk.Label(row3, text="Author Name:").pack(side="left")
        self.author_var = tk.StringVar(value=self._cfg.author_name)
        ttk.Entry(row3, textvariable=self.author_var, width=25).pack(
            side="left", padx=(5, 20)
        )

        ttk.Label(row3, text="Custom Prompt:").pack(side="left")
        self.prompt_var = tk.StringVar(value="")
        ttk.Entry(row3, textvariable=self.prompt_var, width=40).pack(
            side="left", padx=(5, 0)
        )

    def _setup_dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_dnd_drop)
        except ImportError:
            pass

    def _on_dnd_drop(self, event):
        data = event.data
        path = str(data).strip()

        if path.startswith("{") and path.endswith("}"):
            path = path[1:-1]

        if not os.path.isfile(path):
            return

        if path.lower().endswith(".docx"):
            self._start_processing(path)
        else:
            self.status_label.config(text="Only .docx files are supported.")

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select a Word document",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
        )
        if path:
            if not path.lower().endswith(".docx"):
                self.status_label.config(text="Only .docx files are supported.")
                return
            self._start_processing(path)

    def _apply_settings(self):
        try:
            self._cfg.llm_provider = LLMProvider(self.provider_var.get())
        except ValueError:
            pass
        try:
            self._cfg.editing_style = EditingStyle(self.style_var.get())
        except ValueError:
            pass
        try:
            self._cfg.export_format = ExportFormat(self.export_var.get())
        except ValueError:
            pass

        self._cfg.batch_size = self.batch_var.get()
        self._cfg.temperature = self.temp_var.get()
        self._cfg.enable_review = self.review_var.get()
        self._cfg.author_name = self.author_var.get()
        self._cfg.custom_system_prompt = self.prompt_var.get()

    def _start_processing(self, path: str):
        self._drop_file_path = path
        self._result_path = None
        self.open_btn.config(state="disabled")
        self._apply_settings()
        self.status_label.config(
            text=f"Processing '{os.path.basename(path)}'..."
        )
        self.progress_bar["value"] = 0
        self.root.update_idletasks()

        threading.Thread(
            target=self._run_edit, args=(path,), daemon=True
        ).start()

    def _update_progress(self, pct: float, msg: str):
        self.root.after(0, lambda: self.progress_bar.config(value=pct))
        self.root.after(0, lambda: self.status_label.config(text=msg))

    def _on_llm_progress(self, progress: PipelineProgress):
        self._update_progress(
            min(progress.percentage * 0.7 + 15, 85),
            progress.message,
        )

    def _run_edit(self, path: str):
        try:
            from src.changelog import format_change_log, generate_change_summary
            from src.doc_parser import parse_docx
            from src.doc_writer import apply_edits
            from src.llm_client import LLMEdit, call_ollama
            from src.review import apply_decisions, cli_review, create_review_items

            cfg = self._cfg

            self._update_progress(5, "Parsing document...")
            paragraphs = parse_docx(path)
            if not paragraphs:
                self._update_progress(
                    0, "No content found in the document."
                )
                return

            self._paragraphs = paragraphs
            self._update_progress(
                15,
                f"Sending {len(paragraphs)} paragraphs to "
                f"{cfg.active_model}...",
            )

            edits_list = call_ollama(
                paragraphs=paragraphs,
                batch_size=cfg.batch_size,
                config=cfg,
                on_progress=self._on_llm_progress,
            )

            if cfg.enable_review:
                self._update_progress(
                    75,
                    "Review mode - check terminal for review prompt...",
                )
                items = create_review_items(edits_list, paragraphs)
                self._edit_items = items
                decisions = cli_review(items)
                edits_dict = apply_decisions(edits_list, decisions)
            else:
                edits_dict = LLMEdit.to_edits_dict(edits_list)

            self._update_progress(85, "Generating change summary...")
            summary = generate_change_summary(edits_list, paragraphs)
            change_log = format_change_log(summary)
            logger.info(change_log)

            self._update_progress(90, "Writing output document...")
            base, _ext = os.path.splitext(path)

            fmt = cfg.export_format
            ext_map = {
                ExportFormat.DOCX_TRACK_CHANGES: "_edited.docx",
                ExportFormat.DOCX_PLAIN: "_edited.docx",
                ExportFormat.MARKDOWN: "_edited.md",
                ExportFormat.HTML: "_edited.html",
                ExportFormat.PLAIN_TEXT: "_edited.txt",
            }
            output_path = base + ext_map.get(fmt, "_edited.docx")
            if os.path.exists(output_path):
                output_path = (
                    base + "_edited_2" + ext_map.get(fmt, ".docx")
                )

            actual_path = apply_edits(
                input_path=path,
                paragraphs=paragraphs,
                edits=edits_dict,
                output_path=output_path,
                export_format=fmt,
                author=cfg.author_name,
            )
            self._result_path = actual_path

            self._update_progress(
                100,
                f"Done! Saved to '{os.path.basename(actual_path)}'",
            )
            self.root.after(
                0, lambda: self.open_btn.config(state="normal")
            )

        except Exception as exc:
            logger.exception("Error during edit processing")
            self.root.after(
                0,
                lambda e=exc: self.status_label.config(
                    text=f"Error: {e}"
                ),
            )

    def _open_result(self):
        if not self._result_path or not os.path.isfile(self._result_path):
            messagebox.showerror(
                "No result found",
                "The edited file was not saved.\n"
                "Check the status label for errors.",
            )
            return
        try:
            os.startfile(self._result_path)
        except AttributeError:
            import subprocess
            import sys

            if sys.platform == "darwin":
                subprocess.run(["open", self._result_path], check=False)
            else:
                subprocess.run(
                    ["xdg-open", self._result_path], check=False
                )


if __name__ == "__main__":
    app = EditGUI()
    app.root.mainloop()
