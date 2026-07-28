#!/usr/bin/env python3
"""Find UI controls that render but are wired to nothing.

Artifice apps kept shipping controls that look functional and are not: a Save
button with no handler, a Test Connection button duplicated so the second copy
was unreachable, and three element ids cached in JS that had never existed in
any template (which threw and disabled *every* control on the page). None of
these are visible in a diff and none fail a test. This finds them statically.

    uv run python scripts/audit-controls.py            # all four apps
    uv run python scripts/audit-controls.py graph      # one app

Exits non-zero if anything is unbound, so it can gate CI.

It counts three ways a control can legitimately be bound, and missing any of
them produces false positives — an earlier hand-rolled version of this check
scanned only `static/*.js` and wrongly condemned five controls that were bound
in a template's own inline <script>:

  1. by id or class in an external static/*.js
  2. by id or class in an inline <script> block in any template
  3. by an inline on* attribute on the element itself
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPS = ["ocr", "draft", "graph", "transcribe"]

TAG = re.compile(r"<(button|input|select|textarea|form)\b[^>]*?>", re.S | re.I)
ID_ATTR = re.compile(r'\bid="([A-Za-z0-9_-]+)"')
CLASS_ATTR = re.compile(r'\bclass="([^"]*)"')
ON_ATTR = re.compile(r'\bon[a-z]+\s*=\s*"[^"]+"')
SCRIPT = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)


def audit(app: str) -> list[tuple[str, str, str]]:
    slug = app.replace("-", "_")
    web = REPO / "apps" / f"artifice-{app}" / "src" / f"artifice_{slug}" / "web"
    templates = sorted((web / "templates").glob("*.html")) if (web / "templates").is_dir() else []
    if not templates:
        return []

    sources = [p.read_text(encoding="utf-8") for p in sorted((web / "static").rglob("*.js"))]
    for tpl in templates:
        sources.extend(SCRIPT.findall(tpl.read_text(encoding="utf-8")))
    js = "\n".join(sources)

    def referenced(name: str) -> bool:
        return re.search(r"\b" + re.escape(name) + r"\b", js) is not None

    unbound: list[tuple[str, str, str]] = []
    for tpl in templates:
        for match in TAG.finditer(tpl.read_text(encoding="utf-8")):
            tag = match.group(0)
            found_id = ID_ATTR.search(tag)
            if not found_id:
                continue
            element_id = found_id.group(1)
            if referenced(element_id) or ON_ATTR.search(tag):
                continue
            classes = CLASS_ATTR.search(tag)
            if classes and any(referenced(c) for c in classes.group(1).split()):
                continue
            unbound.append((tpl.name, match.group(1).lower(), element_id))
    return unbound


def main() -> int:
    targets = sys.argv[1:] or APPS
    total = 0
    for app in targets:
        slug = app.replace("-", "_")
        findings = audit(app)
        total += len(findings)
        if not (REPO / "apps" / f"artifice-{app}" / "src" / f"artifice_{slug}" / "web" / "templates").is_dir():
            print(f"artifice-{app}: no web/templates, skipped")
            continue
        if findings:
            print(f"artifice-{app}: {len(findings)} unbound control(s)")
            for template, kind, element_id in findings:
                print(f"  {template:20} {kind:9} #{element_id}")
        else:
            print(f"artifice-{app}: clean")
    if total:
        print(f"\n{total} control(s) render but are bound to nothing.")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
