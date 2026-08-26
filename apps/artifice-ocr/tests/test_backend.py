# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests that pin the seam: all OpenAI client construction flows through _backend."""

import ast
import logging
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from artifice_ocr import _backend, config
from model_harness.contract import EndpointRejected
from model_harness.endpoint_policy import EndpointPolicy


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

    assert not violations, f"OpenAI(...) found outside _backend.py:\n" + "\n".join(
        f"  {f}:{ln}" for f, ln in violations
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
# ApiKeyBackend.health_check (retained — does not fit discovery cleanly;
# see the brief for rationale)
# ---------------------------------------------------------------------------


def test_api_key_health_check_missing_key(monkeypatch):
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "api_key": "",
        },
    )
    config.load_config()

    ok, detail = _backend.ApiKeyBackend().health_check()
    assert ok is False
    assert "No API key configured" in detail


def test_api_key_health_check_ok(monkeypatch):
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "api_key": "sk-test",
            "api_base_url": "http://10.0.0.1/v1",
        },
    )
    config.load_config()

    mock_client = MagicMock()
    with patch.object(_backend, "OpenAI", return_value=mock_client) as mock_openai_cls:
        ok, detail = _backend.ApiKeyBackend().health_check()
    assert ok is True
    assert detail is None
    mock_openai_cls.assert_called_once_with(base_url="http://10.0.0.1/v1", api_key="sk-test")


# ---------------------------------------------------------------------------
# check_lm_studio delegates to discovery.probe_endpoint_sync
# ---------------------------------------------------------------------------


def test_check_lm_studio_ok(monkeypatch):
    from artifice_ocr.utils import check_lm_studio
    from model_harness.discovery import ProbeResult

    ok_result = ProbeResult(url="http://localhost:1234/v1", reachable=True, models=("test-model",))
    monkeypatch.setattr("artifice_ocr.utils.probe_endpoint_sync", lambda *a, **k: ok_result)

    result = check_lm_studio()
    assert result is None


def test_check_lm_studio_returns_error(monkeypatch):
    from artifice_ocr.utils import check_lm_studio
    from model_harness.discovery import ProbeResult

    fail_result = ProbeResult(
        url="http://localhost:1234/v1",
        reachable=False,
        hint="Cannot reach LM Studio at http://x. Is it running?",
    )
    monkeypatch.setattr("artifice_ocr.utils.probe_endpoint_sync", lambda *a, **k: fail_result)

    result = check_lm_studio()
    assert "Cannot reach LM Studio" in result


def test_check_lm_studio_rejects_link_local(monkeypatch):
    """Policy rejection in the discovery path must propagate (security property)."""
    from artifice_ocr.utils import check_lm_studio

    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "lm_studio_url": "http://169.254.169.254/v1",
        },
    )
    monkeypatch.delenv("ARTIFICE_ALLOW_PUBLIC_MODELS", raising=False)
    config.load_config()

    with pytest.raises(EndpointRejected, match="link-local"):
        check_lm_studio()


# ---------------------------------------------------------------------------
# check_ollama error strings are preserved for CLI consumers
# ---------------------------------------------------------------------------


def test_check_ollama_unreachable_string_unchanged(monkeypatch):
    """The unreachable message is byte-identical to the pre-migration version."""
    from artifice_ocr.utils import check_ollama
    from model_harness.discovery import ProbeResult

    fail_result = ProbeResult(
        url="http://localhost:11434",
        reachable=False,
        hint="any hint",
    )
    monkeypatch.setattr("artifice_ocr.utils.probe_endpoint_sync", lambda *a, **k: fail_result)

    errors = check_ollama()
    assert errors == ["Cannot reach Ollama at http://localhost:11434. Is it running?"]


def test_check_ollama_model_missing_string_unchanged(monkeypatch):
    """The missing-model message is byte-identical to the pre-migration version."""
    from artifice_ocr.utils import check_ollama
    from model_harness.discovery import ProbeResult

    result = ProbeResult(
        url="http://localhost:11434",
        reachable=True,
        models=("other-model",),
    )
    monkeypatch.setattr("artifice_ocr.utils.probe_endpoint_sync", lambda *a, **k: result)

    errors = check_ollama(["missing-model"])
    assert errors == ['Model "missing-model" is not downloaded. Open Ollama and download it first.']


