# SPDX-License-Identifier: AGPL-3.0-or-later
from importlib.resources import files

import shared_ui


def test_shell_assets_and_template_are_packaged():
    package = files(shared_ui)
    for relative in ("assets/shell.css", "assets/shell.js", "templates/_app_shell.html"):
        assert (package / relative).is_file()


def test_shell_template_has_landmarks_and_extension_blocks():
    source = (files(shared_ui) / "templates/_app_shell.html").read_text()
    assert source.count("<main") == 1
    assert 'id="workspace"' in source
    assert "{% block workspace %}" in source
    assert "{% block inspector %}" in source
    assert "{% block activity %}" in source


def test_shell_javascript_exposes_documented_api():
    source = (files(shared_ui) / "assets/shell.js").read_text()
    for member in ("init", "publishActivity", "removeActivity", "setModelStatus", "getPreferences", "setPreferences", "refreshSuiteApps"):
        assert member in source
