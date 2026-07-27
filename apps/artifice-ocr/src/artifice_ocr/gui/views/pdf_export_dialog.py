"""Compile processed text into one PDF — batch-first, threaded, live progress.

The batch source is the queue: the current selection, or the whole run when
nothing is selected (main_view passes the stems in).  A folder of .txt files
remains available as an alternative source for ad-hoc exports.
"""

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .. import theme

POLL_MS = 80

STAGE_CHOICES = [
    ("cleaned", "Cleaned text"),
    ("raw_ocr", "Raw OCR text"),
    ("translated", "Translation"),
]

FORMAT_CHOICES = [
    ("pdf", "PDF"),
    ("md", "Markdown"),
]

STYLE_CHOICES = [
    ("readable", "Readable"),
    ("academic", "Academic"),
    ("compact", "Compact"),
]


def _derive_output_folder(item, output_dir: str = "output") -> str | None:
    """Try to guess the output text folder for a queue item.

    Matches patterns like:
      <output_dir>/cleaned/text/<Item Title>/page.txt  (Tropy item)
      <output_dir>/cleaned/text/page.txt               (single file)
    Returns the containing folder path or None.
    """
    stem = getattr(item, "stem", None)
    if not stem:
        return None

    # Tropy items have a stem like "Item Title/pagename"
    if "/" in stem:
        item_dir = stem.rsplit("/", 1)[0]
    elif "\\" in stem:
        item_dir = stem.rsplit("\\", 1)[0]
    else:
        item_dir = None

    for stage_dir, _ in STAGE_CHOICES:
        candidate = Path(output_dir) / stage_dir / "text"
        if item_dir:
            full = candidate / item_dir
        else:
            full = candidate
        if full.exists():
            return str(full)
    return None


