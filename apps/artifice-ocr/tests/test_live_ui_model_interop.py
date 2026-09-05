# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Release-gate OCR calls driven through the real browser interface."""

from __future__ import annotations

import os
import re
import shutil
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from artifice_ocr import _resolution, config
from artifice_ocr.jobs import JobItem, State
from artifice_ocr.web.runtime import state
from artifice_ocr.web.server import app
from playwright.sync_api import expect, sync_playwright

pytestmark = [
    pytest.mark.live_interop,
    pytest.mark.skipif(
        os.environ.get("ARTIFICE_LIVE_MODELS") != "1",
        reason="use scripts/interop/run-live-release-gate.sh",
    ),
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.parametrize(
    ("backend", "url_env", "model_env", "url_key"),
    [
        ("ollama", "ARTIFICE_LIVE_OLLAMA_URL", "ARTIFICE_LIVE_OLLAMA_MODEL", "ollama_url"),
        (
            "lm_studio",
            "ARTIFICE_LIVE_LM_STUDIO_URL",
            "ARTIFICE_LIVE_LM_STUDIO_MODEL",
            "lm_studio_url",
        ),
    ],
)
def test_real_vision_ocr_from_visible_ui(backend, url_env, model_env, url_key):
    """Run one real OCR job from the visible Source controls for each backend."""
    url = os.environ.get(url_env, "").strip()
    model = os.environ.get(model_env, "").strip()
    if not url:
        pytest.fail(f"Live release gate requires {url_env}")

    case_dir = Path.cwd() / "build" / "live-interop" / f"{backend}-{os.getpid()}"
    case_dir.mkdir(parents=True, exist_ok=True)
    image = case_dir / f"live-ui-{backend}.jpg"
    shutil.copyfile(Path(__file__).parent / "fixtures" / "proceedings_usnm_173.jpg", image)
    output = case_dir / "output"
    job = JobItem(path=str(image))

    config.reset()
    config.load_config(include_user_settings=False)
    config.apply_overrides(
        {
            "ocr_engine": "vision_model",
            "ocr_backend": backend,
            "ocr_model": model,
            url_key: url,
            "history_db": str(case_dir / "history.sqlite3"),
            "resume": False,
            "max_ocr_workers": 1,
            "ocr_repetition_guard": True,
            "tesseract_fallback_on_failure": False,
        }
    )
    _resolution.reset()
    state.clear()
    state.runner = None
    state.run_id = None
    if state._history is not None:
        state._history.close()
        state._history = None
    state.add_items([job])

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/api/queue", timeout=0.25).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        pytest.fail("live UI server did not start")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"])
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(base_url, wait_until="domcontentloaded")
            overlay = page.locator(".byom-overlay")
            if overlay.count():
                page.locator(".byom-close").click()
            expect(page.locator("#queue-body tr[data-id]")).to_have_count(1)
            if page.locator("#stage-cleanup").is_checked():
                page.locator("#stage-cleanup").uncheck()
            if page.locator("#stage-title").is_checked():
                page.locator("#stage-title").uncheck()
            if page.locator("#stage-translate").is_checked():
                page.locator("#stage-translate").uncheck()
            page.locator("#output-dir").fill(str(output))
            page.locator("#btn-run").click()
            try:
                expect(page.locator("#btn-run")).to_be_disabled(timeout=30_000)
            except AssertionError:
                pytest.fail("UI run did not start:\n" + page.locator("#log").inner_text())
            expect(page.locator("#queue-body tr[data-id]")).to_have_class(
                re.compile("state-done"),
                timeout=150_000,
            )
            expect(page.locator("#status-text")).to_contain_text("Done", timeout=10_000)
            browser.close()

        assert job.state is State.DONE, job.error
        result = job.results["raw"]
        assert result["engine"] == backend
        assert result["model"]
        assert len(result["extracted_text"].strip()) >= 100
        assert (output / "raw_ocr" / "text" / f"{image.stem}.txt").is_file()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        state.clear()
        state.runner = None
        state.run_id = None
        if state._history is not None:
            state._history.close()
            state._history = None
        _resolution.reset()
        config.reset()
        shutil.rmtree(case_dir, ignore_errors=True)
