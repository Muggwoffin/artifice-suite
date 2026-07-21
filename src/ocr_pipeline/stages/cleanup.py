import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import ollama

from src.ocr_pipeline._logging import get_logger
from src.ocr_pipeline._retry import retry
from src.ocr_pipeline.config import get as cfg

log = get_logger("cleanup")

PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"

SYSTEM_PROMPT = (
    "You are an archivist expert in early 20th-century documents. "
    "You perform conservative syntactic cleanup of OCR text."
)


def _load_user_prompt(raw_text: str) -> str:
    prompt_file = PROMPT_DIR / "cleanup_prompt.txt"
    template = prompt_file.read_text(encoding="utf-8")

    lines = template.splitlines()
    user_lines = [
        line for line in lines if not line.startswith("SYSTEM_PROMPT:")
    ]
    user_template = "\n".join(user_lines).strip()

    return user_template.replace("{raw_text}", raw_text)


@retry(max_attempts=4, base_delay=1.0, label="Ollama cleanup")
def _call_cleanup(raw_text: str) -> str:
    model = cfg("cleanup_model")
    user_prompt = _load_user_prompt(raw_text)

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0},
    )

    return response.message.content


def perform(
    raw_text: str,
    *,
    source_file: str = "",
    output_dir: str = "output",
) -> Dict[str, Any]:
    model = cfg("cleanup_model")
    log.info("Cleaning OCR data with %s", model)

    cleaned_text = _call_cleanup(raw_text)

    base_output_dir = Path(output_dir)
    text_dir = base_output_dir / "cleaned" / "text"
    json_dir = base_output_dir / "cleaned" / "json"

    text_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(source_file).stem if source_file else "unknown"
    text_path = text_dir / f"{stem}.txt"
    json_path = json_dir / f"{stem}.json"

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    data = {
        "source_file": source_file,
        "stage": "cleaned",
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "engine": "ollama",
        "model": model,
        "system_prompt": SYSTEM_PROMPT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log.info("Cleanup complete (%d -> %d chars)", len(raw_text), len(cleaned_text))
    return data