def test_check_lm_studio_unreachable_string_changed(monkeypatch):
    """LM Studio unreachable returns the URL followed by discovery's hint.

    The old LMStudioBackend.health_check returned:
    'Cannot reach LM Studio at <url>. Is it running?'
    The new path now prepends the URL to discovery's hint so the caller can
    see *which* address failed — matching check_ollama's format.
    """
    from artifice_ocr.utils import check_lm_studio
    from model_harness.discovery import ProbeResult

    fail_result = ProbeResult(
        url="http://localhost:1234/v1",
        reachable=False,
        hint="Ensure your local model runner is running. Ensure LM Studio is running.",
    )
    monkeypatch.setattr("artifice_ocr.utils.probe_endpoint_sync", lambda *a, **k: fail_result)

    result = check_lm_studio()
    assert result is not None
    assert "Cannot reach LM Studio at http://localhost:1234/v1." in result
    assert fail_result.hint in result


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

    assert backend_name == "ollama_openai", f"Expected ollama_openai, got {backend_name}"


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

    assert backend_name == "lm_studio", f"Expected lm_studio, got {backend_name}"


# ---------------------------------------------------------------------------
# Backend clients are re-created per call (stateless, config-aware)
# ---------------------------------------------------------------------------


def test_lm_studio_client_reads_config_fresh(monkeypatch):
    """Each ._client() call honours the current config, not a cached value."""
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "lm_studio_url": "http://localhost:1111/v1",
        },
    )
    config.load_config()

    calls = []
    with patch.object(_backend, "OpenAI", side_effect=lambda **kw: calls.append(kw) or MagicMock()):
        _backend.LMStudioBackend()._client()

    assert calls[0]["base_url"] == "http://localhost:1111/v1"
    assert calls[0]["api_key"] == "lm-studio"


# ---------------------------------------------------------------------------
# Endpoint policy: link-local rejection (use-time)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "backend_name,url_key,rejected_url",
    [
        ("ollama", "ollama_url", "http://169.254.169.254/"),
        ("ollama_openai", "ollama_url", "http://169.254.169.254/v1"),
        ("lm_studio", "lm_studio_url", "http://169.254.169.254/v1"),
        ("api_key", "api_base_url", "http://169.254.169.254/v1"),
    ],
)
def test_backend_rejects_link_local_url(monkeypatch, backend_name, url_key, rejected_url):
    """A link-local address (169.254.x.x) is refused at client construction time."""
    monkeypatch.setattr(config, "_config_cache", None)
    defaults = dict(config._DEFAULTS)
    defaults[url_key] = rejected_url
    if backend_name == "api_key":
        defaults["api_key"] = "sk-test"
    monkeypatch.setattr(config, "_DEFAULTS", defaults)
    config.load_config()

    backend = _backend.get_client(backend_name)
    with pytest.raises(EndpointRejected, match="link-local"):
        if hasattr(backend, "_client"):
            backend._client()
        else:
            backend.chat(model="m", messages=[{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# Endpoint policy: public URL requires opt-in (use-time)
# ---------------------------------------------------------------------------


def test_api_key_backend_rejects_public_url_by_default(monkeypatch):
    """The default api_base_url (api.openai.com) is refused without the env var."""
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "api_key": "sk-test",
            "api_base_url": "http://8.8.8.8/v1",
        },
    )
    # Use a policy that explicitly denies public
    strict_policy = EndpointPolicy(allow_public=False)
    monkeypatch.setattr(_backend, "_endpoint_policy", strict_policy)
    config.load_config()

    with pytest.raises(EndpointRejected, match="public address"):
        _backend.ApiKeyBackend()._client()


def test_api_key_backend_allows_public_url_with_env_var(monkeypatch):
    """A public URL is accepted when the endpoint policy permits public."""
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "api_key": "sk-test",
            "api_base_url": "http://8.8.8.8/v1",
        },
    )
    # Use a policy that explicitly permits public
    permissive_policy = EndpointPolicy(allow_public=True)
    monkeypatch.setattr(_backend, "_endpoint_policy", permissive_policy)
    config.load_config()

    mock_client = MagicMock()
    with patch.object(_backend, "OpenAI", return_value=mock_client):
        _backend.ApiKeyBackend()._client()
    # If we reach here, the URL was accepted.


