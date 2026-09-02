# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_user_configuration(tmp_path, monkeypatch):
    """Keep the suite independent of a developer's real saved settings.

    ``config.load_config()`` deliberately merges ``~/.artifice_ocr/settings.json``
    and model endpoint environment variables. Tests that replace ``_DEFAULTS``
    otherwise still receive the maintainer's real URLs, making a clean CI run
    pass while the same suite fails on a configured workstation.
    """
    from artifice_ocr import config

    user_dir = tmp_path / "artifice-user"
    monkeypatch.setattr(config, "_USER_DIR", user_dir)
    monkeypatch.setattr(config, "_SETTINGS_PATH", user_dir / "settings.json")
    for name in (
        "ARTIFICE_OCR_CONFIG",
        "OCR_MODEL",
        "CLEANUP_MODEL",
        "TRANSLATE_MODEL",
        "LM_STUDIO_URL",
        "OLLAMA_URL",
        "OUTPUT_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    config.reset()
    yield
    config.reset()


@pytest.fixture
def safe_tmp_path():
    """Temp directory NOT under any blocked root or blocked home child.

    pytest's ``tmp_path`` resolves to a system temp directory that may be
    under a POSIX blocked root (e.g. ``/private/var`` on macOS) or a
    Windows blocked home child (e.g. ``AppData``), causing the pathcheck
    to reject legitimate test photo paths.

    This fixture places temp directories under ``~/.artifice_ocr_test_tmp/``
    which is not in any blocklist and not under any blocked root.
    """
    base = Path.home() / ".artifice_ocr_test_tmp"
    base.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=str(base)))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)
