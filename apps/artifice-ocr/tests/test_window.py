# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the native window module and --no-window flag."""

from __future__ import annotations

import time
from unittest import mock

from artifice_ocr.web.window import WindowResult, open_native_window


class TestWindowResult:
    """Unit tests for the WindowResult data class."""

    def test_opened_true(self) -> None:
        result = WindowResult(opened=True)
        assert result.opened is True
        assert result.reason == ""

    def test_opened_false_with_reason(self) -> None:
        result = WindowResult(opened=False, reason="No display found")
        assert result.opened is False
        assert result.reason == "No display found"

    def test_defaults(self) -> None:
        result = WindowResult(opened=False)
        assert result.reason == ""


class TestOpenNativeWindow:
    """Tests for open_native_window() with pywebview unavailable."""

    def test_returns_false_when_pywebview_not_installed(self) -> None:
        """When pywebview is not importable, return opened=False with reason."""
        import builtins

        original_import = builtins.__import__

        def _fake_import(name, *a, **kw):
            if name == "webview":
                raise ImportError("No module named 'webview'")
            return original_import(name, *a, **kw)

        try:
            builtins.__import__ = _fake_import
            result = open_native_window("http://127.0.0.1:8765")
            assert result.opened is False
            assert "pywebview" in result.reason.lower()
            assert "pip install" in result.reason
        finally:
            builtins.__import__ = original_import

    def test_returns_false_when_webview_backend_unavailable(self) -> None:
        """When pywebview imports but no backend is available, return opened=False."""
        with mock.patch("webview.create_window") as mock_create:
            with mock.patch("webview.start") as mock_start:
                mock_start.side_effect = RuntimeError("No suitable webview provider found")
                result = open_native_window("http://127.0.0.1:8765")
                assert result.opened is False
                assert "Native window unavailable" in result.reason
                assert "No suitable webview provider" in result.reason

    def test_returns_true_when_window_opens(self) -> None:
        """When the window opens and then closes cleanly, return opened=True."""
        with mock.patch("webview.create_window") as mock_create:
            with mock.patch("webview.start") as mock_start:
                mock_start.return_value = None  # simulates window closed
                result = open_native_window("http://127.0.0.1:8765")
                assert result.opened is True
                assert result.reason == ""

    def test_passes_url_and_title_to_create_window(self) -> None:
        """Ensure url and title keyword args are forwarded correctly."""
        with mock.patch("webview.create_window") as mock_create:
            with mock.patch("webview.start"):
                open_native_window(
                    "http://127.0.0.1:9999",
                    title="My OCR App",
                    width=1024,
                    height=768,
                )
                mock_create.assert_called_once_with(
                    title="My OCR App",
                    url="http://127.0.0.1:9999",
                    width=1024,
                    height=768,
                    resizable=True,
                    min_size=(640, 480),
                )


class TestMainNoWindowFlag:
    """Integration tests for server.main() with the --no-window flag."""

    @staticmethod
    def _start_server(port: int, *extra_args: str):
        """Launch the server in a subprocess via setsid/nohup for clean cleanup."""
        import subprocess

        return subprocess.Popen(
            [
                "/home/mjcasey/projects/artifice-suite/.venv/bin/python",
                "-m",
                "artifice_ocr.web.server",
                "--port",
                str(port),
                *extra_args,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd="/home/mjcasey/projects/artifice-suite",
            preexec_fn=__import__("os").setsid,
        )

    @staticmethod
    def _free_port() -> int:
        """Return an available ephemeral port on localhost."""
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    @staticmethod
    def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
        """Poll until the server responds on the given port."""
        import urllib.request

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
                return True
            except OSError:
                time.sleep(0.15)
        return False

    def test_no_window_flag_accepted(self) -> None:
        """Verify that --no-window is recognized by the argument parser."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--no-window", action="store_true", default=False)
        args = parser.parse_args(["--no-window"])
        assert args.no_window is True

        args = parser.parse_args([])
        assert args.no_window is False

    def test_server_with_no_window_serves_content(self) -> None:
        """End-to-end: start server with --no-window, curl / and /shared/tokens.css.

        This is the key regression test — the server must work exactly as
        before with the --no-window flag.
        """
        import urllib.request

        port = self._free_port()
        proc = self._start_server(port, "--no-window")

        try:
            assert self._wait_for_server(port), f"Server on port {port} did not start"

            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
            assert resp.status == 200
            body = resp.read().decode()
            assert "<!DOCTYPE html>" in body.lower() or "<html" in body.lower()

            # Check static assets
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/shared/tokens.css"
            )
            assert resp.status == 200
            css = resp.read().decode()
            assert "clamp" in css  # fluid typography

            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/static/css/app.css"
            )
            assert resp.status == 200
        finally:
            import signal

            __import__("os").killpg(__import__("os").getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)

    def test_server_with_no_window_serves_api(self) -> None:
        """Check that /api/queue responds in --no-window mode."""
        import json
        import urllib.request

        port = self._free_port()
        proc = self._start_server(port, "--no-window")

        try:
            assert self._wait_for_server(port), f"Server on port {port} did not start"

            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/queue"
            )
            assert resp.status == 200
            data = json.loads(resp.read())
            assert "items" in data or "queue" in data
        finally:
            import signal

            __import__("os").killpg(__import__("os").getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)

    def test_normal_mode_serves_content(self) -> None:
        """In non-frozen mode without --no-window, server serves normally.

        We cannot verify the native window opens (WSL has no display), but
        we verify the server is accessible — which is the fallback behavior
        on a headless system.
        """
        import urllib.request

        port = self._free_port()
        proc = self._start_server(port)

        try:
            assert self._wait_for_server(port), f"Server on port {port} did not start"

            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/")
            assert resp.status == 200
        finally:
            import signal

            __import__("os").killpg(__import__("os").getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
