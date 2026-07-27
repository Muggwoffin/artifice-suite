"""Zoomable/pannable preview of the scanned source page behind a History item.

Renders through PyMuPDF (`fitz`), already a required dependency elsewhere in
this codebase (see `stages/ocr.py`) — no Pillow needed. `fitz.open()` treats a
plain raster image the same as a one-page PDF (`page.rect` in points, at an
implicit 72dpi for images), so a single render path covers jpg/png/tif/pdf
alike. A Tropy page is one page inside a shared PDF, hence the `page`
parameter to `load()` — only meaningful when the source is a PDF.
"""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .. import theme

BASE_DPI = 150.0        # render DPI at "100%" (fit-to-pane) zoom
MAX_LONG_EDGE = 4000.0  # cap the rendered raster so extreme zoom stays sane
MIN_ZOOM = 0.2
MAX_ZOOM = 8.0
ZOOM_STEP = 1.2


def _dpi_for_zoom(
    page_width_pt: float,
    page_height_pt: float,
    zoom: float,
    base_dpi: float = BASE_DPI,
    max_long_edge: float = MAX_LONG_EDGE,
) -> float:
    """The render DPI for a given zoom level, capped so the output raster's
    long edge never exceeds `max_long_edge` pixels."""
    dpi = base_dpi * zoom
    long_edge_pt = max(page_width_pt, page_height_pt, 1.0)
    long_edge_px = long_edge_pt / 72 * dpi
    if long_edge_px > max_long_edge:
        dpi = dpi * max_long_edge / long_edge_px
    return max(dpi, 1.0)


class ImagePane(ttk.Frame):
    """Canvas showing the source scan: mouse-wheel zoom toward the cursor,
    click-drag pan, double-click (or the Reset button) to fit-to-pane.

    Only mounted where a caller opts in (`CompareView(with_image=True)`) —
    the plain Preview tab's `CompareView` does not carry this pane.
    """

    def __init__(self, master):
        super().__init__(master, style="Card.TFrame")

        header = ttk.Frame(self, style="Card.TFrame")
        header.pack(fill=tk.X, padx=10, pady=(8, 2))
        ttk.Label(header, text="SOURCE SCAN", style="Card.TLabel",
                  font=theme.FONT_LABEL, foreground=theme.FG_DIM).pack(side=tk.LEFT)
        self.zoom_label = ttk.Label(header, text="", style="Card.TLabel",
                                    font=theme.FONT_LABEL, foreground=theme.FG_DIM)
        self.zoom_label.pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(header, text="Reset", command=self.reset_view).pack(side=tk.RIGHT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=(4, 0))

        # Explicit initial size, not just fill=BOTH/expand=True: a bare
        # Canvas requests almost no natural size, and ttk.PanedWindow only
        # honours `weight` once the window is *resized* — its initial
        # layout falls back to each pane's requested size, so without this
        # the pane would render at ~1px wide until the user dragged a sash.
        self.canvas = tk.Canvas(self, bg=theme.FRAME_BG, highlightthickness=0,
                                width=320, height=400)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=(6, 6), pady=(0, 8))

        self._doc = None
        self._page = None
        self._photo = None
        self._image_item = None
        self._zoom = 1.0
        self._offset = (0.0, 0.0)  # top-left corner of the image, canvas coords
        self._drag_start = None
        self._placeholder = self.canvas.create_text(
            10, 10, anchor=tk.NW, fill=theme.FG_DIM, font=theme.FONT_SMALL,
            text="No source scan",
        )

        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_wheel(e, delta=120))
        self.canvas.bind("<Button-5>", lambda e: self._on_wheel(e, delta=-120))
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)
        self.canvas.bind("<Double-Button-1>", lambda _e: self.reset_view())
        self.canvas.bind("<Configure>", self._on_resize)

    # ------------------------------------------------------------- loading
    def load(self, path: str, page: int | None = None) -> None:
        self._close_doc()
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            index = page or 0 if Path(path).suffix.lower() == ".pdf" else 0
            index = max(0, min(index, len(doc) - 1))
            self._doc = doc
            self._page = doc[index]
        except Exception:
            self._doc = None
            self._page = None
            self._show_placeholder("Could not load source image")
            return
        self._fit_and_render()

    def clear(self) -> None:
        self._close_doc()
        self._show_placeholder("No source scan")

    def _close_doc(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None
        self._page = None
        self.canvas.delete("image")
        self._image_item = None

    def _show_placeholder(self, text: str) -> None:
        self.canvas.delete("image")
        self._image_item = None
        self.canvas.itemconfigure(self._placeholder, text=text)
        self.zoom_label.configure(text="")

    # ---------------------------------------------------------- rendering
    def _fit_scale(self) -> float:
        if self._page is None:
            return 1.0
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        pw, ph = self._page.rect.width, self._page.rect.height
        if pw <= 0 or ph <= 0:
            return 1.0
        # page rect is in points; BASE_DPI is what "zoom == 1.0" renders at.
        native_w = pw / 72 * BASE_DPI
        native_h = ph / 72 * BASE_DPI
        return min(cw / native_w, ch / native_h, 4.0)

    def _fit_and_render(self) -> None:
        self._zoom = self._fit_scale()
        self._render(center=True)

    def reset_view(self) -> None:
        if self._page is not None:
            self._fit_and_render()

    def _render(self, center: bool = False) -> None:
        if self._page is None:
            return
        import fitz  # PyMuPDF
        dpi = _dpi_for_zoom(self._page.rect.width, self._page.rect.height, self._zoom)
        pix = self._page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
        self._photo = tk.PhotoImage(data=pix.tobytes("ppm"))
        self.canvas.delete("image")

        if center:
            cw = max(self.canvas.winfo_width(), 100)
            ch = max(self.canvas.winfo_height(), 100)
            ox = max((cw - self._photo.width()) / 2, 0)
            oy = max((ch - self._photo.height()) / 2, 0)
            self._offset = (ox, oy)

        self._image_item = self.canvas.create_image(
            *self._offset, anchor=tk.NW, image=self._photo, tags=("image",))
        self.canvas.itemconfigure(self._placeholder, text="")
        self.zoom_label.configure(text=f"{self._zoom * 100:.0f}%")

    def _on_resize(self, _event=None) -> None:
        # Only auto-fits before the first render — once loaded, resizing the
        # pane shouldn't fight a zoom/pan the user has already set up.
        if self._page is not None and self._image_item is None:
            self._fit_and_render()

    # -------------------------------------------------------------- zoom
    def _on_wheel(self, event, delta: int | None = None) -> None:
        if self._page is None:
            return
        delta = event.delta if delta is None else delta
        factor = ZOOM_STEP if delta > 0 else (1 / ZOOM_STEP)
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._zoom * factor))
        if new_zoom == self._zoom:
            return
        cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        ox, oy = self._offset
        # Keep the point under the cursor stationary across the zoom change.
        scale_ratio = new_zoom / self._zoom
        self._offset = (cx - (cx - ox) * scale_ratio, cy - (cy - oy) * scale_ratio)
        self._zoom = new_zoom
        self._render(center=False)

    # -------------------------------------------------------------- pan
    def _on_drag_start(self, event) -> None:
        self._drag_start = (event.x, event.y, self._offset)

    def _on_drag_move(self, event) -> None:
        if self._drag_start is None or self._image_item is None:
            return
        sx, sy, (ox, oy) = self._drag_start
        self._offset = (ox + (event.x - sx), oy + (event.y - sy))
        self.canvas.coords(self._image_item, *self._offset)
