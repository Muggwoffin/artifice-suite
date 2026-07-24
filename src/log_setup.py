"""Centralized logging configuration for the PersonaeEdit tool.

Provides structured logging with optional file output, rotation, and
configurable verbosity levels.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

_INITIALIZED = False


def setup_logging(
    level: str = "INFO",
    log_file: str = "",
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 3,
) -> None:
    """Configure logging for the application.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional path to a log file. If empty, only console output.
        max_bytes: Max size per log file before rotation.
        backup_count: Number of rotated log files to keep.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_fmt = logging.Formatter(
        "%(asctime)s %(name)-25s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(console_fmt)
    root_logger.addHandler(console_handler)

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_fmt = logging.Formatter(
            "%(asctime)s %(name)-25s %(levelname)-7s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)  # always capture everything to file
        file_handler.setFormatter(file_fmt)
        root_logger.addHandler(file_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    logging.debug("Logging initialized: level=%s, file=%s", level, log_file or "(none)")


def get_log_file_path() -> str:
    """Return the default log file path next to the main script."""
    project_root = Path(__file__).resolve().parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    return str(log_dir / "personaeedit.log")
