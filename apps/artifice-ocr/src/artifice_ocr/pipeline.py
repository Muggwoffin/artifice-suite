# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

import json
import time
from pathlib import Path
from typing import Any

from ._logging import get_logger
from .config import get as cfg
from .stages import ocr, cleanup, translate

log = get_logger("pipeline")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".pdf"}


def _output_exists(stage: str, stem: str, output_dir: str) -> bool:
    """Check if output for a stage already exists."""
    p = Path(output_dir) / stage / "text" / f"{stem}.txt"
    return p.exists()


def _load_existing_text(stage: str, stem: str, output_dir: str) -> str:
    p = Path(output_dir) / stage / "text" / f"{stem}.txt"
    return p.read_text(encoding="utf-8")


def run_ocr_step(
    file_path: str | Path,
    output_dir: str,
    *,
    skip_ocr: bool = False,
    resume: bool = True,
    force: bool = False,
    page: int | None = None,
    stem: str | None = None,
    orientation: int = 1,
) -> dict:
    """Run the OCR stage for one file, or resolve it from existing output.

    `page` selects a single 0-based PDF page; `stem` overrides the output key,
    which is what keeps per-page outputs from colliding on the filename stem.
    `orientation` is Tropy's `photos.orientation` value (EXIF 1-8 convention,
    1 = normal) — a Tropy-sourced item can be scanned rotated or upside-down
    with nothing in the filename or the image's own EXIF data to say so; this
    is the one place that information travels from the Tropy database to the
    image the model actually sees.

    Returns the raw_ocr data dict, annotated with `_elapsed` and (when the
    stage did not actually run) `_skipped`.
    """
    f = Path(file_path)
    key = stem or f.stem
    t0 = time.monotonic()

    if skip_ocr:
        log.info("OCR %s [skipped by user]", f.name)
        data = {
            "source_file": str(f),
            "stage": "raw_ocr",
            "extracted_text": "(OCR skipped)",
            "_skipped": True,
        }
    elif resume and not force and _output_exists("raw_ocr", key, output_dir):
        log.info("OCR %s [skip — already done]", key)
        data = {
            "source_file": str(f),
            "stage": "raw_ocr",
            "extracted_text": _load_existing_text("raw_ocr", key, output_dir),
            "_skipped": True,
        }
    else:
        data = ocr.perform(str(f), output_dir=output_dir, page=page, stem=stem,
                           orientation=orientation)

    data["_elapsed"] = time.monotonic() - t0
    return data


def run_cleanup_step(
    raw_data: dict,
    stem: str,
    output_dir: str,
    *,
    skip_cleanup: bool = False,
    resume: bool = True,
    force: bool = False,
) -> dict:
    """Run the cleanup stage for one file, or resolve it from existing output."""
    t0 = time.monotonic()

    if skip_cleanup:
        log.info("Cleanup %s [skipped by user]", stem)
        data = {
            "source_file": raw_data["source_file"],
            "stage": "cleaned",
            "cleaned_text": raw_data["extracted_text"],
            "raw_text": raw_data["extracted_text"],
            "_skipped": True,
        }
    elif resume and not force and _output_exists("cleaned", stem, output_dir):
        log.info("Cleanup %s [skip — already done]", stem)
        data = {
            "source_file": raw_data["source_file"],
            "stage": "cleaned",
            "cleaned_text": _load_existing_text("cleaned", stem, output_dir),
            "raw_text": raw_data["extracted_text"],
            "_skipped": True,
        }
    else:
        data = cleanup.perform(
            raw_data["extracted_text"],
            source_file=raw_data["source_file"],
            output_dir=output_dir,
            stem=stem,
        )

    data["_elapsed"] = time.monotonic() - t0
    return data


def run_translate_step(
    cleaned_data: dict,
    stem: str,
    output_dir: str,
    *,
    resume: bool = True,
    force: bool = False,
) -> dict:
    """Run the translate stage for one file, or resolve it from existing output."""
    t0 = time.monotonic()

    if resume and not force and _output_exists("translated", stem, output_dir):
        log.info("Translate %s [skip — already done]", stem)
        data = {
            "source_file": cleaned_data["source_file"],
            "stage": "translated",
            "translated_text": _load_existing_text("translated", stem, output_dir),
            "cleaned_text": cleaned_data["cleaned_text"],
            "_skipped": True,
        }
    else:
        data = translate.perform(
            cleaned_data["cleaned_text"],
            source_file=cleaned_data["source_file"],
            output_dir=output_dir,
            stem=stem,
        )

    data["_elapsed"] = time.monotonic() - t0
    return data


