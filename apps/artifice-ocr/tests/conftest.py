# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import shutil
import tempfile
from pathlib import Path

import pytest


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
