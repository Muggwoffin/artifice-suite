import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
) -> dict:
    """Run the OCR stage for one file, or resolve it from existing output.

    `page` selects a single 0-based PDF page; `stem` overrides the output key,
    which is what keeps per-page outputs from colliding on the filename stem.

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
        data = ocr.perform(str(f), output_dir=output_dir, page=page, stem=stem)

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
    Run pipeline on multiple files. OCR runs concurrently,
    cleanup and translate serialize per-file.
    Returns dict with per-file results and batch summary.
    """
    resume = cfg("resume")
    max_workers = cfg("max_ocr_workers")

    files = [Path(f).resolve() for f in file_paths]
    t_batch_start = time.monotonic()
    log.info("Batch: %d file(s), OCR workers=%d", len(files), max_workers)

    # Phase 1: Concurrent OCR
    ocr_results: dict[str, dict] = {}
    ocr_texts: dict[str, str] = {}
    ocr_timings: dict[str, float] = {}

    def _run_ocr(f: Path) -> tuple[str, dict]:
        return (str(f), run_ocr_step(
            f, output_dir,
            skip_ocr=skip_ocr, resume=resume, force=force,
        ))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_ocr, f): f for f in files}
        for future in as_completed(futures):
            fpath, result = future.result()
            stem = Path(fpath).stem
            ocr_results[fpath] = result
            ocr_texts[fpath] = result["extracted_text"]
            ocr_timings[fpath] = result.get("_elapsed", 0)
            skipped = " [skipped]" if result.get("_skipped") else ""
            log.info(
                "  OCR %s%s -> %d chars (%.1fs)",
                Path(fpath).name, skipped,
                len(result["extracted_text"]),
                ocr_timings[fpath],
            )

    # Phase 2: Serial cleanup + translate (per file, in order)
    all_results: dict[str, dict] = {}
    timings: dict[str, dict[str, float]] = {}

    for f in files:
        fpath = str(f)
        raw_data = ocr_results[fpath]
        stem = f.stem
        file_timings: dict[str, float] = {"ocr": ocr_timings.get(fpath, 0)}

        cleaned_data = run_cleanup_step(
            raw_data, stem, output_dir,
            skip_cleanup=skip_cleanup, resume=resume, force=force,
        )
        if not cleaned_data.get("_skipped"):
            file_timings["cleanup"] = cleaned_data["_elapsed"]

        result: dict[str, Any] = {"raw": raw_data, "cleaned": cleaned_data}

        if not skip_translate:
            translated_data = run_translate_step(
                cleaned_data, stem, output_dir,
                resume=resume, force=force,
            )
            if not translated_data.get("_skipped"):
                file_timings["translate"] = translated_data["_elapsed"]
            result["translated"] = translated_data

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
