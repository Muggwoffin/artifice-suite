"""Tests for the cleanup content-preservation guard.

The fixtures are real failure cases from the ISK archive audit, not invented
ones: each of these is something gemma4:12b actually did to a page.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.ocr_pipeline import _guard, config


@pytest.fixture(autouse=True)
def strict_guard():
    """Run each test against the shipped defaults."""
    config.apply_overrides({
        "cleanup_guard": True,
        "cleanup_guard_max_deleted_words": 2,
        "cleanup_guard_min_length_ratio": 0.97,
        "cleanup_guard_protect_nouns": True,
    })
    yield
    config.reset()
    config.load_config()


# --------------------------------------------------------------------------- #
# things the guard must reject
# --------------------------------------------------------------------------- #

def test_rejects_deleted_clause():
    """IMG_7186: a fragmentary SOE cable had whole clauses removed."""
    raw = ("ly safe in Italian occupied zone. Unwilling tzerland as he sees no "
           "useful activity here. to join you but only if he can work.")
    cleaned = ("ly safe in Italian occupied zone. Unwilling to join you but "
               "only if he can work.")

    result = _guard.check(raw, cleaned)

    assert result.ok is False
    assert result.words_deleted >= 8
    assert any("deleted" in r for r in result.reasons)


def test_rejects_corrupted_place_name_even_when_other_copies_survive():
    """IMG_7317: Elsass appeared five times; only the third was corrupted.

    A set-based check misses this entirely, which is why nouns are counted.
    """
    raw = ("Chef der Zivilverwaltung im Elsass (Abteilung...) einreichen. "
           "Dienststellen im Elsass melden. Verwaltung im Elsass bestimmt.")
    cleaned = ("Chef der Zivilverwaltung im Elsass (Abteilung...) einreichen. "
               "Dienststellen im Elsass melden. Verwaltung im Elass bestimmt.")

    result = _guard.check(raw, cleaned)

    assert result.ok is False
    assert "Elsass" in result.nouns_dropped


def test_rejects_corruption_of_an_already_correct_word():
    """IMG_7278: Gewerkschaftern -> Gewerkshaftern, a word that was fine."""
    raw = "zwischen den ehemaligen Gewerkschaftern und den Arbeiternachwuchs"
    cleaned = "zwischen den ehemaligen Gewerkshaftern und den Arbeiternachwuchs"

    result = _guard.check(raw, cleaned)

    assert result.ok is False
    assert "Gewerkschaftern" in result.nouns_dropped


def test_rejects_wholesale_shrinkage():
    raw = "Ein sehr langer Absatz mit vielen Woertern, der erhalten bleiben muss."
    cleaned = "Ein kurzer Absatz."

    result = _guard.check(raw, cleaned)

    assert result.ok is False
    assert result.length_ratio < 0.97


def test_rejects_introduced_accents():
    raw = "Der Bericht ueber die Taetigkeit war unvollstandig."
    cleaned = "Der Bericht über die Tätigkeit war unvollständig."

    result = _guard.check(raw, cleaned)

    assert result.ok is False
    assert any("accent" in r for r in result.reasons)


def test_rejects_empty_output():
    result = _guard.check("Some real archival text here.", "   ")

    assert result.ok is False
    assert "output empty" in result.reasons


# --------------------------------------------------------------------------- #
# things the guard must allow
# --------------------------------------------------------------------------- #

def test_allows_hyphenated_line_rejoin():
    """The repair cleanup exists to make must survive the guard."""
    raw = "Der Be-\nricht war unvollstandig und teilweise unklar."
    cleaned = "Der Bericht war unvollstandig und teilweise unklar."

    result = _guard.check(raw, cleaned)

    assert result.ok is True, result.reasons


def test_allows_lowercase_typo_fix():
    raw = "Es scheint, dass die Verbindung unterbrocheu war."
    cleaned = "Es scheint, dass die Verbindung unterbrochen war."

    result = _guard.check(raw, cleaned)

    assert result.ok is True, result.reasons


def test_capitalised_word_protection_covers_all_german_nouns():
    """A documented consequence, not an accident.

    German capitalises every noun, so protecting capitalised words means the
    model may not touch German nouns at all — including the rn->m repair in
    "Narnen" -> "Namen", which is a fix we would otherwise want. That is the
    price of blocking "Elsass" -> "Elass", and it is why the rejected text is
    kept in the JSON for review and why the rule has an off switch.
    """
    raw = "Die Narnen der Mitglieder konnten nicht ermittelt werden."
    cleaned = "Die Namen der Mitglieder konnten nicht ermittelt werden."

    assert _guard.check(raw, cleaned).ok is False

    config.apply_overrides({"cleanup_guard_protect_nouns": False})
    assert _guard.check(raw, cleaned).ok is True


def test_allows_whitespace_only_change():
    raw = "Es  scheint , dass die Verbindung  unterbrochen war."
    cleaned = "Es scheint, dass die Verbindung unterbrochen war."

    result = _guard.check(raw, cleaned)

    assert result.ok is True, result.reasons


def test_allows_unchanged_text():
    text = "Der Bericht ueber die Taetigkeit der Gruppe war unvollstandig."

    assert _guard.check(text, text).ok is True


def test_noun_protection_can_be_disabled():
    """Turning the rule off should let a name fix through (CAHTOLIC -> CATHOLIC)."""
    raw = "ADDRESS OF THE CAHTOLIC MISSION IN BERNE"
    cleaned = "ADDRESS OF THE CATHOLIC MISSION IN BERNE"

    assert _guard.check(raw, cleaned).ok is False

    config.apply_overrides({"cleanup_guard_protect_nouns": False})
    assert _guard.check(raw, cleaned).ok is True


# --------------------------------------------------------------------------- #
# integration with the stage
# --------------------------------------------------------------------------- #

@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_stage_keeps_raw_text_when_guard_rejects(mock_chat, tmp_path):
    from src.ocr_pipeline.stages import cleanup

    raw = ("ly safe in Italian occupied zone. Unwilling tzerland as he sees no "
           "useful activity here. to join you but only if he can work.")
    lossy = "ly safe in Italian occupied zone. Unwilling to join you."
    mock_chat.return_value = MagicMock(message=MagicMock(content=lossy))

    result = cleanup.perform(raw, source_file="page.tif", output_dir=str(tmp_path))

    assert result["cleaned_text"] == raw            # raw survives
    assert result["guard"]["ok"] is False
    assert result["rejected_cleaned_text"] == lossy  # kept for review

    written = (tmp_path / "cleaned" / "text" / "page.txt").read_text(encoding="utf-8")
    assert written == raw


@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_stage_accepts_a_safe_repair(mock_chat, tmp_path):
    from src.ocr_pipeline.stages import cleanup

    raw = "Der Be-\nricht war unvollstandig."
    good = "Der Bericht war unvollstandig."
    mock_chat.return_value = MagicMock(message=MagicMock(content=good))

    result = cleanup.perform(raw, source_file="page.tif", output_dir=str(tmp_path))

    assert result["cleaned_text"] == good
    assert result["guard"]["ok"] is True
    assert "rejected_cleaned_text" not in result


@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_guard_can_be_switched_off_entirely(mock_chat, tmp_path):
    from src.ocr_pipeline.stages import cleanup

    config.apply_overrides({"cleanup_guard": False})
    raw = "A much longer piece of archival text that should have been preserved."
    mock_chat.return_value = MagicMock(message=MagicMock(content="short"))

    result = cleanup.perform(raw, source_file="page.tif", output_dir=str(tmp_path))

    assert result["cleaned_text"] == "short"


# --------------------------------------------------------------------------- #
# OCR degeneracy guard: greedy decoding looping on hallucinated filler
# --------------------------------------------------------------------------- #
#
# Real failure mode, not a hypothetical: a Tropy page scanned upside-down
# (R_58_373_0060), with nothing anywhere — not Tropy's own orientation
# metadata, not the file's EXIF — saying so. Fed to the OCR model as-is, it
# hallucinated a plausible-sounding German sentence and then had no way to
# stop repeating it: 900+ lines of one sentence on that page, a 3-line cycle
# repeated ~30 times on another in the same folder. Unlike the cleanup/
# structure guards above, there is no source text to fall back to here.

def test_repetition_guard_rejects_a_single_line_looped():
    looped = "\n\n".join(["Verwaltung Werte von Welleben eine Grundlage setzen."] * 50)

    result = _guard.check_no_repetition_loop(looped)

    assert result.ok is False
    assert "unique" in result.reasons[0]


def test_repetition_guard_rejects_a_short_cycle():
    """A same-line-N-times-in-a-row check would miss this: no single line
    ever repeats twice in a row, only the 3-line cycle as a whole does."""
    cycle = [
        "First line of the hallucinated cycle.",
        "Second line of the hallucinated cycle.",
        "Third line of the hallucinated cycle.",
    ]
    looped = "\n\n".join(cycle * 15)

    result = _guard.check_no_repetition_loop(looped)

    assert result.ok is False


def test_repetition_guard_accepts_real_varied_text():
    real = "\n\n".join(
        f"This is genuinely distinct archival sentence number {i} of the page."
        for i in range(40)
    )

    result = _guard.check_no_repetition_loop(real)

    assert result.ok is True, result.reasons


def test_repetition_guard_ignores_short_output():
    """Too little text for 'repetition' to mean anything — a short page
    legitimately repeating a couple of header lines must not trip this."""
    short = "Abschrift\n\naus\n\nden Akten 303/4 - Württemberg\n\nAbschrift der Anlage"

    result = _guard.check_no_repetition_loop(short)

    assert result.ok is True


def test_repetition_guard_rejects_empty_output():
    result = _guard.check_no_repetition_loop("   ")

    assert result.ok is False
    assert "output empty" in result.reasons
