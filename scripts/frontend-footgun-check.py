#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Frontend footgun check: catches three bug patterns that shipped and required live-browser
verification to catch during the 2026-08-10 session.

Pattern 1: unguarded top-level `.addEventListener` calls (throw when the target element is
absent on the current page — e.g. an editor-only element referenced on an /about page).

Pattern 2: inline <script> blocks in Jinja templates containing addEventListener (invisible to
audits that only scan static/*.js — this caused the "five dead controls" incident, commit
e74d243).

Pattern 3: `.catch(() => {})`-shaped silent swallows with an empty body.

TODO: not yet covered — script-load-order check (bind.js/toast.js vs app.js), unguarded
module-scope function calls whose body itself does unguarded DOM writes (e.g. loadSettings()),
and the CSS `.hidden` id-vs-class selector mismatch check. These need more context-sensitive
analysis than this pass attempts.

Exit: 0 if clean, 1 if any violations found.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

JS_GLOB = "apps/*/src/*/web/static/**/*.js"
HTML_GLOB = "apps/*/src/*/web/templates/**/*.html"

ADD_LISTENER_RE = re.compile(
    r'^\s{0,2}([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.addEventListener\('
)
GUARD_IF_RE = re.compile(r'^\s*if\s*\(\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\)')
BIND_IF_PRESENT_RE = re.compile(r'window\.ArtificeBind\.bindIfPresent\(')

EMPTY_CATCH_RE = re.compile(
    r'\.catch\(\s*(?:function\s*\([^)]*\)|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)\s*\{\s*\}\s*\)'
)

SCRIPT_TAG_RE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)


def check_unguarded_listeners(path: Path) -> list[str]:
    violations = []
    lines = path.read_text(encoding="utf-8").splitlines()
    depth = 0
    prev_line = ""
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if depth == 0:
            m = ADD_LISTENER_RE.match(line)
            if m:
                ident = m.group(1)
                base = ident.split(".")[0]
                if base == "document" or BIND_IF_PRESENT_RE.search(line):
                    pass
                else:
                    guard_match = GUARD_IF_RE.match(line) or GUARD_IF_RE.match(prev_line)
                    guarded = bool(guard_match and guard_match.group(1) == ident)
                    if not guarded:
                        violations.append(
                            f"{path}:{i}: unguarded top-level .addEventListener "
                            f"on `{ident}` — {stripped}"
                        )
        depth += line.count("{") - line.count("}")
        prev_line = line
    return violations


def check_inline_script_bindings(path: Path) -> list[str]:
    violations = []
    text = path.read_text(encoding="utf-8")
    for m in SCRIPT_TAG_RE.finditer(text):
        body = m.group(1)
        if "addEventListener" in body:
            line_no = text[: m.start()].count("\n") + 1
            violations.append(
                f"{path}:{line_no}: inline <script> block contains addEventListener "
                "— move to an external .js file"
            )
    return violations


def check_empty_catch(path: Path) -> list[str]:
    violations = []
    text = path.read_text(encoding="utf-8")
    for m in EMPTY_CATCH_RE.finditer(text):
        # HTMLMediaElement.play() returns a Promise that rejects whenever
        # playback is interrupted (e.g. a near-simultaneous pause(), or a
        # user re-triggering play on the same element) — an empty .catch()
        # here is the standard, MDN-documented way to silence that specific,
        # harmless rejection, not a swallowed error. Exempt it rather than
        # forcing a toast on routine media interaction.
        preceding = text[max(0, m.start() - 12) : m.start()]
        if preceding.endswith(".play()"):
            continue
        line_no = text[: m.start()].count("\n") + 1
        violations.append(
            f"{path}:{line_no}: empty .catch() swallow — surface the error "
            "(e.g. window.ArtificeToast.error)"
        )
    return violations


def main() -> int:
    all_violations: list[str] = []

    for path in sorted(REPO_ROOT.glob(JS_GLOB)):
        all_violations.extend(check_unguarded_listeners(path))
        all_violations.extend(check_empty_catch(path))

    for path in sorted(REPO_ROOT.glob(HTML_GLOB)):
        all_violations.extend(check_inline_script_bindings(path))

    if all_violations:
        print(f"frontend-footgun-check: {len(all_violations)} violation(s) found\n")
        for v in all_violations:
            print(v)
        return 1

    print("frontend-footgun-check: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
