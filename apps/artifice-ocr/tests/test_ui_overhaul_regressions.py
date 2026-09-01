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
    assert 'apply(await api("GET", "/api/config"))' in js


def test_all_static_buttons_are_non_submitting_controls():
    """Future form wrappers must not turn a toolbar click into navigation."""
    html = (_WEB / "templates" / "index.html").read_text(encoding="utf-8")
    buttons = re.findall(r"<button\b[^>]*>", html, flags=re.IGNORECASE)
    missing = [button for button in buttons if 'type="button"' not in button.lower()]
    assert not missing, f"buttons missing type=button: {missing[:5]}"
