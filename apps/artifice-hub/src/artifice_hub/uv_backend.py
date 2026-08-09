# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Subprocess layer for ``uv`` operations.

Security boundary — every function that builds a command line validates the
app slug against :mod:`artifice_hub.registry` before reaching a subprocess
call.  All calls use list-form argv (``shell=False``).

Threading model
---------------
Install and upgrade jobs run on worker threads, never the event loop.
Each job carries a thread-safe ``JobState`` that survives browser refresh.
Progress is streamed via SSE from a per-job queue.

PyInstaller compatibility
--------------------------
``_scrubbed_env()`` restores ``LD_LIBRARY_PATH`` / ``DYLD_LIBRARY_PATH``.
A frozen bundle sets these to ``_MEIPASS``, which can cause ``uv`` and its
child processes to load the wrong shared libraries.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .registry import APPS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


class ErrorKind(Enum):
    UV_MISSING = "uv_missing"
    NETWORK = "network"
    DISK_FULL = "disk_full"
    RESOLUTION = "resolution"
    UNKNOWN = "unknown"


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    error_kind: ErrorKind
    error_detail: str  # human-readable, suitable for the UI


# Patterns matched against combined stderr + captured stdout tail
_NETWORK_RE = re.compile(
    r"(Connection refused|Network is unreachable|Temporary failure in name resolution|"
    r"Could not resolve host|SSL: CERTIFICATE_VERIFY_FAILED|timed out|"
    r"error sending request)",
    re.IGNORECASE,
)
_DISK_FULL_RE = re.compile(
    r"(No space left on device|Disk quota exceeded|ENOSPC)", re.IGNORECASE
)
_RESOLUTION_RE = re.compile(
    r"(No solution found|Resolution failed|conflicting dependencies|"
    r"Could not find a version that satisfies)",
    re.IGNORECASE,
)

# ── ANSI escape stripping (uv uses \r for progress bars) ──────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_CR_RE = re.compile(r"\r+")

# ---------------------------------------------------------------------------
# Environment scrubbing (PyInstaller safety)
# ---------------------------------------------------------------------------


