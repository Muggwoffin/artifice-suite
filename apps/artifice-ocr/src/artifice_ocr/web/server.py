"""FastAPI backend for the web frontend.

This module owns the FastAPI ``app`` and the bootstrap code (CLI, port
discovery, browser launch). Individual route groups live under ``routers/``
and are included here.
"""

import os
import socket
import sys
import webbrowser
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .routers import analytics as analytics_router
from .routers import events as events_router
from .routers import history as history_router
from .routers import pdf_export as pdf_export_router
from .routers import queue as queue_router
from .routers import run as run_router
from .routers import settings as settings_router
from .routers import tropy as tropy_router
from .routers import ludwiglang as ludwiglang_router

app = FastAPI(title="OCR Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8765",
        "http://127.0.0.1:8765",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path.startswith("/shared/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.include_router(queue_router.router)
app.include_router(run_router.router)
app.include_router(events_router.router)
app.include_router(settings_router.router)
app.include_router(history_router.router)
app.include_router(analytics_router.router)
app.include_router(tropy_router.router)
app.include_router(pdf_export_router.router)
app.include_router(ludwiglang_router.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# ── Shared design system (resolved from installed shared-ui package) ───────
import importlib.resources
import shared_ui
_SHARED_UI = importlib.resources.files(shared_ui) / "assets"
app.mount("/shared", StaticFiles(directory=str(_SHARED_UI)), name="shared")


def _asset_version() -> str:
    """Cache-busting version for the /static and /shared links in index.html.

    Derived from the newest mtime across both asset trees and recomputed on
    every request to "/", so an asset edited while the server is running is
    picked up immediately and the version changes only when an asset
    actually did. The cost is a directory walk (stat only, no file reads)
    once per page load — negligible for a static tree this size, but it
    would not scale to a very large one.
    """
    roots = (STATIC_DIR, Path(str(_SHARED_UI)))
    mtimes = [p.stat().st_mtime for root in roots for p in root.rglob("*") if p.is_file()]
    return str(int(max(mtimes))) if mtimes else "0"


@app.get("/")
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__ASSET_V__", _asset_version()))


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------------------------------------------------------- #
# bootstrap
# --------------------------------------------------------------------------- #

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, *, timeout: float = 10.0) -> bool:
    import time as _time

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            try:
                probe.connect(("127.0.0.1", port))
                return True
            except OSError:
                _time.sleep(0.1)
    return False


def _start_server_thread(port: int):
    import threading

    import uvicorn

    errors: list[BaseException] = []

    def _serve():
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    return thread, errors


def _report_startup_failure(port: int, thread, errors: list[BaseException]) -> None:
    if errors:
        detail = f"{type(errors[0]).__name__}: {errors[0]}"
    elif thread.is_alive():
        detail = "No response within 10s, though the server thread is still running."
    else:
        detail = "The server thread exited without ever starting to listen."
    message = (f"OCR Pipeline's local server could not start on port {port}.\n\n"
              f"{detail}\n\n"
              f"Close any other OCR Pipeline window and try again.")
    print(f"ERROR: {message}")
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("OCR Pipeline — server did not start", message)
        root.destroy()
    except Exception:
        pass


def _ensure_std_streams() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


def main() -> None:
    _ensure_std_streams()

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765,
                        help="Port for the local server (default: 8765)")
    args = parser.parse_args()

    port = args.port
    url = f"http://127.0.0.1:{port}"

    server_thread, server_errors = _start_server_thread(port)
    if not _wait_for_server(port):
        _report_startup_failure(port, server_thread, server_errors)
        return

    webbrowser.open(url)
    print(f"OCR Pipeline running at {url}  (Ctrl+C to stop)")
    try:
        server_thread.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
