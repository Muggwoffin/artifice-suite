import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import ollama

from src.ocr_pipeline._logging import get_logger
from src.ocr_pipeline._retry import retry
from src.ocr_pipeline.config import get as cfg

log = get_logger("translate")

PROMPT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts"

SYSTEM_PROMPT = (
    "You are a translator specializing in historical documents. "
    "You translate text into English while preserving tone and style."
)

LANG_DETECT_PROMPT = (
    "Identify the primary language of the following text. "
    "Reply with ONLY the ISO 639-1 language code (e.g. 'de', 'fr', 'en', 'ja', 'ru'). "
    "If the text contains multiple languages, reply with the majority language code. "
    "Do not explain.\n\n{text}"
)

COMMON_LANGUAGES = {
    "de": "German",
    "fr": "French",
    "en": "English",
    "it": "Italian",
    "ja": "Japanese",
    "ru": "Russian",
    "es": "Spanish",
    "pt": "Portuguese",
    "pl": "Polish",
    "nl": "Dutch",
    "la": "Latin",
}


def _load_user_prompt(text: str) -> str:
    prompt_file = PROMPT_DIR / "translation_prompt.txt"
    template = prompt_file.read_text(encoding="utf-8")

    lines = template.splitlines()
    user_lines = [
        line for line in lines if not line.startswith("SYSTEM_PROMPT:")
    ]
    user_template = "\n".join(user_lines).strip()

    return user_template.replace("{text}", text)


@retry(max_attempts=3, base_delay=1.0, label="Lang detect")
def _call_lang_detect(text: str) -> str:
    model = cfg("translate_model")
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "user", "content": LANG_DETECT_PROMPT.format(text=text[:2000])},
        ],
        options={"temperature": 0},
    )
    return response.message.content.strip().lower()


def detect_language(text: str) -> str:
    """Detect source language via LLM. Returns ISO 639-1 code."""
    try:
        code = _call_lang_detect(text)
        if len(code) <= 3 and code.isalpha():
            return code
        return "unknown"
    except Exception:
        return "unknown"


@retry(max_attempts=4, base_delay=1.0, label="Ollama translate")
def _call_translate(cleaned_text: str) -> str:
    model = cfg("translate_model")
    user_prompt = _load_user_prompt(cleaned_text)

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
    cleaned_text: str,
    *,
    source_file: str = "",
    output_dir: str = "output",
) -> Dict[str, Any]:
    log.info("Detecting source language...")
    detected_lang = detect_language(cleaned_text)
    lang_name = COMMON_LANGUAGES.get(detected_lang, detected_lang)
    log.info("Detected language: %s (%s)", lang_name, detected_lang)

    model = cfg("translate_model")
    log.info("Translating with %s", model)

    translated_text = _call_translate(cleaned_text)

    base_output_dir = Path(output_dir)
    text_dir = base_output_dir / "translated" / "text"
    json_dir = base_output_dir / "translated" / "json"

    text_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(source_file).stem if source_file else "unknown"
    text_path = text_dir / f"{stem}.txt"
    json_path = json_dir / f"{stem}.json"

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(translated_text)

    data = {
        "source_file": source_file,
        "stage": "translated",
        "source_language": detected_lang,
        "source_language_name": lang_name,
        "cleaned_text": cleaned_text,
        "translated_text": translated_text,
        "engine": "ollama",
        "model": model,
        "system_prompt": SYSTEM_PROMPT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log.info("Translation complete (%d -> %d chars)", len(cleaned_text), len(translated_text))
    return data
