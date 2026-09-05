# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Short visible-control smoke test for a frozen Artifice OCR server."""

from __future__ import annotations

import sys

from playwright.sync_api import expect, sync_playwright


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: packaged-ui-smoke.py BASE_URL")
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"])
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(sys.argv[1], wait_until="domcontentloaded")
        overlay = page.locator(".byom-overlay")
        if overlay.count():
            page.locator(".byom-close").click()

        for view in ("preview", "settings", "main"):
            page.locator(f'.shell-nav a[href="/?view={view}"]').click()
            expect(page.locator(f"#panel-{view}")).to_be_visible()
        expect(page.locator("#set-max_ocr_workers")).not_to_have_value("")

        page.locator('[data-shell-action="model"]').click()
        expect(page.locator(".byom-overlay")).to_be_visible()
        page.locator(".byom-close").click()
        page.locator("#btn-add-tropy").click()
        expect(page.locator("#modal-tropy-add")).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("#modal-tropy-add")).to_be_hidden()
        browser.close()
    if errors:
        raise AssertionError(f"packaged UI page errors: {errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
