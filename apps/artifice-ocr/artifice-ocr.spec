# -*- mode: python ; coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Maurice Casey
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# PyInstaller spec for artifice-ocr — Linux standalone executable.
#
# onedir (not onefile) was chosen deliberately:
#
#   1. Startup speed — onedir maps files directly from disk instead of
#      extracting a self-contained archive to a temp directory on every launch.
#
#   2. Debuggability — you can inspect the _internal/ tree to see exactly
#      what shipped, which onefile compresses into an opaque .pak.
#
#   3. __file__ safety — onefile extracts to a different temp directory each
#      launch, which breaks __file__-relative paths harder.  We already fixed
#      the two remaining __file__ sites, but onedir is the safer choice for
#      a codebase that carries a fossil record of the pattern.
#
#   4. Distribution model — on macOS this becomes an .app bundle; on Windows
#      it is a folder you zip.  Both are standard.  onefile is primarily for
#      CLI tools with no bundled data, which this is not.
#
# Usage (from the repo root):
#   uv run --with pyinstaller pyinstaller apps/artifice-ocr/artifice-ocr.spec

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# ---------------------------------------------------------------------------
# Configuration — paths relative to the repo root
# ---------------------------------------------------------------------------
APP_NAME = "artifice-ocr"
PACKAGE = "artifice_ocr"
ENTRY_POINT = "artifice_ocr.web.server:main"

# ---------------------------------------------------------------------------
# Hidden imports — uvicorn, fastapi, and friends load things dynamically
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
    # jinja2 — PackageLoader loads templates at runtime
    "jinja2.ext",
    # Other dynamic loaders
    "multipart",
    "multipart.multipart",
    # artisecure_io — dynamic import in config.py
    "secure_io",
    # model_harness — only loaded when a model is actually called;
    # include it so the BYOM onboarding screen works from a cold bundle.
    "model_harness",
    "model_harness.contract",
    "model_harness.registry",
]

# ---------------------------------------------------------------------------
# Data files — collect_data_files() picks up everything declared in
# pyproject.toml [tool.setuptools.package-data] for both artifice_ocr and
# shared_ui, plus the shared_ui templates (hatchling include rule).
# ---------------------------------------------------------------------------
datas = []
datas.extend(collect_data_files("artifice_ocr"))
datas.extend(collect_data_files("shared_ui"))

# ---------------------------------------------------------------------------
# Analysis
#
# We point PyInstaller at a dedicated freeze-entry script (imports
# server.main() through normal Python import machinery) rather than at
# server.py directly.  Running server.py as a bare script breaks relative
# imports ("from .routers import ..." → "attempted relative import with no
# known parent package").  The wrapper uses absolute imports and preserves
# the package context.
#
# The pathex list gives PyInstaller the source directories it needs to find
# artifice_ocr and its dependencies (shared_ui, model_harness, secure_io).
# ---------------------------------------------------------------------------
_SPEC_DIR = Path(SPECPATH)
_REPO_ROOT = _SPEC_DIR.parent.parent
_FREEZE_ENTRY = str(_REPO_ROOT / "apps" / APP_NAME / "src" / PACKAGE / "_freeze_entry.py")

a = Analysis(
    [_FREEZE_ENTRY],
    pathex=[
        str(_REPO_ROOT / "apps" / "artifice-ocr" / "src"),
        str(_REPO_ROOT / "apps" / "artifice-graph" / "src"),
        str(_REPO_ROOT / "apps" / "artifice-draft" / "src"),
        str(_REPO_ROOT / "apps" / "artifice-transcribe" / "src"),
        str(_REPO_ROOT / "packages" / "shared-ui"),
        str(_REPO_ROOT / "packages" / "model-harness" / "src"),
        str(_REPO_ROOT / "packages" / "secure-io" / "src"),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# onedir EXE
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # user sees the server-startup banner
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
