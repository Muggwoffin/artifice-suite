"""Analytics tab: throughput, confidence distribution and per-model comparison.

Charts are drawn straight onto a tk.Canvas — this deliberately avoids adding
matplotlib for what amounts to three bar charts.
"""

import tkinter as tk
from tkinter import ttk

from .. import theme


class AnalyticsView(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.history = app.history

        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=16, pady=(12, 0))
        ttk.Label(top, text="Analytics", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side=tk.RIGHT)

        self.tiles = ttk.Frame(self)
        self.tiles.pack(fill=tk.X, padx=16, pady=(10, 0))

        self.canvas = tk.Canvas(self, bg=theme.BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)
        self.canvas.bind("<Configure>", lambda _: self._draw())

        self._stats: dict = {}
        self.refresh()

    # ---------------------------------------------------------------- update
    def refresh(self):
        self._stats = self.history.stats()
        self._build_tiles()
        self._draw()

    def _build_tiles(self):
        for child in self.tiles.winfo_children():
            child.destroy()

        s = self._stats
        confidences = s.get("confidences") or []
        avg_conf = sum(confidences) / len(confidences) if confidences else None
        files = s.get("files") or 0
        elapsed = s.get("elapsed") or 0

        tiles = [
            ("Runs", f"{s.get('runs', 0):,}", theme.ACCENT),
            ("Documents", f"{files:,}", theme.GOLD),
            ("Failures", f"{s.get('failed', 0):,}",
             theme.ERROR if s.get("failed") else theme.SUCCESS),
            ("Avg confidence",
             "—" if avg_conf is None else f"{avg_conf:.0f}/100",
             _conf_color(avg_conf)),
            ("Avg per doc",
             "—" if not files else f"{elapsed / files:.1f}s", theme.INDIGO),
        ]

        for i, (label, value, color) in enumerate(tiles):
            self.tiles.columnconfigure(i, weight=1)
            card = ttk.Frame(self.tiles, style="Card.TFrame")
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            ttk.Label(card, text=value, style="Card.TLabel",
                      font=theme.FONT_STAT, foreground=color).pack(
                anchor=tk.W, padx=16, pady=(14, 0))
            ttk.Label(card, text=label.upper(), style="Card.TLabel",
                      font=theme.FONT_LABEL, foreground=theme.FG_DIM).pack(
                anchor=tk.W, padx=16, pady=(2, 14))

    # --------------------------------------------------------------- drawing
    def _draw(self):
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 50 or height < 50:
            return

        if not self._stats.get("runs"):
            self.canvas.create_text(
                width // 2, height // 2,
                text="No runs recorded yet — run a batch to populate analytics.",
                fill=theme.FG_DIM, font=theme.FONT,
            )
            return

        col_w = width // 2 - 12
        self._draw_stage_throughput(8, 8, col_w, height // 2 - 16)
        self._draw_confidence_histogram(width // 2 + 12, 8, col_w, height // 2 - 16)
        self._draw_recent_runs(8, height // 2 + 8, width - 16, height // 2 - 16)

    def _panel(self, x, y, w, h, title):
        """A panel is a sheet of raised paper with a hairline rule."""
        self.canvas.create_rectangle(x, y, x + w, y + h, fill=theme.FRAME_BG,
                                     outline=theme.RULE)
        self.canvas.create_text(x + 16, y + 16, text=title.upper(), anchor=tk.W,
                                fill=theme.FG_DIM, font=theme.FONT_LABEL)
        self.canvas.create_line(x + 16, y + 30, x + w - 16, y + 30,
                                fill=theme.RULE)

    def _draw_stage_throughput(self, x, y, w, h):
        self._panel(x, y, w, h, "Throughput  (chars / second)")
        totals = self._stats.get("stage_totals") or {}
        rows = [
            (name, acc["chars"] / acc["elapsed"] if acc["elapsed"] else 0, acc["n"])
            for name, acc in totals.items() if acc["n"]
        ]
        if not rows:
            self.canvas.create_text(x + 12, y + 44, text="No completed stages yet.",
                                    anchor=tk.W, fill=theme.FG_DIM, font=theme.FONT_SMALL)
            return

        peak = max(r[1] for r in rows) or 1
        colors = {"ocr": theme.ACCENT, "cleanup": theme.GOLD, "translate": theme.INDIGO}
        bar_h = 22
        top = y + 40
        for i, (name, rate, n) in enumerate(rows):
            row_y = top + i * (bar_h + 14)
            if row_y + bar_h > y + h - 8:
                break
            self.canvas.create_text(x + 12, row_y + bar_h / 2, text=name, anchor=tk.W,
                                    fill=theme.FG, font=theme.FONT_SMALL)
            bar_x = x + 90
            bar_w = max(int((w - 190) * rate / peak), 2)
            self.canvas.create_rectangle(bar_x, row_y, bar_x + bar_w, row_y + bar_h,
                                         fill=colors.get(name, theme.ACCENT), outline="")
            self.canvas.create_text(x + w - 12, row_y + bar_h / 2,
                                    text=f"{rate:,.0f}  (n={n})", anchor=tk.E,
                                    fill=theme.FG_DIM, font=theme.FONT_SMALL)

    def _draw_confidence_histogram(self, x, y, w, h):
        self._panel(x, y, w, h, "Confidence distribution")
        confidences = self._stats.get("confidences") or []
        if not confidences:
            self.canvas.create_text(x + 12, y + 44,
                                    text="Confidence scoring produced no scores yet.",
                                    anchor=tk.W, fill=theme.FG_DIM, font=theme.FONT_SMALL)
            return

        buckets = [0] * 5  # 0-19, 20-39, 40-59, 60-79, 80-100
        for c in confidences:
            buckets[min(int(c) // 20, 4)] += 1
        peak = max(buckets) or 1

        labels = ["0-19", "20-39", "40-59", "60-79", "80+"]
        colors = [theme.ERROR, theme.ERROR, theme.WARNING, theme.WARNING, theme.SUCCESS]
        base_y = y + h - 34
        chart_h = base_y - (y + 44)
        slot = (w - 24) / 5

        for i, count in enumerate(buckets):
            bar_h = int(chart_h * count / peak)
            bx = x + 12 + i * slot + slot * 0.18
            bw = slot * 0.64
            if count:
                self.canvas.create_rectangle(bx, base_y - bar_h, bx + bw, base_y,
                                             fill=colors[i], outline="")
                self.canvas.create_text(bx + bw / 2, base_y - bar_h - 9, text=str(count),
                                        fill=theme.FG, font=theme.FONT_SMALL)
            self.canvas.create_text(bx + bw / 2, base_y + 14, text=labels[i],
                                    fill=theme.FG_DIM, font=theme.FONT_SMALL)

    def _draw_recent_runs(self, x, y, w, h):
        self._panel(x, y, w, h, "Recent runs  (seconds per document)")
        recent = list(reversed(self._stats.get("recent") or []))
        if not recent:
            self.canvas.create_text(x + 12, y + 44, text="No finished runs yet.",
                                    anchor=tk.W, fill=theme.FG_DIM, font=theme.FONT_SMALL)
            return

        rates = [
            (r["elapsed"] / r["total"]) if r["total"] else 0
            for r in recent
        ]
        peak = max(rates) or 1
        base_y = y + h - 26
        chart_h = base_y - (y + 42)
        slot = (w - 24) / max(len(rates), 1)

        points = []
        for i, (rate, run) in enumerate(zip(rates, recent)):
            px = x + 12 + slot * (i + 0.5)
            py = base_y - chart_h * (rate / peak)
            points.extend([px, py])
            color = theme.ERROR if run["failed"] else theme.ACCENT
            self.canvas.create_oval(px - 3, py - 3, px + 3, py + 3,
                                    fill=color, outline="")
        if len(points) >= 4:
            self.canvas.create_line(*points, fill=theme.ACCENT_DIM, width=2,
                                    smooth=True)

        self.canvas.create_text(x + 12, base_y + 12, text=f"oldest of last {len(recent)}",
                                anchor=tk.W, fill=theme.FG_DIM, font=theme.FONT_SMALL)
        self.canvas.create_text(x + w - 12, base_y + 12, text="newest",
                                anchor=tk.E, fill=theme.FG_DIM, font=theme.FONT_SMALL)
        self.canvas.create_text(x + w - 12, y + 42, text=f"peak {peak:.1f}s/doc",
                                anchor=tk.E, fill=theme.FG_DIM, font=theme.FONT_SMALL)


def _conf_color(value) -> str:
    if value is None:
        return theme.FG_DIM
    if value >= 80:
        return theme.SUCCESS
    if value >= 55:
        return theme.WARNING
    return theme.ERROR
