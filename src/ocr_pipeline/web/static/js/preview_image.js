/*
 * Pan/zoom viewport for the source-scan image pane — used by both the Preview
 * tab and the History tab. A factory function accepts a map of element IDs so
 * two independent viewports (PreviewImage and HistoryImage) share the same
 * pan/zoom/math without duplicating the pointer-event logic.
 *
 * Pointer Events (not mouse-only handlers) so drag-to-pan also works with
 * touch on a tablet with no extra code.
 */

function createImageViewport(ids) {
  const viewport = document.getElementById(ids.viewport);
  const img = document.getElementById(ids.img);
  const empty = document.getElementById(ids.empty);
  const resetBtn = document.getElementById(ids.resetBtn);
  const zoomReadout = document.getElementById(ids.zoomReadout);

  let scale = 1, tx = 0, ty = 0;
  let fitScale = 1;
  let dragging = false;
  let dragStart = null;

  function apply() {
    img.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    if (zoomReadout) zoomReadout.textContent = fitScale ? `${Math.round((scale / fitScale) * 100)}%` : "";
  }

  function fitToPane() {
    if (!img.naturalWidth) return;
    const vw = viewport.clientWidth, vh = viewport.clientHeight;
    fitScale = Math.min(vw / img.naturalWidth, vh / img.naturalHeight, 1) || 1;
    scale = fitScale;
    tx = (vw - img.naturalWidth * scale) / 2;
    ty = (vh - img.naturalHeight * scale) / 2;
    apply();
  }

  function load(src) {
    img.onload = () => {
      img.style.display = "block";
      empty.style.display = "none";
      fitToPane();
    };
    img.onerror = () => {
      img.style.display = "none";
      empty.textContent = "(image unavailable)";
      empty.style.display = "";
    };
    empty.textContent = "";
    empty.style.display = "none";
    img.src = src;
  }

  function clear() {
    img.removeAttribute("src");
    img.style.display = "none";
    empty.textContent = "(no document selected)";
    empty.style.display = "";
  }

  viewport.addEventListener("wheel", (e) => {
    if (!img.naturalWidth) return;
    e.preventDefault();
    const rect = viewport.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top;
    const factor = Math.exp(-e.deltaY * 0.001);
    const newScale = Math.min(Math.max(scale * factor, fitScale * 0.2), fitScale * 20);
    tx = cx - ((cx - tx) / scale) * newScale;
    ty = cy - ((cy - ty) / scale) * newScale;
    scale = newScale;
    apply();
  }, { passive: false });

  viewport.addEventListener("pointerdown", (e) => {
    if (!img.naturalWidth) return;
    dragging = true;
    dragStart = { x: e.clientX, y: e.clientY, tx, ty };
    viewport.setPointerCapture(e.pointerId);
  });
  viewport.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    tx = dragStart.tx + (e.clientX - dragStart.x);
    ty = dragStart.ty + (e.clientY - dragStart.y);
    apply();
  });
  viewport.addEventListener("pointerup", (e) => {
    dragging = false;
    try { viewport.releasePointerCapture(e.pointerId); } catch { /* already released */ }
  });
  viewport.addEventListener("dblclick", fitToPane);
  if (resetBtn) resetBtn.addEventListener("click", fitToPane);
  window.addEventListener("resize", () => { if (img.naturalWidth) fitToPane(); });

  return { load, clear, fitToPane };
}

const PreviewImage = createImageViewport({
  viewport: "image-viewport",
  img: "preview-image",
  empty: "image-empty",
  resetBtn: "btn-image-reset",
  zoomReadout: "image-zoom-readout",
});
window.PreviewImage = PreviewImage;

const HistoryImage = createImageViewport({
  viewport: "history-image-viewport",
  img: "history-image",
  empty: "history-image-empty",
  resetBtn: "btn-history-image-reset",
  zoomReadout: "history-image-zoom-readout",
});
window.HistoryImage = HistoryImage;
