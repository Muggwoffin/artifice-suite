"""Content-preservation guard for the cleanup stage.

Cleanup asks a language model to rewrite a page of archival text. Measured over
130 real pages, it left 64% untouched, made genuine repairs on some of the
rest (`CAHTOLIC` -> `CATHOLIC`, `ERNSTFRIEDRHCH` -> `ERNSTFRIEDRICH`), and on a
minority did real damage: it corrupted words that were already correct
(`Gewerkschaftern` -> `Gewerkshaftern`), altered a place name (`Elsass` ->
`Elass`), and on fragmentary pages deleted whole clauses it could not parse.

The guard makes that failure mode safe. It compares the model's output against
the source and, if the output looks lossy or has altered a proper noun,
discards it and keeps the raw text. A page is therefore either cleaned or
untouched — never quietly truncated.

The check is deliberately whole-page rather than per-edit: reverting individual
edits would produce a text that never existed in either version, which is worse
than a clean no-op and much harder to audit.
"""

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ._logging import get_logger
from .config import get as cfg

log = get_logger("guard")

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_UMLAUT = re.compile(r"[äöüÄÖÜßéèêàâçñ]")

# Capitalised tokens shorter than this are too noisy to protect (initials,
# "Der", "Am", roman numerals).
_MIN_NOUN_LEN = 4


@dataclass
class GuardResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    words_deleted: int = 0
    nouns_dropped: list[str] = field(default_factory=list)
    length_ratio: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reasons": self.reasons,
            "words_deleted": self.words_deleted,
            "nouns_dropped": self.nouns_dropped[:20],
            "length_ratio": round(self.length_ratio, 4),
        }


def _words(text: str) -> list[str]:
    return _WORD.findall(text)


def _proper_nouns(text: str) -> Counter:
    """Capitalised tokens, excluding ones that merely start a sentence.

    Counted rather than collected into a set: a page may use a name several
    times and have only one occurrence corrupted. `Elsass` appearing five
    times and `Elass` once still leaves `Elsass` present, so set membership
    would miss the corruption entirely.
    """
    nouns: Counter = Counter()
    for match in _WORD.finditer(text):
        token = match.group()
        if len(token) < _MIN_NOUN_LEN or not token[:1].isupper():
            continue
        preceding = text[max(0, match.start() - 2):match.start()]
        if preceding.strip() in ("", ".", "!", "?", ":", ";"):
            continue  # sentence-initial; capitalisation carries no information
        nouns[token] += 1
    return nouns


def check(raw: str, cleaned: str) -> GuardResult:
    """Decide whether `cleaned` is a safe replacement for `raw`."""
    result = GuardResult(ok=True)

    if not cleaned.strip():
        result.ok = False
        result.reasons.append("output empty")
        return result

    raw_words, clean_words = _words(raw), _words(cleaned)

    # Measured in letters, not characters. A correct repair removes hyphens,
    # newlines and doubled spaces, so a raw-character ratio punishes exactly
    # the behaviour cleanup exists for: rejoining "Be-\nricht" into "Bericht"
    # is a 2-character loss and zero letters lost.
    raw_letters = sum(len(w) for w in raw_words)
    clean_letters = sum(len(w) for w in clean_words)
    result.length_ratio = (clean_letters / raw_letters) if raw_letters else 1.0

    # 1. Whole words removed. Replacements are edits; deletions are losses.
    #    A rejoined hyphenated word shows up as a replace, not a delete, so
    #    legitimate repairs do not trip this.
    matcher = difflib.SequenceMatcher(None, raw_words, clean_words, autojunk=False)
    deleted = sum(i2 - i1 for op, i1, i2, _, _ in matcher.get_opcodes()
                  if op == "delete")
    result.words_deleted = deleted

    max_deleted = cfg("cleanup_guard_max_deleted_words")
    if deleted > max_deleted:
        result.ok = False
        result.reasons.append(
            f"{deleted} word(s) deleted from the source (limit {max_deleted})")

    # 2. Shrinkage, which catches losses spread across many small edits.
    min_ratio = cfg("cleanup_guard_min_length_ratio")
    if result.length_ratio < min_ratio:
        result.ok = False
        result.reasons.append(
            f"output keeps {result.length_ratio:.0%} of the source letters "
            f"(limit {min_ratio:.0%})")

    # 3. Proper nouns. A wrong "correction" to a name is invisible to a reader
    #    and breaks full-text search, so names are not the model's to edit.
    if cfg("cleanup_guard_protect_nouns"):
        # Counter subtraction keeps only positive residues, i.e. nouns that
        # lost at least one occurrence.
        missing = _proper_nouns(raw) - _proper_nouns(cleaned)
        dropped = sorted(missing)
        result.nouns_dropped = dropped
        if dropped:
            result.ok = False
            result.reasons.append(
                f"proper noun(s) altered or dropped: {', '.join(dropped[:5])}")

    # 4. Modernisation: accents appearing where the source had none.
    if _UMLAUT.search(cleaned) and not _UMLAUT.search(raw):
        result.ok = False
        result.reasons.append("accents introduced where the source had none")

    return result


def check_structure_only(original: str, structured: str) -> GuardResult:
    """Verify that structuring preserved every word of the original.

    This is stricter than check() — it requires exact word-sequence equality
    (whitespace-insensitive). The structuring stage must never alter a word;
    it may only add paragraph breaks and blank lines.
    """
    result = GuardResult(ok=True)

    if not structured.strip():
        result.ok = False
        result.reasons.append("output empty")
        return result

    original_words = _words(original)
    structured_words = _words(structured)

    if len(original_words) != len(structured_words):
        result.ok = False
        result.words_deleted = abs(len(original_words) - len(structured_words))
        if len(original_words) > len(structured_words):
            result.reasons.append(
                f"structured text has {result.words_deleted} fewer word(s) than original"
            )
        else:
            result.reasons.append(
                f"structured text has {result.words_deleted} more word(s) than original"
            )
        return result

    for i, (orig, struct) in enumerate(zip(original_words, structured_words)):
        if orig != struct:
            result.ok = False
            result.reasons.append(
                f"word {i+1} differs: '{orig}' -> '{struct}'"
            )
            break

    return result


def apply(raw: str, cleaned: str) -> tuple[str, GuardResult]:
    """Return the text to keep, plus the verdict.

    When the guard is disabled the cleaned text passes through unexamined.
    """
    if not cfg("cleanup_guard"):
        return cleaned, GuardResult(ok=True, reasons=["guard disabled"])

    result = check(raw, cleaned)
    if result.ok:
        return cleaned, result

    log.warning("Cleanup rejected, keeping raw text: %s", "; ".join(result.reasons))
    return raw, result
