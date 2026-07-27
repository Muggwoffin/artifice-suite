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
        return f"Cannot reach LM Studio at {url}. Is it running?"


def check_ollama(required_models: list[str] | None = None, url: str | None = None) -> list[str]:
    """Return list of error messages for Ollama. Empty list = all OK."""
    import ollama as _ollama_client

    errors: list[str] = []
    try:
        host = url or "http://localhost:11434"
        client = _ollama_client.Client(host=host)
        available = {m.model for m in client.list().models}
    except Exception as exc:
        return [f"Cannot reach Ollama at {url or 'http://localhost:11434'}. Is it running?"]

    if required_models:
        for model in required_models:
            if model not in available:
                errors.append(f'Model "{model}" is not downloaded. Open Ollama and download it first.')

    return errors
