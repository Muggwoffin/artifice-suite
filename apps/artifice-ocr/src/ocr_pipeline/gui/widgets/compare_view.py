"""Side-by-side Raw / Cleaned / Translated comparison with diff highlighting."""

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..._diff import confidence_tier
from ..._diff import diff_ranges as _diff_ranges
from ..._diff import marker_ranges as _marker_ranges
from .. import theme
from .image_pane import ImagePane

PANES = [
    ("raw", "Raw OCR"),
    ("cleaned", "Cleaned"),
    ("translated", "Translated"),
]


class ComparePane(ttk.Frame):
    """One titled text pane.

    `editable=True` turns this into a manual-correction surface (History's
    raw pane only): the Text widget stays enabled, a "Save correction"
    button tracks a dirty flag against the last-loaded content, and Ctrl+S
    saves. Diff-highlight ranges are never applied to an editable pane —
    once a user starts correcting text, ranges computed against the
    pre-edit version would be stale.
    """

    def __init__(
        self, master, title: str, *,
        editable: bool = False,
        on_save: "Callable[[str], None] | None" = None,
    ):
        super().__init__(master, style="Card.TFrame")
        self.editable = editable
        self._on_save = on_save
        self._loaded_text = ""

        header = ttk.Frame(self, style="Card.TFrame")
        header.pack(fill=tk.X, padx=10, pady=(8, 2))
        ttk.Label(header, text=title.upper(), style="Card.TLabel",
                  font=theme.FONT_LABEL, foreground=theme.FG_DIM).pack(side=tk.LEFT)

        self.save_btn = None
        if editable:
            self.save_btn = ttk.Button(header, text="Save correction",
                                       style="Accent.TButton", state=tk.DISABLED,
                                       command=self._save)
            self.save_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.meta = ttk.Label(header, text="", style="Card.TLabel",
                              font=theme.FONT_LABEL, foreground=theme.FG_DIM)
        self.meta.pack(side=tk.RIGHT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=(4, 0))

        # Serif for the document text: this is a reading surface, and it
        # matches the body face used on the site.
        self.text = tk.Text(
            self, bg=theme.FRAME_BG, fg=theme.FG, font=theme.FONT_BODY,
            relief=tk.FLAT, bd=0, wrap=tk.WORD, padx=12, pady=10,
            insertbackground=theme.FG, state=(tk.NORMAL if editable else tk.DISABLED),
            spacing1=1, spacing3=3,
            selectbackground=theme.SEL_BG, selectforeground=theme.FG,
        )
        self.scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=self.scroll.set)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=(0, 8))
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=(0, 8), padx=(0, 6))

        self.text.tag_configure("insert_", background=theme.DIFF_INSERT)
        self.text.tag_configure("delete_", background=theme.DIFF_DELETE)
        self.text.tag_configure("replace_", background=theme.DIFF_REPLACE)
        self.text.tag_configure("marker", background=theme.MARKER_BG,
                                foreground=theme.FG)
        self.text.tag_configure("empty", foreground=theme.FG_DIM,
                                font=theme.FONT_SMALL)

        if editable:
            self.text.bind("<<Modified>>", self._on_modified)
            self.text.bind("<Control-s>", self._save_shortcut)
            self.text.bind("<Control-S>", self._save_shortcut)

    def set_text(self, content: str, placeholder: str = "(not run)") -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        if content:
            self.text.insert("1.0", content)
            self.meta.configure(text=f"{len(content):,} chars")
        elif self.editable:
            self.meta.configure(text="")
        else:
            self.text.insert("1.0", placeholder, "empty")
            self.meta.configure(text="")

        if self.editable:
            self._loaded_text = content or ""
            self.text.edit_modified(False)
            if self.save_btn is not None:
                self.save_btn.configure(state=tk.DISABLED)
        else:
            self.text.configure(state=tk.DISABLED)

    def apply_ranges(self, ranges: list[tuple[int, int, str]]) -> None:
        """Tag character ranges (start, end, tag) on the current content."""
        was_disabled = str(self.text["state"]) == tk.DISABLED
        if was_disabled:
            self.text.configure(state=tk.NORMAL)
        for start, end, tag in ranges:
            self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")
        if was_disabled:
            self.text.configure(state=tk.DISABLED)

    # ------------------------------------------------------------- editing
    def _on_modified(self, _event=None) -> None:
        if not self.text.edit_modified():
            return
        current = self.text.get("1.0", "end-1c")
        dirty = current != self._loaded_text
        if self.save_btn is not None:
            self.save_btn.configure(state=(tk.NORMAL if dirty else tk.DISABLED))
        self.text.edit_modified(False)

    def _save(self) -> None:
        text = self.text.get("1.0", "end-1c")
        if self._on_save is not None:
            self._on_save(text)
        self._loaded_text = text
        if self.save_btn is not None:
            self.save_btn.configure(state=tk.DISABLED)

    def _save_shortcut(self, _event=None) -> str:
        if self.save_btn is not None and str(self.save_btn["state"]) != tk.DISABLED:
            self._save()
        return "break"


