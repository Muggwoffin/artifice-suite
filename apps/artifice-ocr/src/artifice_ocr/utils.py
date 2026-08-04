# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import ollama as _ollama

from artifice_ocr._backend import get_client


def check_lm_studio(url: str | None = None) -> str | None:
    """Return an error message if LM Studio is unreachable, else None."""
    ok, detail = get_client("lm_studio").health_check()
    return detail if not ok else None


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
