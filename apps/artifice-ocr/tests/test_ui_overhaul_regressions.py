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


def test_simplified_settings_use_auto_detecting_defaults_and_sections():
    from artifice_ocr import config

    html = (_WEB / "templates" / "index.html").read_text(encoding="utf-8")
    js = (_WEB / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    defaults = config._DEFAULTS
    assert defaults["ocr_backend"] == defaults["cleanup_backend"] == "auto"
    assert defaults["translate_backend"] == "auto"
    assert defaults["ocr_model"] == defaults["cleanup_model"] == ""
    assert defaults["translate_model"] == ""
    assert defaults["max_ocr_workers"] == 2
    assert defaults["resume"] is True
    assert defaults["confidence_enabled"] is True
    assert defaults["tesseract_fallback_on_failure"] is True
    assert defaults["tropy_live_browse_enabled"] is True
    assert defaults["tropy_api_port"] == 0
    for section in (
        "settings-models",
        "settings-processing",
        "settings-tropy",
        "settings-diagnostics",
    ):
        assert f'id="{section}"' in html
    assert 'id="detected-local-models"' in html
    assert "load().then(runPreflight)" in js


def test_fabricated_review_controls_and_export_are_present():
    html = (_WEB / "templates" / "index.html").read_text(encoding="utf-8")
    preview = (_WEB / "static" / "js" / "preview.js").read_text(encoding="utf-8")
    history = (_WEB / "static" / "js" / "history.js").read_text(encoding="utf-8")
    assert 'id="preview-fabricated-result"' in html
    assert 'id="history-fabricated-result"' in html
    assert 'id="btn-history-export-fabricated"' in html
    assert "/fabricated-result" in preview
    assert "/fabricated-result" in history
    assert "/api/history/fabricated-results" in history


def test_stage_defaults_use_canonical_raw_ocr_key():
    app = (_WEB / "static" / "js" / "app.js").read_text(encoding="utf-8")
    pdf = (_WEB / "static" / "js" / "pdf_export.js").read_text(encoding="utf-8")
    assert 'return "raw_ocr"' in app
    assert 'preferredStage() || "raw_ocr"' in pdf
    assert 'preferredStage() || "raw"' not in pdf


def test_mockup_respects_reduced_motion_for_programmatic_scrolls():
    mockup = (
        Path(__file__).resolve().parents[3] / "mockups" / "artifice-ocr-tropy-workbench.html"
    ).read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in mockup
    assert mockup.count("behavior: scrollBehavior") == 2


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


def test_tropy_browser_explains_when_live_browsing_is_disabled():
    js = (_WEB / "static" / "js" / "tropy.js").read_text(encoding="utf-8")
    assert 'error.message === "Live Tropy browse is not enabled"' in js
    assert "Enable Tropy project browsing in Settings before adding pages." in js
    assert 'tropy["btn-tropy-browse-load"].disabled = true' in js


def test_tropy_first_workspace_removes_unrelated_surfaces_and_exposes_pages():
    html = (_WEB / "templates" / "index.html").read_text(encoding="utf-8")
    base = (_WEB / "templates" / "base.html").read_text(encoding="utf-8")
    js = (_WEB / "static" / "js" / "tropy.js").read_text(encoding="utf-8")

    assert "Tropy round trip" in html
    assert "Choose Tropy pages" in html
    assert 'id="stage-title"' in html
    assert re.search(r'id="stage-ocr"[^>]*checked[^>]*disabled', html)
    assert "Analytics" not in html
    assert "Send to Draft" not in html
    assert "Send to Graph" not in html
    assert "Run templates" not in html
    assert "batch-template" not in html
    assert "analytics.js" not in base
    assert "handoff.js" not in base
    assert "tropy-browse-page-check" in js
    assert "photo_ids: [...selectedPhotos.keys()]" in js


def test_send_to_tropy_uses_explicit_queue_selection():
    js = (_WEB / "static" / "js" / "tropy.js").read_text(encoding="utf-8")
    app = (_WEB / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "window.QueueTab" in app
    assert "selectedIds: selectedQueueIds" in app
    assert "preferredStage" in app
    assert "window.QueueTab?.selectedIds?.()" in js
    assert "item_ids: sendContext?.itemIds || []" in js
    assert "Select one or more completed Tropy pages" in js
