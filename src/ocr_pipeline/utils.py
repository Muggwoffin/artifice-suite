import ollama as _ollama
from openai import OpenAI

from src.ocr_pipeline.config import get as cfg


def check_lm_studio(url: str | None = None) -> str | None:
    """Return an error message if LM Studio is unreachable, else None."""
    if url is None:
        url = cfg("lm_studio_url")
    try:
        client = OpenAI(base_url=url, api_key="lm-studio")
        client.models.list()
        return None
    except Exception as exc:
        return f"Cannot reach LM Studio at {url} ({exc.__class__.__name__})"


def check_ollama(required_models: list[str] | None = None) -> list[str]:
    """Return list of error messages for Ollama. Empty list = all OK."""
    errors: list[str] = []
    try:
        available = {m.model for m in _ollama.list().models}
    except Exception as exc:
        return [f"Cannot reach Ollama server ({exc.__class__.__name__})"]

    if required_models:
        for model in required_models:
            if model not in available:
                errors.append(f"Model not pulled: {model}  (run: ollama pull {model})")

    return errors
