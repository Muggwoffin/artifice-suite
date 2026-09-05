# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Seeded, replayable browser interaction stress tests."""

import json
import os
import random
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect


def _seeds() -> list[int]:
    explicit = os.environ.get("ARTIFICE_STRESS_SEEDS")
    if explicit:
        return [int(value.strip()) for value in explicit.split(",") if value.strip()]
    count = int(os.environ.get("ARTIFICE_STRESS_SEED_COUNT", "8"))
    return list(range(104729, 104729 + count))


def _dismiss_onboarding(page) -> None:
    # autostart sets data-state and opens its overlay in the same JS callback.
    # Wait for that callback, not an arbitrary delay after DOMContentLoaded.
    expect(page.locator('[data-shell-action="model"]')).to_have_attribute(
        "data-state", re.compile("^(configured|unconfigured)$"), timeout=15_000
    )
    if page.locator(".byom-overlay").count():
        page.locator(".byom-close").click()


def _tab(page, name: str) -> None:
    # Exercise the visible application-shell navigation. The legacy .tab
    # controls remain in the DOM as the panel controller but are intentionally
    # visually clipped by shell.css.
    page.locator(f'.shell-nav a[href="/?view={name}"]').click()
    _dismiss_onboarding(page)
    expect(page.locator(f"#panel-{name}")).to_be_visible()
    if name == "settings":
        expect(page.locator("#set-max_ocr_workers")).not_to_have_value("")


def _assert_invariants(page) -> None:
    active_tabs = page.locator(".tab.active")
    expect(active_tabs).to_have_count(1)
    assert page.locator(".panel.active").count() == 1
    assert page.locator(".modal-backdrop:not(.hidden)").count() <= 1
    ids = page.locator("#queue-body tr[data-id]").evaluate_all(
        "rows => rows.map(row => row.dataset.id)"
    )
    assert len(ids) == len(set(ids))
    connection = page.locator('[data-shell-action="model"]')
    connection_state = connection.get_attribute("data-state")
    if connection_state is not None:
        expect(connection.locator(".status-dot")).to_have_attribute("data-state", connection_state)


