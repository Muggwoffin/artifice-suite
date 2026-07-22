"""Send finished OCR results back into a Tropy project.

Preview first: the dialog opens showing exactly which rows would be created,
and the write button stays disabled until that preview is clean. A backup is
taken before anything is written.
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ...tropy import recent_projects
from ...tropy_write import (
    TARGET_NOTES,
    TARGET_TRANSCRIPTIONS,
    TropyWriter,
    entries_from_items,
)
from .. import theme

STAGE_CHOICES = [
    ("cleaned", "Cleaned text"),
    ("raw_ocr", "Raw OCR text"),
    ("translated", "Translation"),
]


class TropySendDialog(tk.Toplevel):
    """Modal preview-and-write dialog for Tropy write-back."""

    def __init__(self, master, items, *, default_project: str = ""):
        super().__init__(master)
        self.title("Send results to Tropy")
        self.geometry("940x600")
        self.minsize(820, 520)
        self.configure(bg=theme.BG)
        self.transient(master)

        self.items = [i for i in items if (i.source or {}).get("photo_id")]
        self.preview = None
        self.written = 0

        self._build()
        if default_project:
            self.project_var.set(default_project)
        self._load_recent()

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

        if not self.items:
            self._set_status(
                "None of the queued documents came from Tropy — nothing to send.",
                theme.WARNING)

    # ---------------------------------------------------------------- layout
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=14, pady=(12, 0))
        ttk.Label(top, text="Tropy project:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(top, textvariable=self.project_var,
                                          state="readonly", width=52)
        self.project_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        self.project_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh())
        ttk.Button(top, text="Browse…", command=self._browse).pack(side=tk.LEFT)

        opts = ttk.Frame(self)
        opts.pack(fill=tk.X, padx=14, pady=(10, 0))

        ttk.Label(opts, text="Write as:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        self.var_notes = tk.BooleanVar(value=True)
        self.var_transcriptions = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Notes", variable=self.var_notes,
                        command=self._refresh).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Checkbutton(opts, text="Transcriptions", variable=self.var_transcriptions,
                        command=self._refresh).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(opts, text="Text:", font=theme.FONT_BOLD).pack(side=tk.LEFT, padx=(24, 0))
        self.stage_var = tk.StringVar(value=STAGE_CHOICES[0][1])
        stage_combo = ttk.Combobox(opts, textvariable=self.stage_var, state="readonly",
                                   values=[label for _, label in STAGE_CHOICES],
                                   width=16)
        stage_combo.pack(side=tk.LEFT, padx=(8, 0))
        stage_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        self.var_backup = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Back up first", variable=self.var_backup).pack(
            side=tk.RIGHT)

        self.status = ttk.Label(self, text="", style="Dim.TLabel", wraplength=880,
                                justify=tk.LEFT)
        self.status.pack(anchor=tk.W, padx=14, pady=(10, 0))

        table = ttk.Frame(self)
        table.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)

        cols = ("page", "target", "action", "detail")
        self.tree = ttk.Treeview(table, columns=cols, show="headings")
        for col, head, width, anchor in [
            ("page", "PAGE", 300, tk.W), ("target", "TARGET", 120, tk.W),
            ("action", "ACTION", 120, tk.W), ("detail", "DETAIL", 340, tk.W),
        ]:
            self.tree.heading(col, text=head, anchor=anchor)
            self.tree.column(col, width=width, anchor=anchor,
                             stretch=(col == "detail"))
        scroll = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("insert", foreground=theme.ACCENT)
        self.tree.tag_configure("duplicate", foreground=theme.FG_DIM)
        self.tree.tag_configure("missing-photo", foreground=theme.ERROR)
        self.tree.tag_configure("empty", foreground=theme.FG_DIM)

        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=14, pady=(0, 14))
        self.summary = ttk.Label(footer, text="", style="Dim.TLabel")
        self.summary.pack(side=tk.LEFT)

        self.write_btn = ttk.Button(footer, text="Write to Tropy",
                                    style="Accent.TButton",
                                    command=self._write, state=tk.DISABLED)
        self.write_btn.pack(side=tk.RIGHT)
        ttk.Button(footer, text="Close", command=self._close).pack(
            side=tk.RIGHT, padx=(0, 8))
        ttk.Button(footer, text="Refresh preview", command=self._refresh).pack(
            side=tk.RIGHT, padx=(0, 8))

    # -------------------------------------------------------------- projects
    def _load_recent(self):
        seen, unique = set(), []
        for p in recent_projects():
            if str(p) not in seen:
                seen.add(str(p))
                unique.append(str(p))
        self.project_combo.configure(values=unique)
        if not self.project_var.get() and unique:
            self.project_var.set(unique[0])
        if self.project_var.get():
            self._refresh()

    def _browse(self):
        chosen = filedialog.askdirectory(title="Select a .tropy project folder",
                                         parent=self)
        if chosen:
            self.project_var.set(chosen)
            values = list(self.project_combo.cget("values"))
            if chosen not in values:
                self.project_combo.configure(values=[chosen] + values)
            self._refresh()

    # --------------------------------------------------------------- preview
    def _targets(self) -> list[str]:
        targets = []
        if self.var_notes.get():
            targets.append(TARGET_NOTES)
        if self.var_transcriptions.get():
            targets.append(TARGET_TRANSCRIPTIONS)
        return targets

    def _stage(self) -> str:
        label = self.stage_var.get()
        return next((k for k, v in STAGE_CHOICES if v == label), "cleaned")

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.write_btn.configure(state=tk.DISABLED)
        self.preview = None

        project = self.project_var.get()
        if not project or not self.items:
            return

        self._set_status("Building preview…", theme.FG_DIM)
        self.update_idletasks()

        entries = entries_from_items(self.items, stage=self._stage())
        try:
            with TropyWriter(project) as writer:
                preview = writer.preview(entries, self._targets())
        except Exception as exc:
            self._set_status(f"Could not read project: {exc}", theme.ERROR)
            return

        self.preview = preview
        for plan in preview.plans:
            self.tree.insert("", tk.END, tags=(plan.action,), values=(
                plan.entry.label or f"photo {plan.entry.photo_id}",
                plan.target, plan.action, plan.reason,
            ))

        self.summary.configure(text=preview.summary())
        if preview.blockers:
            self._set_status(" • ".join(preview.blockers), theme.ERROR)
        elif not preview.insertable:
            self._set_status("Nothing new to write — everything is already in Tropy.",
                             theme.FG_DIM)
        else:
            self._set_status(
                f"{len(preview.insertable)} row(s) will be created. "
                f"The project is only modified when you press Write.",
                theme.FG_SOFT)
            self.write_btn.configure(state=tk.NORMAL)

    def _set_status(self, text: str, colour: str):
        self.status.configure(text=text, foreground=colour)

    # ----------------------------------------------------------------- write
    def _write(self):
        if self.preview is None or not self.preview.insertable:
            return
        n = len(self.preview.insertable)
        targets = ", ".join(self._targets())
        if not messagebox.askyesno(
            "Write to Tropy",
            f"Create {n} row(s) in {targets} in\n{self.project_var.get()}?\n\n"
            f"{'A backup will be taken first.' if self.var_backup.get() else 'NO BACKUP will be taken.'}",
            parent=self,
        ):
            return

        self.write_btn.configure(state=tk.DISABLED)
        self._set_status("Writing…", theme.FG_DIM)
        self.update_idletasks()

        try:
            with TropyWriter(self.project_var.get()) as writer:
                report = writer.write(self.preview,
                                      make_backup=self.var_backup.get())
        except Exception as exc:
            self._set_status(f"Write failed: {exc}", theme.ERROR)
            return

        self.written += report.written
        if report.errors:
            self._set_status("Write failed and was rolled back: "
                             + "; ".join(report.errors), theme.ERROR)
            messagebox.showerror("Write failed",
                                 "\n".join(report.errors), parent=self)
            return

        note = f"Wrote {report.written} row(s)."
        if report.backup:
            note += f"  Backup: {report.backup.name}"
        self._set_status(note, theme.SUCCESS)
        messagebox.showinfo("Written", note, parent=self)
        self._refresh()

    def _close(self):
        self.grab_release()
        self.destroy()
