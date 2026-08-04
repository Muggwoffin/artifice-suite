# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for prompts module."""

from __future__ import annotations

from artifice_draft.models import EditingStyle
from artifice_draft.prompts import get_system_prompt, list_styles


def test_list_styles():
    styles = list_styles()
    assert "academic" in styles
    assert "creative" in styles
    assert "concise" in styles
    assert "business" in styles
    assert "custom" in styles


def test_academic_prompt():
    prompt = get_system_prompt(EditingStyle.ACADEMIC)
    assert "academic" in prompt.lower() or "grammar" in prompt.lower()
    assert "JSON" in prompt or "json" in prompt


def test_creative_prompt():
    prompt = get_system_prompt(EditingStyle.CREATIVE)
    assert "creative" in prompt.lower() or "voice" in prompt.lower()


def test_concise_prompt():
    prompt = get_system_prompt(EditingStyle.CONCISE)
    assert "brevity" in prompt.lower() or "concise" in prompt.lower()


def test_business_prompt():
    prompt = get_system_prompt(EditingStyle.BUSINESS)
    assert "business" in prompt.lower() or "professional" in prompt.lower()


def test_custom_prompt():
    custom = "Fix everything, be a pirate."
    prompt = get_system_prompt(EditingStyle.CUSTOM, custom_prompt=custom)
    assert "pirate" in prompt


def test_custom_prompt_empty_falls_back():
    prompt = get_system_prompt(EditingStyle.CUSTOM, custom_prompt="")
    assert len(prompt) > 50


def test_default_is_academic():
    prompt = get_system_prompt()
    assert len(prompt) > 50
