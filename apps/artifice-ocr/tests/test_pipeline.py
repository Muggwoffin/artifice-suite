# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for pipeline.py's skip-reason reporting and identity-aware OCR resume.

A resumed run that reuses existing output must say *why* it skipped a stage
("not selected by the user" vs "output already exists"), and the OCR resume
check must not silently reuse another photo's output when two Tropy photos
collide on the same output stem — but it must still treat every pre-existing
sidecar-less output as valid (the non-destructive fallback).
"""

import json
from pathlib import Path
from unittest.mock import patch

from artifice_ocr.pipeline import (
    SKIP_ALREADY_EXISTS,
    SKIP_NOT_SELECTED,
    run_cleanup_step,
    run_ocr_step,
    run_title_step,
    run_translate_step,
)


def _write_existing_ocr_output(output_dir, stem, text="Existing text", identity=None):
    text_dir = Path(output_dir) / "raw_ocr" / "text"
    json_dir = Path(output_dir) / "raw_ocr" / "json"
    text_path = text_dir / f"{stem}.txt"
    json_path = json_dir / f"{stem}.json"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")
    data = {"source_file": "orig.png", "stage": "raw_ocr", "extracted_text": text}
    if identity:
        data.update(identity)
    json_path.write_text(json.dumps(data), encoding="utf-8")


# --------------------------------------------------------------------------- #
# run_ocr_step — skip reasons
# --------------------------------------------------------------------------- #


class TestOcrStepSkipReason:
    def test_skip_ocr_reports_not_selected(self, tmp_path):
        result = run_ocr_step("doc.png", str(tmp_path), skip_ocr=True)
        assert result["_skipped"] is True
        assert result["_skip_reason"] == SKIP_NOT_SELECTED

    def test_resume_with_no_sidecar_identity_falls_back_to_existence(self, tmp_path):
        """No `source` and/or a sidecar with no identity fields (every file
        that predates this feature) must still resume — non-destructive."""
        _write_existing_ocr_output(tmp_path, "doc")
        result = run_ocr_step("doc.png", str(tmp_path), resume=True, stem="doc")
        assert result["_skipped"] is True
        assert result["_skip_reason"] == SKIP_ALREADY_EXISTS
        assert result["_skip_key"] == "doc"

    def test_resume_skips_when_sidecar_identity_matches(self, tmp_path):
        _write_existing_ocr_output(tmp_path, "doc", identity={"checksum": "abc123"})
        result = run_ocr_step(
            "doc.png",
            str(tmp_path),
            resume=True,
            stem="doc",
            source={"checksum": "abc123"},
        )
        assert result["_skipped"] is True
        assert result["_skip_reason"] == SKIP_ALREADY_EXISTS
        assert result["_skip_key"] == "doc"

    def test_resume_reocrs_when_sidecar_identity_differs(self, tmp_path):
        """Two colliding photos sharing a stem: the sidecar records the FIRST
        photo's checksum, and a SECOND, different photo must not silently
        reuse its text."""
        _write_existing_ocr_output(tmp_path, "doc", identity={"checksum": "old-checksum"})
        img = tmp_path / "doc.png"
        img.write_bytes(b"fake-image-bytes")

        with patch("artifice_ocr.pipeline.ocr.perform") as mock_perform:
            mock_perform.return_value = {
                "source_file": str(img),
                "stage": "raw_ocr",
                "extracted_text": "fresh text",
            }
            result = run_ocr_step(
                str(img),
                str(tmp_path),
                resume=True,
                stem="doc",
                source={"checksum": "new-checksum"},
            )

        mock_perform.assert_called_once()
        assert result["extracted_text"] == "fresh text"
        assert result.get("_skipped") is not True

    def test_resume_falls_back_to_existence_when_current_source_has_no_identity(self, tmp_path):
        """The sidecar has identity, but the *current* photo carries none
        (e.g. an ad-hoc, non-Tropy file) — nothing to compare, so existence
        alone must still decide."""
        _write_existing_ocr_output(tmp_path, "doc", identity={"checksum": "abc123"})
        result = run_ocr_step("doc.png", str(tmp_path), resume=True, stem="doc", source=None)
        assert result["_skipped"] is True
        assert result["_skip_reason"] == SKIP_ALREADY_EXISTS

    def test_force_bypasses_resume_even_with_matching_identity(self, tmp_path):
        _write_existing_ocr_output(tmp_path, "doc", identity={"checksum": "abc123"})
        img = tmp_path / "doc.png"
        img.write_bytes(b"fake-image-bytes")

        with patch("artifice_ocr.pipeline.ocr.perform") as mock_perform:
            mock_perform.return_value = {
                "source_file": str(img),
                "stage": "raw_ocr",
                "extracted_text": "new text",
            }
            result = run_ocr_step(
                str(img),
                str(tmp_path),
                resume=True,
                force=True,
                stem="doc",
                source={"checksum": "abc123"},
            )

        mock_perform.assert_called_once()
        assert result.get("_skipped") is not True

    def test_no_existing_output_does_not_skip(self, tmp_path):
        img = tmp_path / "doc.png"
        img.write_bytes(b"fake-image-bytes")
        with patch("artifice_ocr.pipeline.ocr.perform") as mock_perform:
            mock_perform.return_value = {
                "source_file": str(img),
                "stage": "raw_ocr",
                "extracted_text": "new text",
            }
            result = run_ocr_step(str(img), str(tmp_path), resume=True, stem="doc")
        mock_perform.assert_called_once()
        assert result.get("_skipped") is not True

    def test_source_passed_through_to_ocr_perform(self, tmp_path):
        """`source` must reach `ocr.perform` so the OCR sidecar can record
        the identity of a freshly-OCR'd photo for future resumes."""
        img = tmp_path / "doc.png"
        img.write_bytes(b"fake-image-bytes")
        with patch("artifice_ocr.pipeline.ocr.perform") as mock_perform:
            mock_perform.return_value = {
                "source_file": str(img),
                "stage": "raw_ocr",
                "extracted_text": "text",
            }
            run_ocr_step(
                str(img),
                str(tmp_path),
                resume=True,
                stem="doc",
                source={"checksum": "zzz"},
            )
        _args, kwargs = mock_perform.call_args
        assert kwargs.get("source") == {"checksum": "zzz"}


