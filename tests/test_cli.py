import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from src.ocr_pipeline.cli import app

runner = CliRunner()


def _mock_openai_response(text="Sample extracted text"):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = text
    return mock_resp


# ---------------------------------------------------------------------------
# OCR stage tests
# ---------------------------------------------------------------------------

@patch("src.ocr_pipeline.stages.ocr._get_client")
def test_ocr_stage_writes_files(mock_get_client, tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response("Hello from OCR")
    mock_get_client.return_value = mock_client

    from src.ocr_pipeline.stages import ocr

    test_image = tmp_path / "doc.png"
    test_image.write_bytes(b"\x89PNG fake")

    out_dir = tmp_path / "output"
    result = ocr.perform(str(test_image), output_dir=str(out_dir))

    assert result["extracted_text"] == "Hello from OCR"
    assert result["engine"] == "lm-studio"
    assert result["model"] == "allenai/olmocr-2-7b"
    assert "timestamp" in result

    text_file = out_dir / "raw_ocr" / "text" / "doc.txt"
    json_file = out_dir / "raw_ocr" / "json" / "doc.json"
    assert text_file.exists()
    assert json_file.exists()
    assert text_file.read_text(encoding="utf-8") == "Hello from OCR"

    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["source_file"] == str(test_image.resolve())
    assert data["stage"] == "raw_ocr"

    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args
    assert call_kwargs.kwargs["model"] == "allenai/olmocr-2-7b"
    user_msg = call_kwargs.kwargs["messages"][0]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    assert len(user_msg["content"]) == 2
    assert user_msg["content"][0]["type"] == "text"
    assert user_msg["content"][1]["type"] == "image_url"
    assert "base64," in user_msg["content"][1]["image_url"]["url"]


@patch("src.ocr_pipeline.stages.ocr._get_client")
def test_ocr_stage_rejects_unsupported_type(mock_get_client, tmp_path):
    from src.ocr_pipeline.stages import ocr

    test_file = tmp_path / "doc.bmp"
    test_file.write_bytes(b"fake")

    try:
        ocr.perform(str(test_file))
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unsupported file type" in str(e)

    mock_get_client.assert_not_called()


@patch("src.ocr_pipeline.stages.ocr._get_client")
def test_ocr_cli_wires_through(mock_get_client, tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response("CLI test text")
    mock_get_client.return_value = mock_client

    test_image = tmp_path / "scan.tiff"
    test_image.write_bytes(b"fake tiff")
    out_dir = tmp_path / "cli_output"

    result = runner.invoke(
        app, ["ocr", str(test_image), "--output-dir", str(out_dir)]
    )
    assert result.exit_code == 0
    assert "Processing" in result.output
    assert "CLI test text" in json.loads(
        (out_dir / "raw_ocr" / "json" / "scan.json").read_text(encoding="utf-8")
    )["extracted_text"]


@patch("src.ocr_pipeline.stages.ocr._get_client")
def test_raw_output_preserved_fully(mock_get_client, tmp_path):
    noisy_text = "  Dr. Smith's 1938 report — pg. 1  "
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(noisy_text)
    mock_get_client.return_value = mock_client

    from src.ocr_pipeline.stages import ocr

    test_image = tmp_path / "archival.jpg"
    test_image.write_bytes(b"fake jpg")
    out_dir = tmp_path / "output"

    result = ocr.perform(str(test_image), output_dir=str(out_dir))
    assert result["extracted_text"] == noisy_text

    text_file = out_dir / "raw_ocr" / "text" / "archival.txt"
    assert text_file.read_text(encoding="utf-8") == noisy_text


# ---------------------------------------------------------------------------
# Cleanup stage tests
# ---------------------------------------------------------------------------

@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_cleanup_stage_writes_files(mock_chat, tmp_path):
    mock_chat.return_value = MagicMock(message=MagicMock(content="Cleaned output text"))

    from src.ocr_pipeline.stages import cleanup

    out_dir = tmp_path / "output"
    result = cleanup.perform(
        "Dirty OCR text here",
        source_file="doc.png",
        output_dir=str(out_dir),
    )

    assert result["cleaned_text"] == "Cleaned output text"
    assert result["raw_text"] == "Dirty OCR text here"
    assert result["engine"] == "ollama"
    assert result["model"] == "gemma4:12b"
    assert result["source_file"] == "doc.png"
    assert "timestamp" in result

    text_file = out_dir / "cleaned" / "text" / "doc.txt"
    json_file = out_dir / "cleaned" / "json" / "doc.json"
    assert text_file.exists()
    assert json_file.exists()
    assert text_file.read_text(encoding="utf-8") == "Cleaned output text"

    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["stage"] == "cleaned"
    assert data["raw_text"] == "Dirty OCR text here"

    mock_chat.assert_called_once()
    call_kwargs = mock_chat.call_args
    assert call_kwargs.kwargs["model"] == "gemma4:12b"


@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_cleanup_stage_uses_prompt_file(mock_chat, tmp_path):
    mock_chat.return_value = MagicMock(message=MagicMock(content="ok"))

    from src.ocr_pipeline.stages import cleanup

    cleanup.perform("test text", output_dir=str(tmp_path))

    call_kwargs = mock_chat.call_args
    messages = call_kwargs.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "archivist" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "test text" in messages[1]["content"]
    assert "{raw_text}" not in messages[1]["content"]


@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_cleanup_cli_wires_through(mock_chat, tmp_path):
    mock_chat.return_value = MagicMock(message=MagicMock(content="Cleaned via CLI"))

    raw_file = tmp_path / "raw_ocr.txt"
    raw_file.write_text("Some raw OCR output", encoding="utf-8")
    out_dir = tmp_path / "cli_output"

    result = runner.invoke(
        app, ["cleanup", str(raw_file), "--output-dir", str(out_dir)]
    )
    assert result.exit_code == 0
    assert "Cleaned" in result.output

    json_file = out_dir / "cleaned" / "json" / "raw_ocr.json"
    assert json_file.exists()
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["cleaned_text"] == "Cleaned via CLI"
    assert data["raw_text"] == "Some raw OCR output"


@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_cleanup_preserves_raw_text_in_json(mock_chat, tmp_path):
    raw = "Hon. J. Smith, Dec. 1938 — re: budget"
    mock_chat.return_value = MagicMock(message=MagicMock(content="cleaned version"))

    from src.ocr_pipeline.stages import cleanup

    out_dir = tmp_path / "output"
    result = cleanup.perform(raw, source_file="report.tif", output_dir=str(out_dir))

    json_file = out_dir / "cleaned" / "json" / "report.json"
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["raw_text"] == raw
    assert data["source_file"] == "report.tif"


# ---------------------------------------------------------------------------
# Translate stage tests
# ---------------------------------------------------------------------------

@patch("src.ocr_pipeline.stages.translate.ollama.chat")
def test_translate_stage_writes_files(mock_chat, tmp_path):
    mock_chat.return_value = MagicMock(message=MagicMock(content="Translated output text"))

    from src.ocr_pipeline.stages import translate

    out_dir = tmp_path / "output"
    result = translate.perform(
        "German text here",
        source_file="doc.txt",
        output_dir=str(out_dir),
    )

    assert result["translated_text"] == "Translated output text"
    assert result["cleaned_text"] == "German text here"
    assert result["engine"] == "ollama"
    assert result["model"] == "translategemma:4b"
    assert result["source_file"] == "doc.txt"
    assert result["stage"] == "translated"
    assert "timestamp" in result
    assert "source_language" in result

    text_file = out_dir / "translated" / "text" / "doc.txt"
    json_file = out_dir / "translated" / "json" / "doc.json"
    assert text_file.exists()
    assert json_file.exists()
    assert text_file.read_text(encoding="utf-8") == "Translated output text"

    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["stage"] == "translated"
    assert data["cleaned_text"] == "German text here"
    assert "source_language" in data

    # 2 calls: language detection + translation
    assert mock_chat.call_count == 2


@patch("src.ocr_pipeline.stages.translate.ollama.chat")
def test_translate_stage_uses_prompt_file(mock_chat, tmp_path):
    mock_chat.return_value = MagicMock(message=MagicMock(content="ok"))

    from src.ocr_pipeline.stages import translate

    translate.perform("Ein Test", output_dir=str(tmp_path))

    call_kwargs = mock_chat.call_args
    messages = call_kwargs.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "translator" in messages[0]["content"].lower()
    assert messages[1]["role"] == "user"
    assert "Ein Test" in messages[1]["content"]
    assert "{text}" not in messages[1]["content"]


@patch("src.ocr_pipeline.stages.translate.ollama.chat")
def test_translate_cli_wires_through(mock_chat, tmp_path):
    mock_chat.return_value = MagicMock(message=MagicMock(content="Translated via CLI"))

    cleaned_file = tmp_path / "cleaned.txt"
    cleaned_file.write_text("Some cleaned text", encoding="utf-8")
    out_dir = tmp_path / "cli_output"

    result = runner.invoke(
        app, ["translate", str(cleaned_file), "--output-dir", str(out_dir)]
    )
    assert result.exit_code == 0
    assert "Translated" in result.output

    json_file = out_dir / "translated" / "json" / "cleaned.json"
    assert json_file.exists()
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["translated_text"] == "Translated via CLI"
    assert data["cleaned_text"] == "Some cleaned text"


@patch("src.ocr_pipeline.stages.translate.ollama.chat")
def test_translate_preserves_cleaned_text_in_json(mock_chat, tmp_path):
    cleaned = "Die Dokumente aus dem Jahr 1938"
    mock_chat.return_value = MagicMock(message=MagicMock(content="The documents from 1938"))

    from src.ocr_pipeline.stages import translate

    out_dir = tmp_path / "output"
    result = translate.perform(cleaned, source_file="report.txt", output_dir=str(out_dir))

    json_file = out_dir / "translated" / "json" / "report.json"
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["cleaned_text"] == cleaned
    assert data["source_file"] == "report.txt"


# ---------------------------------------------------------------------------
# Language detection tests
# ---------------------------------------------------------------------------

@patch("src.ocr_pipeline.stages.translate.ollama.chat")
def test_detect_language_returns_iso_code(mock_chat, tmp_path):
    mock_chat.return_value = MagicMock(message=MagicMock(content="de"))

    from src.ocr_pipeline.stages.translate import detect_language

    lang = detect_language("Das ist ein Test")
    assert lang == "de"

    call_kwargs = mock_chat.call_args
    assert call_kwargs.kwargs["model"] == "translategemma:4b"
    assert "Identify the primary language" in call_kwargs.kwargs["messages"][0]["content"]


@patch("src.ocr_pipeline.stages.translate.ollama.chat")
def test_detect_language_handles_garbled_response(mock_chat, tmp_path):
    mock_chat.return_value = MagicMock(message=MagicMock(content="The language is German."))

    from src.ocr_pipeline.stages.translate import detect_language

    lang = detect_language("Some text")
    assert lang == "unknown"


@patch("src.ocr_pipeline.stages.translate.ollama.chat")
def test_translate_includes_detected_language_in_json(mock_chat, tmp_path):
    mock_chat.side_effect = [
        MagicMock(message=MagicMock(content="fr")),
        MagicMock(message=MagicMock(content="The documents from 1938")),
    ]

    from src.ocr_pipeline.stages import translate

    result = translate.perform(
        "Les documents de 1938",
        source_file="archive.txt",
        output_dir=str(tmp_path / "out"),
    )

    assert result["source_language"] == "fr"
    assert result["source_language_name"] == "French"


# ---------------------------------------------------------------------------
# Config loading tests
# ---------------------------------------------------------------------------

def test_config_defaults_are_set():
    from src.ocr_pipeline import config

    config.reset()
    cfg = config.load_config()
    assert cfg["ocr_model"] == "allenai/olmocr-2-7b"
    assert cfg["cleanup_model"] == "gemma4:12b"
    assert cfg["translate_model"] == "translategemma:4b"
    assert cfg["lm_studio_url"] == "http://localhost:1234/v1"
    config.reset()


def test_config_file_override(tmp_path):
    from src.ocr_pipeline import config

    cfg_file = tmp_path / "test.yaml"
    cfg_file.write_text(
        'ocr_model: "custom-model"\noutput_dir: "/tmp/out"\n',
        encoding="utf-8",
    )

    config.reset()
    cfg = config.load_config(cfg_file)
    assert cfg["ocr_model"] == "custom-model"
    assert cfg["output_dir"] == "/tmp/out"
    assert cfg["cleanup_model"] == "gemma4:12b"  # default preserved
    config.reset()


def test_config_env_override(tmp_path, monkeypatch):
    from src.ocr_pipeline import config

    monkeypatch.setenv("OCR_MODEL", "env-model")

    config.reset()
    cfg = config.load_config()
    assert cfg["ocr_model"] == "env-model"
    config.reset()


def test_config_get_shorthand():
    from src.ocr_pipeline import config

    config.reset()
    assert config.get("ocr_model") == "allenai/olmocr-2-7b"
    assert config.get("nonexistent", "fallback") == "fallback"
    config.reset()


# ---------------------------------------------------------------------------
# PDF OCR tests
# ---------------------------------------------------------------------------

@patch("src.ocr_pipeline.stages.ocr._ocr_single_image")
@patch("src.ocr_pipeline.stages.ocr._pdf_to_page_images")
def test_pdf_ocr_concatenates_pages(mock_pages, mock_ocr, tmp_path):
    mock_pages.return_value = [tmp_path / "p1.png", tmp_path / "p2.png"]
    mock_ocr.side_effect = ["Text from page 1", "Text from page 2"]

    from src.ocr_pipeline.stages import ocr

    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"fake pdf")

    out_dir = tmp_path / "output"
    result = ocr.perform(str(pdf_path), output_dir=str(out_dir))

    assert "Page Break" in result["extracted_text"]
    assert "Text from page 1" in result["extracted_text"]
    assert "Text from page 2" in result["extracted_text"]
    assert result["total_pages"] == 2
    assert mock_ocr.call_count == 2


@patch("src.ocr_pipeline.stages.ocr._ocr_single_image")
def test_single_image_ocr_sets_total_pages_1(mock_ocr, tmp_path):
    mock_ocr.return_value = "Single page text"

    from src.ocr_pipeline.stages import ocr

    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG fake")

    result = ocr.perform(str(img), output_dir=str(tmp_path / "out"))
    assert result["total_pages"] == 1


# ---------------------------------------------------------------------------
# P2: Folder input / batch pipeline tests
# ---------------------------------------------------------------------------

@patch("src.ocr_pipeline.stages.ocr._get_client")
@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
@patch("src.ocr_pipeline.stages.translate.ollama.chat")
def test_pipeline_batch_folder(mock_translate, mock_cleanup, mock_get_client, tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response("Batch OCR text")
    mock_get_client.return_value = mock_client
    mock_cleanup.return_value = MagicMock(message=MagicMock(content="Batch cleaned"))
    mock_translate.side_effect = [
        MagicMock(message=MagicMock(content="en")),
        MagicMock(message=MagicMock(content="Batch translated")),
    ]

    scan_dir = tmp_path / "scans"
    scan_dir.mkdir()
    for i in range(3):
        img = scan_dir / f"scan_{i}.png"
        img.write_bytes(b"\x89PNG fake")

    out_dir = tmp_path / "output"
    result = runner.invoke(
        app, ["pipeline", str(scan_dir), "--output-dir", str(out_dir)]
    )
    assert result.exit_code == 0
    assert "3 file(s)" in result.output

    for i in range(3):
        assert (out_dir / "raw_ocr" / "text" / f"scan_{i}.txt").exists()


@patch("src.ocr_pipeline.stages.ocr._get_client")
@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_pipeline_skip_translate(mock_cleanup, mock_get_client, tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response("OCR text")
    mock_get_client.return_value = mock_client
    mock_cleanup.return_value = MagicMock(message=MagicMock(content="Cleaned text"))

    img = tmp_path / "doc.png"
    img.write_bytes(b"\x89PNG fake")
    out_dir = tmp_path / "output"

    result = runner.invoke(
        app, ["pipeline", str(img), "--output-dir", str(out_dir), "--skip-translate"]
    )
    assert result.exit_code == 0
    assert (out_dir / "raw_ocr" / "text" / "doc.txt").exists()
    assert (out_dir / "cleaned" / "text" / "doc.txt").exists()
    assert not (out_dir / "translated" / "text" / "doc.txt").exists()


@patch("src.ocr_pipeline.stages.ocr._get_client")
@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_pipeline_force_reprocess(mock_cleanup, mock_get_client, tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response("Fresh OCR")
    mock_get_client.return_value = mock_client
    mock_cleanup.return_value = MagicMock(message=MagicMock(content="Fresh cleaned"))

    img = tmp_path / "doc.png"
    img.write_bytes(b"\x89PNG fake")
    out_dir = tmp_path / "output"

    # First run — creates output
    runner.invoke(app, ["pipeline", str(img), "--output-dir", str(out_dir)])
    text_file = out_dir / "raw_ocr" / "text" / "doc.txt"
    assert text_file.read_text(encoding="utf-8") == "Fresh OCR"
    mock_client.chat.completions.create.assert_called_once()

    # Second run without --force — should skip OCR
    mock_client.chat.completions.create.reset_mock()
    mock_cleanup.reset_mock()
    runner.invoke(app, ["pipeline", str(img), "--output-dir", str(out_dir)])
    mock_client.chat.completions.create.assert_not_called()
    mock_cleanup.assert_not_called()

    # Third run with --force — should re-run everything
    mock_client.chat.completions.create.return_value = _mock_openai_response("Re-OCR")
    mock_cleanup.return_value = MagicMock(message=MagicMock(content="Re-cleaned"))
    runner.invoke(app, ["pipeline", str(img), "--output-dir", str(out_dir), "--force"])
    mock_client.chat.completions.create.assert_called_once()
    assert text_file.read_text(encoding="utf-8") == "Re-OCR"


@patch("src.ocr_pipeline.stages.ocr._get_client")
def test_collect_files_directory(mock_get_client, tmp_path):
    from src.ocr_pipeline.pipeline import _collect_files

    scan_dir = tmp_path / "scans"
    scan_dir.mkdir()
    (scan_dir / "a.png").write_bytes(b"fake")
    (scan_dir / "b.pdf").write_bytes(b"fake")
    (scan_dir / "c.txt").write_text("unsupported")
    (scan_dir / "d.jpg").write_bytes(b"fake")

    files = _collect_files(str(scan_dir))
    names = [f.name for f in files]
    assert "a.png" in names
    assert "b.pdf" in names
    assert "d.jpg" in names
    assert "c.txt" not in names


@patch("src.ocr_pipeline.stages.ocr._get_client")
def test_collect_files_empty_directory_raises(mock_get_client, tmp_path):
    from src.ocr_pipeline.pipeline import _collect_files

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    try:
        _collect_files(str(empty_dir))
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        assert "No supported files" in str(e)


def test_resume_config_default():
    from src.ocr_pipeline import config
    config.reset()
    assert config.get("resume") is True
    config.reset()


def test_max_ocr_workers_config_default():
    from src.ocr_pipeline import config
    config.reset()
    assert config.get("max_ocr_workers") == 2
    config.reset()


# ---------------------------------------------------------------------------
# P3: Retry logic tests
# ---------------------------------------------------------------------------

def test_retry_succeeds_on_first_attempt():
    from src.ocr_pipeline._retry import retry

    call_count = 0

    @retry(max_attempts=3, base_delay=0.01, label="test")
    def succeed():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = succeed()
    assert result == "ok"
    assert call_count == 1


def test_retry_retries_on_failure_then_succeeds():
    from src.ocr_pipeline._retry import retry

    call_count = 0

    @retry(max_attempts=3, base_delay=0.01, label="test")
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("transient")
        return "recovered"

    result = flaky()
    assert result == "recovered"
    assert call_count == 3


def test_retry_raises_after_max_attempts():
    from src.ocr_pipeline._retry import retry

    @retry(max_attempts=2, base_delay=0.01, label="test")
    def always_fail():
        raise ConnectionError("permanent")

    try:
        always_fail()
        assert False, "Should have raised"
    except ConnectionError:
        pass


def test_retry_ignores_non_retryable_exceptions():
    from src.ocr_pipeline._retry import retry

    @retry(max_attempts=3, base_delay=0.01, label="test")
    def value_error():
        raise ValueError("not retryable")

    try:
        value_error()
        assert False, "Should have raised"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# P3: Preflight command tests
# ---------------------------------------------------------------------------

@patch("src.ocr_pipeline.cli.check_lm_studio")
@patch("src.ocr_pipeline.cli.check_ollama")
def test_preflight_passes(mock_ollama, mock_lm):
    mock_lm.return_value = None
    mock_ollama.return_value = []

    result = runner.invoke(app, ["preflight"])
    assert result.exit_code == 0
    assert "All checks passed" in result.output


@patch("src.ocr_pipeline.cli.check_lm_studio")
@patch("src.ocr_pipeline.cli.check_ollama")
def test_preflight_shows_lm_failure(mock_ollama, mock_lm):
    mock_lm.return_value = "Cannot reach LM Studio"
    mock_ollama.return_value = []

    result = runner.invoke(app, ["preflight"])
    assert result.exit_code == 1
    assert "FAIL" in result.output


# ---------------------------------------------------------------------------
# P3: --skip-cleanup and --skip-ocr CLI flags
# ---------------------------------------------------------------------------

@patch("src.ocr_pipeline.stages.ocr._get_client")
@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_pipeline_skip_cleanup(mock_cleanup, mock_get_client, tmp_path):
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response("OCR text")
    mock_get_client.return_value = mock_client

    img = tmp_path / "doc.png"
    img.write_bytes(b"\x89PNG fake")
    out_dir = tmp_path / "output"

    result = runner.invoke(
        app, ["pipeline", str(img), "--output-dir", str(out_dir), "--skip-cleanup", "--skip-translate"]
    )
    assert result.exit_code == 0
    assert (out_dir / "raw_ocr" / "text" / "doc.txt").exists()
    assert not (out_dir / "cleaned" / "text" / "doc.txt").exists()
    assert not (out_dir / "translated" / "text" / "doc.txt").exists()
    mock_cleanup.assert_not_called()


@patch("src.ocr_pipeline.stages.ocr._get_client")
@patch("src.ocr_pipeline.stages.cleanup.ollama.chat")
def test_pipeline_skip_ocr(mock_cleanup, mock_get_client, tmp_path):
    mock_cleanup.return_value = MagicMock(message=MagicMock(content="Cleaned text"))

    img = tmp_path / "doc.png"
    img.write_bytes(b"\x89PNG fake")
    out_dir = tmp_path / "output"

    result = runner.invoke(
        app, ["pipeline", str(img), "--output-dir", str(out_dir), "--skip-ocr", "--skip-translate"]
    )
    assert result.exit_code == 0
    assert not (out_dir / "raw_ocr" / "text" / "doc.txt").exists()
    assert (out_dir / "cleaned" / "text" / "doc.txt").exists()
    mock_get_client.assert_not_called()


# ---------------------------------------------------------------------------
# P3: Config apply_overrides
# ---------------------------------------------------------------------------

def test_config_apply_overrides():
    from src.ocr_pipeline import config
    config.reset()
    config.apply_overrides({"ocr_model": "custom-model", "resume": False})
    assert config.get("ocr_model") == "custom-model"
    assert config.get("resume") is False
    assert config.get("cleanup_model") == "gemma4:12b"  # default preserved
    config.reset()