class CompareView(ttk.Frame):
    """Three synced panes plus a confidence readout.

    `with_image=True` mounts a source-scan `ImagePane` to the left of the
    text panes. `editable_raw=True` makes the Raw OCR pane a manual
    correction surface, calling `on_save_raw(text)` when the user saves —
    both default off, so the plain Preview tab's `CompareView` (used for the
    live queue) is unaffected; only History opts in.
    """

    def __init__(
        self, master, *,
        with_image: bool = False,
        editable_raw: bool = False,
        on_save_raw: "Callable[[str], None] | None" = None,
    ):
        super().__init__(master)
        self.editable_raw = editable_raw
        self.on_save_raw = on_save_raw

        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=12, pady=(10, 0))
        self.title_label = ttk.Label(bar, text="No document selected", style="Head.TLabel")
        self.title_label.pack(side=tk.LEFT)

        self.conf_label = ttk.Label(bar, text="", style="Dim.TLabel")
        self.conf_label.pack(side=tk.RIGHT)

        self.diff_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar, text="Highlight cleanup changes", variable=self.diff_enabled,
            command=self._rerender,
        ).pack(side=tk.RIGHT, padx=(0, 16))

        self.sync_scroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar, text="Sync scroll", variable=self.sync_scroll,
        ).pack(side=tk.RIGHT, padx=(0, 16))

        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        self._pane_weights: list[int] = []

        self.image: ImagePane | None = None
        if with_image:
            self.image = ImagePane(paned)
            paned.add(self.image, weight=2)
            self._pane_weights.append(2)

        self.panes: dict[str, ComparePane] = {}
        for key, title in PANES:
            editable = editable_raw and key == "raw"
            pane = ComparePane(
                paned, title, editable=editable,
                on_save=self._handle_save_raw if editable else None,
            )
            paned.add(pane, weight=1)
            self.panes[key] = pane
            self._pane_weights.append(1)

        if self.image is not None:
            # ttk.PanedWindow ignores `weight` for the *initial* layout — every
            # sash starts at 0 regardless, collapsing every pane but the last
            # until the window is manually resized. Set real starting
            # positions ourselves, once, the first time the paned window
            # actually has a size to measure.
            self._sash_positions_set = False
            paned.bind("<Configure>", self._set_initial_sash_positions, add="+")

        self._wire_sync_scroll()
        self._current: dict[str, str] = {}

    def _set_initial_sash_positions(self, event=None) -> None:
        if self._sash_positions_set or self.image is None:
            return
        paned = self.image.master
        width = paned.winfo_width()
        if width <= 1:
            return
        total_weight = sum(self._pane_weights)
        cumulative = 0
        for i, weight in enumerate(self._pane_weights[:-1]):
            cumulative += weight
            paned.sashpos(i, int(width * cumulative / total_weight))
        self._sash_positions_set = True

    # ---------------------------------------------------------- sync scroll
    def _wire_sync_scroll(self):
        for key, pane in self.panes.items():
            pane.text.configure(
                yscrollcommand=lambda first, last, k=key: self._on_scroll(k, first, last)
            )
            pane.scroll.configure(command=lambda *a, k=key: self._on_drag(k, *a))
            pane.text.bind("<MouseWheel>", lambda e, k=key: self._on_wheel(k, e))

    def _on_scroll(self, key: str, first, last):
        self.panes[key].scroll.set(first, last)

    def _on_drag(self, key: str, *args):
        targets = self.panes.values() if self.sync_scroll.get() else [self.panes[key]]
        for pane in targets:
            pane.text.yview(*args)

    def _on_wheel(self, key: str, event):
        delta = -1 * (event.delta // 120)
        targets = self.panes.values() if self.sync_scroll.get() else [self.panes[key]]
        for pane in targets:
            pane.text.yview_scroll(delta, "units")
        return "break"

    # -------------------------------------------------------------- content
    def show(
        self,
        *,
        title: str,
        raw: str = "",
        cleaned: str = "",
        translated: str = "",
        confidence: int | None = None,
        language: str = "",
        image_path: str | None = None,
        image_page: int | None = None,
    ) -> None:
        self._current = {"raw": raw or "", "cleaned": cleaned or "",
                         "translated": translated or "", "title": title,
                         "language": language}
        self.title_label.configure(text=title)

        bits = []
        if language:
            bits.append(f"source: {language}")
        if confidence is not None:
            bits.append(f"confidence {confidence}/100")
        self.conf_label.configure(
            text="   ".join(bits),
            foreground=_conf_color(confidence),
        )
        self._rerender()

        if self.image is not None:
            if image_path:
                self.image.load(image_path, image_page)
            else:
                self.image.clear()

    def clear(self) -> None:
        self._current = {}
        self.title_label.configure(text="No document selected")
        self.conf_label.configure(text="")
        for pane in self.panes.values():
            pane.set_text("")
        if self.image is not None:
            self.image.clear()

    def _handle_save_raw(self, text: str) -> None:
        """Wired to the raw pane's Save button/Ctrl+S when `editable_raw`."""
        self._current["raw"] = text
        if self.on_save_raw is not None:
            self.on_save_raw(text)
        self._rerender()

    def _rerender(self):
        if not self._current:
            return
        raw = self._current.get("raw", "")
        cleaned = self._current.get("cleaned", "")
        translated = self._current.get("translated", "")

        raw_pane = self.panes["raw"]
        # Skip re-touching an editable raw pane whose content already
        # matches — e.g. right after a save — so the cursor/scroll position
        # a user was just working at isn't reset out from under them.
        if not (raw_pane.editable and raw_pane.text.get("1.0", "end-1c") == raw):
            raw_pane.set_text(raw)
        self.panes["cleaned"].set_text(cleaned)
        self.panes["translated"].set_text(translated)

        if self.diff_enabled.get() and raw and cleaned:
            raw_ranges, clean_ranges = _diff_ranges(raw, cleaned)
            if not raw_pane.editable:
                raw_pane.apply_ranges(raw_ranges)
            self.panes["cleaned"].apply_ranges(clean_ranges)

        for key in ("cleaned", "translated"):
            content = self._current.get(key, "")
            if content:
                self.panes[key].apply_ranges(_marker_ranges(content))


def _conf_color(confidence: int | None) -> str:
    return {
        "none": theme.FG_DIM, "low": theme.ERROR,
        "medium": theme.WARNING, "high": theme.SUCCESS,
    }[confidence_tier(confidence)]