def _collect_files(input_path: str) -> list[Path]:
    """If input_path is a directory, return all supported files inside it.
    If it's a file, return a single-element list."""
    p = Path(input_path).resolve()
    if p.is_dir():
        files = sorted(
            f for f in p.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not files:
            raise FileNotFoundError(
                f"No supported files ({', '.join(SUPPORTED_EXTENSIONS)}) in {p}"
            )
        return files
    return [p]


def run_pipeline(
    input_path: str,
    output_dir: str = "output",
    *,
    skip_translate: bool = False,
    skip_cleanup: bool = False,
    skip_ocr: bool = False,
    force: bool = False,
) -> dict:
    """
    Orchestrate: OCR -> Cleanup -> Translate for a single file.
    Returns dict with raw, cleaned, and optionally translated data.
    """
    files = _collect_files(input_path)
    if len(files) == 1:
        return _run_single(
            files[0], output_dir,
            skip_translate=skip_translate,
            skip_cleanup=skip_cleanup,
            skip_ocr=skip_ocr,
            force=force,
        )

    return run_pipeline_batch(
        [str(f) for f in files], output_dir,
        skip_translate=skip_translate,
        skip_cleanup=skip_cleanup,
        skip_ocr=skip_ocr,
        force=force,
    )


def _run_single(
    file_path: Path,
    output_dir: str,
    *,
    skip_translate: bool = False,
    skip_cleanup: bool = False,
    skip_ocr: bool = False,
    force: bool = False,
    resume: bool | None = None,
) -> dict:
    """Run the full pipeline on a single file."""
    if resume is None:
        resume = cfg("resume")

    stem = file_path.stem
    t_start = time.monotonic()
    log.info("Starting pipeline for %s", file_path.name)

    raw_data = run_ocr_step(
        file_path, output_dir,
        skip_ocr=skip_ocr, resume=resume, force=force,
    )
    cleaned_data = run_cleanup_step(
        raw_data, stem, output_dir,
        skip_cleanup=skip_cleanup, resume=resume, force=force,
    )

    result = {
        "raw": raw_data,
        "cleaned": cleaned_data,
    }

    if not skip_translate:
        result["translated"] = run_translate_step(
            cleaned_data, stem, output_dir,
            resume=resume, force=force,
        )

    elapsed = time.monotonic() - t_start
    log.info("Pipeline complete for %s in %.1fs", file_path.name, elapsed)
    return result


def run_pipeline_batch(
    file_paths: list[str],
    output_dir: str = "output",
    *,
    skip_translate: bool = False,
    skip_cleanup: bool = False,
    skip_ocr: bool = False,
    force: bool = False,
) -> dict:
    """
    Run pipeline on multiple files in three strictly sequential passes:
      1. OCR all files
      2. Cleanup all files
      3. Translate all files

    Only one inference engine is active at a time.
    Returns dict with per-file results and batch summary.
    """
    resume = cfg("resume")
    files = [Path(f).resolve() for f in file_paths]
    t_batch_start = time.monotonic()
    log.info("Batch: %d file(s), sequential passes", len(files))

    # Phase 1: Sequential OCR
    ocr_results: dict[str, dict] = {}
    ocr_timings: dict[str, float] = {}

    for f in files:
        fpath = str(f)
        stem = f.stem
        t0 = time.monotonic()
        result = run_ocr_step(
            f, output_dir,
            skip_ocr=skip_ocr, resume=resume, force=force,
        )
        elapsed = time.monotonic() - t0
        ocr_results[fpath] = result
        ocr_timings[fpath] = elapsed
        skipped = " [skipped]" if result.get("_skipped") else ""
        log.info(
            "  OCR %s%s -> %d chars (%.1fs)",
            f.name, skipped, len(result["extracted_text"]), elapsed,
        )

    # Phase 2: Sequential cleanup
    cleanup_results: dict[str, dict] = {}
    cleanup_timings: dict[str, float] = {}

    for f in files:
        fpath = str(f)
        stem = f.stem
        raw_data = ocr_results[fpath]
        t0 = time.monotonic()
        cleaned_data = run_cleanup_step(
            raw_data, stem, output_dir,
            skip_cleanup=skip_cleanup, resume=resume, force=force,
        )
        elapsed = time.monotonic() - t0
        cleanup_results[fpath] = cleaned_data
        cleanup_timings[fpath] = elapsed if not cleaned_data.get("_skipped") else 0

    # Phase 3: Sequential translate
    translate_results: dict[str, dict] = {}
    translate_timings: dict[str, float] = {}

    if not skip_translate:
        for f in files:
            fpath = str(f)
            stem = f.stem
            cleaned_data = cleanup_results[fpath]
            t0 = time.monotonic()
            translated_data = run_translate_step(
                cleaned_data, stem, output_dir,
                resume=resume, force=force,
            )
            elapsed = time.monotonic() - t0
            translate_results[fpath] = translated_data
            translate_timings[fpath] = elapsed if not translated_data.get("_skipped") else 0

    # Assemble results
    all_results: dict[str, dict] = {}
    timings: dict[str, dict[str, float]] = {}

    for f in files:
        fpath = str(f)
        file_timings: dict[str, float] = {"ocr": ocr_timings.get(fpath, 0)}
        result: dict[str, Any] = {
            "raw": ocr_results[fpath],
            "cleaned": cleanup_results[fpath],
        }
        if cleanup_timings.get(fpath, 0):
            file_timings["cleanup"] = cleanup_timings[fpath]
        if not skip_translate:
            result["translated"] = translate_results[fpath]
            if translate_timings.get(fpath, 0):
                file_timings["translate"] = translate_timings[fpath]
        all_results[fpath] = result
        timings[fpath] = file_timings

    batch_elapsed = time.monotonic() - t_batch_start
    log.info("Batch complete in %.1fs", batch_elapsed)

    return {
        "files": all_results,
        "batch_size": len(files),
        "batch_elapsed": batch_elapsed,
        "timings": timings,
    }