def _scrubbed_env() -> dict[str, str]:
    """Return a copy of ``os.environ`` with PyInstaller library paths removed.

    When the Hub runs inside a PyInstaller bundle, ``LD_LIBRARY_PATH`` and
    ``DYLD_LIBRARY_PATH`` are set to ``_MEIPASS`` so the frozen process finds
    its own shared libraries.  Those paths would poison any ``uv`` child
    process (and any process ``uv`` spawns, e.g. the ASR stack), so strip them.
    """
    env = os.environ.copy()
    for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        if key in env:
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass and meipass in env[key]:
                parts = [p for p in env[key].split(os.pathsep) if p != meipass]
                if parts:
                    env[key] = os.pathsep.join(parts)
                else:
                    del env[key]
    return env


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def find_uv() -> str | None:
    """Locate the ``uv`` binary.

    Checks ``PATH``, then common user-install locations across platforms.
    Returns the absolute path or ``None`` if ``uv`` is not installed.
    """
    found = shutil.which("uv")
    if found:
        return found

    candidates = [
        Path.home() / ".local" / "bin" / "uv",
        Path.home() / ".cargo" / "bin" / "uv",
        Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "uv.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def tool_bin_dir(uv: str) -> Path | None:
    """Return the ``uv tool dir --bin`` directory.

    Returns ``None`` if the command fails (e.g. ``uv`` not found, or
    version too old).
    """
    try:
        result = subprocess.run(
            [uv, "tool", "dir", "--bin"],
            capture_output=True,
            text=True,
            timeout=5,
            env=_scrubbed_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# uv tool list parsing
# ---------------------------------------------------------------------------


def list_tools(uv: str) -> dict[str, str]:
    """Parse ``uv tool list`` into a ``{slug: version}`` dict.

    ``uv`` prints installed tools to stdout.  When no tools are installed it
    prints "No tools installed" to **stderr** and exits 0 — so we inspect
    stderr for that phrase and return an empty dict, not an error.
    """
    try:
        result = subprocess.run(
            [uv, "tool", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_scrubbed_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception:
        return {}

    # uv may report "No tools installed" on stderr
    combined = result.stdout + result.stderr
    if "No tools installed" in combined or "no tools installed" in combined.lower():
        return {}

    tools: dict[str, str] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Format: "artifice-ocr (v0.2.0)" or "artifice-ocr v0.2.0"
        match = re.match(r"(\S+)\s+(?:\(?v?([^)]+)\)?)", line)
        if match:
            tools[match.group(1)] = match.group(2).strip()
    return tools


def outdated_tools(uv: str) -> set[str]:
    """Return the set of installed tool slugs that have updates available.

    Parses ``uv tool list --outdated``.  Returns an empty set on any error
    (missing ``uv``, no tools installed, etc.).
    """
    try:
        result = subprocess.run(
            [uv, "tool", "list", "--outdated"],
            capture_output=True,
            text=True,
            timeout=10,
            env=_scrubbed_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception:
        return set()

    outdated: set[str] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"(\S+)", line)
        if match:
            outdated.add(match.group(1))
    return outdated


# ---------------------------------------------------------------------------
# Job state for SSE streaming
# ---------------------------------------------------------------------------


@dataclass
class JobState:
    job_id: str
    slug: str
    action: str  # "install" | "upgrade"
    events: queue.Queue[str | None] = field(default_factory=queue.Queue)
    result: CommandResult | None = None
    complete: bool = False
    started_at: float = field(default_factory=time.time)

    def push(self, line: str) -> None:
        """Push a log line to the event queue.  Strips ANSI escapes and
        splits ``\r``-delimited progress bar chunks into individual events."""
        clean = _ANSI_RE.sub("", line)
        for chunk in _CR_RE.split(clean):
            chunk = chunk.strip()
            if chunk:
                self.events.put(chunk)

    def finish(self, result: CommandResult | None = None) -> None:
        self.result = result
        self.complete = True
        self.events.put(None)  # sentinel — SSE client closes


# In-memory store (survives browser refresh but not server restart)
_jobs: dict[str, JobState] = {}


def _classify_error(stderr: str) -> tuple[ErrorKind, str]:
    """Classify a subprocess failure from its combined stderr tail."""
    tail = stderr[-2000:] if len(stderr) > 2000 else stderr
    if _NETWORK_RE.search(tail):
        return ErrorKind.NETWORK, tail.strip()
    if _DISK_FULL_RE.search(tail):
        return ErrorKind.DISK_FULL, tail.strip()
    if _RESOLUTION_RE.search(tail):
        return ErrorKind.RESOLUTION, tail.strip()
    return ErrorKind.UNKNOWN, tail.strip()


# ---------------------------------------------------------------------------
# Subprocess runners (run on worker threads)
# ---------------------------------------------------------------------------


def _run_subprocess(
    cmd: list[str],
    job: JobState,
    *,
    timeout: int = 3600,
) -> CommandResult:
    """Run *cmd* as a subprocess, streaming output to *job* for SSE.

    ``uv`` uses ``\r`` for progress bars, so ``job.push()`` splits on
    ``\r`` at write time rather than waiting for line-buffered ``\n``.

    A daemon reader thread consumes stdout line-by-line.  The main thread
    calls ``proc.wait()`` as the primary completion signal — this avoids
    the bug where a grandchild holding the stdout pipe prevents EOF from
    ever arriving and ``job.finish()`` (called by the caller after we
    return) is therefore never reached.
    """
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered — reader thread consumes line-by-line
            env=_scrubbed_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        captured: list[str] = []

        def _reader() -> None:
            """Read stdout line-by-line, push to job, accumulate."""
            assert proc.stdout is not None
            for line in proc.stdout:
                captured.append(line)
                job.push(line)

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()

        # Primary completion signal — does not depend on stdout EOF
        proc.wait(timeout=timeout)

        # Give the reader thread a chance to drain remaining buffered output
        reader.join(timeout=5.0)

        if reader.is_alive():
            # Pipe held open by a grandchild — force-close to unblock the
            # reader's blocking read so it hits EOF and exits.
            assert proc.stdout is not None
            proc.stdout.close()
            reader.join(timeout=2.0)

        full_output = "".join(captured)

        if proc.returncode == 0:
            return CommandResult(
                returncode=0,
                stdout=full_output,
                stderr="",
                error_kind=ErrorKind.UNKNOWN,
                error_detail="",
            )

        kind, detail = _classify_error(full_output)
        return CommandResult(
            returncode=proc.returncode,
            stdout=full_output,
            stderr=full_output,
            error_kind=kind,
            error_detail=detail,
        )
    except FileNotFoundError:
        job.push("ERROR: uv not found — please install uv first")
        return CommandResult(
            returncode=127,
            stdout="",
            stderr="uv executable not found",
            error_kind=ErrorKind.UV_MISSING,
            error_detail="The 'uv' binary was not found. Install it from https://docs.astral.sh/uv/",
        )
    except Exception as exc:
        job.push(f"ERROR: {exc}")
        return CommandResult(
            returncode=1,
            stdout="",
            stderr=str(exc),
            error_kind=ErrorKind.UNKNOWN,
            error_detail=str(exc),
        )


def install_app(
    uv: str,
    slug: str,
    variant: str | None,
    job: JobState,
) -> CommandResult:
    """Install *slug* via ``uv tool install``, streaming progress to *job*."""
    from .registry import AsrVariant, get_install_spec

    # Validate slug against the frozen registry
    if slug not in APPS:
        msg = f"Unknown app slug: {slug}"
        job.push(msg)
        return CommandResult(
            returncode=1,
            stdout="",
            stderr=msg,
            error_kind=ErrorKind.UNKNOWN,
            error_detail=msg,
        )

    asr_variant = None
    if variant == "cuda":
        asr_variant = AsrVariant.CUDA
    elif variant == "cpu":
        asr_variant = AsrVariant.CPU

    repo_root = os.environ.get("ARTIFICE_SUITE_ROOT", "").strip() or None
    install_spec = get_install_spec(slug, asr_variant, repo_root=repo_root)

    cmd = [uv, "tool", "install", install_spec]
    # Add torch backend hints for transcribe ASR installs
    if slug == "artifice-transcribe" and variant == "cuda":
        cmd.extend(["--torch-backend", "auto"])
    elif slug == "artifice-transcribe" and variant == "cpu":
        cmd.extend(["--torch-backend", "cpu"])

    job.push(f"$ {' '.join(cmd)}")
    return _run_subprocess(cmd, job)


def upgrade_app(uv: str, slug: str, job: JobState) -> CommandResult:
    """Upgrade *slug* via ``uv tool upgrade``, streaming progress to *job*."""
    if slug not in APPS:
        msg = f"Unknown app slug: {slug}"
        job.push(msg)
        return CommandResult(
            returncode=1,
            stdout="",
            stderr=msg,
            error_kind=ErrorKind.UNKNOWN,
            error_detail=msg,
        )

    cmd = [uv, "tool", "upgrade", slug]
    job.push(f"$ {' '.join(cmd)}")
    return _run_subprocess(cmd, job)


def uninstall_app(uv: str, slug: str) -> CommandResult:
    """Uninstall *slug* via ``uv tool uninstall`` (non-streaming)."""
    if slug not in APPS:
        return CommandResult(
            returncode=1,
            stdout="",
            stderr=f"Unknown app slug: {slug}",
            error_kind=ErrorKind.UNKNOWN,
            error_detail=f"Unknown app slug: {slug}",
        )

    try:
        result = subprocess.run(
            [uv, "tool", "uninstall", slug],
            capture_output=True,
            text=True,
            timeout=60,
            env=_scrubbed_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            return CommandResult(
                returncode=0, stdout=result.stdout, stderr=result.stderr,
                error_kind=ErrorKind.UNKNOWN, error_detail="",
            )
        kind, detail = _classify_error(result.stderr)
        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            error_kind=kind,
            error_detail=detail,
        )
    except Exception as exc:
        return CommandResult(
            returncode=1, stdout="", stderr=str(exc),
            error_kind=ErrorKind.UNKNOWN, error_detail=str(exc),
        )


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------


def launch_app(uv: str, slug: str) -> tuple[bool, str]:
    """Launch an installed app directly (entry-point shell-out).

    Tries the direct entry-point binary first (from ``uv tool dir --bin``),
    then falls back to ``uv tool run <slug>``.

    Returns ``(ok, message)``.
    """
    if slug not in APPS:
        return False, f"Unknown app: {slug}"

    spec = APPS[slug]
    entry = spec.entry_point

    # 1. Try direct entry-point invocation
    bin_dir = tool_bin_dir(uv)
    if bin_dir is not None:
        exe = bin_dir / (entry + (".exe" if sys.platform == "win32" else ""))
        if exe.is_file():
            try:
                subprocess.Popen(
                    [str(exe)],
                    start_new_session=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
                return True, f"Launched {spec.display_name}"
            except Exception:
                pass  # fall through to uv tool run

    # 2. Fall back to `uv tool run <entry_point>`
    try:
        subprocess.Popen(
            [uv, "tool", "run", "--from", slug, entry],
            start_new_session=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True, f"Launched {spec.display_name}"
    except Exception as exc:
        return False, f"Failed to launch {spec.display_name}: {exc}"
