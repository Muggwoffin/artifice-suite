# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Pure utility functions for LLM client: token estimation, prompt building, batch packing.

These are stateless, trivially testable functions that share no logic with the
provider transports or orchestration loop.
"""

import json
import math

# Rough estimate: 1 token ~ 4 characters for English text
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate for a text string."""
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def build_user_prompt(paragraphs: list[dict]) -> str:
    """Build the user prompt from a chunk of paragraphs."""
    if not paragraphs:
        return "[]"

    text_block = "\n\n".join(p["text"] for p in paragraphs)
    metadata = json.dumps([
        {
            "index": i,
            "style": p.get("style_name", "Normal"),
            "bold": p.get("is_bold", False),
            "italic": p.get("is_italic", False),
        }
        for i, p in enumerate(paragraphs)
    ])

    return (
        f"Below are {len(paragraphs)} paragraphs from a document.\n"
        f"Contextual metadata: {metadata}\n\n"
        f"Original text:\n{text_block}"
    )


def _compute_dynamic_batch_sizes(
    paragraphs: list[dict],
    max_batch_size: int,
    max_tokens: int,
) -> list[list[dict]]:
    """Split paragraphs into batches that respect token limits.

    Uses a greedy bin-packing approach: keeps adding paragraphs to the current
    batch until adding the next one would exceed the token budget, then starts
    a new batch.
    """
    if not paragraphs:
        return []

    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_tokens = 0
    overhead_tokens = 200  # prompt template overhead

    for para in paragraphs:
        para_tokens = _estimate_tokens(para["text"])

        if current_batch and (
            len(current_batch) >= max_batch_size
            or (current_tokens + para_tokens + overhead_tokens) > max_tokens
        ):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(para)
        current_tokens += para_tokens

    if current_batch:
        batches.append(current_batch)

    return batches
