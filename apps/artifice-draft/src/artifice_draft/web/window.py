# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Native desktop window via pywebview (WebView2 / WKWebView / WebKitGTK).

All pywebview imports are local to ``open_native_window()`` so that users of
``uv tool install artifice-draft`` (who may not have a webview backend) can
still import and run the CLI and web server without pywebview installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class WindowError(Exception):
    """Raised when a native window cannot be opened."""


class WindowResult:
    """Return value from :func:`open_native_window`.

    Carries whether the window opened and, if not, a human-readable reason
    suitable for printing to the user.
    """

    def __init__(self, opened: bool, reason: str = "") -> None:
        self.opened = opened
        self.reason = reason


def open_native_window(
    url: str,
    *,
    title: str = "ArtificeDraft",
    width: int = 1280,
    height: int = 800,
) -> WindowResult:
    """Open *url* in a native desktop window.

    Returns a :class:`WindowResult`.  If the window opened, this call blocks
    until the user closes it and then returns ``opened=True``.  If no webview
    backend is available (headless session, missing system libraries, or
    pywebview not installed) it returns ``opened=False`` with a short human
    reason.

    This function is designed to be called *after* the local server is already
    listening, so the user sees a populated page immediately.
    """
    # ------------------------------------------------------------------
    # In a PyInstaller frozen build on Windows, pywebview's pythonnet backend
    # loads Python.Runtime.dll from _internal/pythonnet/runtime/, which then
    # needs to resolve the embedded pythonXY.dll. That DLL lives in
    # _internal/ (== sys._MEIPASS at runtime), which is not on %PATH% and
    # PYTHONNET_PYDLL is unset, so the .NET loader fails with "Failed to
    # resolve Python.Runtime.Loader.Initialize" before webview.start() ever
    # runs. Both env vars must be set before ``import webview`` triggers
    # pythonnet's own DLL search — setting them after is too late.
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", None)
        if base_dir is not None:
            base_dir = Path(base_dir)
            dll_name = f"python{sys.version_info.major}{sys.version_info.minor}.dll"
            dll_path = base_dir / dll_name
            if dll_path.exists():
                os.environ["PYTHONNET_PYDLL"] = str(dll_path)
            os.environ["PATH"] = str(base_dir) + os.pathsep + os.environ.get("PATH", "")

    # ------------------------------------------------------------------
    # Try to import pywebview.  Both the import itself and the subsequent
    # ``webview.start()`` can fail in headless / missing-backend scenarios.
    # We catch every case here so the caller only has one place to handle.
    # ------------------------------------------------------------------
    try:
        import webview  # noqa: PLC0415 — deliberate lazy import
    except ImportError:
        return WindowResult(
            opened=False,
            reason="pywebview is not installed — run `pip install pywebview`.",
        )

    # webview.start() raises WebViewException when no backend is found, and a
    # bare RuntimeError / ImportError when a system dependency (pythonnet,
    # GTK, etc.) is missing at runtime.
    try:
        webview.create_window(
            title=title,
            url=url,
            width=width,
            height=height,
            resizable=True,
            min_size=(640, 480),
        )
        # webview.start() blocks until the window is closed.
        webview.start(gui=None)  # let pywebview auto-detect
    except Exception as exc:
        msg = str(exc).strip() or type(exc).__name__
        return WindowResult(opened=False, reason=f"Native window unavailable: {msg}")

    return WindowResult(opened=True, reason="")
