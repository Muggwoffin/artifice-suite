# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the ``uv`` subprocess layer."""

import sys
from pathlib import Path
from unittest.mock import patch

from artifice_hub.uv_backend import (
    ErrorKind,
    JobState,
    _classify_error,
    _scrubbed_env,
    find_uv,
    launch_app,
    list_tools,
    outdated_tools,
    tool_bin_dir,
    uninstall_app,
)

# ── _scrubbed_env ─────────────────────────────────────────────────────


class TestScrubbedEnv:
    def test_removes_meipass_from_ld_path(self, monkeypatch):
        meipass = "/tmp/_MEI123456"
        monkeypatch.setattr(sys, "_MEIPASS", meipass, raising=False)
        monkeypatch.setenv("LD_LIBRARY_PATH", f"/usr/lib:{meipass}:/opt/lib")
        env = _scrubbed_env()
        assert meipass not in env.get("LD_LIBRARY_PATH", "")
        assert "/usr/lib" in env["LD_LIBRARY_PATH"]
        assert "/opt/lib" in env["LD_LIBRARY_PATH"]

    def test_deletes_key_when_only_meipass(self, monkeypatch):
        meipass = "/tmp/_MEI123456"
        monkeypatch.setattr(sys, "_MEIPASS", meipass, raising=False)
        monkeypatch.setenv("LD_LIBRARY_PATH", meipass)
        env = _scrubbed_env()
        assert "LD_LIBRARY_PATH" not in env

    def test_leaves_other_vars_untouched(self, monkeypatch):
        meipass = "/tmp/_MEI123456"
        monkeypatch.setattr(sys, "_MEIPASS", meipass, raising=False)
        monkeypatch.setenv("LD_LIBRARY_PATH", meipass)
        monkeypatch.setenv("PATH", "/usr/bin")
        env = _scrubbed_env()
        assert "LD_LIBRARY_PATH" not in env
        assert env["PATH"] == "/usr/bin"


# ── find_uv ───────────────────────────────────────────────────────────


class TestFindUv:
    def test_finds_on_path(self):
        with patch("shutil.which", return_value="/usr/local/bin/uv"):
            assert find_uv() == "/usr/local/bin/uv"

    def test_finds_in_local_bin(self):
        def mock_which(cmd):
            return None

        with (
            patch("shutil.which", side_effect=mock_which),
            patch.object(Path, "is_file", return_value=True),
        ):
            result = find_uv()
            assert result is not None  # found via home dir fallback

    def test_returns_none_when_missing(self):
        def mock_which(cmd):
            return None

        with (
            patch("shutil.which", side_effect=mock_which),
            patch.object(Path, "is_file", return_value=False),
        ):
            assert find_uv() is None


# ── tool_bin_dir ──────────────────────────────────────────────────────


class TestToolBinDir:
    def test_returns_path_on_success(self):
        class MockResult:
            returncode = 0
            stdout = "/home/user/.local/share/uv/tools/bin\n"

        with patch("subprocess.run", return_value=MockResult()):
            result = tool_bin_dir("uv")
            assert result == Path("/home/user/.local/share/uv/tools/bin")

    def test_returns_none_on_failure(self):
        class MockResult:
            returncode = 1
            stdout = ""

        with patch("subprocess.run", return_value=MockResult()):
            result = tool_bin_dir("uv")
            assert result is None

    def test_returns_none_on_exception(self):
        with patch("subprocess.run", side_effect=OSError("not found")):
            result = tool_bin_dir("uv")
            assert result is None


# ── list_tools ────────────────────────────────────────────────────────


