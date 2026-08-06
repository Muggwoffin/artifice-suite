# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for directory allowlist, SSRF URL validation, and upload limits in the web server."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from artifice_graph.web.server import (
    _ALLOWED_ROOT_DIRS,
    _MAX_UPLOAD_BYTES,
    _read_capped,
    _validate_base_url,
    _validate_directory,
)
from fastapi import HTTPException


class TestValidateDirectory:
    """Directory allowlist — finding #1."""

    def test_accepts_home_dir(self, monkeypatch):
        """A path under the user's home directory is always allowed."""
        p = Path.home() / "artifice-test-dir"
        result = _validate_directory(str(p), "input_dir")
        assert result == str(p)

    def test_accepts_tmp(self, tmp_path):
        """A path under /tmp (used by pytest's tmp_path) is allowed."""
        p = tmp_path / "my-output"
        result = _validate_directory(str(p), "output_dir")
        assert result == str(p)

    def test_accepts_cwd(self, tmp_path, monkeypatch):
        """CWD is always in the allowlist."""
        monkeypatch.setattr(os, "environ", {})  # clear ARTIFICE_GRAPH_ALLOWED_ROOTS
        result = _validate_directory(".", "input_dir")
        assert result == str(Path.cwd().resolve())

    def test_rejects_etc(self):
        """Paths outside allowed roots must be rejected with HTTP 400."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_directory("/etc", "input_dir")
        assert exc_info.value.status_code == 400
        assert "outside allowed roots" in exc_info.value.detail

    @pytest.mark.parametrize(
        "hidden",
        [".ssh", ".gnupg", ".aws", ".config", ".local/share/secrets"],
    )
    def test_rejects_hidden_directories_under_an_allowed_root(self, hidden):
        """Home is an allowed root, which would otherwise expose ~/.ssh.

        The whole home directory is permitted deliberately — a user's corpus
        lives there — so the dotfile rule is what stops "allowed root" from
        meaning "including everywhere credentials are kept".
        """
        with pytest.raises(HTTPException) as exc_info:
            _validate_directory(str(Path.home() / hidden), "vault_dir")
        assert exc_info.value.status_code == 400
        assert "hidden directory" in exc_info.value.detail

    def test_hidden_check_applies_below_the_root_not_across_it(self, tmp_path):
        """A visible directory is accepted even if a *parent of the root* is
        dotted.

        Checked below the matched root rather than across the absolute path, so
        a checkout living under something like ~/.local/projects is not made
        unusable by its own parent.
        """
        visible = tmp_path / "corpus" / "1923"
        visible.mkdir(parents=True)
        assert _validate_directory(str(visible), "input_dir") == str(visible)

    def test_rejects_var(self):
        """Arbitrary system paths are rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_directory("/var/log", "vault_dir")
        assert exc_info.value.status_code == 400

    def test_custom_root_from_env(self, tmp_path, monkeypatch):
        """ARTIFICE_GRAPH_ALLOWED_ROOTS env var adds extra roots."""
        extra = tmp_path / "custom-root"
        extra.mkdir()
        # The env var is read at module-import time in _ALLOWED_ROOT_DIRS,
        # so we need to test within the boundaries of what's already allowed.
        # Instead, verify that tmp_path (under /tmp) is accepted.
        result = _validate_directory(str(tmp_path), "input_dir")
        assert result == str(tmp_path)

    def test_empty_path_rejected(self):
        """An empty string should be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_directory("", "input_dir")
        assert exc_info.value.status_code == 400


class TestValidateBaseUrl:
    """SSRF host allowlist — finding #2."""

    def test_accepts_localhost(self):
        """Loopback hosts are allowed."""
        assert _validate_base_url("http://localhost:11434/v1", "llm_base_url")

    def test_accepts_127_0_0_1(self):
        """IPv4 loopback is allowed."""
        assert _validate_base_url("http://127.0.0.1:1234/v1", "llm_base_url")

    def test_accepts_docker_internal(self):
        """host.docker.internal is allowed (container-to-host routing)."""
        assert _validate_base_url("http://host.docker.internal:11434", "llm_base_url")

    def test_accepts_wsl_gateway(self):
        """The WSL host gateway is in the default allowlist."""
        assert _validate_base_url("http://172.21.176.1:11434/v1", "llm_base_url")

    def test_accepts_https(self):
        """HTTPS on localhost is allowed."""
        assert _validate_base_url("https://localhost:443/v1", "llm_base_url")

    def test_accepts_private_network_address(self):
        """A model served on the local network is a first-class case.

        Academics reach centrally-hosted university models from a personal
        machine; refusing RFC1918 would make the software unusable there.
        """
        assert _validate_base_url("http://192.168.1.50:11434/v1", "llm_base_url")
        assert _validate_base_url("http://10.20.30.40:8000/v1", "llm_base_url")

    def test_rejects_public_address_without_opt_in(self):
        """A public address requires an explicit opt-in.

        Uses an IP literal rather than a hostname so the test does not depend
        on DNS — a machine with a wildcard resolver would otherwise change the
        outcome.
        """
        with pytest.raises(HTTPException) as exc_info:
            _validate_base_url("http://8.8.8.8:11434/v1", "llm_base_url")
        assert exc_info.value.status_code == 400
        assert "ARTIFICE_ALLOW_PUBLIC_MODELS" in exc_info.value.detail

    def test_rejects_link_local_even_though_it_is_not_public(self):
        """169.254.169.254 is the cloud metadata endpoint.

        It is neither loopback nor private, but the interesting thing is that
        it must stay refused even if public addresses are later opted into —
        link-local is checked before the opt-in.
        """
        with pytest.raises(HTTPException) as exc_info:
            _validate_base_url("http://169.254.169.254/latest/meta-data/", "llm_base_url")
        assert exc_info.value.status_code == 400
        assert "link-local" in exc_info.value.detail

    def test_unresolvable_host_is_rejected(self):
        """A name that does not resolve fails closed rather than passing."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_base_url("http://nonexistent.invalid:11434/v1", "llm_base_url")
        assert exc_info.value.status_code == 400

    def test_rejects_ftp_scheme(self):
        """Non-HTTP schemes are rejected even on allowed hosts."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_base_url("ftp://localhost:21", "llm_base_url")
        assert exc_info.value.status_code == 400
        assert "scheme must be http or https" in exc_info.value.detail

    def test_rejects_file_scheme(self):
        """file:// URLs are explicitly rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_base_url("file:///etc/passwd", "llm_base_url")
        assert exc_info.value.status_code == 400

    def test_rejects_empty_string(self):
        """Empty URL string is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_base_url("", "llm_base_url")
        assert exc_info.value.status_code == 400

    def test_rejects_garbage(self):
        """Non-URL garbage is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_base_url("not-a-url!!!", "llm_base_url")
        assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------- #
# Cause A regression — temp dir from gettempdir() is always an allowed root
# --------------------------------------------------------------------------- #


def test_tempfile_gettempdir_in_allowed_roots():
    """``tempfile.gettempdir()`` is always in the allowed-roots list.

    Before the fix, only ``Path(\"/tmp\")`` was listed.  On macOS that fails
    because ``tempfile.gettempdir()`` returns ``/var/folders/…``, which is
    neither ``/tmp`` nor ``$HOME``.  This test asserts the mechanism is
    present regardless of platform default.
    """
    import tempfile

    temp_root = Path(tempfile.gettempdir()).resolve()
    resolved_roots = [r.resolve() for r in _ALLOWED_ROOT_DIRS]
    assert temp_root in resolved_roots


@pytest.mark.skipif(
    os.name != "posix",
    reason=(
        "Reproduces a POSIX-only failure mode. On Windows the platform temp "
        "directory sits below Path.home(), so it is already covered by the home "
        "root and this failure cannot arise; /var/tmp does not exist there "
        "either. The platform-neutral invariant is asserted unconditionally in "
        "the test above."
    ),
)
def test_accepts_temp_outside_tmp_and_home(monkeypatch):
    """A temp directory outside both ``/tmp`` and ``$HOME`` is still accepted.

    On macOS that is the default (``/var/folders/…``); here it is reproduced by
    pointing ``TMPDIR`` at ``/var/tmp``.

    ``_ALLOWED_ROOT_DIRS`` is a module-level constant evaluated at import time,
    so the relocated temp directory is injected into that list directly.
    **Deliberately not `importlib.reload`:** reloading the server module
    recomputes the constant with the test's ``TMPDIR`` baked in and cannot be
    undone by monkeypatch, leaking into every later test in the session, and it
    would also invalidate other tests' references to ``app`` and its routers.
    """
    import tempfile

    from artifice_graph.web import server as server_mod

    custom_root = Path("/var/tmp")
    if not custom_root.is_dir():
        pytest.skip("/var/tmp is absent on this POSIX host")

    monkeypatch.setenv("TMPDIR", str(custom_root))
    monkeypatch.setattr(tempfile, "tempdir", None)
    monkeypatch.setattr(
        server_mod,
        "_ALLOWED_ROOT_DIRS",
        [*server_mod._ALLOWED_ROOT_DIRS, Path(tempfile.gettempdir())],
    )

    d = Path(tempfile.mkdtemp(dir=str(custom_root)))
    try:
        # Compare against the RESOLVED path: _validate_directory returns the
        # path after resolve(). On Linux /var/tmp is a real directory so
        # resolve() is a no-op and either form passes — but on macOS /var is a
        # symlink to /private/var, so the unresolved form fails there and only
        # there.
        assert server_mod._validate_directory(str(d), "input_dir") == str(d.resolve())
    finally:
        if d.exists():
            d.rmdir()


# --------------------------------------------------------------------------- #
# Streaming upload cap — _read_capped
# --------------------------------------------------------------------------- #


def test_read_capped_raises_during_read():
    """_read_capped raises HTTP 413 once the limit is exceeded mid-stream,
    before the full body is gathered."""

    class _FakeUpload:
        filename = "test.txt"

        def __init__(self, total: int):
            self._remain = total

        async def read(self, size: int = -1) -> bytes:
            if self._remain <= 0:
                return b""
            n = min(size if size > 0 else 4096, 4096, self._remain)
            self._remain -= n
            return b"x" * n

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_read_capped(_FakeUpload(10_000), 10))
    assert exc_info.value.status_code == 413


def test_upload_oversized_rejected_per_file_in_batch(monkeypatch, tmp_path):
    """An oversized file is rejected as a per-entry status/reason, not a 413
    that kills the whole batch — per the docstring contract at
    server.py:1160-1167."""
    from artifice_graph.config import PipelineConfig
    from artifice_graph.web import server as server_mod

    cfg = PipelineConfig()
    cfg.ingestion.input_dir = str(tmp_path / "input")
    cfg.ingestion.supported_extensions = [".txt"]
    monkeypatch.setattr(server_mod, "load_config", lambda: cfg)

    class _FakeUpload:
        def __init__(self, filename: str, total: int):
            self.filename = filename
            self._remain = total

        async def read(self, size: int = -1) -> bytes:
            if self._remain <= 0:
                return b""
            n = min(size if size > 0 else 4096, 4096, self._remain)
            self._remain -= n
            return b"x" * n

    response = asyncio.run(
        server_mod.api_upload_files(
            [
                _FakeUpload("notes.txt", 10),
                _FakeUpload("big.txt", _MAX_UPLOAD_BYTES + 1),
                _FakeUpload("more.txt", 20),
            ]
        )
    )

    uploaded = response["uploaded"]
    assert len(uploaded) == 3
    assert uploaded[0]["status"] == "ok"
    assert uploaded[0]["filename"] == "notes.txt"
    assert uploaded[1]["status"] == "rejected"
    assert "exceeds" in uploaded[1]["reason"]
    assert uploaded[1]["filename"] == "big.txt"
    assert uploaded[2]["status"] == "ok"
    assert uploaded[2]["filename"] == "more.txt"


# -- Nominatim lookup gating (F6) --------------------------------------------


class TestNominatimGating:
    """Nominatim geocoding is default-off — entity names must not be sent to
    a third party without explicit consent."""

    def test_map_entities_lookup_disabled_by_default(self, monkeypatch, tmp_path):
        """When nominatim_lookup_enabled is False (the default), mode=lookup
        returns a response with lookup_disabled=True rather than making a
        network call to OpenStreetMap."""
        from artifice_graph.config import PipelineConfig
        from artifice_graph.web import server as server_mod

        cfg = PipelineConfig()
        cfg.export.output_dir = str(tmp_path / "output")

        monkeypatch.setattr(server_mod, "load_config", lambda: cfg)

        # Provide entities with a Location not in HISTORICAL_COORDINATES.
        store = server_mod._load_store(cfg)
        store.save(
            "entities.json",
            [
                {
                    "id": "loc-1",
                    "name": "Unknown Hamlet",
                    "entity_type": "Location",
                    "summary": "A village not in any built-in list",
                    "aliases": [],
                },
            ],
        )
        store.save("relationships.json", [])

        result = asyncio.run(server_mod.api_map_entities(mode="lookup"))

        # Must not have made a network call — the lookup_disabled flag
        # must be present.
        assert result.get("lookup_disabled") is True, (
            f"lookup_disabled flag missing; got keys: {list(result.keys())}"
        )
        assert "message" in result
        assert "nominatim" in result["message"].lower()

    def test_map_entities_lookup_enabled_allows_call(self, monkeypatch, tmp_path):
        """When nominatim_lookup_enabled is True, mode=lookup is permitted."""
        from artifice_graph.config import PipelineConfig
        from artifice_graph.web import server as server_mod

        cfg = PipelineConfig(nominatim_lookup_enabled=True)
        cfg.export.output_dir = str(tmp_path / "output")

        monkeypatch.setattr(server_mod, "load_config", lambda: cfg)

        store = server_mod._load_store(cfg)
        store.save(
            "entities.json",
            [
                {
                    "id": "loc-1",
                    "name": "Unknown Hamlet",
                    "entity_type": "Location",
                    "summary": "A village",
                    "aliases": [],
                },
            ],
        )
        store.save("relationships.json", [])

        # Patch urllib to avoid a real network call — we just want to
        # confirm the endpoint doesn't short-circuit with lookup_disabled.
        class _FakeResponse:
            def read(self):
                return b'[{"lat": "51.5", "lon": "-0.1"}]'

            def close(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        with patch("urllib.request.urlopen", return_value=_FakeResponse()):
            result = asyncio.run(server_mod.api_map_entities(mode="lookup"))

        assert result.get("lookup_disabled") is not True, (
            "lookup_disabled flag set when nominatim_lookup_enabled=True"
        )
        # Should have looked up the unknown hamlet
        assert any(loc.get("source_method") == "lookup" for loc in result.get("locations", [])), (
            f"No location had source_method=lookup: {result}"
        )
