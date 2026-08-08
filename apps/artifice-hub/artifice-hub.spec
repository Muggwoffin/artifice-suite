# -*- mode: python ; coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# PyInstaller spec for artifice-hub — cross-platform standalone executable.
#
# ONEFILE — deliberate, ratified deviation.
#
# The Hub is a tiny launcher (fastapi + pywebview, no model libraries, no
# data files beyond webview's js/ and shared_ui assets).  It is meant to be
# a single double-clickable download, and the onefile startup penalty
# (extracting a self-contained archive to a temp directory) is negligible at
# this size.  Every other app in the suite uses onedir; this does not.
#
# Rationale:
#   1. The Hub has no model weights, no bundled data beyond CSS/JS, and no
#      __file__-relative paths (all imports resolve through importlib).
#   2. A single .exe / single-file .app is the expected UX for a launcher.
#      Users download one file, double-click it, and get a native window.
#   3. The onedir rationale (startup speed, debuggability, freeze safety)
#      is for apps that ship data and need introspection — none applies here.
#
# Usage (from the repo root):
#   uv run --with pyinstaller pyinstaller apps/artifice-hub/artifice-hub.spec

import sys
from pathlib import Path

from PyInstaller.compat import is_win
from PyInstaller.utils.hooks import collect_data_files

# ---------------------------------------------------------------------------
# Configuration — paths relative to the repo root
# ---------------------------------------------------------------------------
APP_NAME = "artifice-hub"
PACKAGE = "artifice_hub"
ENTRY_POINT = "artifice_hub._freeze_entry:main"

# ---------------------------------------------------------------------------
# Hidden imports — uvicorn, fastapi, pywebview load things dynamically
# that PyInstaller's static analysis misses.
# ---------------------------------------------------------------------------
HIDDEN_IMPORTS = [
    # uvicorn
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    # fastapi
    "fastapi",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    "fastapi.staticfiles",
    # starlette
    "starlette",
    "starlette.routing",
    "starlette.middleware",
    # pywebview — dynamically loads platform backends at runtime;
    # PyInstaller's static analysis cannot discover these.
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.win32",
    "webview.platforms.gtk",
    "webview.platforms.cocoa",
    "webview.platforms.qt",
    "webview.platforms.cef",
    "webview.platforms.mshtml",
    "webview.platforms.edgechromium",
    "webview.dom",
    "webview.dom.element",
    "webview.dom.event",
    "webview.dom.dom",
    "webview.dom.propdict",
    "webview.dom.classlist",
    "webview.menu",
    "webview.http",
    "webview.event",
    "webview.screen",
    "webview.localization",
    "webview.guilib",
    "webview.util",
    "webview.state",
    "webview.models",
    "webview.errors",
    "webview._version",
    # pythonnet — the bridge pywebview uses to talk to WinForms/WebView2
    # on Windows.  Not used on Linux/macOS but harmless as a hidden import.
    "clr",
]

# Deliberately NOT included — the Hub makes zero model calls:
#   multipart*, secure_io, model_harness*

# ---------------------------------------------------------------------------
# Data files
# ---------------------------------------------------------------------------
datas = []
datas.extend(collect_data_files("artifice_hub"))
datas.extend(collect_data_files("shared_ui"))

# pywebview ships js/ and lib/ directories that its backends need at runtime.
datas.extend(collect_data_files("webview", subdir="js"))
if is_win:
    datas.extend(collect_data_files("webview", subdir="lib"))

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
_SPEC_DIR = Path(SPECPATH)
_REPO_ROOT = _SPEC_DIR.parent.parent
_FREEZE_ENTRY = str(_REPO_ROOT / "apps" / APP_NAME / "src" / PACKAGE / "_freeze_entry.py")

# Hookspath: include pywebview's own PyInstaller hook so its js/ and lib/
# data files are automatically collected on every platform.
_WEBVIEW_HOOKSPATH = []
try:
    import webview as _wv
    import os as _os

    _hook_dir = _os.path.join(_os.path.dirname(_wv.__file__), "__pyinstaller")
    if _os.path.isdir(_hook_dir):
        _WEBVIEW_HOOKSPATH.append(_hook_dir)
except Exception:
    pass

a = Analysis(
    [_FREEZE_ENTRY],
    pathex=[
        str(_REPO_ROOT / "apps" / "artifice-hub" / "src"),
        str(_REPO_ROOT / "packages" / "shared-ui"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=_WEBVIEW_HOOKSPATH,
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# ONEFILE EXE — the Hub is a single double-clickable download
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,    # include binaries (onedir exclude_binaries=True; onefile bundles them)
    a.datas,       # include datas (onedir defers to COLLECT; onefile bundles them)
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # GUI app — no console window. Startup failure → tkinter dialog.
    icon='../../apps/artifice-hub/assets/artifice-hub.ico',
)
