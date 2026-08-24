# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import base64
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


from artifice_ocr import _guard
from artifice_ocr._backend import get_client as _get_backend_client
from artifice_ocr._logging import get_logger
from artifice_ocr._resolution import backend_for, model_for
from artifice_ocr._retry import retry
from artifice_ocr.config import get as cfg

log = get_logger("ocr")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"}

OCR_PROMPT = (
    "OCR: Extract all visible text from this document image. "
    "Return only the raw text exactly as it appears. "
    "Do not add commentary, labels, or formatting."
)

_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _exif_orientation_matrix(orientation: int, width: float, height: float):
    """Matrix that corrects a Tropy `photos.orientation` value for a
    page/image of the given (pre-transform) size. Tropy uses the same 1-8
    convention as the EXIF Orientation tag — 1 is normal, 3 is a 180°
    rotation, and so on. Returns None for 1 or an unrecognised value: better
    to OCR the image as scanned than guess wrong about a value this project
    has never seen.

    Confirmed necessary on a real archive page (Tropy orientation 1/normal,
    i.e. nobody had flagged it) that was actually scanned upside down: fed
    to the model as-is, it hallucinated plausible-sounding filler instead of
    transcribing, then looped on it — see `_guard.check_no_repetition_loop`.
    Each of the 8 matrices below was checked against Pillow's reference
    `Image.transpose()` output before shipping.
    """
    import fitz  # PyMuPDF

    if orientation == 1:
        return None
    w, h = width, height
    matrices = {
        2: fitz.Matrix(-1, 0, 0, 1, w, 0),          # mirrored horizontal
        3: fitz.Matrix(1, 1).prerotate(180),         # rotated 180°
        4: fitz.Matrix(1, 0, 0, -1, 0, h),           # mirrored vertical
        5: fitz.Matrix(0, 1, 1, 0, 0, 0),            # mirrored + rotated 270°
        6: fitz.Matrix(1, 1).prerotate(90),          # rotated 90° CW
        7: fitz.Matrix(0, -1, -1, 0, h, w),          # mirrored + rotated 90° CW
        8: fitz.Matrix(1, 1).prerotate(270),         # rotated 270° CW
    }
    return matrices.get(orientation)


def _encode_image(path: Path, orientation: int = 1) -> tuple[str, str]:
    """Returns (base64, mime). Applies an orientation correction (see
    `_exif_orientation_matrix`) when `orientation` isn't 1 — the corrected
    bytes are always a fresh PNG render regardless of the source format.

    Rendered at the source's own native resolution, not fitz's default
    ~72dpi page-point size: a pure rotation/mirror matrix with no
    accompanying scale factor was measured losing ~5.5x resolution on a
    real 3458x5067 scan (rendered at 623x913 instead) — confirmed to make
    the model report the page as unreadable where the uncorrected,
    full-resolution image did not. The scale factor is uniform (x and y),
    so it commutes with any rotation angle and composition order here
    doesn't matter, unlike a non-uniform scale would.
    """
    if orientation != 1:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        try:
            page = doc[0]
            orient_mat = _exif_orientation_matrix(orientation, page.rect.width, page.rect.height)
            if orient_mat is not None:
                native = fitz.Pixmap(str(path))
                zoom = native.width / page.rect.width if page.rect.width else 1.0
                mat = fitz.Matrix(zoom, zoom) * orient_mat
                pix = page.get_pixmap(matrix=mat)
                return base64.standard_b64encode(pix.tobytes("png")).decode("utf-8"), "image/png"
        finally:
            doc.close()

    with open(path, "rb") as f:
        data = f.read()
    mime = _MIME_MAP.get(path.suffix.lower(), "image/png")
    return base64.standard_b64encode(data).decode("utf-8"), mime


@retry(max_attempts=4, base_delay=2.0, label="OCR")
def _ocr_single_image(image_path: Path, orientation: int = 1) -> str:
    """Send a single image to the OCR backend and return extracted text.

    All backends use their OpenAI-compatible endpoint for OCR because
    images are sent as ``image_url`` content blocks — the format supported
    by LM Studio, Ollama's ``/v1`` endpoint, and Hugging Face alike.
    """
    image_b64, mime = _encode_image(image_path, orientation)
    backend = backend_for("vision")
    model = model_for("vision")

    # Ollama's native API carries images in an ``images`` field, not as
    # ``image_url`` content blocks.  Route through the ``ollama_openai``
    # backend which hits the OpenAI-compatible ``/v1`` endpoint so the
    # message format is the same for every backend.
    be_name = "ollama_openai" if backend == "ollama" else backend
    client = _get_backend_client(be_name)

    response = client.chat(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }
        ],
        temperature=0.0,
    )
    return response.message.content or ""


def _pdf_to_page_images(pdf_path: Path, orientation: int = 1) -> list[Path]:
    """Render each PDF page as a temporary PNG. Returns list of paths."""
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    page_images = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="ocr_pdf_"))
    zoom = fitz.Matrix(200 / 72, 200 / 72)

    for page_num in range(len(doc)):
        page = doc[page_num]
        orient_mat = _exif_orientation_matrix(orientation, page.rect.width, page.rect.height)
        mat = orient_mat * zoom if orient_mat is not None else zoom
        pix = page.get_pixmap(matrix=mat)
        img_path = tmp_dir / f"page_{page_num + 1:04d}.png"
        pix.save(str(img_path))
        page_images.append(img_path)

    doc.close()
    return page_images


