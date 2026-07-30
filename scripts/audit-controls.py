#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Find UI controls that render but are wired to nothing.

Artifice apps kept shipping controls that look functional and are not: a Save
button with no handler, a Test Connection button duplicated so the second copy
was unreachable, and three element ids cached in JS that had never existed in
any template (which threw and disabled *every* control on the page). None of
these are visible in a diff and none fail a test. This finds them statically.

    uv run python scripts/audit-controls.py            # all four apps
    uv run python scripts/audit-controls.py graph      # one app

Exits non-zero if anything is unbound, so it can gate CI.

It counts four ways a control can legitimately be bound:

  1. by id or class in an external static/*.js
  2. by id or class in an inline <script> block in any template
  3. by an inline on* attribute on the element itself
  4. dynamically — the id is assembled at runtime from a static prefix
     (e.g. `` `set-${key}` `` or `` "set-" + key ``).  These controls are
     reported in a separate category rather than condemned.
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

# ---------------------------------------------------------------------------
# Dynamic id construction patterns
#   Template literal:  `` `prefix${...}` ``
#   String concat:      "prefix" + var   or   'prefix' + var
#
# Two tiers of pattern:
#
#   _PERMISSIVE_*  –  detect ANY candidate (single char allowed).  Used only
#                     to compute the “rejected” set; never for exemption.
#   _STRICT_*      –  the real gate.  Requires ≥ 3 characters AND a trailing
#                     separator (``-`` or ``_``) so that accidental captures
#                     like ``"s" + id`` or `` `dot${...}` `` cannot silently
#                     exempt dozens of unrelated static controls whose ids
#                     just happen to share an initial letter or two.
# ---------------------------------------------------------------------------
_PERMISSIVE_TEMPLATE = re.compile(r"`([A-Za-z0-9][A-Za-z0-9_-]*)\$\{")
_PERMISSIVE_CONCAT = re.compile(r"""["']([A-Za-z0-9][A-Za-z0-9_-]*)["']\s*\+""")

_STRICT_TEMPLATE = re.compile(r"`([A-Za-z0-9][A-Za-z0-9_-]+[-_])\$\{")
_STRICT_CONCAT = re.compile(r"""["']([A-Za-z0-9][A-Za-z0-9_-]+[-_])["']\s*\+""")


def _collect_dynamic_prefixes(js: str) -> tuple[set[str], set[str]]:
    """Return ``(trusted, rejected)`` prefix sets.

    *trusted* — prefixes that pass the strict rule (≥ 3 chars, trailing
      separator).  These are safe to use for dynamic-binding exemption.
    *rejected* — prefixes the permissive pattern found but the strict rule
      rejected.  Reported so a legitimate dynamic convention without a
      separator is never silently dropped into the “unbound” bucket.
    """
    permissive: set[str] = set()
    for m in _PERMISSIVE_TEMPLATE.finditer(js):
        permissive.add(m.group(1))
    for m in _PERMISSIVE_CONCAT.finditer(js):
        permissive.add(m.group(1))

    strict: set[str] = set()
    for m in _STRICT_TEMPLATE.finditer(js):
        strict.add(m.group(1))
    for m in _STRICT_CONCAT.finditer(js):
        strict.add(m.group(1))

    return strict, permissive - strict


def audit(app: str) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]], set[str]] | None:
    """Return ``(unbound, dynamic, rejected_prefixes)``, or *None* if nothing to audit.

    *unbound* entries are controls with no reachable binding — a real finding.
    *dynamic* entries are controls whose id begins with a prefix that is
    assembled at runtime in JS — known to be safe, reported separately so the
    maintainer can see the gate knows about them.
    *rejected_prefixes* are dynamic-binding candidates that the permissive
    pattern found but the strict rule refused (too short or no separator).
    """
    slug = app.replace("-", "_")
    web = REPO / "apps" / f"artifice-{app}" / "src" / f"artifice_{slug}" / "web"

    # Determine which HTML files to scan: templates first, then static index.html
    html_files: list[Path] = []
    if (web / "templates").is_dir():
        html_files = sorted((web / "templates").glob("*.html"))
    if not html_files:
        static_index = web / "static" / "index.html"
        if static_index.is_file():
            html_files = [static_index]

    if not html_files:
        return None  # nothing to audit — no templates and no static index.html

    # Gather all JS source text: external .js files + inline <script> blocks
    sources = [p.read_text(encoding="utf-8") for p in sorted((web / "static").rglob("*.js"))]
    for html_file in html_files:
        sources.extend(SCRIPT.findall(html_file.read_text(encoding="utf-8")))
    js = "\n".join(sources)

    def referenced(name: str) -> bool:
        return re.search(r"\b" + re.escape(name) + r"\b", js) is not None

    dynamic_prefixes, rejected_prefixes = _collect_dynamic_prefixes(js)

    unbound: list[tuple[str, str, str]] = []
    dynamic: list[tuple[str, str, str]] = []
    for html_file in html_files:
        for match in TAG.finditer(html_file.read_text(encoding="utf-8")):
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
            # Check dynamic binding: any prefix covers this id?
            if any(element_id.startswith(p) for p in dynamic_prefixes):
                dynamic.append((html_file.name, match.group(1).lower(), element_id))
                continue
            unbound.append((html_file.name, match.group(1).lower(), element_id))
    return unbound, dynamic, rejected_prefixes


def main() -> int:
    targets = sys.argv[1:] or APPS
    unbound_total = 0
    for app in targets:
        findings = audit(app)
        if findings is None:
            print(f"artifice-{app}: no web/templates or static/index.html, skipped")
            continue
        unbound, dynamic, rejected = findings
        unbound_total += len(unbound)
        if unbound or dynamic:
            if unbound:
                print(f"artifice-{app}: {len(unbound)} unbound control(s)")
                for template, kind, element_id in unbound:
                    print(f"  {template:20} {kind:9} #{element_id}")
            else:
                print(f"artifice-{app}: clean (0 unbound)")
            if dynamic:
                print(f"artifice-{app}: {len(dynamic)} control(s) dynamically bound, "
                      "not statically verifiable")
                for template, kind, element_id in dynamic:
                    print(f"  {template:20} {kind:9} #{element_id}")
        else:
            print(f"artifice-{app}: clean")
        if rejected:
            print(f"artifice-{app}: {len(rejected)} dynamic prefix(es) rejected "
                  f"(too short or no separator): {', '.join(sorted(rejected))}")
    if unbound_total:
        print(f"\n{unbound_total} control(s) render but are bound to nothing.")
    return 1 if unbound_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
