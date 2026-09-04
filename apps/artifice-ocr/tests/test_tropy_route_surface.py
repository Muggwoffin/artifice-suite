# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The supported Tropy HTTP surface is live browse plus Developer API notes."""

from artifice_ocr import config
from artifice_ocr.web.routers.settings import _CONFIG_KEYS
from artifice_ocr.web.server import app


def test_legacy_tropy_routes_are_not_registered():
    paths = set(app.openapi()["paths"])

    assert "/api/tropy/import/preview" not in paths
    assert "/api/tropy/import/add" not in paths
    assert "/api/tropy/export" not in paths
    assert "/api/tropy/export/history" not in paths
    assert "/api/tropy/writeback/preview" not in paths
    assert "/api/tropy/writeback/commit" not in paths


def test_supported_tropy_routes_remain_registered():
    paths = set(app.openapi()["paths"])

    assert "/api/tropy/browse/projects" in paths
    assert "/api/tropy/browse/enqueue" in paths
    assert "/api/tropy/notes/preview" in paths
    assert "/api/tropy/notes/commit" in paths


def test_deprecated_tropy_settings_are_ignored():
    for key in ("tropy_writeback_enabled", "tropy_last_export_path"):
        assert key not in config.PERSISTED_KEYS
        assert key not in _CONFIG_KEYS
