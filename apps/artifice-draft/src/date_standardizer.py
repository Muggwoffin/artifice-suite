"""Date format normalization per journal style guide preferences."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.style_guides import load_guide

# Matches dates like: 3/4/1918, 03/04/1918, 3-4-1918
_AMBIGUOUS_MDY_RE = re.compile(
    r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b"
)

# Matches dates like: March 12, 1945 or March 12 1945
_MONTH_DAY_YEAR_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)

# Matches dates like: 12 March 1945
_DAY_MONTH_YEAR_RE = re.compile(
    r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})\b",
    re.IGNORECASE,
)

# Matches approximate dates: c. 1450, ca. 12th century, circa 1800
_APPROX_DATE_RE = re.compile(
    r"\b(c\.?|ca\.?|circa|c\.?\s*)\s*(\d{1,4}(?:\s*(?:th|st|nd|rd)\s+century)?)\b",
    re.IGNORECASE,
)

# Month name to number mapping
_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}
_MONTH_NAMES = list(_MONTHS.keys())

# Date format templates per guide
_FORMATS = {
    "chicago": "{day} {month} {year}",       # 12 March 1945
    "mla": "{month} {day}, {year}",           # March 12, 1945
    "apa": "{month} {day}, {year}",           # March 12, 1945
}


@dataclass
class DateAdvisory:
    """A single date formatting advisory."""

    paragraph_index: int
    rule: str
    message: str
    severity: str  # "warning" | "info"
    original_text: str = ""
    suggested_fix: str | None = None


def _format_date(day: str, month_name: str, year: str, fmt_template: str) -> str:
    """Format a date according to a template."""
    day_int = int(day)
    month_lower = month_name.lower()
    month_num = _MONTHS.get(month_lower, "01")
    month_abbr = month_name[:3] if len(month_name) > 3 else month_name

    return fmt_template.format(
        day=str(day_int),
        month=month_name.capitalize() if len(month_name) > 3 else month_abbr,
        month_abbr=month_abbr,
        year=year,
        month_num=month_num,
    )


def standardize_dates(
    paragraphs: list[dict],
    guide_name: str = "",
) -> list[DateAdvisory]:
    """Check and suggest date format normalization.

    Args:
        paragraphs: Parsed paragraph dicts from doc_parser.
        guide_name: Name of the active style guide.

    Returns:
        List of DateAdvisory objects describing issues found.
    """
    advisories: list[DateAdvisory] = []
    guide = load_guide(guide_name) if guide_name else None

    fmt_template = _FORMATS.get(guide_name.lower() if guide_name else "", "")

    for para in paragraphs:
        idx = para["paragraph_index"]
        text = para["text"]

        # Check for ambiguous M/D/Y dates
        for match in _AMBIGUOUS_MDY_RE.finditer(text):
            part1, part2, year = int(match.group(1)), int(match.group(2)), match.group(3)
            # If both parts are <= 12, it's ambiguous (could be M/D or D/M)
            if part1 <= 12 and part2 <= 12:
                advisories.append(DateAdvisory(
                    paragraph_index=idx,
                    rule="ambiguous_date",
                    message=(
                        f"Date '{match.group()}' is ambiguous — "
                        f"could be {part1}/{part2}/{year} or {part2}/{part1}/{year}. "
                        f"Use an unambiguous format (e.g., '12 March {year}' or 'March 12, {year}')."
                    ),
                    severity="warning",
                    original_text=match.group(),
                ))

        # Check for M/D/Y format and suggest guide-appropriate format
        if fmt_template:
            for match in _AMBIGUOUS_MDY_RE.finditer(text):
                part1, part2, year = int(match.group(1)), int(match.group(2)), match.group(3)
                if part1 > 12 or part2 > 12:
                    # Unambiguous — one part must be the month
                    if part1 > 12:
                        day, month_num = str(part1), str(part2)
                    else:
                        day, month_num = str(part2), str(part1)
                    month_name = [k for k, v in _MONTHS.items() if v == month_num.zfill(2)]
                    if month_name:
                        suggested = _format_date(day, month_name[0], year, fmt_template)
                        advisories.append(DateAdvisory(
                            paragraph_index=idx,
                            rule="date_format_normalization",
                            message=f"Consider using {fmt_template.replace('{day}', 'DD').replace('{month}', 'Month').replace('{year}', 'YYYY')} format.",
                            severity="info",
                            original_text=match.group(),
                            suggested_fix=suggested,
                        ))

            # Check M/D/Y in Month Day, Year form vs guide preference
            for match in _MONTH_DAY_YEAR_RE.finditer(text):
                month_name, day, year = match.group(1), match.group(2), match.group(3)
                if guide_name.lower() == "chicago":
                    suggested = _format_date(day, month_name, year, fmt_template)
                    if suggested != match.group():
                        advisories.append(DateAdvisory(
                            paragraph_index=idx,
                            rule="date_format_normalization",
                            message=f"Chicago style prefers day-month-year format.",
                            severity="info",
                            original_text=match.group(),
                            suggested_fix=suggested,
                        ))

    return advisories