def _pdf_single_page_image(pdf_path: Path, page_index: int, orientation: int = 1) -> tuple[Path, int]:
    """Render one page of a PDF. Returns (temp PNG path, total page count).

    Used when a caller addresses pages individually — Tropy stores one row per
    page, so rendering all 275 pages to OCR one of them would be absurd.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    total = len(doc)
    try:
        if not 0 <= page_index < total:
            raise ValueError(
                f"Page {page_index + 1} out of range for {pdf_path.name} "
                f"({total} page(s))"
            )
        page = doc[page_index]
        zoom = fitz.Matrix(200 / 72, 200 / 72)
        orient_mat = _exif_orientation_matrix(orientation, page.rect.width, page.rect.height)
        mat = orient_mat * zoom if orient_mat is not None else zoom
        pix = page.get_pixmap(matrix=mat)
        tmp_dir = Path(tempfile.mkdtemp(prefix="ocr_pdf_"))
        img_path = tmp_dir / f"page_{page_index + 1:04d}.png"
        pix.save(str(img_path))
    finally:
        doc.close()
    return img_path, total


def perform(
    input_path: str,
    *,
    output_dir: str = "output",
    page: int | None = None,
    stem: str | None = None,
    orientation: int = 1,
) -> Dict[str, Any]:
    """OCR a document.

    `page` selects a single 0-based page of a PDF instead of the whole file.
    `stem` overrides the output filename, and may contain a relative
    subdirectory (``"Item Title/file_p0002"``) to group results.
    `orientation` is Tropy's `photos.orientation` value (see
    `_exif_orientation_matrix`); 1 (the default) means no correction.
    """
    path = Path(input_path).resolve()
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {path.suffix}. Supported: {SUPPORTED_EXTENSIONS}"
        )

    log.info("Starting OCR for %s", path.name)

    is_pdf = path.suffix.lower() == ".pdf"
    model = model_for("vision")
    page_number = 1

    if is_pdf and page is not None:
        img_path, num_pages = _pdf_single_page_image(path, page, orientation)
        log.info("OCR page %d/%d of %s", page + 1, num_pages, path.name)
        try:
            extracted_text = _ocr_single_image(img_path)
        finally:
            img_path.unlink(missing_ok=True)
        page_number = page + 1
    elif is_pdf:
        page_images = _pdf_to_page_images(path, orientation)
        page_texts = []
        for i, img_path in enumerate(page_images):
            log.info("OCR page %d/%d of %s", i + 1, len(page_images), path.name)
            page_texts.append(_ocr_single_image(img_path))
            img_path.unlink(missing_ok=True)

        extracted_text = "\n\n--- Page Break ---\n\n".join(page_texts)
        num_pages = len(page_texts)
    else:
        extracted_text = _ocr_single_image(path, orientation)
        num_pages = 1

    # The model has no fallback text to revert to here (unlike cleanup/
    # structure, which can keep the source on rejection) — a degenerate OCR
    # result has nothing safe to substitute, so a guard failure fails the
    # item outright rather than writing it to raw_ocr/ looking like a
    # success. See _guard.check_no_repetition_loop's docstring for the real
    # failure this catches.
    guard_result = None
    if cfg("ocr_repetition_guard"):
        guard_result = _guard.check_no_repetition_loop(extracted_text)
        if not guard_result.ok:
            base_output_dir = Path(output_dir)
            json_dir = base_output_dir / "raw_ocr" / "json"
            json_dir.mkdir(parents=True, exist_ok=True)
            base_name = stem or path.stem
            json_path = json_dir / f"{base_name}.json"
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({
                    "source_file": str(path),
                    "stage": "raw_ocr",
                    "rejected_extracted_text": extracted_text,
                    "engine": backend_for("vision"),
                    "model": model,
                    "ocr_prompt": OCR_PROMPT,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "page": page_number,
                    "total_pages": num_pages,
                    "guard": guard_result.to_dict(),
                }, f, indent=2)
            raise RuntimeError(
                f"OCR rejected for {path.name}: {'; '.join(guard_result.reasons)}"
            )

    base_output_dir = Path(output_dir)
    text_dir = base_output_dir / "raw_ocr" / "text"
    json_dir = base_output_dir / "raw_ocr" / "json"

    text_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    base_name = stem or path.stem
    text_path = text_dir / f"{base_name}.txt"
    json_path = json_dir / f"{base_name}.json"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(extracted_text)

    data = {
        "source_file": str(path),
        "stage": "raw_ocr",
        "extracted_text": extracted_text,
        "engine": backend_for("vision"),
        "model": model,
        "ocr_prompt": OCR_PROMPT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "page": page_number,
        "total_pages": num_pages,
    }
    if guard_result is not None:
        data["guard"] = guard_result.to_dict()

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log.info("OCR complete for %s (%d chars, %d pages)", path.name, len(extracted_text), num_pages)
    return data
