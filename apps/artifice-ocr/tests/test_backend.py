"""Tests that pin the seam: all OpenAI client construction flows through _backend."""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from artifice_ocr import _backend, config


# ---------------------------------------------------------------------------
# Static audit: no OpenAI( outside _backend.py
# ---------------------------------------------------------------------------

def _source_files_under(pkg_dir: Path) -> list[Path]:
    return sorted(p for p in pkg_dir.rglob("*.py") if p.name != "__init__.py")


def test_no_openai_construction_outside_backend_module():
    """Every ``OpenAI(...)`` call in the source tree must live in _backend.py."""
    src_root = Path(__file__).resolve().parent.parent / "src" / "artifice_ocr"
    backend_file = src_root / "_backend.py"

    violations: list[tuple[str, int]] = []

    for py_file in _source_files_under(src_root):
        if py_file.resolve() == backend_file.resolve():
            continue
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "OpenAI":
                    violations.append((str(py_file), node.lineno))

    assert not violations, (
        f"OpenAI(...) found outside _backend.py:\n"
        + "\n".join(f"  {f}:{ln}" for f, ln in violations)
    )


# ---------------------------------------------------------------------------
# get_client routing
# ---------------------------------------------------------------------------

def test_get_client_returns_ollama_backend_by_default():
    client = _backend.get_client("ollama")
    assert isinstance(client, _backend.OllamaBackend)


def test_get_client_returns_ollama_openai_backend():
    client = _backend.get_client("ollama_openai")
    assert isinstance(client, _backend.OllamaOpenAIBackend)


def test_get_client_returns_lm_studio_backend():
    client = _backend.get_client("lm_studio")
    assert isinstance(client, _backend.LMStudioBackend)


def test_get_client_returns_huggingface_backend():
    client = _backend.get_client("huggingface")
    assert isinstance(client, _backend.HuggingFaceBackend)


def test_get_client_returns_api_key_backend():
    client = _backend.get_client("api_key")
    assert isinstance(client, _backend.ApiKeyBackend)


def test_get_client_unknown_backend_defaults_to_ollama():
    client = _backend.get_client("nonexistent")
    assert isinstance(client, _backend.OllamaBackend)


def test_get_client_case_insensitive():
    client = _backend.get_client("LM_STUDIO")
    assert isinstance(client, _backend.LMStudioBackend)


# ---------------------------------------------------------------------------
# LMStudioBackend.health_check
# ---------------------------------------------------------------------------

def test_lm_studio_health_check_ok(monkeypatch):
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(config, "_DEFAULTS", {**config._DEFAULTS,
        "lm_studio_url": "http://test:1234/v1",
    })
    config.load_config()

    mock_client = MagicMock()
    with patch.object(_backend, "OpenAI", return_value=mock_client) as mock_openai_cls:
        ok, detail = _backend.LMStudioBackend().health_check()
    assert ok is True
    assert detail is None
    mock_openai_cls.assert_called_once_with(base_url="http://test:1234/v1", api_key="lm-studio")


def test_lm_studio_health_check_unreachable(monkeypatch):
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(config, "_DEFAULTS", {**config._DEFAULTS,
        "lm_studio_url": "http://test:1234/v1",
    })
    config.load_config()

    mock_client = MagicMock()
    mock_client.models.list.side_effect = ConnectionError("refused")
    with patch.object(_backend, "OpenAI", return_value=mock_client):
        ok, detail = _backend.LMStudioBackend().health_check()
    assert ok is False
    assert "Cannot reach LM Studio" in detail


# ---------------------------------------------------------------------------
# ApiKeyBackend.health_check
# ---------------------------------------------------------------------------

def test_api_key_health_check_missing_key(monkeypatch):
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(config, "_DEFAULTS", {**config._DEFAULTS,
        "api_key": "",
    })
    config.load_config()

    ok, detail = _backend.ApiKeyBackend().health_check()
    assert ok is False
    assert "No API key configured" in detail


