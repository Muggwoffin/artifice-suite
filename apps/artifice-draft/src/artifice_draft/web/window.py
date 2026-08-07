# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Native desktop window via pywebview (WebView2 / WKWebView / WebKitGTK).

All pywebview imports are local to ``open_native_window()`` so that users of
``uv tool install artifice-draft`` (who may not have a webview backend) can
still import and run the CLI and web server without pywebview installed.
"""

from __future__ import annotations

import contextlib
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


def _unblock_pythonnet_assemblies(pythonnet_dir: Path) -> None:
    """Strip the Windows Zone.Identifier (Mark-of-the-Web) from pythonnet's
    bundled .NET assemblies.

    A file downloaded via a browser — or extracted from a zip that was itself
    downloaded — is tagged with a Zone.Identifier NTFS alternate-data-stream
    marking its origin as "Internet".  .NET Framework's classic assembly loader
    (netfx, which is pythonnet's default runtime on Windows) refuses to resolve
    functions from an assembly carrying that tag, failing with "Failed to
    resolve Python.Runtime.Loader.Initialize" — a documented
    pythonnet/clr-loader issue
    (https://github.com/pythonnet/clr-loader/issues/74), not a bundling defect.
    This strips the tag before pythonnet ever touches the DLL.  A no-op (not an
    error) when the stream is absent (e.g. every CI-built binary, or after a
    user manually unblocks the download).
    """
    if not pythonnet_dir.is_dir():
        return
    for path in pythonnet_dir.rglob("*"):
        if path.is_file():
            with contextlib.suppress(OSError):
                os.remove(f"{path}:Zone.Identifier")


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
    # In a PyInstaller frozen build on Windows, files downloaded via a
    # browser (or extracted from a zip that was itself downloaded) carry a
    # Zone.Identifier NTFS alternate-data-stream (Mark-of-the-Web) that tags
    # their origin as "Internet".  .NET Framework's classic assembly loader
    # (netfx, which is pythonnet's default runtime on Windows) refuses to
    # resolve functions from assemblies carrying that tag, raising
    # "Failed to resolve Python.Runtime.Loader.Initialize" — a documented
    # pythonnet/clr-loader issue
    # (https://github.com/pythonnet/clr-loader/issues/74), not a bundling
    # defect.  Strip the Zone.Identifier ADS from pythonnet's bundled .NET
    # assemblies before ``import webview`` triggers pythonnet's own
    # ``import clr`` — doing it after is too late.
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        base_dir = getattr(sys, "_MEIPASS", None)
        if base_dir is not None:
            _unblock_pythonnet_assemblies(Path(base_dir) / "pythonnet")

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
