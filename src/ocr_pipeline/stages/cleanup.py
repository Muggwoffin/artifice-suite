import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import ollama

from src.ocr_pipeline._chunking import chunk_text, reassemble, estimate_tokens
from src.ocr_pipeline._logging import get_logger
from src.ocr_pipeline._prompts import get_cleanup_prompt
from src.ocr_pipeline._retry import retry
from src.ocr_pipeline.config import get as cfg

log = get_logger("cleanup")


@retry(max_attempts=4, base_delay=1.0, label="Ollama cleanup")
def _call_cleanup_chunk(
    raw_text: str,
    system_prompt: str,
    user_template: str,
) -> str:
    """Clean up a single chunk of text."""
    user_prompt = user_template.replace("{raw_text}", raw_text)
    model = cfg("cleanup_model")

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0},
    )

    return response.message.content


def _cleanup_with_chunking(
    raw_text: str,
    system_prompt: str,
    user_template: str,
) -> str:
    """Clean text, chunking if it exceeds the model's context window."""
    max_tokens = cfg("chunk_max_tokens")
    overlap_tokens = cfg("chunk_overlap_tokens")

    est_tokens = estimate_tokens(raw_text)
    if est_tokens <= max_tokens:
        return _call_cleanup_chunk(raw_text, system_prompt, user_template)

    log.info(
        "Text too long (%d est. tokens), chunking for cleanup...",
        est_tokens,
    )
    chunks = chunk_text(raw_text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    log.info("Cleaning %d chunk(s)...", len(chunks))

    cleaned_chunks = []
    for i, chunk in enumerate(chunks):
        log.info("  Chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
        cleaned = _call_cleanup_chunk(chunk, system_prompt, user_template)
        cleaned_chunks.append(cleaned)

    return reassemble(cleaned_chunks)


def perform(
    raw_text: str,
    *,
    source_file: str = "",
    output_dir: str = "output",
    stem: str | None = None,
) -> Dict[str, Any]:
    """Clean raw OCR text.

    `stem` overrides the output filename (derived from `source_file` by
    default) and may contain a relative subdirectory.
    """
    doc_type = cfg("document_type")
    prompts = get_cleanup_prompt(doc_type)
    system_prompt = prompts["system"]
    user_template = prompts["user"]

    model = cfg("cleanup_model")
    log.info("Cleaning with %s (doc_type=%s)", model, doc_type)

    cleaned_text = _cleanup_with_chunking(raw_text, system_prompt, user_template)

    base_output_dir = Path(output_dir)
    text_dir = base_output_dir / "cleaned" / "text"
    json_dir = base_output_dir / "cleaned" / "json"

    text_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    base_name = stem or (Path(source_file).stem if source_file else "unknown")
    text_path = text_dir / f"{base_name}.txt"
    json_path = json_dir / f"{base_name}.json"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    data = {
        "source_file": source_file,
        "stage": "cleaned",
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "engine": "ollama",
        "model": model,
        "system_prompt": system_prompt,
        "document_type": doc_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log.info("Cleanup complete (%d -> %d chars)", len(raw_text), len(cleaned_text))
    return data
