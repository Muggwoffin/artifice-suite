"""History tab: past runs, their items, and a full comparison of each result."""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .. import theme
from ..widgets.compare_view import CompareView


class HistoryView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.history = app.history
        self._runs: dict[str, int] = {}
        self._items: dict[str, int] = {}
        self._current_item_id: int | None = None

        self._build_header()
        self._build_body()
        self.refresh()

    # ---------------------------------------------------------------- layout
    def _build_header(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=16, pady=(12, 0))
        ttk.Label(top, text="History", style="Title.TLabel").pack(side=tk.LEFT)

        ttk.Button(top, text="Refresh", command=self.refresh).pack(side=tk.RIGHT)
        ttk.Button(top, text="Delete Run", style="Danger.TButton",
                   command=self._delete_run).pack(side=tk.RIGHT, padx=(0, 8))

        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var, width=24)
        entry.pack(side=tk.RIGHT, padx=(0, 8))
        entry.bind("<Return>", lambda _: self._search())
        ttk.Label(top, text="Find file:", style="Dim.TLabel").pack(
            side=tk.RIGHT, padx=(0, 6))

    def _build_body(self):
        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        lists = ttk.PanedWindow(paned, orient=tk.HORIZONTAL)
        paned.add(lists, weight=1)

        # Runs -----------------------------------------------------------
        run_frame = ttk.Frame(lists)
        lists.add(run_frame, weight=1)
        ttk.Label(run_frame, text="Runs", style="Head.TLabel").pack(
            anchor=tk.W, pady=(0, 4))

        run_cols = ("started", "stages", "files", "failed", "elapsed")
        self.run_tree = ttk.Treeview(run_frame, columns=run_cols,
                                     show="headings", selectmode="browse")
        for col, head, width in [
            ("started", "Started", 140), ("stages", "Stages", 150),
            ("files", "Files", 55), ("failed", "Failed", 55),
            ("elapsed", "Elapsed", 75),
        ]:
            self.run_tree.heading(col, text=head.upper(), anchor=(tk.W if col in ("started", "stages") else tk.CENTER))
            self.run_tree.column(col, width=width,
                                 anchor=tk.W if col in ("started", "stages") else tk.CENTER)
        run_scroll = ttk.Scrollbar(run_frame, orient=tk.VERTICAL,
                                   command=self.run_tree.yview)
        self.run_tree.configure(yscrollcommand=run_scroll.set)
        self.run_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        run_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.run_tree.bind("<<TreeviewSelect>>", self._on_run_selected)
        self.run_tree.tag_configure("failed", foreground=theme.ERROR)

        # Items ----------------------------------------------------------
        item_frame = ttk.Frame(lists)
        lists.add(item_frame, weight=1)
        ttk.Label(item_frame, text="Documents", style="Head.TLabel").pack(
            anchor=tk.W, pady=(0, 4))

        item_cols = ("name", "state", "lang", "conf")
        self.item_tree = ttk.Treeview(item_frame, columns=item_cols,
                                      show="headings", selectmode="browse")
        for col, head, width in [
            ("name", "File", 240), ("state", "State", 80),
            ("lang", "Language", 90), ("conf", "Conf", 55),
        ]:
            self.item_tree.heading(col, text=head.upper(), anchor=(tk.W if col == "name" else tk.CENTER))
            self.item_tree.column(col, width=width,
                                  anchor=tk.W if col == "name" else tk.CENTER)
        item_scroll = ttk.Scrollbar(item_frame, orient=tk.VERTICAL,
                                    command=self.item_tree.yview)
        self.item_tree.configure(yscrollcommand=item_scroll.set)
        self.item_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        item_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.item_tree.bind("<<TreeviewSelect>>", self._on_item_selected)
        for state, color in theme.STATE_COLORS.items():
            self.item_tree.tag_configure(state, foreground=color)

        # Comparison -----------------------------------------------------
        self.compare = CompareView(
            paned, with_image=True, editable_raw=True,
            on_save_raw=self._save_raw_correction,
        )
        paned.add(self.compare, weight=2)

    # --------------------------------------------------------------- loading
    def refresh(self):
        self.run_tree.delete(*self.run_tree.get_children())
        self._runs.clear()
        for run in self.history.list_runs():
            row = str(run["run_id"])
            self._runs[row] = run["run_id"]
            started = (run["started"] or "").replace("T", " ")[:16]
            self.run_tree.insert(
                "", tk.END, iid=row,
                values=(started, run["stages"], run["total"],
                        run["failed"], f"{run['elapsed']:.1f}s"),
                tags=("failed",) if run["failed"] else (),
            )
        self.item_tree.delete(*self.item_tree.get_children())
        self._current_item_id = None
        self.compare.clear()

    def _on_run_selected(self, _event=None):
        selection = self.run_tree.selection()
        if not selection:
            return
        self._load_items(self.history.list_items(self._runs[selection[0]]))

    def _search(self):
        term = self.search_var.get().strip()
        if not term:
            self.refresh()
            return
        self._load_items(self.history.search_items(term))

    def _load_items(self, rows):
        self.item_tree.delete(*self.item_tree.get_children())
        self._items.clear()
        for row in rows:
            key = str(row["item_id"])
            self._items[key] = row["item_id"]
            self.item_tree.insert(
                "", tk.END, iid=key,
                values=(
                    row["name"], row["state"], row["language"] or "—",
                    row["confidence"] if row["confidence"] is not None else "—",
                ),
                tags=(row["state"],),
            )
        self._current_item_id = None
        self.compare.clear()

    def _on_item_selected(self, _event=None):
        selection = self.item_tree.selection()
        if not selection:
            return
        item_id = self._items[selection[0]]
        row = self.history.get_item(item_id)
        if row is None:
            return
        self._current_item_id = item_id
        self.compare.show(
            title=f"{row['name']}   —   {Path(row['source_file']).parent}",
            raw=row["raw_text"] or "",
            cleaned=row["cleaned_text"] or "",
            translated=row["translated_text"] or "",
            confidence=row["confidence"],
            language=row["language"] or "",
            image_path=row["source_file"],
            image_page=row["page"],
        )

    def _save_raw_correction(self, text: str) -> None:
        if self._current_item_id is None:
            return
        self.history.update_raw_text(self._current_item_id, text)

    def _delete_run(self):
        selection = self.run_tree.selection()
        if not selection:
            return
        run_id = self._runs[selection[0]]
        if messagebox.askyesno(
            "Delete run",
            f"Delete run #{run_id} and all of its recorded documents?\n"
            "This only removes history — output files are left alone.",
        ):
            self.history.delete_run(run_id)
            self.refresh()
