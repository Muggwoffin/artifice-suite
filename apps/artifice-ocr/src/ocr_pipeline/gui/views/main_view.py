"""Main tab: drop zone, live batch queue, run controls and log."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from tkinterdnd2 import DND_FILES

from ...jobs import State
from .. import theme
from ..widgets.queue_table import QueueTable

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"}


class MainView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self._build_header()
        self._build_drop_zone()
        self._build_queue()
        self._build_queue_controls()
        self._build_run_controls()
        self._build_log()

    # ---------------------------------------------------------------- header
    def _build_header(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=16, pady=(12, 0))
        ttk.Label(top, text="Batch Queue", style="Title.TLabel").pack(side=tk.LEFT)
        self.count_label = ttk.Label(top, text="0 files", style="Dim.TLabel")
        self.count_label.pack(side=tk.RIGHT)

    # ------------------------------------------------------------- drop zone
    def _build_drop_zone(self):
        self.drop_frame = tk.Frame(self, bg=theme.FRAME_BG, bd=1,
                                   relief=tk.SOLID, highlightthickness=0,
                                   cursor="hand2")
        self.drop_frame.configure(highlightbackground=theme.RULE)
        self.drop_frame.pack(fill=tk.X, padx=16, pady=(10, 0))

        self.drop_label = tk.Label(
            self.drop_frame,
            text="Drop files or folders here, or click to browse",
            font=theme.FONT, bg=theme.FRAME_BG, fg=theme.FG_DIM, pady=14,
            cursor="hand2",
        )
        self.drop_label.pack(fill=tk.X, padx=4, pady=2)

        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_frame.dnd_bind("<<DropEnter>>", self._on_drop_enter)
        self.drop_frame.dnd_bind("<<DropLeave>>", self._on_drop_leave)
        self.drop_label.bind("<Button-1>", lambda _: self.browse_files())

    def _on_drop_enter(self, _event):
        self.drop_frame.configure(bg=theme.SEL_BG)
        self.drop_label.configure(bg=theme.SEL_BG, fg=theme.ACCENT_DEEP)

    def _on_drop_leave(self, _event):
        self.drop_frame.configure(bg=theme.FRAME_BG)
        self.drop_label.configure(bg=theme.FRAME_BG, fg=theme.FG_DIM)

    # ----------------------------------------------------------------- queue
    def _build_queue(self):
        self.queue = QueueTable(
            self,
            on_selection_change=self._on_item_selected,
            on_context_action=self._on_context_action,
        )
        self.queue.pack(fill=tk.BOTH, expand=True, padx=16, pady=(10, 0))

    def _build_queue_controls(self):
        row = ttk.Frame(self)
        row.pack(fill=tk.X, padx=16, pady=(6, 0))

        ttk.Button(row, text="Browse Files", command=self.browse_files).pack(side=tk.LEFT)
        ttk.Button(row, text="Add Folder", command=self.browse_folder).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Add from Tropy…", command=self.add_from_tropy).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Remove Selected", style="Danger.TButton",
                   command=self._remove_selected).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Clear All", style="Danger.TButton",
                   command=self._clear).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Separator(row, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)

        self.skip_btn = ttk.Button(row, text="Skip", command=self._skip_selected,
                                   state=tk.DISABLED)
        self.skip_btn.pack(side=tk.LEFT)
        ttk.Button(row, text="Retry", command=self._retry_selected).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="View →", command=self._view_selected).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Compile PDF…", command=self.compile_pdf).pack(
            side=tk.RIGHT, padx=(0, 6))
        ttk.Button(row, text="Send to Tropy…", command=self.send_to_tropy).pack(
            side=tk.RIGHT)
        ttk.Button(row, text="Send to LudwigLang…",
                   command=self.send_to_ludwiglang).pack(side=tk.RIGHT, padx=(0, 6))

    # ---------------------------------------------------------- run controls
    def _build_run_controls(self):
        stages_row = ttk.Frame(self)
        stages_row.pack(fill=tk.X, padx=16, pady=(10, 0))

        ttk.Label(stages_row, text="Stages:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        for text, var in [
            ("OCR", self.app.var_ocr),
            ("Cleanup", self.app.var_cleanup),
            ("Translate", self.app.var_translate),
            ("Force re-run", self.app.var_force),
        ]:
            ttk.Checkbutton(stages_row, text=text, variable=var).pack(
                side=tk.LEFT, padx=(12, 0))

        out_row = ttk.Frame(self)
        out_row.pack(fill=tk.X, padx=16, pady=(8, 0))
        ttk.Label(out_row, text="Output:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        ttk.Entry(out_row, textvariable=self.app.output_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        ttk.Button(out_row, text="…", width=3,
                   command=self._browse_output_dir).pack(side=tk.LEFT)

        self.run_btn = ttk.Button(out_row, text="▶  Run Pipeline",
                                  style="Accent.TButton", command=self.app.start_run)
        self.run_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.pause_btn = ttk.Button(out_row, text="⏸  Pause",
                                    command=self.app.toggle_pause, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.RIGHT, padx=(8, 0))
        self.stop_btn = ttk.Button(out_row, text="⏹  Stop", style="Danger.TButton",
                                   command=self.app.cancel_run, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.RIGHT)

        prog_row = ttk.Frame(self)
        prog_row.pack(fill=tk.X, padx=16, pady=(8, 0))
        self.progress = ttk.Progressbar(prog_row, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)

    # ------------------------------------------------------------------- log
    def _build_log(self):
        self.log = scrolledtext.ScrolledText(
            self, bg=theme.ENTRY_BG, fg=theme.FG_SOFT, font=theme.FONT_MONO,
            height=8, relief=tk.FLAT, bd=0, state=tk.DISABLED,
            insertbackground=theme.FG, padx=10, pady=6,
        )
        self.log.pack(fill=tk.BOTH, expand=False, padx=16, pady=(10, 12))
        self.log.tag_configure("success", foreground=theme.SUCCESS)
        self.log.tag_configure("warning", foreground=theme.WARNING)
        self.log.tag_configure("error", foreground=theme.ERROR)
        self.log.tag_configure("accent", foreground=theme.ACCENT)

    def log_message(self, msg: str, tag: str = "") -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n", tag)
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    # --------------------------------------------------------------- actions
    def _on_drop(self, event):
        self._on_drop_leave(event)
        paths = self.winfo_toplevel().tk.splitlist(event.data)
        collected: list[str] = []
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                collected.extend(
                    str(f) for f in sorted(pp.rglob("*"))
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
                )
            elif pp.suffix.lower() in SUPPORTED_EXTENSIONS:
                collected.append(str(pp))
        self._add(collected, "drag-and-drop")

    def browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Select document files",
            filetypes=[
                ("Documents", "*.jpg *.jpeg *.png *.tif *.tiff *.pdf"),
                ("Image files", "*.jpg *.jpeg *.png *.tif *.tiff"),
                ("PDF files", "*.pdf"),
                ("All files", "*.*"),
            ],
        )
        self._add(list(paths), "browse")

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select a folder of documents")
        if not folder:
            return
        files = [
            str(f) for f in sorted(Path(folder).rglob("*"))
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        self._add(files, f"folder {Path(folder).name}")

    def compile_pdf(self):
        """Compile the batch (selection, else whole queue) into one PDF."""
        from .pdf_export_dialog import PdfExportDialog, _derive_output_folder

        output_dir = self.app.output_var.get().strip() or "output"

        # The batch is the current selection; with nothing selected it is the
        # whole queue run.  Stems dedupe in queue order.
        batch = self.queue.selected_items() or list(self.queue.items)
        stems: list[str] = []
        seen: set[str] = set()
        for item in batch:
            if item.stem and item.stem not in seen:
                seen.add(item.stem)
                stems.append(item.stem)

        if batch:
            default_folder = _derive_output_folder(batch[0], output_dir)
        else:
            default_folder = str(Path(output_dir) / "cleaned" / "text")

        dialog = PdfExportDialog(
            self.winfo_toplevel(),
            default_folder=default_folder,
            batch_stems=stems or None,
            output_dir=output_dir,
        )
        self.wait_window(dialog)

    def send_to_tropy(self):
        """Write finished results back into a Tropy project."""
        from .tropy_send import TropySendDialog

        selected = self.queue.selected_items()
        items = selected or self.queue.items
        tropy_items = [i for i in items if (i.source or {}).get("photo_id")]
        if not tropy_items:
            messagebox.showinfo(
                "Nothing to send",
                "None of these documents came from Tropy.\n\n"
                "Use 'Add from Tropy…' to queue pages from a project, run them, "
                "then send the results back.")
            return

        dialog = TropySendDialog(self.winfo_toplevel(), tropy_items)
        self.wait_window(dialog)
        if dialog.written:
            self.log_message(
                f"Wrote {dialog.written} row(s) back to Tropy", "success")

    def send_to_ludwiglang(self):
        """Export a cleaned collection as a LudwigLang .md file."""
        from .ludwiglang_export import LudwigLangExportDialog

        output_dir = self.app.output_var.get().strip() or "output"
        dialog = LudwigLangExportDialog(
            self.winfo_toplevel(), output_dir=output_dir)
        self.wait_window(dialog)

    def add_from_tropy(self):
        """Open the Tropy picker and queue whatever it returns."""
        from .tropy_picker import TropyPicker

        picker = TropyPicker(self.winfo_toplevel(),
                             output_dir=self.app.output_var.get() or "output")
        self.wait_window(picker)
        if not picker.result:
            return

        added = self.queue.add_items(picker.result)
        self.update_counts()
        self.log_message(
            f"Added {added} page(s) from Tropy "
            f"(manifest written to the output folder)", "accent")

    def _add(self, paths: list[str], source: str):
        added = self.queue.add_paths(paths)
        self.update_counts()
        if added:
            self.log_message(f"Added {added} file(s) via {source}", "accent")
        elif paths:
            self.log_message("All dropped files were already queued", "warning")

    def _browse_output_dir(self):
        d = filedialog.askdirectory(title="Select output directory")
        if d:
            self.app.output_var.set(d)

    def _remove_selected(self):
        self.queue.remove_selected()
        self.update_counts()

    def _clear(self):
        self.queue.clear()
        self.update_counts()

    def _skip_selected(self):
        for item in self.queue.selected_items():
            self.app.skip_item(item)

    def _retry_selected(self):
        self.app.retry_items(self.queue.selected_items())

    def _view_selected(self):
        selected = self.queue.selected_items()
        if selected:
            self.app.show_in_preview(selected[0])

    def _on_item_selected(self, item):
        if item is not None:
            self.app.preview_item(item)

    def _on_context_action(self, action: str, items: list):
        if action == "retry":
            self.app.retry_items(items)
        elif action == "skip":
            for item in items:
                self.app.skip_item(item)
        elif action == "remove":
            self._remove_selected()
        elif action == "open_output" and items:
            self.app.open_output_folder(items[0])

    # --------------------------------------------------------------- display
    def update_counts(self):
        items = self.queue.items
        n = len(items)
        done = sum(1 for i in items if i.state is State.DONE)
        failed = sum(1 for i in items if i.state is State.FAILED)
        text = f"{n} file{'s' if n != 1 else ''}"
        if done or failed:
            text += f"  ·  {done} done"
            if failed:
                text += f"  ·  {failed} failed"
        self.count_label.configure(text=text)

    def set_running(self, running: bool):
        self.run_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.pause_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        self.skip_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        if not running:
            self.pause_btn.configure(text="⏸  Pause")

    def set_progress(self, done: int, total: int):
        self.progress.configure(maximum=max(total, 1), value=done)
