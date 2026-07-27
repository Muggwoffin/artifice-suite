"""Windowed launcher for the OCR Pipeline GUI.

The `.pyw` extension means Windows runs this without a console window. That
also means an unhandled error would vanish silently, so everything here is
wrapped: failures are written to ~/.artifice_ocr/launcher.log and shown in a
dialog.

This machine has several Python installations and only one of them carries the
project's dependencies. If the interpreter that started this launcher cannot
import them, the launcher looks for one that can and re-executes itself with
it — so the desktop shortcut keeps working across Python upgrades.
"""

import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = Path.home() / ".artifice_ocr" / "launcher.log"

# Imported by name; `fitz` is PyMuPDF's module name.
REQUIRED = ("tkinterdnd2", "openai", "ollama", "yaml", "fitz")

# Guard against an interpreter-hunting loop.
SENTINEL = "ARTIFICE_OCR_LAUNCHER_REEXEC"


def _log(message: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except OSError:
        pass


def _show_error(title: str, message: str) -> None:
    """Report a failure that would otherwise be invisible."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        # No tkinter at all — the log is the only channel left.
        _log(f"{title}: {message}")


def _missing_packages() -> list[str]:
    import importlib.util

    missing = []
    for name in REQUIRED:
        try:
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        except (ImportError, ValueError):
            missing.append(name)
    return missing


def _installed_interpreters() -> list[Path]:
    """Every python.exe the `py` launcher knows about, newest first."""
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


def _interpreter_has_deps(exe: Path) -> bool:
    try:
        result = subprocess.run(
            [str(exe), "-c", f"import {', '.join(REQUIRED)}"],
            capture_output=True, timeout=40,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _find_working_interpreter() -> Path | None:
    for exe in _installed_interpreters():
        if exe.resolve() == Path(sys.executable).resolve():
            continue
        if _interpreter_has_deps(exe):
            # Prefer the windowed twin so no console flashes up.
            windowed = exe.with_name("pythonw.exe")
            return windowed if windowed.exists() else exe
    return None


def main() -> int:
    # The package lives under src/, matching a normal editable install; add it
    # to the path so `artifice_ocr` resolves without a real `pip install -e .`.
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))

    missing = _missing_packages()
    if missing:
        if os.environ.get(SENTINEL):
            _show_error(
                "OCR Pipeline — missing dependencies",
                f"This Python cannot run the tool.\n\n"
                f"Interpreter: {sys.executable}\n"
                f"Missing: {', '.join(missing)}\n\n"
                f"Install them with:\n    pip install -e .\n\n"
                f"Log: {LOG}",
            )
            return 1

        replacement = _find_working_interpreter()
        if replacement is None:
            _show_error(
                "OCR Pipeline — missing dependencies",
                f"Missing packages: {', '.join(missing)}\n\n"
                f"No installed Python has them. From\n{ROOT}\nrun:\n"
                f"    pip install -e .\n\nLog: {LOG}",
            )
            return 1

        _log(f"Re-launching with {replacement} (missing: {', '.join(missing)})")
        env = dict(os.environ, **{SENTINEL: "1"})
        # subprocess, not os.execv: on Windows execv flattens the argument list
        # into a command line without quoting, so a project path containing
        # spaces ("…\OCR Pipeline Tool\…") is split and the child never starts.
        try:
            subprocess.Popen(
                [str(replacement), str(Path(__file__).resolve())],
                cwd=str(ROOT), env=env,
            )
        except OSError as exc:
            _show_error("OCR Pipeline failed to start",
                        f"Could not start {replacement}\n\n{exc}\n\nLog: {LOG}")
            return 1
        return 0

    from artifice_ocr.gui import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        detail = traceback.format_exc()
        _log(detail)
        _show_error(
            "OCR Pipeline failed to start",
            f"{detail.strip().splitlines()[-1]}\n\nFull details in:\n{LOG}",
        )
        sys.exit(1)
