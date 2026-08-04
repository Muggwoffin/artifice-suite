# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Centralized logging for the OCR pipeline.

Usage:
    from artifice_ocr._logging import get_logger
    log = get_logger("ocr")
    log.info("Starting OCR for %s", filename)
"""

import logging
import sys

_FORMAT = "%(asctime)s [%(name)-10s] %(levelname)-5s %(message)s"
_DATEFMT = "%H:%M:%S"

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger("artifice_ocr")
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    root.addHandler(handler)

    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(f"artifice_ocr.{name}")