def _actions(page, rng: random.Random):
    def switch_tab():
        _tab(page, rng.choice(["main", "preview", "history", "settings"]))

    def toggle_selection():
        _tab(page, "main")
        boxes = page.locator("#queue-body .row-select")
        if boxes.count():
            boxes.nth(rng.randrange(boxes.count())).click()

    def select_all_twice():
        _tab(page, "main")
        page.locator("#select-all-rows").click()
        page.locator("#select-all-rows").click()

    def preview_item():
        _tab(page, "preview")
        picker = page.locator("#preview-item-select")
        if picker.input_value():
            picker.select_option(index=rng.randrange(picker.locator("option").count()))
            expect(page.locator("#panel-preview .compare-title")).not_to_have_text(
                "No document selected"
            )

    def toggle_fabricated():
        preview_item()
        checkbox = page.locator("#preview-fabricated-result")
        if checkbox.is_enabled():
            checkbox.click()

    def edit_review_text():
        preview_item()
        textarea = page.locator('.compare-pane[data-pane="raw"] textarea')
        if textarea.count():
            textarea.fill(f"seeded correction {rng.randrange(1000)}")
            page.locator("#btn-save-raw").click()

    def open_close_tropy():
        _tab(page, "main")
        page.locator("#btn-add-tropy").click()
        expect(page.locator("#modal-tropy-add")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("#modal-tropy-add")).to_be_hidden()

    def open_close_connection_setup():
        page.locator('[data-shell-action="model"]').click()
        expect(page.locator(".byom-overlay")).to_be_visible()
        page.locator(".byom-close").click()
        expect(page.locator(".byom-overlay")).to_have_count(0)

    def malformed_tropy_path():
        _tab(page, "main")
        page.locator("#btn-add-tropy").click()
        path = page.locator("#tropy-browse-path")
        if path.is_enabled():
            path.fill("/definitely/not/a/project.tropy")
            page.locator("#btn-tropy-browse-load").click()
            expect(page.locator("#tropy-browse-error")).to_be_visible(timeout=5000)
        page.keyboard.press("Escape")

    def batch_replace():
        _tab(page, "main")
        page.locator("#btn-batch-correct").click()
        expect(page.locator("#modal-batch-correct")).to_be_visible()
        page.locator("#batch-find").fill("old")
        page.locator("#batch-replace").fill(f"old-{rng.randrange(10)}")
        page.locator("#btn-batch-apply").click()
        expect(page.locator("#batch-status")).to_contain_text("Applied", timeout=5000)
        page.locator("#btn-batch-cancel").click()

    def settings_round_trip():
        _tab(page, "settings")
        backend = rng.choice(["auto", "ollama", "lm_studio"])
        page.locator("#set-ocr_backend").select_option(backend)
        page.locator("#set-ocr_model").fill("stress-model")
        page.locator("#btn-settings-save").click()
        expect(page.locator("#settings-saved")).to_contain_text("Saved", timeout=5000)

    def invalid_setting():
        _tab(page, "settings")
        port = page.locator("#set-tropy_api_port")
        port.fill("99999")
        page.locator("#btn-settings-save").click()
        assert port.evaluate("element => !element.validity.valid")
        port.fill("0")

    def reload_page():
        page.reload(wait_until="domcontentloaded")
        _dismiss_onboarding(page)
        expect(page.locator(".panel.active")).to_be_visible()

    return [
        switch_tab,
        toggle_selection,
        select_all_twice,
        preview_item,
        toggle_fabricated,
        edit_review_text,
        open_close_tropy,
        open_close_connection_setup,
        malformed_tropy_path,
        batch_replace,
        settings_round_trip,
        invalid_setting,
        reload_page,
    ]


@pytest.mark.ui_stress
@pytest.mark.parametrize("seed", _seeds())
def test_seeded_browser_actions(seed, stress_server, chromium_browser):
    """Run the action grammar; any seed can be replayed with one environment variable."""
    artifact_root = Path(os.environ.get("ARTIFICE_STRESS_ARTIFACTS", ".artifacts/ui-stress"))
    artifact_dir = artifact_root / f"seed-{seed}"
    events: list[dict] = []
    browser_errors: list[str] = []
    server_errors: list[str] = []
    context = chromium_browser.new_context(viewport={"width": 1440, "height": 1000})
    context.set_default_timeout(5000)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    page.on("pageerror", lambda error: browser_errors.append(str(error)))
    page.on(
        "response",
        lambda response: (
            server_errors.append(f"{response.status} {response.url}")
            if response.status >= 500
            else None
        ),
    )
    failed = False
    try:
        page.goto(stress_server, wait_until="domcontentloaded")
        _dismiss_onboarding(page)
        expect(page.locator("#queue-body tr[data-id]")).to_have_count(4)
        rng = random.Random(seed)
        actions = _actions(page, rng)
        action_count = int(os.environ.get("ARTIFICE_STRESS_ACTIONS", "30"))
        for step in range(action_count):
            action = rng.choice(actions)
            events.append({"step": step, "action": action.__name__})
            action()
            _assert_invariants(page)
        assert not browser_errors, browser_errors
        assert not server_errors, server_errors
    except Exception:
        failed = True
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "actions.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
        (artifact_dir / "browser-errors.json").write_text(
            json.dumps(browser_errors, indent=2), encoding="utf-8"
        )
        (artifact_dir / "server-errors.json").write_text(
            json.dumps(server_errors, indent=2), encoding="utf-8"
        )
        (artifact_dir / "page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(artifact_dir / "failure.png"), full_page=True)
        raise
    finally:
        if failed:
            context.tracing.stop(path=str(artifact_dir / "trace.zip"))
        else:
            context.tracing.stop()
        context.close()
