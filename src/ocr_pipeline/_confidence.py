"""Confidence scoring for OCR pipeline outputs.

Uses LLM self-assessment and heuristic markers to estimate quality.
"""

import re
from dataclasses import dataclass, asdict
from typing import Any

import ollama

from src.ocr_pipeline._logging import get_logger
from src.ocr_pipeline._retry import retry
from src.ocr_pipeline.config import get as cfg

log = get_logger("confidence")

# Heuristic uncertainty markers commonly produced by LLMs
_UNCERTAINTY_MARKERS = [
    "i'm not sure",
    "i am not sure",
    "it appears that",
    "it seems",
    "possibly",
    "perhaps",
    "unclear",
    "illegible",
    "unreadable",
    "cannot determine",
    "could not read",
    "not legible",
    "damaged text",
    "faded",
    "torn",
    "obscured",
    "[unclear]",
    "[illegible]",
    "[?]",
    "...",
]

# Prompt that asks the model to self-rate its confidence
_SELF_ASSESSMENT_PROMPT = (
    "You just performed a translation/cleanup of a historical document. "
    "Rate your confidence in the accuracy of your output on a scale of 0-100.\n\n"
    "Consider:\n"
    "- Was the source text clear and legible?\n"
    "- Did you encounter ambiguous words or passages?\n"
    "- How confident are you in the translation choices you made?\n\n"
    "Reply with ONLY a JSON object in this exact format:\n"
    '{{"score": <number 0-100>, "reasoning": "<brief explanation>"}}\n\n'
    "Original source (first 1000 chars):\n{source_text}\n\n"
    "Your output (first 1000 chars):\n{output_text}"
)


@dataclass
class ConfidenceResult:
    score: int  # 0-100
    reasoning: str
    heuristic_score: int  # 0-100 from text markers
    uncertainty_markers_found: list[str]
    overall_score: int  # weighted average

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _heuristic_score(text: str) -> tuple[int, list[str]]:
    """Score text based on uncertainty marker frequency.

    Returns (score 0-100, list of markers found).
    """
    text_lower = text.lower()
    found = []
    for marker in _UNCERTAINTY_MARKERS:
        count = text_lower.count(marker)
        if count > 0:
            found.extend([marker] * min(count, 3))  # cap per-marker

    total_markers = len(found)
    word_count = max(len(text.split()), 1)
    marker_density = total_markers / word_count

    # 0% density -> 100 score, 5%+ density -> 0 score
    score = max(0, int(100 * (1 - marker_density / 0.05)))
    return score, found


@retry(max_attempts=3, base_delay=1.0, label="Self-assessment")
def _call_self_assessment(source_text: str, output_text: str) -> dict[str, Any]:
    """Ask the LLM to rate its own confidence."""
    model = cfg("translate_model")
    prompt = _SELF_ASSESSMENT_PROMPT.format(
        source_text=source_text[:1000],
        output_text=output_text[:1000],
    )

    from src.ocr_pipeline import _llm

    response = _llm.chat(
        ollama.chat,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        think=cfg("ollama_think"),
    )

    raw = response.message.content.strip()
    # Extract JSON from response
    import json
    match = re.search(r'\{[^}]+\}', raw)
    if match:
        return json.loads(match.group())
    return {"score": 50, "reasoning": "Could not parse self-assessment"}


def evaluate_confidence(
    source_text: str,
    output_text: str,
    *,
    enable_self_assessment: bool = True,
) -> ConfidenceResult:
    """Evaluate confidence of a pipeline output.

    Combines heuristic marker detection with optional LLM self-assessment.
    """
    h_score, markers = _heuristic_score(source_text + " " + output_text)

    if enable_self_assessment:
        try:
            sa = _call_self_assessment(source_text, output_text)
            llm_score = sa.get("score", 50)
            reasoning = sa.get("reasoning", "")
        except Exception as exc:
            log.warning("Self-assessment failed: %s", exc)
            llm_score = 50
            reasoning = f"Self-assessment failed: {exc.__class__.__name__}"
    else:
        llm_score = h_score
        reasoning = "Self-assessment disabled"

    # Weighted average: 60% heuristic, 40% LLM self-assessment
    overall = int(0.6 * h_score + 0.4 * llm_score)

    result = ConfidenceResult(
        score=llm_score,
        reasoning=reasoning,
        heuristic_score=h_score,
        uncertainty_markers_found=markers,
        overall_score=overall,
    )

    log.info(
        "Confidence: %d/100 (heuristic=%d, llm=%d, markers=%d)",
        overall, h_score, llm_score, len(markers),
    )
    return result