def test_api_key_health_check_ok(monkeypatch):
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(config, "_DEFAULTS", {**config._DEFAULTS,
        "api_key": "sk-test",
        "api_base_url": "https://test.example.com/v1",
    })
    config.load_config()

    mock_client = MagicMock()
    with patch.object(_backend, "OpenAI", return_value=mock_client) as mock_openai_cls:
        ok, detail = _backend.ApiKeyBackend().health_check()
    assert ok is True
    assert detail is None
    mock_openai_cls.assert_called_once_with(
        base_url="https://test.example.com/v1", api_key="sk-test"
    )


# ---------------------------------------------------------------------------
# check_lm_studio delegates to LMStudioBackend.health_check
# ---------------------------------------------------------------------------

def test_check_lm_studio_delegates_to_backend():
    from artifice_ocr.utils import check_lm_studio

    ok, detail = True, None
    with patch.object(_backend.LMStudioBackend, "health_check", return_value=(ok, detail)):
        result = check_lm_studio()
    assert result is None


def test_check_lm_studio_returns_error_from_backend():
    from artifice_ocr.utils import check_lm_studio

    ok, detail = False, "Cannot reach LM Studio at http://x. Is it running?"
    with patch.object(_backend.LMStudioBackend, "health_check", return_value=(ok, detail)):
        result = check_lm_studio()
    assert result == detail


# ---------------------------------------------------------------------------
# OCR stage uses backend with correct Ollama → ollama_openai mapping
# ---------------------------------------------------------------------------

@patch("artifice_ocr.stages.ocr._get_backend_client")
def test_ocr_stage_routes_ollama_to_ollama_openai(mock_get_backend, tmp_path):
    """When ocr_backend is 'ollama', the OCR stage asks for ollama_openai."""
    backend_name = None

    def capture_be_name(be_name):
        nonlocal backend_name
        backend_name = be_name
        mock = MagicMock()
        mock.chat.return_value = MagicMock(message=MagicMock(content="text"))
        return mock

    mock_get_backend.side_effect = capture_be_name

    config.reset()
    config.load_config()
    config.apply_overrides({"ocr_backend": "ollama", "ocr_model": "test-model"})
    try:
        from artifice_ocr.stages import ocr
        img = tmp_path / "scan.png"
        img.write_bytes(b"\x89PNG fake")
        ocr.perform(str(img), output_dir=str(tmp_path / "out"))
    finally:
        config.reset()
        config.load_config()

    assert backend_name == "ollama_openai", (
        f"Expected ollama_openai, got {backend_name}"
    )


@patch("artifice_ocr.stages.ocr._get_backend_client")
def test_ocr_stage_passes_lm_studio_through(mock_get_backend, tmp_path):
    """When ocr_backend is 'lm_studio', it is passed through unchanged."""
    backend_name = None

    def capture_be_name(be_name):
        nonlocal backend_name
        backend_name = be_name
        mock = MagicMock()
        mock.chat.return_value = MagicMock(message=MagicMock(content="text"))
        return mock

    mock_get_backend.side_effect = capture_be_name

    config.reset()
    config.load_config()
    config.apply_overrides({"ocr_backend": "lm_studio", "ocr_model": "test-model"})
    try:
        from artifice_ocr.stages import ocr
        img = tmp_path / "scan.png"
        img.write_bytes(b"\x89PNG fake")
        ocr.perform(str(img), output_dir=str(tmp_path / "out"))
    finally:
        config.reset()
        config.load_config()

    assert backend_name == "lm_studio", (
        f"Expected lm_studio, got {backend_name}"
    )


# ---------------------------------------------------------------------------
# Backend clients are re-created per call (stateless, config-aware)
# ---------------------------------------------------------------------------

def test_lm_studio_client_reads_config_fresh(monkeypatch):
    """Each ._client() call honours the current config, not a cached value."""
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(config, "_DEFAULTS", {**config._DEFAULTS,
        "lm_studio_url": "http://first:1111/v1",
    })
    config.load_config()

    calls = []
    with patch.object(_backend, "OpenAI", side_effect=lambda **kw: calls.append(kw) or MagicMock()):
        _backend.LMStudioBackend()._client()

    assert calls[0]["base_url"] == "http://first:1111/v1"
    assert calls[0]["api_key"] == "lm-studio"
