# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for user-data migration from legacy ``~/.callosip``.

These tests assert that the migration is lazy (no ``shutil.move()`` on
import) and that all four migration states are handled correctly.
"""

from __future__ import annotations

from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def _reset_lazy_cache(monkeypatch):
    """Every test gets a clean cache so the import-side-effect test is
    meaningful and no test state leaks into the next."""
    import artifice_graph.config

    monkeypatch.setattr(artifice_graph.config, "_USER_DATA_DIR", None)


# ── The import itself must NOT move anything ──────────────────────────


def test_accessor_does_not_move_when_no_legacy(tmp_path, monkeypatch):
    """When no legacy directory exists, _get_user_config_path must not
    call shutil.move()."""
    target_dir = tmp_path / "artifice_config"
    legacy_dir = tmp_path / "home" / ".callosip"

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        legacy_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    with mock.patch("shutil.move") as mock_move:
        from artifice_graph.config import _get_user_config_path

        _get_user_config_path()
        mock_move.assert_not_called(), ("shutil.move() was called when no legacy directory exists")


def test_lazy_cache_prevents_repeated_migration(tmp_path, monkeypatch):
    """_get_user_config_path must only call _resolve_user_data_dir once —
    the result is cached."""
    target_dir = tmp_path / "artifice_config"
    legacy_dir = tmp_path / "home" / ".callosip"

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        legacy_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    legacy_dir.mkdir(parents=True)
    (legacy_dir / "config.json").write_text('{"llm": {"model": "test"}}')

    from artifice_graph.config import _get_user_config_path

    first = _get_user_config_path()
    assert first == target_dir / "config.json"

    # Second call returns the same cached result — no further moves.
    with mock.patch("shutil.move") as mock_move:
        second = _get_user_config_path()
        assert second == first
        mock_move.assert_not_called()


# ── Legacy present, target absent → migrates ─────────────────────────


def test_legacy_dir_migrates_on_first_access(tmp_path, monkeypatch):
    """When ~/.callosip exists and the platformdirs target does not,
    calling _get_user_data_dir() performs the migration."""
    target_dir = tmp_path / "artifice_config"
    legacy_dir = tmp_path / "home" / ".callosip"

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        legacy_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    legacy_dir.mkdir(parents=True)
    (legacy_dir / "config.json").write_text('{"llm": {"model": "test"}}')

    from artifice_graph.config import _get_user_config_path

    cfg_path = _get_user_config_path()

    assert cfg_path == target_dir / "config.json"
    assert (target_dir / "config.json").exists(), (
        "config.json was not migrated to the platformdirs target"
    )
    assert not legacy_dir.exists(), "legacy ~/.callosip should be moved, not copied"


# ── Both present → does NOT migrate ──────────────────────────────────


def test_both_present_silent_noop(tmp_path, monkeypatch):
    """When both ~/.callosip and the target dir exist, no migration occurs."""
    target_dir = tmp_path / "artifice_config"
    legacy_dir = tmp_path / "home" / ".callosip"

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        legacy_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    legacy_dir.mkdir(parents=True)
    (legacy_dir / "config.json").write_text('{"llm": {"model": "legacy"}}')

    target_dir.mkdir(parents=True)
    (target_dir / "config.json").write_text('{"llm": {"model": "target"}}')

    with mock.patch("shutil.move") as mock_move:
        from artifice_graph.config import _get_user_config_path

        _get_user_config_path()
        mock_move.assert_not_called()

    # Legacy is untouched.
    assert legacy_dir.exists()
    assert (target_dir / "config.json").read_text() == '{"llm": {"model": "target"}}'


# ── Neither → no-op, returns platformdirs path ───────────────────────


def test_neither_returns_platformdirs_path(tmp_path, monkeypatch):
    """When neither directory exists, the platformdirs path is returned."""
    target_dir = tmp_path / "artifice_config"
    legacy_dir = tmp_path / "home" / ".callosip"

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        legacy_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    from artifice_graph.config import _get_user_config_path

    cfg_path = _get_user_config_path()
    assert cfg_path == target_dir / "config.json"


# ── shutil.move raising → fallback, no crash ─────────────────────────


def test_move_raises_falls_back_to_legacy(tmp_path, monkeypatch):
    """When shutil.move() raises, the legacy directory is used as fallback
    and the app does not crash."""
    target_dir = tmp_path / "artifice_config"
    legacy_dir = tmp_path / "home" / ".callosip"

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        legacy_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    legacy_dir.mkdir(parents=True)
    (legacy_dir / "config.json").write_text('{"llm": {"model": "test"}}')

    def _failing_move(src, dst):
        raise OSError("Simulated cross-device link error")

    with mock.patch("shutil.move", side_effect=_failing_move):
        from artifice_graph.config import _get_user_config_path

        cfg_path = _get_user_config_path()
        # Falls back to legacy path.
        assert cfg_path == legacy_dir / "config.json", (
            f"expected legacy fallback {legacy_dir / 'config.json'}, got {cfg_path}"
        )


# ── ensure_restricted is called on migrated config.json ──────────────


def test_ensure_restricted_called_on_migrated_file(tmp_path, monkeypatch):
    """After migration, ensure_restricted is called on the migrated
    config.json to prevent a moved file from inheriting a looser ACL."""
    target_dir = tmp_path / "artifice_config"
    legacy_dir = tmp_path / "home" / ".callosip"

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        legacy_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    legacy_dir.mkdir(parents=True)
    (legacy_dir / "config.json").write_text('{"llm": {"model": "test"}}')

    with mock.patch("secure_io.ensure_restricted") as mock_er:
        from artifice_graph.config import _get_user_config_path

        _get_user_config_path()

        migrated = target_dir / "config.json"
        mock_er.assert_called_once_with(migrated)


def test_ensure_restricted_failure_is_swallowed(tmp_path, monkeypatch, caplog):
    """If ensure_restricted raises after migration, the failure is logged
    but does not prevent the app from continuing."""
    target_dir = tmp_path / "artifice_config"
    legacy_dir = tmp_path / "home" / ".callosip"

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        legacy_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    legacy_dir.mkdir(parents=True)
    (legacy_dir / "config.json").write_text('{"llm": {"model": "test"}}')

    def _failing_restrict(path):
        raise OSError("Simulated ACL failure")

    with mock.patch("secure_io.ensure_restricted", side_effect=_failing_restrict):
        from artifice_graph.config import _get_user_config_path

        cfg_path = _get_user_config_path()
        # Migration still succeeded.
        assert cfg_path == target_dir / "config.json"
        assert (target_dir / "config.json").exists()

    assert "Could not re-restrict" in caplog.text


# -- Symlink migration rejection (F8) ---------------------------------------


def test_legacy_dir_is_symlink_refuses_migration(tmp_path, monkeypatch, caplog):
    """When the legacy config directory is a symlink, the migration must
    refuse to move it.  A symlink target could be anywhere on the
    filesystem, and ``shutil.move`` on a symlink moves the symlink itself,
    not the target — but the principle is the same: the migration path
    must not touch a symlink because its target is outside the app's
    jurisdiction."""
    target_dir = tmp_path / "artifice_config"
    real_dir = tmp_path / "actual_config"
    real_dir.mkdir()
    (real_dir / "config.json").write_text('{"llm": {"model": "symlink-test"}}')

    symlink_dir = tmp_path / "home" / ".callosip"
    symlink_dir.parent.mkdir(parents=True)
    # Create a symlink pointing to the real directory.
    symlink_dir.symlink_to(real_dir, target_is_directory=True)

    monkeypatch.setattr(
        "artifice_graph.config._LEGACY_CONFIG_DIR",
        symlink_dir,
    )
    monkeypatch.setattr(
        "artifice_graph.config.user_data_dir",
        lambda *a, **kw: str(target_dir),
    )

    # Force a fresh resolution.
    monkeypatch.setattr("artifice_graph.config._USER_DATA_DIR", None)

    from artifice_graph.config import _get_user_config_path

    cfg_path = _get_user_config_path()

    # Must NOT have migrated — returns the new (empty) dir path, not legacy.
    assert cfg_path == target_dir / "config.json"
    # Symlink must still exist (was not moved).
    assert symlink_dir.exists()
    # The target must NOT have been moved into.
    assert not (target_dir / "config.json").exists()
    # Must have logged a warning.
    assert "symlink" in caplog.text.lower()
    assert "refusing" in caplog.text.lower()
