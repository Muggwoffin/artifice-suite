# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Opt-in OCR checks against real Ollama and LM Studio model processes."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from artifice_ocr import _resolution, config
from artifice_ocr.jobs import JobItem, JobRunner, State

pytestmark = [
    pytest.mark.live_interop,
    pytest.mark.skipif(
        os.environ.get("ARTIFICE_LIVE_MODELS") != "1",
        reason="set ARTIFICE_LIVE_MODELS=1 or use scripts/interop/run-live-release-gate.sh",
    ),
]


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
def test_real_vision_model_ocr_pipeline(tmp_path, backend, url_env, model_env, url_key):
    """Send a real scan through the production JobRunner and selected SDK."""
    url = os.environ.get(url_env, "").strip()
    model = os.environ.get(model_env, "").strip()
    if not url:
        pytest.fail(f"Live release gate requires {url_env}")

    image = tmp_path / "proceedings_usnm_173.jpg"
    shutil.copyfile(Path(__file__).parent / "fixtures" / image.name, image)
    output = tmp_path / "output"
    job = JobItem(path=str(image))

    config.reset()
    config.load_config(include_user_settings=False)
    config.apply_overrides(
        {
            "ocr_engine": "vision_model",
            "ocr_backend": backend,
            "ocr_model": model,
            url_key: url,
            "resume": False,
            "ocr_repetition_guard": True,
            # A live model failure must not be hidden by a local OCR fallback.
            "tesseract_fallback_on_failure": False,
        }
    )
    _resolution.reset()
    try:
        # This is the same preflight used by the CLI/web run route. An empty
        # model override deliberately exercises production auto-detection.
        _resolution.resolve_models_for_run(stages={"ocr"})
        resolved_model = _resolution.model_for("vision")
        assert resolved_model
        runner = JobRunner([job], str(output), stages={"ocr"}, force=True, max_workers=1)
        job.reset({"ocr"})
        runner._run()

        assert job.state is State.DONE, job.error
        result = job.results["raw"]
        assert result["engine"] == backend
        assert result["model"] == resolved_model
        assert len(result["extracted_text"].strip()) >= 100
        assert (output / "raw_ocr" / "text" / f"{image.stem}.txt").is_file()
    finally:
        _resolution.reset()
        config.reset()
