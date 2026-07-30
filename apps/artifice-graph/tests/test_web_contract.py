# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Assert every API path ``pipeline.js`` calls is a registered route.

A renamed or removed route silently breaks the UI and no existing test
notices — this catches exactly that class of failure by introspecting
the FastAPI ``app.routes`` table, which is the single source of truth.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from artifice_graph.web.server import app

_PIPELINE_JS = (
    Path(__file__).resolve().parent.parent
    / "src" / "artifice_graph" / "web" / "static" / "pipeline.js"
)

# ── Extract every /api/... path pipeline.js reaches ──────────────────

# Direct fetch("/api/x") or fetch("/api/x", ...), plus new EventSource("/api/x")
_FETCH_PATH = re.compile(
    r"""(?:fetch|EventSource|fetchJson)\s*\(\s*["']([^"']*/api/[^"']*)["']"""
)

# String literal /api/... paths in object literals (e.g. stageToEndpoint)
_API_LITERAL = re.compile(r"""["'](/api/[A-Za-z0-9_/-]+)["']""")


def _extract_paths(js_text: str) -> set[str]:
    """Return every ``/api/...`` path that ``pipeline.js`` references.

    Covers direct ``fetch("/api/x")``, ``Callopp.fetchJson("/api/x")``,
    ``new EventSource("/api/x")``, and string-literal paths in object
    definitions (e.g. ``stageToEndpoint``) that are later used as
    ``fetch(endpoint, ...)`` arguments.
    """
    paths: set[str] = set()

    for m in _FETCH_PATH.finditer(js_text):
        raw = m.group(1)
        # Strip query string so "/api/stream?run=..." → "/api/stream"
        path = raw.split("?")[0]
        paths.add(path)

    # Also collect string-literal /api/... paths from object literals.
    # These are assigned to variables that the fetch call uses later.
    for m in _API_LITERAL.finditer(js_text):
        path = m.group(1)
        paths.add(path)

    return paths


# ── Extract the HTTP method pipeline.js intends for each call ───────

# Capture a fetch call with a method: fetch("/x", { method: "POST" })
_FETCH_WITH_METHOD = re.compile(
    r"""(?:fetch|fetchJson)\s*\(\s*["']([^"']+/api/[^"']*)["']\s*,\s*\{[^}]*method\s*:\s*["'](\w+)["']""",
    re.DOTALL,
)

# fetch without an explicit method → GET (browser default)
_FETCH_NO_METHOD = re.compile(
    r"""(?:fetch|fetchJson)\s*\(\s*["']([^"']+/api/[^"']*)["']\s*\)"""
)

# EventSource is always GET
_EVENT_SOURCE = re.compile(
    r"""EventSource\s*\(\s*["']([^"']+/api/[^"']*)["']"""
)

# Variable assignment: var endpoint  = "/api/test-connection";
_VAR_TO_PATH = re.compile(
    r"""(?:var|let|const)\s+(\w+)\s*=\s*["'](/api/[^"']*)["']"""
)

# fetch(variable, { method: "METHOD" })
_FETCH_VAR_WITH_METHOD = re.compile(
    r"""(?:fetch|fetchJson)\s*\(\s*(\w+)\s*,\s*\{[^}]*method\s*:\s*["'](\w+)["']""",
    re.DOTALL,
)

# fetch(variable) without options → GET
_FETCH_VAR_NO_METHOD = re.compile(
    r"""(?:fetch|fetchJson)\s*\(\s*(\w+)\s*\)"""
)


