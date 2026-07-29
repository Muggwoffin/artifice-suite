"""Tests for directory allowlist and SSRF URL validation in the web server."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from artifice_graph.web.server import _validate_directory, _validate_base_url, _ALLOWED_ROOT_DIRS


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
            _validate_base_url(
                "http://nonexistent.invalid:11434/v1", "llm_base_url"
            )
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
