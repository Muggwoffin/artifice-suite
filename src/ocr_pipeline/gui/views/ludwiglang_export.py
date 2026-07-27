"""Export a cleaned collection as a LudwigLang-importable .md file."""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ...export_ludwiglang import MEDIUM_OPTIONS, export_md, _read_manifest
from ..._logging import get_logger
from .. import theme

log = get_logger("ludwiglang_export")

MEDIUM_LABELS = {
    "typed": "Typed",
    "handwritten": "Handwritten",
    "print": "Print",
}


class LudwigLangExportDialog(tk.Toplevel):
    """Modal dialog for LudwigLang .md export (Transport A)."""

    def __init__(self, master, *, output_dir: str = "output"):
        super().__init__(master)
        self.title("Send to LudwigLang")
        self.geometry("640x500")
        self.minsize(560, 420)
        self.configure(bg=theme.BG)
        self.transient(master)

        self.output_dir = output_dir
        self._build()
        self._load_collections()

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=14, pady=(12, 0))
        ttk.Label(top, text="Collection:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        self.collection_var = tk.StringVar()
        self.collection_combo = ttk.Combobox(top, textvariable=self.collection_var,
                                             state="readonly", width=40)
        self.collection_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        self.collection_combo.bind("<<ComboboxSelected>>", lambda _: self._update_preview())
        ttk.Button(top, text="Refresh", command=self._load_collections).pack(side=tk.LEFT)

        opts = ttk.Frame(self)
        opts.pack(fill=tk.X, padx=14, pady=(10, 0))

        ttk.Label(opts, text="Medium:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        self.medium_var = tk.StringVar(value="print")
        medium_combo = ttk.Combobox(opts, textvariable=self.medium_var, state="readonly",
                                    values=list(MEDIUM_LABELS.values()), width=14)
        medium_combo.pack(side=tk.LEFT, padx=(8, 0))
        medium_combo.bind("<<ComboboxSelected>>", lambda _: self._update_preview())

        ttk.Label(opts, text="Author:", font=theme.FONT_BOLD).pack(side=tk.LEFT, padx=(18, 0))
        self.author_var = tk.StringVar()
        ttk.Entry(opts, textvariable=self.author_var, width=16).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(opts, text="Date:", font=theme.FONT_BOLD).pack(side=tk.LEFT, padx=(12, 0))
        self.date_var = tk.StringVar()
        ttk.Entry(opts, textvariable=self.date_var, width=10).pack(side=tk.LEFT, padx=(6, 0))

        checks = ttk.Frame(self)
        checks.pack(fill=tk.X, padx=14, pady=(8, 0))

        self.var_markers = tk.BooleanVar(value=False)
        ttk.Checkbutton(checks, text="Page markers (-- N --)",
                        variable=self.var_markers).pack(side=tk.LEFT)
        self.var_skip_lang = tk.BooleanVar(value=False)
        ttk.Checkbutton(checks, text="Skip language check",
                        variable=self.var_skip_lang).pack(side=tk.LEFT, padx=(14, 0))

        self.status = ttk.Label(self, text="", style="Dim.TLabel", wraplength=600,
                                justify=tk.LEFT)
        self.status.pack(anchor=tk.W, padx=14, pady=(10, 0))

        preview = ttk.Frame(self)
        preview.pack(fill=tk.BOTH, expand=True, padx=14, pady=(6, 0))
        self.preview_text = tk.Text(preview, bg=theme.ENTRY_BG, fg=theme.FG_SOFT,
                                    font=theme.FONT_MONO, height=10, relief=tk.FLAT,
                                    bd=0, padx=10, pady=6, state=tk.DISABLED,
                                    wrap=tk.WORD)
        scroll = ttk.Scrollbar(preview, orient=tk.VERTICAL,
                               command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=scroll.set)
        self.preview_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=14, pady=(0, 14))

        self.export_btn = ttk.Button(footer, text="Export .md",
                                     style="Accent.TButton",
                                     command=self._export, state=tk.DISABLED)
        self.export_btn.pack(side=tk.RIGHT)
        ttk.Button(footer, text="Close", command=self._close).pack(
            side=tk.RIGHT, padx=(0, 8))

    def _load_collections(self):
        cleaned = Path(self.output_dir) / "cleaned" / "text"
        if not cleaned.exists():
            self.collection_combo.configure(values=[])
            self._set_status(
                f"No output directory found at {cleaned}", theme.ERROR)
            return
        collections = sorted(d.name for d in cleaned.iterdir() if d.is_dir())
        self.collection_combo.configure(values=collections)
        if collections:
            self.collection_var.set(collections[0])
            self._update_preview()
        else:
            self._set_status(
                "No processed collections found in output/cleaned/text/", theme.FG_DIM)

    def _medium_key(self) -> str:
        label = self.medium_var.get()
        for k, v in MEDIUM_LABELS.items():
            if v == label:
                return k
        return "print"

    def _set_status(self, text: str, colour: str):
        self.status.configure(text=text, foreground=colour)

    def _update_preview(self):
        coll = self.collection_var.get()
        if not coll:
            self.preview_text.configure(state=tk.NORMAL)
            self.preview_text.delete("1.0", tk.END)
            self.preview_text.insert(tk.END, "Select a collection above.")
            self.preview_text.configure(state=tk.DISABLED)
            self.export_btn.configure(state=tk.DISABLED)
            return

        cleaned_root = Path(self.output_dir) / "cleaned" / "text" / coll
        if not cleaned_root.exists():
            self._set_status(f"Collection not found: {cleaned_root}", theme.ERROR)
            return

        from ...export_ludwiglang import assemble_collection

        try:
            result = assemble_collection(cleaned_root,
                                         page_markers=self.var_markers.get())
        except FileNotFoundError as exc:
            self._set_status(str(exc), theme.ERROR)
            return

        self.preview_text.configure(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        parts = [
            f"Collection: {result.title}",
            f"Pages:      {result.page_count}",
            f"Skipped:    {result.skipped_count}",
            f"Chars:      {len(result.body)}",
        ]
        if result.skipped_count:
            parts.append(f"Skipped:    {', '.join(result.skipped_stems)}")
        if result.body_truncated:
            parts.append("(truncated to 200K chars)")
        parts.append("")
        parts.append(result.body[:800])
        if len(result.body) > 800:
            parts.append("…")
        self.preview_text.insert(tk.END, "\n".join(parts))
        self.preview_text.configure(state=tk.DISABLED)

        self._set_status(
            f"{result.page_count} page(s), {result.skipped_count} skipped, "
            f"{len(result.body)} chars",
            theme.FG_SOFT if not result.skipped_count else theme.WARNING,
        )
        self.export_btn.configure(state=tk.NORMAL)

    def _export(self):
        coll = self.collection_var.get()
        if not coll:
            return

        cleaned_root = Path(self.output_dir) / "cleaned" / "text" / coll
        manifest = _read_manifest(Path(self.output_dir))

        self.export_btn.configure(state=tk.DISABLED)
        self._set_status("Exporting…", theme.FG_DIM)
        self.update_idletasks()

        try:
            result_path = export_md(
                cleaned_root,
                medium=self._medium_key(),
                author=self.author_var.get(),
                date=self.date_var.get(),
                page_markers=self.var_markers.get(),
                manifest=manifest,
                skip_language_gate=self.var_skip_lang.get(),
            )
        except ValueError as exc:
            self._set_status(str(exc), theme.ERROR)
            self.export_btn.configure(state=tk.NORMAL)
            return

        self._set_status(f"Exported to {result_path}", theme.SUCCESS)
        messagebox.showinfo(
            "Exported",
            f"LudwigLang .md written to:\n\n{result_path}\n\n"
            f"Drag this file onto http://localhost:8765/import in your browser.",
            parent=self,
        )
        self.export_btn.configure(state=tk.NORMAL)

    def _close(self):
        self.grab_release()
        self.destroy()
