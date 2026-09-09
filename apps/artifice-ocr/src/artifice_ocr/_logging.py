# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Centralized logging for the OCR pipeline.

Usage:
    from artifice_ocr._logging import get_logger
    log = get_logger("ocr")
    log.info("Starting OCR for %s", filename)

**Why there is a file handler here.** The app ships as a windowed executable
(``console=False`` in ``artifice-ocr.spec``), which means ``sys.stderr`` goes
nowhere on Windows. For a long time this module logged to stderr alone, so a
packaged run produced no diagnostics at all: a real context-window overflow
reached the user as nothing but ``'NoneType' object has no attribute 'strip'``,
and finding the cause meant re-running the executable with its stderr
redirected to a file. Everything needed had been logged — there was simply
nowhere for it to land. The rotating file handler is that somewhere.
"""

import contextlib
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s [%(name)-10s] %(levelname)-5s %(message)s"
_DATEFMT = "%H:%M:%S"

# The file gets the full logger name and a date, because a log read days later
# out of context needs both. The console keeps its short, scannable form.
_FILE_FORMAT = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"

LOG_DIR_ENV = "ARTIFICE_OCR_LOG_DIR"
LOG_FILENAME = "artifice-ocr.log"

# ~2 MB x 3 backups. Large enough to hold a long multi-page run, small enough
# that a user can attach one to an issue report.
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 3

_configured = False


def log_dir() -> Path:
    """Directory the log file lives in.

    Defaults to ``~/.artifice_ocr/logs``, beside the settings and history the
    app already keeps there, so a user has one place to look. Override with
    ``ARTIFICE_OCR_LOG_DIR`` (the test suite does, to stay out of a real
    developer's log).
    """
    override = os.environ.get(LOG_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return Path.home() / ".artifice_ocr" / "logs"


def log_path() -> Path:
    """Full path of the current log file."""
    return log_dir() / LOG_FILENAME


def _add_file_handler(root: logging.Logger, level: int) -> bool:
    """Attach the rotating file handler. Returns False if it could not be made.

    Failing to open a log must never be the reason a run fails, so every error
    here is swallowed — the app degrades to console-only logging, which is
    exactly the behaviour that existed before this handler.

    ``encoding="utf-8"`` is not optional. Without it the handler uses the
    locale codec (cp1252 on a stock Windows install) and raises
    ``UnicodeEncodeError`` on the first umlaut or curly quote — on the very
    pages most likely to be under investigation. That is the same trap that
    broke the Tesseract subprocess in ``_tesseract.py``; a log that cannot
    record the failing page is worse than no log.
    """
    try:
        directory = log_dir()
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / LOG_FILENAME,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        return False
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_FILE_DATEFMT))
    root.addHandler(handler)
    return True


def _install_exception_hooks(logger: logging.Logger) -> None:
    """Route otherwise-unhandled exceptions into the log as well as stderr.

    Both default hooks print to ``sys.stderr``, which the frozen build
    discards. The failure that motivated this module's file handler died in a
    ``subprocess`` reader thread: its ``UnicodeDecodeError`` traceback went to
    stderr and vanished, leaving only a misleading error three frames away.
    Chaining rather than replacing keeps normal console behaviour intact.
    """
    previous_sys_hook = sys.excepthook
    previous_thread_hook = threading.excepthook

    def _sys_hook(exc_type, exc, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            logger.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        previous_sys_hook(exc_type, exc, tb)

    def _thread_hook(args):
        if args.exc_type is not None and not issubclass(args.exc_type, SystemExit):
            logger.critical(
                "Unhandled exception in thread %s",
                getattr(args.thread, "name", "?"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        previous_thread_hook(args)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger("artifice_ocr")
    root.setLevel(level)

    # ``pythonw.exe`` sets both std streams to None before any of our code
    # runs, and shared_ui.ensure_std_streams() may not have replaced them yet.
    if sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setLevel(level)
        stream.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
        root.addHandler(stream)

    if _add_file_handler(root, level):
        _install_exception_hooks(root)

    root.propagate = False


def reset() -> None:
    """Drop every handler and allow :func:`setup_logging` to run again.

    Exists for the test suite, which needs each test to log into its own
    temporary directory rather than inheriting the first test's handler.
    """
    global _configured
    root = logging.getLogger("artifice_ocr")
    for handler in list(root.handlers):
        root.removeHandler(handler)
        with contextlib.suppress(Exception):
            handler.close()
    _configured = False


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"artifice_ocr.{name}")