class PdfExportDialog(tk.Toplevel):
    """Modal dialog for compiling processed text into a PDF.

    Threading: runs pdf_export.compile()/compile_batch() in a daemon thread,
    drains progress onto the tk main loop via a queue.Queue + self.after()
    polling loop — the same pattern App.gui/app.py uses for JobRunner events.
    """

    def __init__(self, master, *, default_folder: str | None = None,
                 batch_stems: list[str] | None = None,
                 output_dir: str = "output"):
        super().__init__(master)
        self.title("Compile PDF")
        self.geometry("720x560")
        self.minsize(620, 420)
        self.configure(bg=theme.BG)
        self.transient(master)

        self.queue: queue.Queue = queue.Queue()
        self.result_path: str | None = None
        self._thread: threading.Thread | None = None
        self.batch_stems = batch_stems or []
        self.output_dir = output_dir

        self._build(default_folder)

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ---------------------------------------------------------------- layout
    def _build(self, default_folder: str | None):
        pad = 14
        has_batch = bool(self.batch_stems)

        # Source: queue batch vs folder
        src = ttk.Frame(self)
        src.pack(fill=tk.X, padx=pad, pady=(12, 0))

        self.source_var = tk.StringVar(value="batch" if has_batch else "folder")
        self.batch_radio = ttk.Radiobutton(
            src, variable=self.source_var, value="batch",
            text=f"Queue batch ({len(self.batch_stems)} item(s)) → one combined PDF",
            command=self._on_source_change,
        )
        self.batch_radio.pack(anchor=tk.W)
        if not has_batch:
            self.batch_radio.configure(state=tk.DISABLED)

        folder_row = ttk.Frame(src)
        folder_row.pack(fill=tk.X, pady=(6, 0))
        self.folder_radio = ttk.Radiobutton(
            folder_row, variable=self.source_var, value="folder",
            text="Folder:", command=self._on_source_change,
        )
        self.folder_radio.pack(side=tk.LEFT)
        self.folder_var = tk.StringVar(value=default_folder or "")
        self.folder_entry = ttk.Entry(
            folder_row, textvariable=self.folder_var, width=46)
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        self.folder_browse = ttk.Button(
            folder_row, text="Browse…", command=self._browse_folder)
        self.folder_browse.pack(side=tk.LEFT)

        # Stage + Structure row
        opts = ttk.Frame(self)
        opts.pack(fill=tk.X, padx=pad, pady=(10, 0))

        ttk.Label(opts, text="Stage:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        self.stage_var = tk.StringVar(value=STAGE_CHOICES[0][1])
        stage_combo = ttk.Combobox(
            opts, textvariable=self.stage_var, state="readonly",
            values=[label for _, label in STAGE_CHOICES], width=18,
        )
        stage_combo.pack(side=tk.LEFT, padx=(8, 0))

        # Structuring makes one model call per page — opt-in for batches,
        # default-on only for single-folder exports (previous behaviour).
        self.var_structure = tk.BooleanVar(value=not has_batch)
        ttk.Checkbutton(
            opts, text="Structure text (one model call per page)",
            variable=self.var_structure,
        ).pack(side=tk.LEFT, padx=(20, 0))

        # Advanced (format + style), hidden by default
        self.advanced_btn = ttk.Button(
            self, text="Advanced ▸", command=self._toggle_advanced)
        self.advanced_btn.pack(anchor=tk.W, padx=pad, pady=(8, 0))

        self.advanced = ttk.Frame(self)
        fmt_row = ttk.Frame(self.advanced)
        fmt_row.pack(fill=tk.X, pady=(2, 0))

        ttk.Label(fmt_row, text="Format:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        self.format_var = tk.StringVar(value=FORMAT_CHOICES[0][1])
        fmt_combo = ttk.Combobox(
            fmt_row, textvariable=self.format_var, state="readonly",
            values=[label for _, label in FORMAT_CHOICES], width=12,
        )
        fmt_combo.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(fmt_row, text="Style:", font=theme.FONT_BOLD).pack(side=tk.LEFT, padx=(20, 0))
        self.style_var = tk.StringVar(value=STYLE_CHOICES[0][1])
        style_combo = ttk.Combobox(
            fmt_row, textvariable=self.style_var, state="readonly",
            values=[label for _, label in STYLE_CHOICES], width=12,
        )
        style_combo.pack(side=tk.LEFT, padx=(8, 0))

        # Output path — pre-filled for batch exports so the destination is
        # visible before starting (timestamped: no silent overwrite).
        out_row = ttk.Frame(self)
        out_row.pack(fill=tk.X, padx=pad, pady=(10, 0))

        ttk.Label(out_row, text="Output:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        self.output_var = tk.StringVar(value=self._default_output())
        ttk.Entry(out_row, textvariable=self.output_var, width=50).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        ttk.Button(out_row, text="Browse…", command=self._browse_output).pack(side=tk.LEFT)

        # Status
        if has_batch:
            initial = (f"Ready — {len(self.batch_stems)} queue item(s) will be "
                       "compiled into one PDF.")
        else:
            initial = "Choose a folder of processed .txt files, then press Compile."
        self.status = ttk.Label(
            self, text=initial,
            style="Dim.TLabel", wraplength=660, justify=tk.LEFT,
        )
        self.status.pack(anchor=tk.W, padx=pad, pady=(10, 0))

        # Log area
        log_frame = ttk.Frame(self)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=pad, pady=(10, 0))

        self.log = scrolledtext.ScrolledText(
            log_frame, bg=theme.ENTRY_BG, fg=theme.FG_SOFT, font=theme.FONT_MONO,
            height=10, relief=tk.FLAT, bd=0, state=tk.DISABLED,
            insertbackground=theme.FG, padx=10, pady=6,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.tag_configure("success", foreground=theme.SUCCESS)
        self.log.tag_configure("warning", foreground=theme.WARNING)
        self.log.tag_configure("error", foreground=theme.ERROR)
        self.log.tag_configure("accent", foreground=theme.ACCENT)

        # Buttons
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=pad, pady=(10, 14))

        self.open_btn = ttk.Button(
            footer, text="Open File", command=self._open_pdf, state=tk.DISABLED,
        )
        self.open_btn.pack(side=tk.LEFT)

        ttk.Button(footer, text="Close", command=self._close).pack(
            side=tk.RIGHT, padx=(0, 8))

        self.compile_btn = ttk.Button(
            footer, text="Compile", style="Accent.TButton",
            command=self._start_compile,
        )
        self.compile_btn.pack(side=tk.RIGHT)

        self._on_source_change()

    # ------------------------------------------------------- source / layout
    def _on_source_change(self):
        folder_mode = self.source_var.get() == "folder"
        state = tk.NORMAL if folder_mode else tk.DISABLED
        self.folder_entry.configure(state=state)
        self.folder_browse.configure(state=state)

    def _toggle_advanced(self):
        if self.advanced.winfo_ismapped():
            self.advanced.pack_forget()
            self.advanced_btn.configure(text="Advanced ▸")
        else:
            # Reveal directly under its button, above the output row.
            self.advanced.pack(fill=tk.X, padx=14, pady=(2, 0),
                               after=self.advanced_btn)
            self.advanced_btn.configure(text="Advanced ▾")

    def _default_output(self) -> str:
        if not self.batch_stems:
            return ""
        from ... import pdf_export
        return str(pdf_export.default_batch_output(
            self.batch_stems, output_dir=self.output_dir))

    # ---------------------------------------------------------- file dialogs
    def _browse_folder(self):
        chosen = filedialog.askdirectory(title="Select a folder of processed .txt files")
        if chosen:
            self.folder_var.set(chosen)

    def _browse_output(self):
        fmt = self._format()
        if fmt == "md":
            chosen = filedialog.asksaveasfilename(
                title="Save Markdown as",
                defaultextension=".md",
                filetypes=[("Markdown files", "*.md"), ("All files", "*.*")],
            )
        else:
            chosen = filedialog.asksaveasfilename(
                title="Save PDF as",
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            )
        if chosen:
            self.output_var.set(chosen)

    # ----------------------------------------------------------- compile run
    def _stage(self) -> str:
        label = self.stage_var.get()
        return next((k for k, v in STAGE_CHOICES if v == label), "cleaned")

    def _format(self) -> str:
        label = self.format_var.get()
        return next((k for k, v in FORMAT_CHOICES if v == label), "pdf")

    def _style(self) -> str:
        label = self.style_var.get()
        return next((k for k, v in STYLE_CHOICES if v == label), "readable")

    def _start_compile(self):
        if self.source_var.get() == "folder":
            folder = self.folder_var.get().strip()
            if not folder:
                messagebox.showwarning("No folder", "Choose a folder of processed .txt files first.")
                return
            if not Path(folder).exists():
                messagebox.showerror("Folder not found", f"Folder does not exist:\n{folder}")
                return

        self.compile_btn.configure(state=tk.DISABLED)
        self.open_btn.configure(state=tk.DISABLED)
        self._clear_log()
        self._set_status("Compiling…", theme.FG_DIM)

        self.queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.after(POLL_MS, self._pump)

    def _run(self):
        """Run compile()/compile_batch() in the background thread."""
        from ... import pdf_export

        output = self.output_var.get().strip() or None
        try:
            if self.source_var.get() == "batch":
                result = pdf_export.compile_batch(
                    self.batch_stems,
                    output_dir=self.output_dir,
                    stage=self._stage(),
                    structure=self.var_structure.get(),
                    output=output,
                    format=self._format(),
                    style=self._style(),
                    on_progress=lambda msg: self.queue.put(("log", msg)),
                )
            else:
                result = pdf_export.compile(
                    self.folder_var.get().strip(),
                    stage=self._stage(),
                    structure=self.var_structure.get(),
                    output=output,
                    format=self._format(),
                    style=self._style(),
                    on_progress=lambda msg: self.queue.put(("log", msg)),
                )
            self.queue.put(("done", str(result)))
        except Exception as exc:
            self.queue.put(("error", str(exc)))

    def _pump(self):
        """Drain the progress queue on the tk main thread."""
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    tag = "warning" if (
                        "Guard rejected" in payload
                        or payload.startswith("Skipped")
                    ) else ""
                    self._log(payload, tag)
                elif kind == "done":
                    self.result_path = payload
                    self._log(f"PDF written to {payload}", "success")
                    self._set_status(
                        f"Done — {Path(payload).name}", theme.SUCCESS)
                    self.compile_btn.configure(state=tk.NORMAL)
                    self.open_btn.configure(state=tk.NORMAL)
                elif kind == "error":
                    self._log(f"ERROR: {payload}", "error")
                    self._set_status(f"Failed: {payload}", theme.ERROR)
                    self.compile_btn.configure(state=tk.NORMAL)
        except queue.Empty:
            pass
        finally:
            if self._thread and self._thread.is_alive():
                self.after(POLL_MS, self._pump)

    # ------------------------------------------------------------- log/status
    def _clear_log(self):
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def _log(self, msg: str, tag: str = ""):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_status(self, text: str, colour: str):
        self.status.configure(text=text, foreground=colour)

    # ---------------------------------------------------------------- actions
    def _open_pdf(self):
        if self.result_path and Path(self.result_path).exists():
            os.startfile(self.result_path)

    def _close(self):
        self.grab_release()
        self.destroy()
