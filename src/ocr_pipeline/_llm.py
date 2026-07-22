"""Shared helpers for talking to Ollama.

The one thing here worth explaining is `think`.

Reasoning models (gemma4:12b among them) emit a chain-of-thought block before
their answer. On a mechanical task like OCR artifact repair that reasoning is
pure overhead: measured on a real archival page, the model generated 7,664
tokens to produce 442 tokens of output — roughly 17x waste, and about 13x
wall-clock. Disabling it is the single biggest win available on the cleanup
stage, but it must be paired with a strict prompt, because the deliberation is
partly what stopped the model modernising the text.
"""

from typing import Any, Callable

from ._logging import get_logger

log = get_logger("llm")

_THINK_UNSUPPORTED_HINTS = (
    "does not support thinking",
    "thinking is not supported",
    "unknown field",
    "unexpected keyword argument",
    "think",
)


def _is_think_unsupported(exc: Exception) -> bool:
    """Distinguish 'this model/server has no thinking switch' from real errors."""
    message = str(exc).lower()
    if "think" not in message:
        return False
    return any(hint in message for hint in _THINK_UNSUPPORTED_HINTS)


def chat(
    chat_fn: Callable[..., Any],
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    think: bool | None = None,
    num_predict: int | None = None,
) -> Any:
    """Call ``ollama.chat`` with an optional thinking switch.

    `chat_fn` is passed in rather than imported so each stage keeps calling its
    own ``ollama.chat`` attribute — which is what the test suite patches.

    Servers or models that do not understand `think` fall back to a plain call
    rather than failing the whole run.
    """
    options: dict[str, Any] = {"temperature": temperature}
    if num_predict:
        options["num_predict"] = num_predict

    if think is None:
        return chat_fn(model=model, messages=messages, options=options)

    try:
        return chat_fn(model=model, messages=messages, options=options, think=think)
    except Exception as exc:
        if _is_think_unsupported(exc):
            log.debug("%s ignores the thinking switch; retrying without it", model)
            return chat_fn(model=model, messages=messages, options=options)
        raise
