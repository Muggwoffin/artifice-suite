# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Tests for ``secure_io``."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from secure_io import is_restricted, restrict_to_current_user, write_private_json

# ---------------------------------------------------------------------------
# write_private_json
# ---------------------------------------------------------------------------


class TestWritePrivateJson:
    """Correctness and permission tests for ``write_private_json``."""

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        """The file must contain the JSON we supplied."""
        path = tmp_path / "test.json"
        write_private_json(path, {"api_key": "sk-test-123", "output_dir": "/tmp"})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"api_key": "sk-test-123", "output_dir": "/tmp"}

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """A second call must replace the file, not append."""
        path = tmp_path / "test.json"
        write_private_json(path, {"api_key": "first"})
        write_private_json(path, {"api_key": "second"})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"api_key": "second"}

    def test_creates_restricted_file(self, tmp_path: Path) -> None:
        """After ``write_private_json``, ``is_restricted`` must be True."""
        path = tmp_path / "test.json"
        write_private_json(path, {"api_key": "sk-test-123"})
        assert is_restricted(path)

    def test_non_dict_data(self, tmp_path: Path) -> None:
        """Lists and scalars must also be written correctly."""
        path = tmp_path / "test.json"
        write_private_json(path, [1, 2, 3])
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == [1, 2, 3]

    def test_new_file_has_exact_mode_0600(self, tmp_path: Path) -> None:
        """On POSIX, a newly created file must have exactly mode 0600."""
        path = tmp_path / "test.json"
        write_private_json(path, {"x": 1})
        assert (path.stat().st_mode & 0o777) == 0o600

    def test_overwrite_tightens_existing_world_readable_file(self, tmp_path: Path) -> None:
        """Overwriting a world-readable (mode 0644) file with ``write_private_json``
        must tighten it to mode 0600, not leave the looser permissions in place."""
        path = tmp_path / "test.json"
        path.write_text('{"original": true}', encoding="utf-8")
        path.chmod(0o644)
        write_private_json(path, {"x": 1})
        assert (path.stat().st_mode & 0o777) == 0o600


# ---------------------------------------------------------------------------
# restrict_to_current_user
# ---------------------------------------------------------------------------


class TestRestrictToCurrentUser:
    """``restrict_to_current_user`` must secure an already-existing file."""

    def test_restricts_unprotected_file(self, tmp_path: Path) -> None:
        """A file created with default permissions (0o644) must become restricted."""
        path = tmp_path / "unprotected.json"
        path.write_text('{"x": 1}', encoding="utf-8")
        # Default permissions are typically 0o644 (umask-dependent).
        # We explicitly set world-readable to simulate the Windows case
        # where mode bits are ineffective.
        os.chmod(path, 0o644)
        assert not is_restricted(path)
        restrict_to_current_user(path)
        assert is_restricted(path)

    def test_already_restricted_file_stays_restricted(self, tmp_path: Path) -> None:
        """Calling ``restrict_to_current_user`` on an already-restricted file
        must be idempotent."""
        path = tmp_path / "restricted.json"
        write_private_json(path, {"x": 1})
        assert is_restricted(path)
        restrict_to_current_user(path)
        assert is_restricted(path)

    def test_raises_on_nonexistent_file(self, tmp_path: Path) -> None:
        """Restricting a file that does not exist must raise."""
        path = tmp_path / "nonexistent.json"
        with pytest.raises(OSError):
            restrict_to_current_user(path)

    def test_preserves_file_contents(self, tmp_path: Path) -> None:
        """Restricting an existing file must not alter its data."""
        path = tmp_path / "preserve.json"
        content = {"api_key": "sk-secret-value"}
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
        restrict_to_current_user(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == content


# ---------------------------------------------------------------------------
# is_restricted
# ---------------------------------------------------------------------------


class TestIsRestricted:
    """``is_restricted`` reports whether a file is properly secured."""

    def test_returns_false_for_nonexistent_file(self, tmp_path: Path) -> None:
        """A path that doesn't exist is not restricted."""
        assert not is_restricted(tmp_path / "nonexistent.json")

    def test_returns_false_for_world_readable(self, tmp_path: Path) -> None:
        """A file with mode 0644 is not restricted."""
        path = tmp_path / "world_readable.json"
        path.write_text("{}", encoding="utf-8")
        os.chmod(path, 0o644)
        assert not is_restricted(path)

    def test_returns_true_for_restricted(self, tmp_path: Path) -> None:
        """A file written with ``write_private_json`` must be restricted."""
        path = tmp_path / "restricted.json"
        write_private_json(path, {"x": 1})
        assert is_restricted(path)

    def test_group_readable_is_not_restricted(self, tmp_path: Path) -> None:
        """Mode 0640 (owner rw, group r) is still restricted from 'other' but
        not restricted to owner-only, so ``is_restricted`` must return False."""
        path = tmp_path / "group_readable.json"
        path.write_text("{}", encoding="utf-8")
        os.chmod(path, 0o640)
        assert not is_restricted(path)


# ---------------------------------------------------------------------------
# Platform dispatch
# ---------------------------------------------------------------------------


class TestPlatformDispatch:
    """The public API must dispatch to the correct platform implementation."""

    def test_posix_path_uses_open_with_mode(self, monkeypatch, tmp_path: Path) -> None:
        """Under ``sys.platform != 'win32'``, ``write_private_json`` must use
        ``os.open(..., 0o600)``, verified here by checking the resulting
        ``st_mode``."""
        monkeypatch.setattr("secure_io.sys.platform", "linux")
        path = tmp_path / "posix.json"
        write_private_json(path, {"x": 1})
        assert (path.stat().st_mode & 0o777) == 0o600

    @pytest.mark.skipif(os.name != "posix", reason="icacls is Windows-only")
    def test_windows_path_raises_on_posix_when_icacls_missing(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """Monkey-patching ``sys.platform`` to ``"win32"`` on a POSIX system
        must raise because ``icacls`` does not exist.  The error must not
        leave an empty file behind."""
        monkeypatch.setattr("secure_io.sys.platform", "win32")
        path = tmp_path / "win32.json"
        # _restrict_windows calls whoami first, not icacls; both are missing
        # on POSIX, and either way the raised exception should clean up.
        with pytest.raises((FileNotFoundError, subprocess.CalledProcessError)):  # type: ignore[name-defined]
            write_private_json(path, {"x": 1})
        # The empty file created before ACL application must have been removed.
        assert not path.exists()
