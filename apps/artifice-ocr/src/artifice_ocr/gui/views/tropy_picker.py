"""Modal picker for pulling documents out of a Tropy project into the queue.

The project is opened read-only. Nothing in this dialog can modify a Tropy
archive — the only outputs are queue items and a manifest in the output folder.
"""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ...tropy import TropyProject, pages_to_job_items, recent_projects
from .. import theme

ALL_ITEMS = "__all__"


class TropyPicker(tk.Toplevel):
    """Returns the chosen pages via ``self.result`` (a list of JobItem)."""

    def __init__(self, master, *, output_dir: str):
        super().__init__(master)
        self.title("Add from Tropy")
        self.geometry("1000x620")
        self.minsize(860, 520)
        self.configure(bg=theme.BG)
        self.transient(master)

        self.output_dir = output_dir
        self.result: list = []
        self.project: TropyProject | None = None
        self._sources: dict[str, tuple[str, object]] = {}
        self._items: dict[str, object] = {}
        self._pages: list = []

        self._build()
        self._load_recent()

        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    # ---------------------------------------------------------------- layout
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=14, pady=(12, 0))

        ttk.Label(top, text="Tropy project:", font=theme.FONT_BOLD).pack(side=tk.LEFT)
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(top, textvariable=self.project_var,
                                          state="readonly", width=54)
        self.project_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 6))
        self.project_combo.bind("<<ComboboxSelected>>", lambda _: self._open_project())

        ttk.Button(top, text="Browse…", command=self._browse).pack(side=tk.LEFT)

        self.project_label = ttk.Label(self, text="", style="Dim.TLabel")
        self.project_label.pack(anchor=tk.W, padx=14, pady=(6, 0))

        panes = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=14, pady=10)

        # Sources: lists and tags -----------------------------------------
        left = ttk.Frame(panes)
        panes.add(left, weight=1)
        ttk.Label(left, text="Lists & tags", style="Head.TLabel").pack(
            anchor=tk.W, pady=(0, 4))

        self.source_tree = ttk.Treeview(left, columns=("n",), show="tree headings",
                                        selectmode="browse")
        self.source_tree.heading("#0", text="SOURCE", anchor=tk.W)
        self.source_tree.heading("n", text="ITEMS", anchor=tk.CENTER)
        self.source_tree.column("#0", width=250)
        self.source_tree.column("n", width=60, anchor=tk.CENTER, stretch=False)
        src_scroll = ttk.Scrollbar(left, orient=tk.VERTICAL,
                                   command=self.source_tree.yview)
        self.source_tree.configure(yscrollcommand=src_scroll.set)
        self.source_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        src_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.source_tree.bind("<<TreeviewSelect>>", lambda _: self._on_source())

        # Items ------------------------------------------------------------
        right = ttk.Frame(panes)
        panes.add(right, weight=2)
        head = ttk.Frame(right)
        head.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(head, text="Items", style="Head.TLabel").pack(side=tk.LEFT)
        ttk.Label(head, text="select one or more — none selected means all",
                  style="Dim.TLabel").pack(side=tk.RIGHT)

        self.item_tree = ttk.Treeview(right, columns=("pages",), show="headings",
                                      selectmode="extended")
        self.item_tree.heading("#1", text="Pages")
        self.item_tree.configure(columns=("title", "pages"))
        self.item_tree.heading("title", text="TITLE", anchor=tk.W)
        self.item_tree.heading("pages", text="PAGES", anchor=tk.CENTER)
        self.item_tree.column("title", width=380, anchor=tk.W)
        self.item_tree.column("pages", width=70, anchor=tk.CENTER, stretch=False)
        item_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL,
                                    command=self.item_tree.yview)
        self.item_tree.configure(yscrollcommand=item_scroll.set)
        self.item_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        item_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.item_tree.bind("<<TreeviewSelect>>", lambda _: self._update_summary())

        # Footer -----------------------------------------------------------
        footer = ttk.Frame(self)
        footer.pack(fill=tk.X, padx=14, pady=(0, 14))

        self.summary = ttk.Label(footer, text="No project open", style="Dim.TLabel")
        self.summary.pack(side=tk.LEFT)

        self.add_btn = ttk.Button(footer, text="Add to Queue", style="Accent.TButton",
                                  command=self._add, state=tk.DISABLED)
        self.add_btn.pack(side=tk.RIGHT)
        ttk.Button(footer, text="Cancel", command=self._cancel).pack(
            side=tk.RIGHT, padx=(0, 8))

    # ------------------------------------------------------------- projects
    def _load_recent(self):
        self._recent = recent_projects()
        seen, unique = set(), []
        for p in self._recent:
            if str(p) not in seen:
                seen.add(str(p))
                unique.append(p)
        self._recent = unique
        self.project_combo.configure(values=[str(p) for p in self._recent])
        if self._recent:
            self.project_var.set(str(self._recent[0]))
            self._open_project()
        else:
            self.project_label.configure(
                text="No recent Tropy projects found — use Browse.")

    def _browse(self):
        chosen = filedialog.askdirectory(
            title="Select a .tropy project folder", parent=self)
        if not chosen:
            return
        self.project_var.set(chosen)
        values = list(self.project_combo.cget("values"))
        if chosen not in values:
            self.project_combo.configure(values=[chosen] + values)
        self._open_project()

    def _open_project(self):
        path = self.project_var.get()
        if not path:
            return
        if self.project is not None:
            self.project.close()
            self.project = None

        try:
            self.project = TropyProject(path)
        except Exception as exc:
            messagebox.showerror("Could not open project", str(exc), parent=self)
            self.project_label.configure(text=f"Failed to open {path}")
            return

        self.project_label.configure(
            text=f"{self.project.name}  ·  read-only  ·  {self.project.db_path}")
        self._populate_sources()

    # -------------------------------------------------------------- sources
    def _populate_sources(self):
        self.source_tree.delete(*self.source_tree.get_children())
        self._sources.clear()

        all_items = self.project.items()
        node = self.source_tree.insert("", tk.END, text="All items",
                                       values=(len(all_items),))
        self._sources[node] = (ALL_ITEMS, None)

        parents: dict[int, str] = {}
        for lst in self.project.lists():
            parent_node = parents.get(lst.parent_id, "")
            node = self.source_tree.insert(parent_node, tk.END, text=lst.name,
                                           values=(lst.item_count,), open=True)
            parents[lst.list_id] = node
            self._sources[node] = ("list", lst.list_id)

        tags = [t for t in self.project.tags() if t[1]]
        if tags:
            tag_root = self.source_tree.insert("", tk.END, text="Tags", open=True,
                                               values=("",))
            for name, count in tags:
                node = self.source_tree.insert(tag_root, tk.END, text=name,
                                               values=(count,))
                self._sources[node] = ("tag", name)

        children = self.source_tree.get_children()
        if children:
            self.source_tree.selection_set(children[0])

    def _on_source(self):
        selection = self.source_tree.selection()
        if not selection or self.project is None:
            return
        source = self._sources.get(selection[0])
        if source is None:  # a grouping row such as "Tags"
            return

        kind, value = source
        if kind == ALL_ITEMS:
            item_ids = None
        elif kind == "list":
            item_ids = self.project.item_ids_in_list(value)
        else:
            item_ids = self.project.item_ids_with_tag(value)

        self._current_ids = item_ids
        items = self.project.items(item_ids)

        self.item_tree.delete(*self.item_tree.get_children())
        self._items.clear()
        for item in items:
            node = self.item_tree.insert("", tk.END,
                                         values=(item.title, item.photo_count))
            self._items[node] = item
        self._update_summary()

    def _selected_item_ids(self) -> list[int] | None:
        chosen = [self._items[n] for n in self.item_tree.selection() if n in self._items]
        if chosen:
            return [i.item_id for i in chosen]
        return getattr(self, "_current_ids", None)

    def _update_summary(self):
        if self.project is None:
            return
        chosen = [self._items[n] for n in self.item_tree.selection() if n in self._items]
        if chosen:
            n_items, n_pages = len(chosen), sum(i.photo_count for i in chosen)
        else:
            all_shown = list(self._items.values())
            n_items, n_pages = len(all_shown), sum(i.photo_count for i in all_shown)

        self.summary.configure(text=f"{n_items} item(s)  ·  {n_pages} page(s) to queue")
        self.add_btn.configure(state=tk.NORMAL if n_pages else tk.DISABLED)

    # ----------------------------------------------------------------- add
    def _add(self):
        if self.project is None:
            return
        item_ids = self._selected_item_ids()
        self.add_btn.configure(state=tk.DISABLED)
        self.summary.configure(text="Resolving pages…")
        self.update_idletasks()

        try:
            pages = self.project.pages(item_ids)
        except Exception as exc:
            messagebox.showerror("Could not read pages", str(exc), parent=self)
            self.add_btn.configure(state=tk.NORMAL)
            return

        if not pages:
            messagebox.showinfo("Nothing to add", "That selection has no pages.",
                                parent=self)
            self.add_btn.configure(state=tk.NORMAL)
            return

        missing = self.project.missing_assets(pages)
        if missing:
            proceed = messagebox.askyesno(
                "Missing files",
                f"{len(missing)} of {len(pages)} page(s) have no file on disk "
                f"(for example {missing[0].filename}).\n\n"
                "This usually means the originals are not downloaded locally. "
                "Add the rest anyway?",
                parent=self,
            )
            if not proceed:
                self.add_btn.configure(state=tk.NORMAL)
                return
            skip = {id(p) for p in missing}
            pages = [p for p in pages if id(p) not in skip]

        try:
            from ...tropy import write_manifest
            write_manifest(self.output_dir, self.project, pages)
        except Exception as exc:
            # A missing manifest is not worth aborting the run over.
            messagebox.showwarning(
                "Manifest not written",
                f"Could not write the Tropy manifest: {exc}", parent=self)

        self.result = pages_to_job_items(pages, project_path=self.project.db_path)
        self._close()

    def _cancel(self):
        self.result = []
        self._close()

    def _close(self):
        if self.project is not None:
            self.project.close()
            self.project = None
        self.grab_release()
        self.destroy()
