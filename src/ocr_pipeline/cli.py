from pathlib import Path

import typer

from src.ocr_pipeline._logging import get_logger, setup_logging
from src.ocr_pipeline.config import get as cfg
from src.ocr_pipeline.stages import ocr as ocr_stage
from src.ocr_pipeline.stages import cleanup as cleanup_stage
from src.ocr_pipeline.stages import translate as translate_stage
from src.ocr_pipeline.utils import check_lm_studio, check_ollama

log = get_logger("cli")

app = typer.Typer()


def _ollama_models_needed() -> list[str]:
    models = [cfg("cleanup_model")]
    if cfg("translate_enabled"):
        models.append(cfg("translate_model"))
    return models


@app.command()
def preflight():
    """Run a full-stack health check (LM Studio + Ollama + models)."""
    setup_logging(level=0)  # quiet for preflight table

    typer.echo("Pre-flight check")
    typer.echo("-" * 50)

    # LM Studio
    lm_err = check_lm_studio()
    if lm_err:
        typer.echo(f"  LM Studio:  FAIL  ({lm_err})")
    else:
        typer.echo(f"  LM Studio:  OK    ({cfg('lm_studio_url')})")

    # Ollama
    ollama_errors = check_ollama()
    if ollama_errors:
        typer.echo(f"  Ollama:     FAIL  ({ollama_errors[0]})")
    else:
        typer.echo("  Ollama:     OK")

    # Models
    models_needed = _ollama_models_needed()
    model_errors = check_ollama(models_needed)
    for model in models_needed:
        err = next((e for e in model_errors if model in e), None)
        if err:
            typer.echo(f"  Model:      FAIL  {model}  ({err})")
        else:
            typer.echo(f"  Model:      OK    {model}")

    # Config summary
    typer.echo("-" * 50)
    typer.echo(f"  OCR model:        {cfg('ocr_model')}")
    typer.echo(f"  Cleanup model:    {cfg('cleanup_model')}")
    typer.echo(f"  Translate model:  {cfg('translate_model')}")
    typer.echo(f"  Resume:           {cfg('resume')}")
    typer.echo(f"  Max OCR workers:  {cfg('max_ocr_workers')}")
    typer.echo(f"  Document type:    {cfg('document_type')}")
    typer.echo(f"  Confidence:       {'enabled' if cfg('confidence_enabled') else 'disabled'}")
    typer.echo(f"  Chunk max tokens: {cfg('chunk_max_tokens')}")

    has_failure = bool(lm_err) or bool(ollama_errors) or bool(model_errors)
    if has_failure:
        typer.echo("\nSome checks FAILED — pipeline may not run correctly.")
        raise typer.Exit(code=1)
    else:
        typer.echo("\nAll checks passed.")


@app.command()
def ocr(
    input_path: str,
    output_dir: str = typer.Option("output", help="Output directory"),
):
    """Run the OCR stage on a given input file."""
    err = check_lm_studio()
    if err:
        typer.echo(f"ERROR: {err}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Processing {input_path}...")
    result = ocr_stage.perform(input_path, output_dir=output_dir)
    typer.echo(f"Extracted {len(result['extracted_text'])} characters.")
    typer.echo(f"Text written to {output_dir}/raw_ocr/text/")
    typer.echo(f"JSON written to {output_dir}/raw_ocr/json/")


@app.command()
def cleanup(
    text_path: str = typer.Argument(help="Path to raw OCR text file"),
    output_dir: str = typer.Option("output", help="Output directory"),
):
    """Run conservative syntactic cleanup on a raw OCR text file."""
    errors = check_ollama([cfg("cleanup_model")])
    if any("Cannot reach" in e for e in errors):
        typer.echo(f"ERROR: {errors[0]}", err=True)
        raise typer.Exit(code=1)

    p = Path(text_path)
    if not p.exists():
        raise typer.BadParameter(f"File not found: {text_path}")
    raw_text = p.read_text(encoding="utf-8")

    result = cleanup_stage.perform(
        raw_text,
        source_file=str(p),
        output_dir=output_dir,
    )
    typer.echo(f"Cleaned {len(result['cleaned_text'])} characters (was {len(result['raw_text'])}).")
    typer.echo(f"Text written to {output_dir}/cleaned/text/")
    typer.echo(f"JSON written to {output_dir}/cleaned/json/")