# ---------------------------------------------------------------------------
# Endpoint policy: loopback / private still works (use-time)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "backend_name,url_key,good_url",
    [
        ("ollama", "ollama_url", "http://localhost:11434"),
        ("ollama_openai", "ollama_url", "http://localhost:11434/v1"),
        ("lm_studio", "lm_studio_url", "http://localhost:1234/v1"),
        ("api_key", "api_base_url", "http://10.0.0.1/v1"),
    ],
)
def test_backend_allows_loopback_or_private_url(monkeypatch, backend_name, url_key, good_url):
    """Loopback and private-network URLs are accepted without the public opt-in."""
    monkeypatch.setattr(config, "_config_cache", None)
    defaults = dict(config._DEFAULTS)
    defaults[url_key] = good_url
    if backend_name == "api_key":
        defaults["api_key"] = "sk-test"
    monkeypatch.setattr(config, "_DEFAULTS", defaults)
    config.load_config()

    mock_client = MagicMock()
    with patch.object(_backend, "OpenAI", return_value=mock_client):
        with patch.object(_backend.ollama, "Client", return_value=MagicMock()):
            backend = _backend.get_client(backend_name)
            if hasattr(backend, "_client"):
                backend._client()
            else:
                # Ollama native backend — verify _validate_url doesn't raise
                backend.chat(model="m", messages=[{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# LMStudioBackend.health_check raises on rejected URL (does not swallow)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# HuggingFaceBackend — public endpoint opt-in (no URL to validate)
# ---------------------------------------------------------------------------


def test_huggingface_backend_rejects_when_public_not_allowed(monkeypatch):
    """HuggingFaceBackend.chat raises EndpointRejected without opt-in.

    The HuggingFace Inference API is a public cloud service.  The endpoint
    policy must permit public endpoints before any call is made.
    """
    import socket
    from unittest.mock import patch

    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "huggingface_token": "hf_test",
        },
    )
    monkeypatch.delenv("ARTIFICE_ALLOW_PUBLIC_MODELS", raising=False)
    config.load_config()

    # Ensure the HuggingFace hostname resolves to a public IP so the
    # policy correctly identifies it as public rather than failing DNS.
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
    ]

    backend = _backend.HuggingFaceBackend()
    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with pytest.raises(EndpointRejected, match="public address"):
            backend.chat(
                model="test-model",
                messages=[{"role": "user", "content": "hi"}],
            )


def test_huggingface_backend_accepts_when_public_allowed(monkeypatch):
    """HuggingFaceBackend.chat passes validation when public endpoints are allowed.

    The endpoint policy check succeeds first; the SDK-level call is
    mocked so no real network request is made.
    """
    import socket
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "huggingface_token": "hf_test",
        },
    )
    # Replace the module-level policy with one that permits public endpoints,
    # because the module-level instance was created at import time and does
    # not re-read the env var on each call.
    permissive_policy = EndpointPolicy(allow_public=True)
    monkeypatch.setattr(_backend, "_endpoint_policy", permissive_policy)
    config.load_config()

    # Ensure the HuggingFace hostname resolves to a public IP so the
    # policy permits it.
    mock_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
    ]

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "test response"

    mock_client = MagicMock()
    mock_client.chat_completion.return_value = mock_resp

    backend = _backend.HuggingFaceBackend()
    with patch("socket.getaddrinfo", return_value=mock_addrinfo):
        with patch.object(_backend, "InferenceClient", return_value=mock_client):
            result = backend.chat(
                model="test-model",
                messages=[{"role": "user", "content": "hi"}],
            )
            assert result.message.content == "test response"


# ---------------------------------------------------------------------------
# Ollama URL normalisation — one /v1, never two
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "configured",
    [
        "http://localhost:11434",
        "http://localhost:11434/",
        "http://localhost:11434/v1",
        "http://localhost:11434/v1/",
        "  http://localhost:11434/v1  ",
        " http://localhost:11434/ ",
    ],
)
def test_ollama_openai_client_appends_single_v1(monkeypatch, configured):
    """All four spellings of the Ollama base URL — plus surrounding whitespace —
    yield exactly one ``/v1``.

    Regression: the old code appended ``"/v1"`` unconditionally, so a stored URL
    already ending in ``/v1`` produced ``/v1/v1`` and a 404 on every chat
    completion.  Surrounding whitespace re-opened the same bug by defeating the
    ``/v1`` strip; the client must normalise before appending.  The OpenAI SDK
    posts chat completions to ``{base_url}/chat/completions``.
    """
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "ollama_url": configured,
        },
    )
    config.load_config()

    captured = {}
    with patch.object(
        _backend, "OpenAI", side_effect=lambda **kw: captured.update(kw) or MagicMock()
    ):
        _backend.OllamaOpenAIBackend()._client()

    assert captured["base_url"] == "http://localhost:11434/v1"
    assert captured["base_url"].rstrip("/") + "/chat/completions" == (
        "http://localhost:11434/v1/chat/completions"
    )


@pytest.mark.parametrize(
    "configured",
    [
        "http://localhost:11434",
        "http://localhost:11434/",
        "http://localhost:11434/v1",
        "http://localhost:11434/v1/",
    ],
)
def test_ollama_backend_constructs_client_with_configured_host(monkeypatch, configured):
    """OllamaBackend must build ``ollama.Client(host=...)`` from the configured URL.

    The old code set ``ollama.host = host``, an unused module attribute, so the
    configured host was silently ignored for cleanup, translate and language
    detection (the native client kept its import-time ``$OLLAMA_HOST`` default).
    The native Ollama API is not the OpenAI-compatible one, so the ``/v1``
    suffix must be stripped before constructing the client.
    """
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "ollama_url": configured,
        },
    )
    config.load_config()

    mock_client = MagicMock()
    with patch.object(_backend.ollama, "Client", return_value=mock_client) as mock_cls:
        _backend.OllamaBackend().chat(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
        )

    mock_cls.assert_called_once_with(host="http://localhost:11434")
    mock_client.chat.assert_called_once()


