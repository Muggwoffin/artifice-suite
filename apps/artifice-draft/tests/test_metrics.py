"""Tests for metrics module."""

from __future__ import annotations

from artifice_draft.metrics import calculate_document_metrics


def test_calculate_metrics():
    paragraphs = [
        {"paragraph_index": 0, "text": "This is a simple sentence. This is another sentence."},
    ]
    metrics = calculate_document_metrics(paragraphs)
    assert metrics["paragraph_count"] == 1
    assert metrics["total_word_count"] == 9
    assert metrics["total_sentence_count"] == 2
    assert "flesch_reading_ease" in metrics
