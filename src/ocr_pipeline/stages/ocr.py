import base64
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from openai import OpenAI

from src.ocr_pipeline._logging import get_logger
from src.ocr_pipeline._retry import retry
from src.ocr_pipeline.config import get as cfg

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


def _encode_image(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _get_client() -> OpenAI:
    return OpenAI(base_url=cfg("lm_studio_url"), api_key="lm-studio")


@retry(max_attempts=4, base_delay=2.0, label="LM Studio OCR")
def _ocr_single_image(image_path: Path) -> str:
    """Send a single image to LM Studio and return extracted text."""
    image_b64 = _encode_image(image_path)
    mime = _MIME_MAP.get(image_path.suffix.lower(), "image/png")

    model = cfg("ocr_model")
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                ],
            }
        ],
        temperature=0,
    )
    return response.choices[0].message.content


def _pdf_to_page_images(pdf_path: Path) -> list[Path]:
    """Render each PDF page as a temporary PNG. Returns list of paths."""
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    page_images = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="ocr_pdf_"))

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=200)
        img_path = tmp_dir / f"page_{page_num + 1:04d}.png"
        pix.save(str(img_path))
        page_images.append(img_path)

    doc.close()
    return page_images


def _pdf_single_page_image(pdf_path: Path, page_index: int) -> tuple[Path, int]:
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
        pix = doc[page_index].get_pixmap(dpi=200)
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
) -> Dict[str, Any]:
    """OCR a document.

    `page` selects a single 0-based page of a PDF instead of the whole file.
    `stem` overrides the output filename, and may contain a relative
    subdirectory (``"Item Title/file_p0002"``) to group results.
    """
    path = Path(input_path).resolve()
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {path.suffix}. Supported: {SUPPORTED_EXTENSIONS}"
        )

    log.info("Starting OCR for %s", path.name)

    is_pdf = path.suffix.lower() == ".pdf"
    model = cfg("ocr_model")
    page_number = 1

    if is_pdf and page is not None:
        img_path, num_pages = _pdf_single_page_image(path, page)
        log.info("OCR page %d/%d of %s", page + 1, num_pages, path.name)
        try:
            extracted_text = _ocr_single_image(img_path)
        finally:
            img_path.unlink(missing_ok=True)
        page_number = page + 1
    elif is_pdf:
        page_images = _pdf_to_page_images(path)
        page_texts = []
        for i, img_path in enumerate(page_images):
            log.info("OCR page %d/%d of %s", i + 1, len(page_images), path.name)
            page_texts.append(_ocr_single_image(img_path))
            img_path.unlink(missing_ok=True)

        extracted_text = "\n\n--- Page Break ---\n\n".join(page_texts)
        num_pages = len(page_texts)
    else:
        extracted_text = _ocr_single_image(path)
        num_pages = 1

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
        "engine": "lm-studio",
        "model": model,
        "ocr_prompt": OCR_PROMPT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "page": page_number,
        "total_pages": num_pages,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log.info("OCR complete for %s (%d chars, %d pages)", path.name, len(extracted_text), num_pages)
    return data