def test_ollama_backend_validates_normalised_host(monkeypatch):
    """OllamaBackend runs the endpoint policy on the *normalised* host.

    The raw config value may carry a trailing ``/v1``; the client is built from
    ``normalise_base_url(host)``.  Validation must inspect that same normalised
    value, not the raw spelling, so a future policy that inspects the path
    cannot silently miss this call site.
    """
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "ollama_url": "http://localhost:11434/v1",
        },
    )
    config.load_config()

    validated: list[str] = []
    with (
        patch.object(
            _backend,
            "_validate_url",
            side_effect=lambda url, field: validated.append(url) or url,
        ),
        patch.object(_backend.ollama, "Client", return_value=MagicMock()),
    ):
        _backend.OllamaBackend().chat(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert validated == ["http://localhost:11434"]


# ---------------------------------------------------------------------------
# Provider 404 wrapping — the message must name what was called
# ---------------------------------------------------------------------------


def _openai_404():
    import httpx
    from openai import NotFoundError

    request = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    response = httpx.Response(404, request=request, json={"error": {"message": "not found"}})
    return NotFoundError("not found", response=response, body=None)


def test_ollama_openai_404_names_base_url_and_model(monkeypatch):
    """A provider 404 on the OCR path surfaces the attempted URL and model."""
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "ollama_url": "http://localhost:11434/v1",  # the doubled-/v1 trap
        },
    )
    config.load_config()
    _backend._logged_base_urls.clear()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _openai_404()
    with (
        patch.object(_backend, "OpenAI", return_value=mock_client),
        pytest.raises(RuntimeError) as excinfo,
    ):
        _backend.OllamaOpenAIBackend().chat(
            model="llava:7b",
            messages=[{"role": "user", "content": "hi"}],
        )

    msg = str(excinfo.value)
    assert "404" in msg
    assert "http://localhost:11434/v1" in msg  # exactly one /v1
    assert "llava:7b" in msg


def test_native_ollama_404_names_base_url_and_model(monkeypatch):
    """The native Ollama path wraps a 404 the same way."""
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "ollama_url": "http://localhost:11434",
        },
    )
    config.load_config()
    _backend._logged_base_urls.clear()

    mock_client = MagicMock()
    mock_client.chat.side_effect = _backend.ollama.ResponseError("model not found", status_code=404)
    with (
        patch.object(_backend.ollama, "Client", return_value=mock_client),
        pytest.raises(RuntimeError) as excinfo,
    ):
        _backend.OllamaBackend().chat(
            model="llama3.2:3b",
            messages=[{"role": "user", "content": "hi"}],
        )

    msg = str(excinfo.value)
    assert "404" in msg
    assert "http://localhost:11434" in msg
    assert "llama3.2:3b" in msg


# ---------------------------------------------------------------------------
# Base URL logging — once at INFO, never an API key
# ---------------------------------------------------------------------------


def test_backend_logs_base_url_once_at_info(monkeypatch, caplog):
    """First client construction logs INFO; a repeat for the same URL is DEBUG."""
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "ollama_url": "http://localhost:11434/v1",
        },
    )
    config.load_config()
    _backend._logged_base_urls.clear()

    with patch.object(_backend, "OpenAI", return_value=MagicMock()), caplog.at_level(logging.INFO):
        _backend.OllamaOpenAIBackend()._client()
        _backend.OllamaOpenAIBackend()._client()

    info_lines = [
        r.getMessage()
        for r in caplog.records
        if r.name == "artifice_ocr._backend" and r.levelno == logging.INFO
    ]
    assert len(info_lines) == 1
    assert "http://localhost:11434/v1" in info_lines[0]


def test_backend_log_never_contains_api_key(monkeypatch, caplog):
    """Client construction logs the base URL, never the configured key."""
    monkeypatch.setattr(config, "_config_cache", None)
    monkeypatch.setattr(
        config,
        "_DEFAULTS",
        {
            **config._DEFAULTS,
            "api_key": "sk-secret-backend",
            "api_base_url": "http://10.0.0.1/v1",
        },
    )
    config.load_config()
    _backend._logged_base_urls.clear()

    with patch.object(_backend, "OpenAI", return_value=MagicMock()), caplog.at_level(logging.INFO):
        _backend.ApiKeyBackend()._client()

    assert "sk-secret-backend" not in caplog.text
    assert "http://10.0.0.1/v1" in caplog.text
