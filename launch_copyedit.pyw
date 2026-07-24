"""Windowed launcher for the Copy Editor GUI.

Equivalent to ``python scripts/run_edit.py --gui``, but without a console
window. Because `.pyw` suppresses the console, an unhandled error would vanish
silently, so failures are logged to ~/.copyedit/launcher.log and shown in a
dialog.

Two classes of dependency are handled differently:

* REQUIRED — the tool cannot run without these. If the interpreter that
  started the launcher lacks them, another is found and the launcher
  re-executes itself with it.
* PREFERRED — `tkinterdnd2` only enables drag-and-drop; ``src/gui.py`` falls
  back to a file-picker button without it. A missing preferred package is
  worth switching interpreters for, but never worth refusing to start.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "run_edit.py"
LOG = Path.home() / ".copyedit" / "launcher.log"

# `docx` is python-docx; `docx_revisions` provides the tracked-change writer.
REQUIRED = ("docx", "docx_revisions", "requests", "tkinter")
PREFERRED = ("tkinterdnd2",)

SENTINEL = "COPYEDIT_LAUNCHER_REEXEC"


def _log(message: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except OSError:
        pass


def _show_error(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        _log(f"{title}: {message}")


def _missing(names: tuple[str, ...]) -> list[str]:
    absent = []
    for name in names:
        try:
            if importlib.util.find_spec(name) is None:
                absent.append(name)
        except (ImportError, ValueError):
            absent.append(name)
    return absent


def _installed_interpreters() -> list[Path]:
    """Every python.exe the `py` launcher knows about."""
    try:
        result = subprocess.run(
            ["py", "-0p"], capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return []

    found = []
    for line in result.stdout.splitlines():
        part = line.strip()
        idx = part.lower().find("c:\\")
        if idx == -1:
            continue
        candidate = Path(part[idx:].strip().strip('"'))
        if candidate.name.lower() in ("python.exe", "pythonw.exe"):
            found.append(candidate)
    return found


def _interpreter_imports(exe: Path, names: tuple[str, ...]) -> bool:
    try:
        result = subprocess.run(
            [str(exe), "-c", f"import {', '.join(names)}"],
            capture_output=True, timeout=40,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _find_interpreter(names: tuple[str, ...]) -> Path | None:
    here = Path(sys.executable).resolve()
    for exe in _installed_interpreters():
        if exe.resolve() == here:
            continue
        if _interpreter_imports(exe, names):
            windowed = exe.with_name("pythonw.exe")
            return windowed if windowed.exists() else exe
    return None


def _relaunch(exe: Path) -> int:
    """Start the launcher again under `exe`. Not os.execv: on Windows that
    builds a command line without quoting, so a path containing spaces
    ("...\\CopyEdit Tool\\...") is split and the child never starts."""
    env = dict(os.environ, **{SENTINEL: "1"})
    try:
        subprocess.Popen([str(exe), str(Path(__file__).resolve())],
                         cwd=str(ROOT), env=env)
    except OSError as exc:
        _show_error("Copy Editor failed to start",
                    f"Could not start {exe}\n\n{exc}\n\nLog: {LOG}")
        return 1
    return 0


def main() -> int:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    already_switched = bool(os.environ.get(SENTINEL))

    missing = _missing(REQUIRED)
    if missing:
        if already_switched:
            _show_error(
                "Copy Editor — missing dependencies",
                f"This Python cannot run the tool.\n\n"
                f"Interpreter: {sys.executable}\n"
                f"Missing: {', '.join(missing)}\n\n"
                f"Install them with:\n    pip install -r requirements.txt\n\n"
                f"Log: {LOG}",
            )
            return 1

        replacement = _find_interpreter(REQUIRED)
        if replacement is None:
            _show_error(
                "Copy Editor — missing dependencies",
                f"Missing packages: {', '.join(missing)}\n\n"
                f"No installed Python has them. From\n{ROOT}\nrun:\n"
                f"    pip install -r requirements.txt\n\nLog: {LOG}",
            )
            return 1

        _log(f"Re-launching with {replacement} (missing: {', '.join(missing)})")
        return _relaunch(replacement)

    # Everything essential is present. Drag-and-drop is a nicety, so only
    # switch interpreters for it if one is available, and carry on regardless.
    if not already_switched and _missing(PREFERRED):
        better = _find_interpreter(REQUIRED + PREFERRED)
        if better is not None:
            _log(f"Re-launching with {better} for drag-and-drop support")
            return _relaunch(better)
        _log("tkinterdnd2 unavailable — starting with the file picker only")

    if not SCRIPT.exists():
        _show_error("Copy Editor failed to start",
                    f"Entry point not found:\n{SCRIPT}")
        return 1

    # Run the documented entry point rather than reaching into src.gui, so
    # config and logging are set up exactly as they are from the command line.
    sys.argv = [str(SCRIPT), "--gui"]
    spec = importlib.util.spec_from_file_location("run_edit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        detail = traceback.format_exc()
        _log(detail)
        _show_error(
            "Copy Editor failed to start",
            f"{detail.strip().splitlines()[-1]}\n\nFull details in:\n{LOG}",
        )
        sys.exit(1)
