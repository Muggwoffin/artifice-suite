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
):
    """Run the full pipeline: OCR -> Cleanup -> Translate.

    Accepts a single image file or a directory. When given a directory,
    all supported images inside it are processed as a batch.
    """
    from src.ocr_pipeline.pipeline import run_pipeline

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