class TestListTools:
    def test_parses_normal_output(self):
        output = (
            "artifice-ocr v0.2.0\n"
            "artifice-draft v0.2.0\n"
            "artifice-graph v0.2.0\n"
        )

        class MockResult:
            returncode = 0
            stdout = output
            stderr = ""

        with patch("subprocess.run", return_value=MockResult()):
            tools = list_tools("uv")
            assert tools == {
                "artifice-ocr": "0.2.0",
                "artifice-draft": "0.2.0",
                "artifice-graph": "0.2.0",
            }

    def test_no_tools_installed_on_stderr(self):
        class MockResult:
            returncode = 0
            stdout = ""
            stderr = "No tools installed\n"

        with patch("subprocess.run", return_value=MockResult()):
            tools = list_tools("uv")
            assert tools == {}

    def test_no_tools_installed_on_stdout(self):
        class MockResult:
            returncode = 0
            stdout = "No tools installed\n"
            stderr = ""

        with patch("subprocess.run", return_value=MockResult()):
            tools = list_tools("uv")
            assert tools == {}

    def test_exception_returns_empty(self):
        with patch("subprocess.run", side_effect=OSError("spawn failed")):
            tools = list_tools("uv")
            assert tools == {}


# ── outdated_tools ────────────────────────────────────────────────────


class TestOutdatedTools:
    def test_parses_outdated_output(self):
        class MockResult:
            returncode = 0
            stdout = "artifice-ocr\nartifice-draft\n"
            stderr = ""

        with patch("subprocess.run", return_value=MockResult()):
            outdated = outdated_tools("uv")
            assert outdated == {"artifice-ocr", "artifice-draft"}

    def test_exception_returns_empty(self):
        with patch("subprocess.run", side_effect=OSError("spawn failed")):
            outdated = outdated_tools("uv")
            assert outdated == set()


# ── _classify_error ───────────────────────────────────────────────────


class TestClassifyError:
    def test_network_error(self):
        kind, detail = _classify_error("Connection refused")
        assert kind == ErrorKind.NETWORK

    def test_disk_full(self):
        kind, detail = _classify_error("No space left on device")
        assert kind == ErrorKind.DISK_FULL

    def test_resolution_error(self):
        kind, detail = _classify_error("Resolution failed")
        assert kind == ErrorKind.RESOLUTION

    def test_unknown(self):
        kind, detail = _classify_error("Something else happened")
        assert kind == ErrorKind.UNKNOWN
        assert detail == "Something else happened"


# ── uninstall_app ─────────────────────────────────────────────────────


class TestUninstallApp:
    def test_success(self):
        class MockResult:
            returncode = 0
            stdout = "Uninstalled artifice-ocr\n"
            stderr = ""

        with patch("subprocess.run", return_value=MockResult()):
            result = uninstall_app("uv", "artifice-ocr")
            assert result.returncode == 0

    def test_unknown_slug(self):
        result = uninstall_app("uv", "nonexistent-app")
        assert result.returncode == 1
        assert result.error_kind == ErrorKind.UNKNOWN


# ── launch_app ────────────────────────────────────────────────────────


class TestLaunchApp:
    def test_unknown_slug(self):
        ok, msg = launch_app("uv", "nonexistent-app")
        assert not ok
        assert "Unknown" in msg

    def test_no_bin_dir_falls_back_to_tool_run(self):
        with (
            patch("artifice_hub.uv_backend.tool_bin_dir", return_value=None),
            patch("subprocess.Popen") as mock_popen,
        ):
            ok, msg = launch_app("uv", "artifice-ocr")
            assert ok
            mock_popen.assert_called_once()


# ── JobState ──────────────────────────────────────────────────────────


class TestJobState:
    def test_push_strips_ansi_and_splits_cr(self):
        job = JobState(job_id="test", slug="artifice-ocr", action="install")
        job.push("\x1b[32mDownloading...\x1b[0m  50%")
        job.push("\r                      100%")
        item = job.events.get(timeout=1)
        assert item == "Downloading...  50%"
        item2 = job.events.get(timeout=1)
        assert item2 == "100%"

    def test_finish_sends_sentinel(self):
        job = JobState(job_id="test", slug="artifice-ocr", action="install")
        job.finish()
        item = job.events.get(timeout=1)
        assert item is None
        assert job.complete
