# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Experimental structured-prompt variant, for A/B measurement only via
scripts/measure_ocr_accuracy.py. See OLMOCR2_OPTIMISATION_FINDINGS.md s3 —
olmOCR-2-7B-1025 was trained toward YAML-front-matter + Markdown output, not
the raw-text prompt this app uses by default. Whether raw or structured wins
for this app's users is an open, unmeasured question; this only makes the
comparison possible, it does not decide it."""

from artifice_ocr.stages import ocr


def test_default_style_is_raw_and_unchanged():
    assert ocr._STRUCTURED_PROMPT_ADDENDUM not in ocr._effective_prompt("", style="raw")
    assert ocr._effective_prompt("", style="raw") == ocr.OCR_PROMPT


def test_structured_style_asks_for_markdown_and_front_matter():
    prompt = ocr._effective_prompt("", style="structured")
    assert "yaml" in prompt.lower() or "front matter" in prompt.lower()
    assert "markdown" in prompt.lower()


def test_instruction_and_structured_style_compose():
    prompt = ocr._effective_prompt("Expect handwritten German.", style="structured")
    assert "Expect handwritten German." in prompt
    assert "markdown" in prompt.lower()


def test_default_config_key_is_raw():
    from artifice_ocr.config import _DEFAULTS

    assert _DEFAULTS["ocr_prompt_style"] == "raw"
