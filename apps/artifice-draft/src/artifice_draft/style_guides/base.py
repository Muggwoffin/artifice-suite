# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Schema for journal style guides."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StyleGuide:
    """A journal style guide that augments the LLM system prompt.

    Each field is free text intended to be read by the LLM as context
    for how to format and edit the document. The ``system_prompt_addendum``
    field is injected directly into the system prompt when this guide is
    active.
    """

    name: str = ""
    edition: str = ""
    citation_style: str = ""
    footnote_format: str = ""
    bibliography_format: str = ""
    heading_capitalization: str = ""
    prose_rules: list[str] = field(default_factory=list)
    quotation_rules: str = ""
    abbreviation_rules: str = ""
    date_format: str = ""
    page_reference_format: str = ""
    url_format: str = ""
    system_prompt_addendum: str = ""
    custom_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "edition": self.edition,
            "citation_style": self.citation_style,
            "footnote_format": self.footnote_format,
            "bibliography_format": self.bibliography_format,
            "heading_capitalization": self.heading_capitalization,
            "prose_rules": self.prose_rules,
            "quotation_rules": self.quotation_rules,
            "abbreviation_rules": self.abbreviation_rules,
            "date_format": self.date_format,
            "page_reference_format": self.page_reference_format,
            "url_format": self.url_format,
            "system_prompt_addendum": self.system_prompt_addendum,
            "custom_rules": self.custom_rules,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StyleGuide:
        return cls(
            name=data.get("name", ""),
            edition=data.get("edition", ""),
            citation_style=data.get("citation_style", ""),
            footnote_format=data.get("footnote_format", ""),
            bibliography_format=data.get("bibliography_format", ""),
            heading_capitalization=data.get("heading_capitalization", ""),
            prose_rules=data.get("prose_rules", []),
            quotation_rules=data.get("quotation_rules", ""),
            abbreviation_rules=data.get("abbreviation_rules", ""),
            date_format=data.get("date_format", ""),
            page_reference_format=data.get("page_reference_format", ""),
            url_format=data.get("url_format", ""),
            system_prompt_addendum=data.get("system_prompt_addendum", ""),
            custom_rules=data.get("custom_rules", []),
        )