# --------------------------------------------------------------------------- #
# run_cleanup_step / run_title_step / run_translate_step — skip reasons
# --------------------------------------------------------------------------- #


class TestCleanupStepSkipReason:
    def test_skip_cleanup_reports_not_selected(self, tmp_path):
        raw_data = {"source_file": "x", "extracted_text": "raw"}
        result = run_cleanup_step(raw_data, "doc", str(tmp_path), skip_cleanup=True)
        assert result["_skip_reason"] == SKIP_NOT_SELECTED

    def test_resume_cleanup_reports_already_exists(self, tmp_path):
        d = Path(tmp_path) / "cleaned" / "text"
        d.mkdir(parents=True)
        (d / "doc.txt").write_text("cleaned", encoding="utf-8")
        raw_data = {"source_file": "x", "extracted_text": "raw"}
        result = run_cleanup_step(raw_data, "doc", str(tmp_path), resume=True)
        assert result["_skip_reason"] == SKIP_ALREADY_EXISTS
        assert result["_skip_key"] == "doc"


class TestTitleStepSkipReason:
    def test_skip_title_reports_not_selected(self, tmp_path):
        cleaned_data = {"source_file": "x", "cleaned_text": "text"}
        result = run_title_step(cleaned_data, "doc", str(tmp_path), skip_title=True)
        assert result["_skip_reason"] == SKIP_NOT_SELECTED

    def test_resume_title_reports_already_exists(self, tmp_path):
        d = Path(tmp_path) / "title" / "text"
        d.mkdir(parents=True)
        (d / "doc.txt").write_text("A Title", encoding="utf-8")
        cleaned_data = {"source_file": "x", "cleaned_text": "text"}
        result = run_title_step(cleaned_data, "doc", str(tmp_path), resume=True)
        assert result["_skip_reason"] == SKIP_ALREADY_EXISTS
        assert result["_skip_key"] == "doc"


class TestTranslateStepSkipReason:
    def test_resume_translate_reports_already_exists(self, tmp_path):
        d = Path(tmp_path) / "translated" / "text"
        d.mkdir(parents=True)
        (d / "doc.txt").write_text("Translated", encoding="utf-8")
        cleaned_data = {"source_file": "x", "cleaned_text": "text"}
        result = run_translate_step(cleaned_data, "doc", str(tmp_path), resume=True)
        assert result["_skip_reason"] == SKIP_ALREADY_EXISTS
        assert result["_skip_key"] == "doc"
