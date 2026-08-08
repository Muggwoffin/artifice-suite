# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the app registry.

Verifies that every ``entry_point`` declared in :data:`artifice_hub.registry.APPS`
actually exists in the corresponding app's ``[project.scripts]`` table.
This catches drift where an entry point is added to the registry but not
to the app's ``pyproject.toml`` (and vice versa).
"""

import tomllib
from pathlib import Path

import pytest
from artifice_hub.registry import APPS

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APPS_DIR = _REPO_ROOT / "apps"

# Map registry slugs to their app directory names
_SLUG_TO_DIR = {
    "artifice-ocr": "artifice-ocr",
    "artifice-draft": "artifice-draft",
    "artifice-graph": "artifice-graph",
    "artifice-transcribe": "artifice-transcribe",
}


def _load_project_scripts(app_dir: str) -> dict[str, str]:
    """Load ``[project.scripts]`` from *app_dir*/pyproject.toml."""
    toml_path = _APPS_DIR / app_dir / "pyproject.toml"
    if not toml_path.is_file():
        pytest.skip(f"{toml_path} not found")
    with toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    return data.get("project", {}).get("scripts", {})


@pytest.mark.parametrize("slug,spec", APPS.items())
def test_registry_entry_point_in_pyproject_scripts(slug, spec):
    """Every registry entry_point must appear in its app's [project.scripts]."""
    app_dir = _SLUG_TO_DIR.get(slug)
    if app_dir is None:
        pytest.skip(f"No app directory mapped for {slug}")

    scripts = _load_project_scripts(app_dir)
    assert spec.entry_point in scripts, (
        f"Registry says entry_point='{spec.entry_point}' for {slug}, "
        f"but it is not in {app_dir}/pyproject.toml [project.scripts] "
        f"(found: {list(scripts.keys())})"
    )


def test_registry_no_extraneous_entry_points():
    """Every entry_point in the registry must have a real app to verify against."""
    for slug in APPS:
        assert slug in _SLUG_TO_DIR, f"Registry slug {slug} has no _SLUG_TO_DIR mapping"