@app.command()
def translate(
    text_path: str = typer.Argument(help="Path to cleaned text file"),
    output_dir: str = typer.Option("output", help="Output directory"),
):
    """Translate a cleaned text file into English."""
    errors = check_ollama([cfg("translate_model")])
    if any("Cannot reach" in e for e in errors):
        typer.echo(f"ERROR: {errors[0]}", err=True)
        raise typer.Exit(code=1)

    p = Path(text_path)
    if not p.exists():
        raise typer.BadParameter(f"File not found: {text_path}")
    cleaned_text = p.read_text(encoding="utf-8")

    result = translate_stage.perform(
        cleaned_text,
        source_file=str(p),
        output_dir=output_dir,
    )
    typer.echo(f"Translated {len(result['translated_text'])} characters (was {len(result['cleaned_text'])}).")
    typer.echo(f"Text written to {output_dir}/translated/text/")
    typer.echo(f"JSON written to {output_dir}/translated/json/")


@app.command()
def pipeline(
    input_path: str = typer.Argument(
        help="Path to image file or directory of images"
    ),
    output_dir: str = typer.Option("output", help="Output directory"),
    skip_ocr: bool = typer.Option(False, "--skip-ocr", help="Skip the OCR stage"),
    skip_cleanup: bool = typer.Option(False, "--skip-cleanup", help="Skip the cleanup stage"),
    skip_translate: bool = typer.Option(False, "--skip-translate", help="Skip the translation stage"),
    force: bool = typer.Option(False, "--force", help="Re-process even if outputs exist"),
    document_type: str = typer.Option("default", "--doc-type", help="Document type (default, handwritten, typed_clean, technical, formal, casual, multi_lang)"),
    no_confidence: bool = typer.Option(False, "--no-confidence", help="Disable confidence scoring"),
):
    """Run the full pipeline: OCR -> Cleanup -> Translate.

    Accepts a single image file or a directory. When given a directory,
    all supported images inside it are processed as a batch.
    """
    from src.ocr_pipeline import config
    from src.ocr_pipeline.pipeline import run_pipeline

    # Apply CLI overrides to config
    config.apply_overrides({
        "document_type": document_type,
        "confidence_enabled": not no_confidence,
    })

    # Only check services for stages that will actually run
    if not skip_ocr:
        lm_err = check_lm_studio()
        if lm_err:
            typer.echo(f"ERROR: {lm_err}", err=True)
            raise typer.Exit(code=1)

    ollama_models = []
    if not skip_cleanup:
        ollama_models.append(cfg("cleanup_model"))
    if not skip_translate:
        ollama_models.append(cfg("translate_model"))
    if ollama_models:
        ollama_errors = check_ollama(ollama_models)
        if any("Cannot reach" in e for e in ollama_errors):
            typer.echo(f"ERROR: {ollama_errors[0]}", err=True)
            raise typer.Exit(code=1)

    p = Path(input_path)
    if p.is_dir():
        from src.ocr_pipeline.stages.ocr import SUPPORTED_EXTENSIONS
        files = sorted(
            f for f in p.iterdir()
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not files:
            typer.echo(f"No supported files in {input_path}", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Running batch pipeline for {len(files)} file(s)...")
        result = run_pipeline(
            input_path, output_dir=output_dir,
            skip_translate=skip_translate,
            skip_cleanup=skip_cleanup,
            skip_ocr=skip_ocr,
            force=force,
        )

        _print_batch_summary(result, output_dir)
    else:
        stages_done = []
        if not skip_ocr:
            stages_done.append("raw")
        if not skip_cleanup:
            stages_done.append("cleaned")
        if not skip_translate:
            stages_done.append("translated")

        typer.echo(f"Running pipeline for {input_path} ({', '.join(stages_done)})...")
        result = run_pipeline(
            input_path, output_dir=output_dir,
            skip_translate=skip_translate,
            skip_cleanup=skip_cleanup,
            skip_ocr=skip_ocr,
            force=force,
        )

        typer.echo("Pipeline complete.")
        if not skip_ocr:
            typer.echo(f"  OCR:       {len(result['raw']['extracted_text'])} chars")
        if not skip_cleanup:
            typer.echo(f"  Cleanup:   {len(result['cleaned']['cleaned_text'])} chars")
        if "translated" in result:
            typer.echo(f"  Translate: {len(result['translated']['translated_text'])} chars")
        typer.echo(f"Output: {output_dir}/")


@app.command("tropy-browse")
def tropy_browse(
    project: str = typer.Argument(
        None, help="Path to a .tropy project (omit to list recent projects)"
    ),
):
    """Browse a Tropy project: its lists, tags and items.

    Read-only — this never writes to the Tropy database.
    """
    from src.ocr_pipeline.tropy import TropyProject, recent_projects

    if project is None:
        found = recent_projects()
        if not found:
            typer.echo("No recent Tropy projects found.")
            raise typer.Exit(code=1)
        typer.echo("Recent Tropy projects:")
        for p in found:
            typer.echo(f"  {p}")
        return

    with TropyProject(project) as proj:
        typer.echo(f"Project: {proj.name}   ({proj.db_path})")

        typer.echo("\nLists:")
        for lst in proj.lists():
            typer.echo(f"  [{lst.list_id:3}] {lst.label}")

        tags = [t for t in proj.tags() if t[1]]
        if tags:
            typer.echo("\nTags:")
            for name, count in tags:
                typer.echo(f"  {count:5}  {name}")

        items = proj.items()
        total_pages = sum(i.photo_count for i in items)
        typer.echo(f"\nItems: {len(items)}  ({total_pages} pages total)")
        for item in items[:40]:
            typer.echo(f"  [{item.item_id:5}] {item.title}  ({item.photo_count}p)")
        if len(items) > 40:
            typer.echo(f"  ... and {len(items) - 40} more")


@app.command("tropy")
def tropy(
    project: str = typer.Argument(help="Path to a .tropy project"),
    output_dir: str = typer.Option("output", help="Output directory"),
    list_id: int = typer.Option(None, "--list-id", help="Process one list (and its sub-lists)"),
    tag: str = typer.Option(None, "--tag", help="Process items carrying this tag"),
    item_id: list[int] = typer.Option(None, "--item-id", help="Process specific item(s)"),
    limit: int = typer.Option(None, "--limit", help="Stop after N pages (useful for a trial run)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List the work without running it"),
    skip_cleanup: bool = typer.Option(False, "--skip-cleanup", help="Skip the cleanup stage"),
    skip_translate: bool = typer.Option(True, "--skip-translate/--translate",
                                        help="Skip translation (default: skipped)"),
    force: bool = typer.Option(False, "--force", help="Re-process even if outputs exist"),
    document_type: str = typer.Option("default", "--doc-type", help="Document type"),
):
    """OCR a Tropy project into a folder.

    Outputs land in the normal `<output_dir>/<stage>/text/` tree, keyed by
    item title and page (`Max Hodann KV File Part 1/KV-2-2339_01_p0002`),
    plus a `tropy_manifest.json` mapping every output back to its photo.

    The Tropy project is opened read-only and is never modified.
    """
    import queue as _queue

    from src.ocr_pipeline import config
    from src.ocr_pipeline.jobs import JobRunner
    from src.ocr_pipeline.tropy import TropyProject, pages_to_job_items, write_manifest

    config.apply_overrides({"document_type": document_type})

    with TropyProject(project) as proj:
        if list_id is not None:
            ids = proj.item_ids_in_list(list_id)
            scope = f"list {list_id}"
        elif tag:
            ids = proj.item_ids_with_tag(tag)
            scope = f"tag '{tag}'"
        elif item_id:
            ids = list(item_id)
            scope = f"{len(ids)} item(s)"
        else:
            ids = None
            scope = "whole project"

        if ids is not None and not ids:
            typer.echo(f"No items matched {scope}.", err=True)
            raise typer.Exit(code=1)

        pages = proj.pages(ids)
        if not pages:
            typer.echo(f"No pages found for {scope}.", err=True)
            raise typer.Exit(code=1)

        missing = proj.missing_assets(pages)
        if missing:
            typer.echo(f"WARNING: {len(missing)} page(s) have no file on disk "
                       f"(e.g. {missing[0].path.name}) — they will fail.")

        if limit:
            pages = pages[:limit]

        typer.echo(f"{proj.name}: {scope} -> {len(pages)} page(s)")

        if dry_run:
            for page in pages[:60]:
                typer.echo(f"  {page.label:34} -> {page.output_stem}")
            if len(pages) > 60:
                typer.echo(f"  ... and {len(pages) - 60} more")
            typer.echo("\nDry run — nothing was processed.")
            return

        if not skip_cleanup:
            errors = check_ollama([cfg("cleanup_model")])
            if any("Cannot reach" in e for e in errors):
                typer.echo(f"ERROR: {errors[0]}", err=True)
                raise typer.Exit(code=1)
        lm_err = check_lm_studio()
        if lm_err:
            typer.echo(f"ERROR: {lm_err}", err=True)
            raise typer.Exit(code=1)

        manifest = write_manifest(output_dir, proj, pages)
        typer.echo(f"Manifest: {manifest}")

        stages = {"ocr"}
        if not skip_cleanup:
            stages.add("cleanup")
        if not skip_translate:
            stages.add("translate")

        items = pages_to_job_items(pages)
        events: _queue.Queue = _queue.Queue()
        runner = JobRunner(items, output_dir, stages=stages, force=force,
                           events=events)
        runner.start()

        done = 0
        while True:
            event = events.get()
            if event.message:
                typer.echo(f"  {event.message}")
            if event.kind == "item_finished":
                done += 1
                typer.echo(f"  --- {done}/{len(items)} ---")
            if event.kind == "run_finished":
                break

        failed = [i for i in items if i.state.value == "failed"]
        typer.echo(f"\nComplete: {len(items) - len(failed)} ok, {len(failed)} failed")
        typer.echo(f"Output: {output_dir}/")
        if failed:
            raise typer.Exit(code=1)


def _print_batch_summary(result: dict, output_dir: str):
    """Print a detailed summary table for batch processing."""
    files = result.get("files", {})
    timings = result.get("timings", {})
    batch_elapsed = result.get("batch_elapsed", 0)
    batch_size = result.get("batch_size", len(files))

    typer.echo(f"\n{'='*60}")
    typer.echo(f"  BATCH SUMMARY — {batch_size} file(s)  ({batch_elapsed:.1f}s)")
    typer.echo(f"{'='*60}")

    for fpath, data in files.items():
        name = Path(fpath).name
        ocr_chars = len(data["raw"]["extracted_text"])
        clean_chars = len(data["cleaned"]["cleaned_text"])
        skip_marker = " [skip]" if data.get("raw", {}).get("_skipped") else ""

        line = f"  {name}{skip_marker}"
        line += f"  OCR:{ocr_chars}  Clean:{clean_chars}"

        if "translated" in data:
            trans_chars = len(data["translated"]["translated_text"])
            lang = data["translated"].get("source_language_name", "?")
            line += f"  Trans:{trans_chars} ({lang})"
            conf = data["translated"].get("confidence", {}).get("overall_score")
            if conf is not None:
                line += f"  conf:{conf}/100"

        file_t = timings.get(fpath, {})
        parts = []
        if "ocr" in file_t:
            parts.append(f"ocr={file_t['ocr']:.1f}s")
        if "cleanup" in file_t:
            parts.append(f"clean={file_t['cleanup']:.1f}s")
        if "translate" in file_t:
            parts.append(f"trans={file_t['translate']:.1f}s")
        if parts:
            line += f"  [{', '.join(parts)}]"

        typer.echo(line)

    typer.echo(f"{'='*60}")
    typer.echo(f"Output: {output_dir}/")


if __name__ == "__main__":
    app()
