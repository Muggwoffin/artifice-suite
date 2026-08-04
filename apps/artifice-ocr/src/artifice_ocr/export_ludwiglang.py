# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._logging import get_logger

log = get_logger("export_ludwiglang")

_PAGE_SUFFIX = re.compile(r"_p(\d{4})$")

MEDIUM_OPTIONS = ("typed", "handwritten", "print")

MAX_BODY_CHARS = 200_000


@dataclass
class ExportPage:
    stem: str
    page_num: int
    json_path: Path
    data: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        if self.data is None:
            return False
        guard = self.data.get("guard", {})
        return guard.get("ok", False) is True

    @property
    def cleaned_text(self) -> str:
        if self.data is None:
            return ""
        return (self.data.get("cleaned_text") or "").strip()


@dataclass
class AssembleResult:
    title: str
    body: str
    page_count: int = 0
    skipped_count: int = 0
    skipped_stems: list[str] = field(default_factory=list)
    body_truncated: bool = False


def _parse_page_num(stem: str) -> int:
    m = _PAGE_SUFFIX.search(stem)
    if m:
        return int(m.group(1))
    return 0


def _discover_pages(collection_dir: Path) -> list[ExportPage]:
    json_dir = collection_dir / "json"
    if not json_dir.exists():
        raise FileNotFoundError(f"No json directory at {json_dir}")

    pages: list[ExportPage] = []
    for jp in sorted(json_dir.iterdir()):
        if jp.suffix != ".json":
            continue
        stem = jp.stem
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Skipping unreadable %s: %s", jp, exc)
            continue
        pages.append(ExportPage(
            stem=stem,
            page_num=_parse_page_num(stem),
            json_path=jp,
            data=data,
        ))

    pages.sort(key=lambda p: p.page_num)
    return pages


def _read_manifest(output_dir: Path) -> dict[str, Any] | None:
    manifest_path = output_dir / "tropy_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _resolve_author_date(
    collection_name: str,
    manifest: dict[str, Any] | None,
) -> tuple[str, str]:
    if manifest is None:
        return ("", "")
    pages = manifest.get("pages", {})
    for stem, info in pages.items():
        prefix = collection_name + "/"
        if stem.startswith(prefix):
            item = info if isinstance(info, dict) else {}
            return (
                item.get("item_title", ""),
                "",
            )
    return ("", "")


def _detect_language(text: str) -> str:
    from .stages.translate import detect_language
    try:
        return detect_language(text)
    except Exception as exc:
        log.warning("Language detection failed: %s", exc)
        return "unknown"


def _build_frontmatter(
    title: str,
    medium: str,
    author: str = "",
    date: str = "",
) -> dict[str, str]:
    fm: dict[str, str] = {
        "title": title,
        "medium": medium,
        "language": "de",
    }
    if author:
        fm["author"] = author
    if date:
        fm["date"] = date
    return fm


def _format_frontmatter(fm: dict[str, str]) -> str:
    lines = ["---"]
    for key, value in fm.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def assemble_collection(
    collection_dir: Path,
    *,
    page_markers: bool = False,
) -> AssembleResult:
    pages = _discover_pages(collection_dir)

    skipped = [p for p in pages if not p.ok]
    kept = [p for p in pages if p.ok]

    body_parts: list[str] = []
    for i, page in enumerate(kept):
        text = page.cleaned_text
        if not text:
            continue
        if page_markers and i > 0:
            body_parts.append(f"-- {page.page_num} --")
        body_parts.append(text)

    body = "\n\n".join(body_parts)
    truncated = False
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS]
        truncated = True

    return AssembleResult(
        title=collection_dir.name,
        body=body,
        page_count=len(kept),
        skipped_count=len(skipped),
        skipped_stems=[p.stem for p in skipped],
        body_truncated=truncated,
    )


def check_language(body: str) -> str | None:
    if not body.strip():
        return "Body is empty — nothing to export."
    lang = _detect_language(body)
    if lang == "en":
        return (
            f"Detected language is English ('{lang}'), not German. "
            "LudwigLang is a German-language tool. Refusing to export."
        )
    return None


def export_md(
    collection_dir: Path,
    *,
    output_path: Path | None = None,
    medium: str = "print",
    author: str = "",
    date: str = "",
    page_markers: bool = False,
    manifest: dict[str, Any] | None = None,
    skip_language_gate: bool = False,
) -> Path:
    if medium not in MEDIUM_OPTIONS:
        raise ValueError(
            f"medium must be one of {MEDIUM_OPTIONS}, got {medium!r}"
        )

    result = assemble_collection(collection_dir, page_markers=page_markers)

    if result.skipped_count:
        log.warning(
            "Skipped %d page(s) with failed guard check: %s",
            result.skipped_count,
            ", ".join(result.skipped_stems),
        )

    if not skip_language_gate:
        lang_error = check_language(result.body)
        if lang_error:
            raise ValueError(lang_error)

    # Resolve author/date from manifest if not provided
    if not author or not date:
        manifest_author, manifest_date = _resolve_author_date(
            result.title, manifest
        )
        if not author:
            author = manifest_author
        if not date:
            date = manifest_date

    fm = _build_frontmatter(
        title=result.title,
        medium=medium,
        author=author,
        date=date,
    )

    if output_path is None:
        output_path = (
            collection_dir.parent.parent
            / "ludwiglang"
            / result.title
            / "text.md"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = _format_frontmatter(fm) + "\n\n" + result.body + "\n"
    output_path.write_text(content, encoding="utf-8")

    log.info(
        "Exported %s (%d pages, %d skipped, %d chars) to %s",
        result.title,
        result.page_count,
        result.skipped_count,
        len(result.body),
        output_path,
    )
    if result.body_truncated:
        log.warning(
            "Body truncated to %d characters (LudwigLang limit)",
            MAX_BODY_CHARS,
        )

    return output_path
