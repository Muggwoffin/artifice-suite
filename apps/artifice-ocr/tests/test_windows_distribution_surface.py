# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression checks for the Windows Defender false-positive surface.

These are intentionally small source/build-contract checks. They prevent a
future maintenance change from reintroducing the two behaviours that caused
the strongest defense-evasion signal in the frozen OCR executable.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OCR_SRC = ROOT / "apps" / "artifice-ocr" / "src" / "artifice_ocr"


def test_ocr_runtime_does_not_enumerate_processes_or_strip_download_metadata():
    tropy = (OCR_SRC / "tropy_write.py").read_text(encoding="utf-8")
    window = (ROOT / "packages" / "shared-ui" / "shared_ui" / "window.py").read_text(
        encoding="utf-8"
    )

    assert '"tasklist"' not in tropy
    assert '"pgrep"' not in tropy
    assert "CREATE_NO_WINDOW" not in tropy
    assert "Zone.Identifier" not in window
    assert "os.remove" not in window


def test_ocr_pyinstaller_bundle_is_uncompressed_and_windowed():
    spec = (ROOT / "apps" / "artifice-ocr" / "artifice-ocr.spec").read_text(
        encoding="utf-8"
    )
    assert "upx=False" in spec
    assert "console=False" in spec
    assert "uac_admin=False" in spec
    assert "uac_uiaccess=False" in spec
