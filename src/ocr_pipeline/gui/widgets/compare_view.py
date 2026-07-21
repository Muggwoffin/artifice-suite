"""Side-by-side Raw / Cleaned / Translated comparison with diff highlighting."""

import difflib
import re
import tkinter as tk
from tkinter import ttk

from ..._confidence import _UNCERTAINTY_MARKERS
from .. import theme

PANES = [
    ("raw", "Raw OCR"),
    ("cleaned", "Cleaned"),
    ("translated", "Translated"),
]


class ComparePane(ttk.Frame):
    """One titled text pane."""

    def __init__(self, master, title: str):
        super().__init__(master, style="Card.TFrame")

        header = ttk.Frame(self, style="Card.TFrame")
        header.pack(fill=tk.X, padx=10, pady=(8, 2))
        ttk.Label(header, text=title.upper(), style="Card.TLabel",
                  font=theme.FONT_LABEL, foreground=theme.FG_DIM).pack(side=tk.LEFT)
        self.meta = ttk.Label(header, text="", style="Card.TLabel",
                              font=theme.FONT_LABEL, foreground=theme.FG_DIM)
        self.meta.pack(side=tk.RIGHT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=(4, 0))

        # Serif for the document text: this is a reading surface, and it
        # matches the body face used on the site.
        self.text = tk.Text(
            self, bg=theme.FRAME_BG, fg=theme.FG, font=theme.FONT_BODY,
            relief=tk.FLAT, bd=0, wrap=tk.WORD, padx=12, pady=10,
            insertbackground=theme.FG, state=tk.DISABLED,
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

    def set_text(self, content: str, placeholder: str = "(not run)") -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        if content:
            self.text.insert("1.0", content)
            self.meta.configure(text=f"{len(content):,} chars")
        else:
            self.text.insert("1.0", placeholder, "empty")
            self.meta.configure(text="")
        self.text.configure(state=tk.DISABLED)

    def apply_ranges(self, ranges: list[tuple[int, int, str]]) -> None:
        """Tag character ranges (start, end, tag) on the current content."""
        self.text.configure(state=tk.NORMAL)
        for start, end, tag in ranges:
            self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")
        self.text.configure(state=tk.DISABLED)


class CompareView(ttk.Frame):
    """Three synced panes plus a confidence readout."""

    def __init__(self, master):
        super().__init__(master)

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

        self.panes: dict[str, ComparePane] = {}
        for key, title in PANES:
            pane = ComparePane(paned, title)
            paned.add(pane, weight=1)
            self.panes[key] = pane

        self._wire_sync_scroll()
        self._current: dict[str, str] = {}

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

    def clear(self) -> None:
        self._current = {}
        self.title_label.configure(text="No document selected")
        self.conf_label.configure(text="")
        for pane in self.panes.values():
            pane.set_text("")

    def _rerender(self):
        if not self._current:
            return
        raw = self._current.get("raw", "")
        cleaned = self._current.get("cleaned", "")
        translated = self._current.get("translated", "")

        self.panes["raw"].set_text(raw)
        self.panes["cleaned"].set_text(cleaned)
        self.panes["translated"].set_text(translated)

        if self.diff_enabled.get() and raw and cleaned:
            raw_ranges, clean_ranges = _diff_ranges(raw, cleaned)
            self.panes["raw"].apply_ranges(raw_ranges)
            self.panes["cleaned"].apply_ranges(clean_ranges)

        for key in ("cleaned", "translated"):
            content = self._current.get(key, "")
            if content:
                self.panes[key].apply_ranges(_marker_ranges(content))


def _conf_color(confidence: int | None) -> str:
    if confidence is None:
        return theme.FG_DIM
    if confidence >= 80:
        return theme.SUCCESS
    if confidence >= 55:
        return theme.WARNING
    return theme.ERROR


def _diff_ranges(raw: str, cleaned: str) -> tuple[list, list]:
    """Character ranges that differ between raw and cleaned text.

    Diffing on words rather than characters keeps the highlight readable —
    character-level opcodes on OCR text produce confetti.
    """
    raw_words = re.findall(r"\S+\s*", raw)
    clean_words = re.findall(r"\S+\s*", cleaned)

    raw_offsets, pos = [], 0
    for w in raw_words:
        raw_offsets.append(pos)
        pos += len(w)
    clean_offsets, pos = [], 0
    for w in clean_words:
        clean_offsets.append(pos)
        pos += len(w)

    matcher = difflib.SequenceMatcher(
        None, [w.strip() for w in raw_words], [w.strip() for w in clean_words],
        autojunk=False,
    )

    raw_ranges, clean_ranges = [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        tag = f"{op}_"
        if op in ("delete", "replace") and i1 < len(raw_offsets):
            start = raw_offsets[i1]
            end = raw_offsets[i2 - 1] + len(raw_words[i2 - 1]) if i2 > i1 else start
            raw_ranges.append((start, end, "delete_" if op == "delete" else tag))
        if op in ("insert", "replace") and j1 < len(clean_offsets):
            start = clean_offsets[j1]
            end = clean_offsets[j2 - 1] + len(clean_words[j2 - 1]) if j2 > j1 else start
            clean_ranges.append((start, end, "insert_" if op == "insert" else tag))

    return raw_ranges, clean_ranges


def _marker_ranges(text: str) -> list[tuple[int, int, str]]:
    """Highlight the uncertainty markers the confidence scorer looks for."""
    ranges = []
    lowered = text.lower()
    for marker in _UNCERTAINTY_MARKERS:
        if marker == "...":  # too common in ordinary prose to be worth flagging
            continue
        start = 0
        while True:
            idx = lowered.find(marker, start)
            if idx == -1:
                break
            ranges.append((idx, idx + len(marker), "marker"))
            start = idx + len(marker)
    return ranges
