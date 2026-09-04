# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Static contracts for regressions introduced by the suite-shell overhaul."""

import re
from pathlib import Path

_WEB = Path(__file__).resolve().parents[1] / "src" / "artifice_ocr" / "web"


def test_tropy_modal_and_browse_panes_have_bounded_vertical_scrolling():
    css = (_WEB / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert "max-height: calc(100dvh" in css
    assert ".tropy-browse-picker-grid > .tropy-source-pane" in css
    assert ".tropy-browse-picker-grid > .tropy-item-pane" in css
    assert "-webkit-overflow-scrolling: touch" in css


def test_settings_save_includes_queue_output_directory_and_refreshes_from_server():
    js = (_WEB / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    assert 'document.getElementById("output-dir")' in js
    assert 'out.output_dir = outputDir.value || "output"' in js
    assert "outputDir.value = values.output_dir" in js
    assert 'const cfg = await api("GET", "/api/config")' in js
    assert "apply(cfg)" in js


def test_all_static_buttons_are_non_submitting_controls():
    """Future form wrappers must not turn a toolbar click into navigation."""
    html = (_WEB / "templates" / "index.html").read_text(encoding="utf-8")
    buttons = re.findall(r"<button\b[^>]*>", html, flags=re.IGNORECASE)
    missing = [button for button in buttons if 'type="button"' not in button.lower()]
    assert not missing, f"buttons missing type=button: {missing[:5]}"


def test_tropy_handoff_can_detect_unsaved_editor_text():
    preview = (_WEB / "static" / "js" / "preview.js").read_text(encoding="utf-8")
    history = (_WEB / "static" / "js" / "history.js").read_text(encoding="utf-8")
    assert "hasUnsavedEdits" in preview
    assert "hasUnsavedEdits" in history


def test_history_tropy_handoff_uses_live_browse_provenance():
    history = (_WEB / "static" / "js" / "history.js").read_text(encoding="utf-8")
    assert "data.photo_id == null || !data.tropy_project_path" in history
    assert "data.tropy_exportable" not in history


def test_tropy_workspace_exposes_only_live_browse_and_developer_api():
    html = (_WEB / "templates" / "index.html").read_text(encoding="utf-8")
    js = (_WEB / "static" / "js" / "tropy.js").read_text(encoding="utf-8")
    settings = (_WEB / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    assert "tropy-mode-jsonld" not in html
    assert "tropy-dest-jsonld" not in html
    assert "tropy-dest-writeback" not in html
    assert "/api/tropy/notes/preview" in js
    assert "/api/tropy/notes/commit" in js
    assert "/api/tropy/export" not in js
    assert "/api/tropy/writeback" not in js
    assert "tropy_writeback_enabled" not in settings
