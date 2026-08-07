# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for shared_ui.path_validation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from shared_ui.path_validation import (
    build_allowed_roots,
    normalise_path,
    validate_path,
)


class TestNormalisePath:
    """Tests for normalise_path()."""

    def test_empty_string_raises_valueerror(self) -> None:
        with pytest.raises(ValueError, match="path must not be empty"):
            normalise_path("", "source")

    def test_backslashes_normalised_to_forward_slashes(self) -> None:
        result = normalise_path("foo\\bar\\baz", "source")
        assert result == "foo/bar/baz"

    def test_whitespace_only_string_raises(self) -> None:
        with pytest.raises(ValueError, match="path must not be empty"):
            normalise_path("   ", "source")

    def test_mixed_backslashes_and_spaces(self) -> None:
        result = normalise_path("  foo\\bar  ", "source")
        assert result == "foo/bar"

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only check")
    def test_windows_drive_letter_rejected_on_posix(self) -> None:
        with pytest.raises(ValueError, match="is not valid on this platform"):
            normalise_path("C:/Windows", "source")

    def test_plain_path_passes_through(self) -> None:
        result = normalise_path("/home/user/docs", "source")
        assert result == "/home/user/docs"


class TestBuildAllowedRoots:
    """Tests for build_allowed_roots()."""

    def test_default_roots_present(self) -> None:
        roots = build_allowed_roots("NONEXISTENT_ENV_VAR")
        assert any(r == Path.home().resolve() for r in roots)
        assert any(r == Path("/tmp").resolve() for r in roots)
        assert any(r == Path.cwd().resolve() for r in roots)

    def test_extra_root_from_env_var(self, monkeypatch, tmp_path: Path) -> None:
        extra = tmp_path / "extra"
        extra.mkdir()
        monkeypatch.setenv("TEST_EXTRA_ROOTS", str(extra))
        roots = build_allowed_roots("TEST_EXTRA_ROOTS")
        assert extra.resolve() in roots

    def test_multiple_extra_roots_split_on_pathsep(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        d1 = tmp_path / "dir1"
        d2 = tmp_path / "dir2"
        d1.mkdir()
        d2.mkdir()
        monkeypatch.setenv(
            "MULTI_ROOTS", f"{d1}{os.pathsep}{d2}"
        )
        roots = build_allowed_roots("MULTI_ROOTS")
        assert d1.resolve() in roots
        assert d2.resolve() in roots

    def test_env_var_selects_correct_variable(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        """build_allowed_roots(env_var) reads the env var whose *name* is passed."""
        dir_foo = tmp_path / "foo"
        dir_bar = tmp_path / "bar"
        dir_foo.mkdir()
        dir_bar.mkdir()
        monkeypatch.setenv("FOO_ALLOWED_ROOTS", str(dir_foo))
        monkeypatch.setenv("BAR_ALLOWED_ROOTS", str(dir_bar))

        roots_foo = build_allowed_roots("FOO_ALLOWED_ROOTS")
        roots_bar = build_allowed_roots("BAR_ALLOWED_ROOTS")

        assert dir_foo.resolve() in roots_foo
        assert dir_foo.resolve() not in roots_bar
        assert dir_bar.resolve() in roots_bar
        assert dir_bar.resolve() not in roots_foo


class TestValidatePath:
    """Tests for validate_path()."""

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="path must not be empty"):
            validate_path("", "source", allowed_roots_env_var="NONEXISTENT")

    def test_windows_drive_rejected_on_posix(self) -> None:
        if os.name != "posix":
            pytest.skip("POSIX-only check")
        with pytest.raises(
            ValueError, match="is not valid on this platform"
        ):
            validate_path(
                "C:/Windows",
                "source",
                allowed_roots_env_var="NONEXISTENT",
            )

    @pytest.mark.skipif(os.name != "posix", reason="POSIX-only check")
    def test_path_outside_all_roots_raises(self) -> None:
        """A path inside a directory that is NOT an allowed root must be rejected."""
        with pytest.raises(
            ValueError, match="is outside the directories"
        ):
            validate_path(
                "/etc/passwd",
                "source",
                allowed_roots_env_var="NONEXISTENT",
            )

    def test_path_inside_cwd_accepted(self, tmp_path: Path) -> None:
        """A path inside cwd() — a default root — must be accepted."""
        # Create a real file inside cwd so resolve() doesn't fail
        cwd = Path.cwd()
        file_path = cwd / "test_accepted.txt"
        file_path.write_text("hello")
        try:
            result = validate_path(
                str(file_path),
                "source",
                allowed_roots_env_var="NONEXISTENT",
            )
            assert os.path.isabs(result) or result.startswith("/")
        finally:
            file_path.unlink(missing_ok=True)

    def test_hidden_component_below_matched_root_rejected(
        self, tmp_path: Path
    ) -> None:
        """A hidden directory inside an allowed root must be rejected."""
        # tmp_path is typically under /tmp, which is a default allowed root.
        hidden_dir = tmp_path / ".secret"
        hidden_dir.mkdir()
        with pytest.raises(
            ValueError, match="descends into a hidden directory"
        ):
            validate_path(
                str(hidden_dir),
                "source",
                allowed_roots_env_var="NONEXISTENT",
            )

    def test_visible_path_below_matched_root_accepted(
        self, tmp_path: Path
    ) -> None:
        """A visible directory inside an allowed root must be accepted."""
        visible_dir = tmp_path / "visible"
        visible_dir.mkdir()
        result = validate_path(
            str(visible_dir),
            "source",
            allowed_roots_env_var="NONEXISTENT",
        )
        assert os.path.isabs(result)

    def test_env_var_actually_selects_correct_roots(
        self, monkeypatch
    ) -> None:
        """validate_path with FOO env var should honour FOO's extra root
        but not BAR's, and vice versa.

        Uses fabricated absolute paths outside every default root (home,
        tempdir, /tmp, cwd) so that acceptance is driven purely by which env
        var is active.  validate_path uses resolve(strict=False), so these
        paths do not need to exist on disk.
        """
        foo_root = "/opt/_artifice_test_foo_root"
        bar_root = "/opt/_artifice_test_bar_root"
        foo_file = f"{foo_root}/somefile.txt"
        bar_file = f"{bar_root}/somefile.txt"

        monkeypatch.setenv("FOO_ALLOWED_ROOTS", foo_root)
        monkeypatch.setenv("BAR_ALLOWED_ROOTS", bar_root)

        result_foo = validate_path(
            foo_file, "source", allowed_roots_env_var="FOO_ALLOWED_ROOTS"
        )
        assert os.path.isabs(result_foo)

        with pytest.raises(ValueError, match="is outside the directories"):
            validate_path(
                bar_file, "source", allowed_roots_env_var="FOO_ALLOWED_ROOTS"
            )

        result_bar = validate_path(
            bar_file, "source", allowed_roots_env_var="BAR_ALLOWED_ROOTS"
        )
        assert os.path.isabs(result_bar)

        with pytest.raises(ValueError, match="is outside the directories"):
            validate_path(
                foo_file, "source", allowed_roots_env_var="BAR_ALLOWED_ROOTS"
            )
