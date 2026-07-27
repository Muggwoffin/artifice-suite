"""Tkinter GUI for the OCR pipeline.

Entry point stays ``artifice_ocr.gui:main`` — the module became a package but
the console script is unchanged.
"""

from .app import App, main

__all__ = ["App", "main"]