def _extract_methods(js_text: str) -> list[tuple[str, str]]:
    """Return ``[(path, method), ...]`` pairs for every fetch-like call.

    Methods are determined from the explicit ``method`` option when present,
    otherwise defaulted to ``GET`` (the browser default for ``fetch()`` and
    the only supported method for ``EventSource``).
    """
    results: list[tuple[str, str]] = []

    # Calls with explicit method and a string-literal URL
    for m in _FETCH_WITH_METHOD.finditer(js_text):
        path = m.group(1).split("?")[0]
        method = m.group(2).upper()
        if (path, method) not in results:
            results.append((path, method))

    # Calls without a method → GET (string-literal URL)
    for m in _FETCH_NO_METHOD.finditer(js_text):
        path = m.group(1).split("?")[0]
        method = "GET"
        if (path, method) not in results:
            results.append((path, method))

    # EventSource → always GET
    for m in _EVENT_SOURCE.finditer(js_text):
        path = m.group(1).split("?")[0]
        method = "GET"
        if (path, method) not in results:
            results.append((path, method))

    # Build var→path map from variable assignments
    var_map: dict[str, str] = {}
    for m in _VAR_TO_PATH.finditer(js_text):
        var_map[m.group(1)] = m.group(2)

    # Calls where the URL is a variable with an explicit method
    for m in _FETCH_VAR_WITH_METHOD.finditer(js_text):
        var_name = m.group(1)
        method = m.group(2).upper()
        path = var_map.get(var_name)
        if path:
            path = path.split("?")[0]
            if (path, method) not in results:
                results.append((path, method))

    # Calls where the URL is a variable without a method → GET
    for m in _FETCH_VAR_NO_METHOD.finditer(js_text):
        var_name = m.group(1)
        method = "GET"
        path = var_map.get(var_name)
        if path:
            path = path.split("?")[0]
            if (path, method) not in results:
                results.append((path, method))

    return results


# ── Tests ────────────────────────────────────────────────────────────

# Build a lookup from the actual FastAPI routes
_ROUTES: dict[str, set[str]] = {}
for _route in app.routes:
    _rp = getattr(_route, "path", "")
    _rm = getattr(_route, "methods", set())
    if _rp not in _ROUTES:
        _ROUTES[_rp] = set()
    for _m in _rm:
        _ROUTES[_rp].add(_m.upper())


_JS_TEXT = _PIPELINE_JS.read_text(encoding="utf-8")
_EXTRACTED_PATHS = _extract_paths(_JS_TEXT)
_EXTRACTED_METHODS = _extract_methods(_JS_TEXT)


@pytest.mark.parametrize("path", sorted(_EXTRACTED_PATHS))
def test_every_api_path_has_a_registered_route(path: str) -> None:
    """Every /api/... path pipeline.js reaches must be a registered route."""
    assert path in _ROUTES, (
        f"pipeline.js references {path} but no route is registered for it.\n"
        f"Registered API routes: {sorted(_ROUTES.keys())}"
    )


@pytest.mark.parametrize("path,method", _EXTRACTED_METHODS)
def test_every_api_call_method_matches_route(
    path: str, method: str
) -> None:
    """Every fetch() call's HTTP method must match a registered route method.

    A POST to a GET-only endpoint, or vice versa, is a silent runtime break.
    """
    registered_methods = _ROUTES.get(path, set())
    assert method in registered_methods, (
        f"pipeline.js calls {method} {path} but the registered route only "
        f"accepts {sorted(registered_methods)}.\n"
        f"Either the JS method is wrong or the route decorator is."
    )


def test_all_expected_routes_are_referenced() -> None:
    """Sanity-check: verify the extraction didn't miss anything obvious.

    This test is documentary, not a gate — it fails only if a known critical
    route is absent from the extracted set, which would indicate a bug in
    the regex extraction rather than in the code under test.
    """
    expected = {
        "/api/models",
        "/api/state",
        "/api/upload-files",
        "/api/run-all",
        "/api/demo",
        "/api/ingest",
        "/api/extract",
        "/api/resolve",
        "/api/build-vault",
        "/api/build-graph",
        "/api/test-connection",
        "/api/save-config",
        "/api/stream",
    }
    missing = expected - _EXTRACTED_PATHS
    assert not missing, (
        f"Extraction missed expected path(s): {sorted(missing)}.\n"
        f"Update the regex in _extract_paths() or fix the test expectation."
    )
