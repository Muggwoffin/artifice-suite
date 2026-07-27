"""Readability and word count analytics module."""

from __future__ import annotations

import re


def calculate_document_metrics(paragraphs: list[dict]) -> dict:
    """Calculate total word count, paragraph count, average sentence length,

    and approximate Flesch Reading Ease score.
    """
    total_words = 0
    total_sentences = 0
    total_syllables = 0
    para_count = len(paragraphs)

    sentence_endings = re.compile(r'[.!?]+')

    for entry in paragraphs:
        text = entry.get("text", "")
        words = text.split()
        num_words = len(words)
        total_words += num_words

        sentences = sentence_endings.split(text)
        num_sentences = max(1, len([s for s in sentences if s.strip()]))
        total_sentences += num_sentences

        for word in words:
            total_syllables += _count_syllables(word)

    avg_words_per_sentence = total_words / max(1, total_sentences)
    avg_syllables_per_word = total_syllables / max(1, total_words)

    # Flesch Reading Ease formula: 206.835 - 1.015*(words/sentences) - 84.6*(syllables/words)
    flesch_score = 206.835 - (1.015 * avg_words_per_sentence) - (84.6 * avg_syllables_per_word)

    return {
        "paragraph_count": para_count,
        "total_word_count": total_words,
        "total_sentence_count": total_sentences,
        "average_sentence_length": round(avg_words_per_sentence, 1),
        "flesch_reading_ease": round(flesch_score, 1),
    }


def _count_syllables(word: str) -> int:
    word = word.lower().strip(".:;,!?()[]{}'\"")
    if len(word) <= 3:
        return 1
    word = re.sub(r'(?:[^laeiouy]|ed|es|e)$', '', word)
    word = re.sub(r'^y', '', word)
    matches = re.findall(r'[aeiouy]{1,2}', word)
    return max(1, len(matches))
