"""The batch queue: a Treeview with live per-stage status per file."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ...jobs import STAGES, JobItem, State
from .. import theme

COLUMNS = ("name", "ocr", "cleanup", "translate", "conf", "time", "status")

HEADINGS = {
    "name": "File",
    "ocr": "OCR",
    "cleanup": "Cleanup",
    "translate": "Translate",
    "conf": "Conf",
    "time": "Time",
    "status": "Status",
}

WIDTHS = {
    "name": 300, "ocr": 70, "cleanup": 80, "translate": 85,
    "conf": 60, "time": 70, "status": 110,
}


class QueueTable(ttk.Frame):
    """Displays :class:`JobItem` rows and keeps them in sync as stages run.

    Rows are addressed by ``id(item)`` so the table never has to care about
    duplicate filenames from different folders.
    """

    def __init__(self, master, *, on_selection_change=None, on_context_action=None):
        super().__init__(master)
        self.on_selection_change = on_selection_change
        self.on_context_action = on_context_action
        self.items: list[JobItem] = []
        self._rows: dict[str, JobItem] = {}

        self.tree = ttk.Treeview(
            self, columns=COLUMNS, show="headings", selectmode="extended",
        )
        for col in COLUMNS:
            anchor = tk.W if col in ("name", "status") else tk.CENTER
            # Heading and cell share an anchor, so columns read as columns.
            self.tree.heading(col, text=HEADINGS[col].upper(), anchor=anchor)
            self.tree.column(col, width=WIDTHS[col], anchor=anchor,
                             stretch=(col == "name"))

        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for state, color in theme.STATE_COLORS.items():
            self.tree.tag_configure(state, foreground=color)
        self.tree.tag_configure("running", background=theme.FRAME_BG)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-3>", self._on_right_click)

        self._menu = tk.Menu(
            self, tearoff=0, bg=theme.FRAME_BG, fg=theme.FG,
            activebackground=theme.ACCENT, activeforeground=theme.BG,
            font=theme.FONT, borderwidth=0,
        )
        for label, action in [
            ("Retry", "retry"),
            ("Skip", "skip"),
            (None, None),
            ("Open output folder", "open_output"),
            ("Remove from queue", "remove"),
        ]:
            if label is None:
                self._menu.add_separator()
            else:
                self._menu.add_command(
                    label=label,
                    command=lambda a=action: self._fire_action(a),
                )

    # ------------------------------------------------------------- contents
    def set_items(self, items: list[JobItem]) -> None:
        self.items = items
        self.tree.delete(*self.tree.get_children())
        self._rows.clear()
        for item in items:
            row = str(id(item))
            self._rows[row] = item
            self.tree.insert("", tk.END, iid=row, values=self._values(item))
            self.tree.item(row, tags=(item.state.value,))

    def add_paths(self, paths: list[str]) -> int:
        """Append new files, ignoring duplicates. Returns the number added."""
        return self.add_items([JobItem(path=p) for p in paths])

    def add_items(self, items: list[JobItem]) -> int:
        """Append pre-built items, ignoring duplicates.

        Identity is the output stem, not the path: every page of a Tropy PDF
        shares one path but is a distinct unit of work.
        """
        known = {(i.path, i.stem) for i in self.items}
        added = 0
        for item in items:
            key = (item.path, item.stem)
            if key in known:
                continue
            self.items.append(item)
            known.add(key)
            row = str(id(item))
            self._rows[row] = item
            self.tree.insert("", tk.END, iid=row, values=self._values(item))
            self.tree.item(row, tags=(item.state.value,))
            added += 1
        return added

    def remove_selected(self) -> None:
        for item in self.selected_items():
            row = str(id(item))
            self.tree.delete(row)
            self._rows.pop(row, None)
            self.items.remove(item)

    def clear(self) -> None:
        self.set_items([])

    # ------------------------------------------------------------ selection
    def selected_items(self) -> list[JobItem]:
        return [self._rows[r] for r in self.tree.selection() if r in self._rows]

    def _on_select(self, _event=None):
        if self.on_selection_change:
            selected = self.selected_items()
            self.on_selection_change(selected[0] if selected else None)

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            self._menu.tk_popup(event.x_root, event.y_root)

    def _fire_action(self, action: str):
        if self.on_context_action:
            self.on_context_action(action, self.selected_items())

    # --------------------------------------------------------------- update
    def refresh(self, item: JobItem) -> None:
        """Re-render one row in place."""
        row = str(id(item))
        if not self.tree.exists(row):
            return
        self.tree.item(row, values=self._values(item), tags=(item.state.value,))

    def refresh_all(self) -> None:
        for item in self.items:
            self.refresh(item)

    def scroll_to(self, item: JobItem) -> None:
        row = str(id(item))
        if self.tree.exists(row):
            self.tree.see(row)

    # -------------------------------------------------------------- helpers
    def _values(self, item: JobItem) -> tuple:
        cells = [item.name]
        for stage in STAGES:
            cells.append(self._stage_cell(item, stage))
        cells.append("—" if item.confidence is None else f"{item.confidence}")
        cells.append(f"{item.elapsed:.1f}s" if item.elapsed else "—")
        cells.append(self._status_text(item))
        return tuple(cells)

    def _stage_cell(self, item: JobItem, stage: str) -> str:
        status = item.stages[stage]
        glyph = theme.STATE_GLYPHS.get(status.state.value, "·")
        if status.state is State.DONE and status.chars:
            return f"{glyph} {status.chars}"
        return glyph

    def _status_text(self, item: JobItem) -> str:
        if item.state is State.FAILED:
            return f"failed ({item.error.split(':')[0]})" if item.error else "failed"
        running = [s for s in STAGES if item.stages[s].state is State.RUNNING]
        if running:
            from ...jobs import STAGE_LABELS
            return f"{STAGE_LABELS[running[0]]}…"
        return item.state.value
