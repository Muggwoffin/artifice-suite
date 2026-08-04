#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Find UI controls that render but are wired to nothing.

Artifice apps kept shipping controls that look functional and are not: a Save
button with no handler, a Test Connection button duplicated so the second copy
was unreachable, and three element ids cached in JS that had never existed in
any template (which threw and disabled *every* control on the page). None of
these are visible in a diff and none fail a test. This finds them statically.

    uv run python scripts/audit-controls.py            # all four apps
    uv run python scripts/audit-controls.py graph      # one app

Exits non-zero if anything is unbound (in either direction), so it can gate CI.

It counts four ways a control can legitimately be bound:

  1. by id or class in an external static/*.js
  2. by id or class in an inline <script> block in any template
  3. by an inline on* attribute on the element itself
  4. dynamically — the id is assembled at runtime from a static prefix
     (e.g. `` `set-${key}` `` or `` "set-" + key ``).  These controls are
     reported in a separate category rather than condemned.

The reverse direction (JS → template) checks every element id that JS looks
up via getElementById, querySelector(\"#x\"), querySelectorAll(\"#x\"), and
recognised getElementById wrapper functions (e.g. the ``$`` idiom), asserting
that each one appears as an id= in some template or static HTML.  It reuses
the same dynamic-prefix carve-out so that runtime-assembled ids are reported
separately rather than condemned.
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


# ---------------------------------------------------------------------------
# JS → template reverse check: find ids the JS looks up that have no
# matching id= in any template.
# ---------------------------------------------------------------------------

# getElementById("x") or getElementById('x')
_GET_BY_ID_LITERAL = re.compile(r"getElementById\(\s*[\"']([A-Za-z0-9_-]+)[\"']\s*\)")

# querySelector("...#x...") and querySelectorAll("...#x...") — capture the
# entire selector string; id portions are extracted from each match.
_QUERY_SEL_STRING = re.compile(r"querySelector(?:All)?\(\s*[\"']([^\"']+)[\"']\s*\)")

# id portion extractor (applied to selector strings)
_ID_SELECTOR = re.compile(r"#([A-Za-z0-9_-]+)")

# Array literal fed into forEach/map that calls getElementById, e.g.:
#   ["id1", "id2", ...].forEach(id => { els[id] = document.getElementById(id); })
_ARRAY_FEEDING = re.compile(
    r"\[([^\]]+)\]\.(?:forEach|map)\s*\([^)]*\bgetElementById\b", re.DOTALL
)

# Wrapper detection: ``var $ = function(id) { return document.getElementById(id); }``
_WRAPPER_TRAD = re.compile(
    r"(?:var|let|const)\s+(\w+)\s*=\s*function\s*\(\s*(\w+)\s*\)\s*\{"
    r"[^}]*return\s+document\.getElementById\(\s*\2\s*\)",
    re.DOTALL,
)

# Wrapper detection: ``const $ = (id) => document.getElementById(id);``
_WRAPPER_ARROW = re.compile(
    r"(?:var|let|const)\s+(\w+)\s*=\s*\(\s*(\w+)\s*\)\s*=>\s*document\.getElementById\(\s*\2\s*\)"
)

# Wrapper call: NAME("x") or NAME('x') — matched only when NAME is a known wrapper
_WRAPPER_CALL = re.compile(r"(\w+)\s*\(\s*[\"']([A-Za-z0-9_-]+)[\"']\s*\)")


def _find_getelementbyid_wrappers(js: str) -> set[str]:
    """Return names of variables defined as simple getElementById wrappers."""
    wrappers: set[str] = set()
    for pattern in (_WRAPPER_TRAD, _WRAPPER_ARROW):
        for m in pattern.finditer(js):
            wrappers.add(m.group(1))
    return wrappers


def _collect_js_referenced_ids(js: str, wrapper_names: set[str]) -> set[str]:
    """Collect every element id that JS references through id-lookup APIs.

    Covers ``getElementById("x")``, ``querySelector("#x")``,
    ``querySelectorAll("#x")``, array→forEach→getElementById patterns, and
    recognised wrapper functions (e.g. ``$("x")``).
    """
    ids: set[str] = set()

    # getElementById("x") / getElementById('x')
    for m in _GET_BY_ID_LITERAL.finditer(js):
        ids.add(m.group(1))

    # querySelector / querySelectorAll — extract #id portions
    for m in _QUERY_SEL_STRING.finditer(js):
        selector = m.group(1)
        for id_m in _ID_SELECTOR.finditer(selector):
            ids.add(id_m.group(1))

    # Array literal → forEach/map → getElementById
    for m in _ARRAY_FEEDING.finditer(js):
        array_body = m.group(1)
        for str_m in re.finditer(r"[\"']([A-Za-z0-9_-]+)[\"']", array_body):
            ids.add(str_m.group(1))

    # Wrapper calls: NAME("x") where NAME is a known wrapper
    if wrapper_names:
        for m in _WRAPPER_CALL.finditer(js):
            if m.group(1) in wrapper_names:
                ids.add(m.group(2))

    return ids


def _collect_template_ids(html_texts: list[str]) -> set[str]:
    """Collect every ``id=\"...\"`` from a list of HTML source strings."""
    ids: set[str] = set()
    for text in html_texts:
        for m in re.finditer(r'id="([A-Za-z0-9_-]+)"', text):
            ids.add(m.group(1))
    return ids


# id= inside a template literal or string (innerHTML): ``id="my-id"``
_JS_HTML_ID = re.compile(r'id="([A-Za-z0-9_-]+)"')

# element.id = "x" or element.id = 'x' (assignment)
_JS_DOT_ID = re.compile(r'\.id\s*=\s*["\']([A-Za-z0-9_-]+)["\']')

# setAttribute("id", "x")
_JS_SET_ATTR_ID = re.compile(r'setAttribute\(\s*["\']id["\']\s*,\s*["\']([A-Za-z0-9_-]+)["\']\s*\)')


def _collect_js_created_ids(js: str) -> set[str]:
    """Collect every element id that the JS itself creates at runtime.

    Covers ``el.id = "x"``, ``setAttribute("id", "x")``, and ``id="x"``
    inside template-literals / strings that get injected as innerHTML.
    """
    ids: set[str] = set()
    for m in _JS_DOT_ID.finditer(js):
        ids.add(m.group(1))
    for m in _JS_SET_ATTR_ID.finditer(js):
        ids.add(m.group(1))
    for m in _JS_HTML_ID.finditer(js):
        ids.add(m.group(1))
    return ids


_AuditResult = tuple[
    list[tuple[str, str, str]],      # unbound  (template → JS)
    list[tuple[str, str, str]],      # dynamic  (template → JS, dynamic prefix)
    set[str],                        # rejected_prefixes
    list[str],                       # reverse_unbound  (JS → template)
    list[str],                       # reverse_dynamic  (JS → template, dynamic prefix)
] | None


def audit(app: str) -> _AuditResult:
    """Return ``(unbound, dynamic, rejected, rev_unbound, rev_dynamic)``, or *None*.

    **Forward** (template → JS):
    *unbound* entries are controls with no reachable binding — a real finding.
    *dynamic* entries are controls whose id begins with a prefix that is
    assembled at runtime in JS — known to be safe.
    *rejected_prefixes* are dynamic-binding candidates that the permissive
    pattern found but the strict rule refused (too short or no separator).

    **Reverse** (JS → template):
    *rev_unbound* are element ids that JS looks up but that appear in no
    template — a real finding (the same class as the motivating incident).
    *rev_dynamic* are ids whose prefix matches a dynamic construction pattern,
    reported separately.
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
    js_sources: list[str] = [
        p.read_text(encoding="utf-8")
        for p in sorted((web / "static").rglob("*.js"))
    ]
    html_texts: list[str] = []
    for html_file in html_files:
        text = html_file.read_text(encoding="utf-8")
        html_texts.append(text)
        js_sources.extend(SCRIPT.findall(text))
    js = "\n".join(js_sources)

    def referenced(name: str) -> bool:
        return re.search(r"\b" + re.escape(name) + r"\b", js) is not None

    dynamic_prefixes, rejected_prefixes = _collect_dynamic_prefixes(js)

    # ── Forward check: template controls with no JS binding ──────────
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

    # ── Reverse check: JS-referenced ids not in any template ─────────
    wrapper_names = _find_getelementbyid_wrappers(js)
    js_ids = _collect_js_referenced_ids(js, wrapper_names)
    template_ids = _collect_template_ids(html_texts)

    # Also treat ids that JS creates at runtime (el.id = "x", innerHTML)
    # as "known" — a JS-created element that JS later looks up is not a bug.
    js_created_ids = _collect_js_created_ids(js)
    all_known_ids = template_ids | js_created_ids

    reverse_unbound: list[str] = []
    reverse_dynamic: list[str] = []
    for js_id in sorted(js_ids):
        if js_id in all_known_ids:
            continue
        if any(js_id.startswith(p) for p in dynamic_prefixes):
            reverse_dynamic.append(js_id)
            continue
        reverse_unbound.append(js_id)

    return unbound, dynamic, rejected_prefixes, reverse_unbound, reverse_dynamic


def main() -> int:
    targets = sys.argv[1:] or APPS
    unbound_total = 0
    for app in targets:
        findings = audit(app)
        if findings is None:
            print(f"artifice-{app}: no web/templates or static/index.html, skipped")
            continue
        unbound, dynamic, rejected, rev_unbound, rev_dynamic = findings
        unbound_total += len(unbound) + len(rev_unbound)

        # ── Forward findings ────────────────────────────────────────
        if unbound or dynamic:
            if unbound:
                print(f"artifice-{app}: {len(unbound)} unbound control(s)")
                for template, kind, element_id in unbound:
                    print(f"  {template:20} {kind:9} #{element_id}")
            else:
                print(f"artifice-{app}: clean (0 unbound controls)")
            if dynamic:
                print(f"artifice-{app}: {len(dynamic)} control(s) dynamically bound, "
                      "not statically verifiable")
                for template, kind, element_id in dynamic:
                    print(f"  {template:20} {kind:9} #{element_id}")
        else:
            print(f"artifice-{app}: clean (0 unbound controls)")

        # ── Reverse findings ─────────────────────────────────────────
        if rev_unbound:
            print(f"artifice-{app}: REVERSE: {len(rev_unbound)} id(s) in JS not "
                  f"found in any template")
            for js_id in rev_unbound:
                print(f"  #{js_id} (looked up in JS but absent from templates)")
        else:
            print(f"artifice-{app}: reverse clean (0 missing template ids)")

        if rev_dynamic:
            print(f"artifice-{app}: REVERSE: {len(rev_dynamic)} id(s) dynamically "
                  f"constructed, not statically verifiable")
            for js_id in rev_dynamic:
                print(f"  #{js_id}")

        # ── Rejected prefixes ────────────────────────────────────────
        if rejected:
            print(f"artifice-{app}: {len(rejected)} dynamic prefix(es) rejected "
                  f"(too short or no separator): {', '.join(sorted(rejected))}")

    if unbound_total:
        print(f"\n{unbound_total} unbound item(s) total (forward + reverse).")
    return 1 if unbound_total else 0


if __name__ == "__main__":
    raise SystemExit(main())
