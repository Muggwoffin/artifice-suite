"""Application shell: tabs, the job runner event pump, and history recording."""

import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from tkinterdnd2 import TkinterDnD

from .. import config
from ..history import HistoryStore
from ..jobs import STAGES, JobItem, JobRunner, State
from . import theme
from .views.analytics_view import AnalyticsView
from .views.history_view import HistoryView
from .views.main_view import MainView
from .views.settings_view import SettingsView
from .widgets.compare_view import CompareView

TITLE = "OCR Pipeline — Historical Document Processor"
WINDOW_SIZE = "1180x860"
POLL_MS = 80


class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(980, 700)
        self.configure(bg=theme.BG)

        config.load_config()
        config.apply_overrides(config.load_user_settings())

        theme.apply(self)

        self.history = HistoryStore()
        self.events: queue.Queue = queue.Queue()
        self.runner: JobRunner | None = None
        self.run_id: int | None = None
        self._run_started_at = 0.0

        self.var_ocr = tk.BooleanVar(value=True)
        self.var_cleanup = tk.BooleanVar(value=True)
        self.var_translate = tk.BooleanVar(value=False)
        self.var_force = tk.BooleanVar(value=False)
        self.output_var = tk.StringVar(value=str(config.get("output_dir") or "output"))

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_MS, self._pump_events)

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=16, pady=(12, 0))
        ttk.Label(header, text="OCR Pipeline", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="local-first  ·  LM Studio + Ollama",
                  style="Dim.TLabel").pack(side=tk.LEFT, padx=(12, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        self.main_view = MainView(self.notebook, self)
        self.preview_view = CompareView(self.notebook)
        self.history_view = HistoryView(self.notebook, self)
        self.analytics_view = AnalyticsView(self.notebook, self)
        self.settings_view = SettingsView(self.notebook, self)

        self.notebook.add(self.main_view, text="Main")
        self.notebook.add(self.preview_view, text="Preview")
        self.notebook.add(self.history_view, text="History")
        self.notebook.add(self.analytics_view, text="Analytics")
        self.notebook.add(self.settings_view, text="Settings")

        self._build_status_bar()

    def _build_status_bar(self):
        bar = tk.Frame(self, bg=theme.ACCENT_DIM)
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(bar, textvariable=self.status_var, font=theme.FONT,
                 bg=theme.ACCENT_DIM, fg=theme.FG, anchor=tk.W,
                 padx=12, pady=4).pack(side=tk.LEFT)

        self.stage_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.stage_var, font=theme.FONT_SMALL,
                 bg=theme.ACCENT_DIM, fg=theme.FG_DIM, anchor=tk.E,
                 padx=12, pady=4).pack(side=tk.RIGHT)

    # --------------------------------------------------------------- running
    def start_run(self, items: list[JobItem] | None = None):
        items = items if items is not None else self.main_view.queue.items
        if not items:
            messagebox.showwarning("No files", "Add at least one document to process.")
            return

        stages = {name for name, var in (
            ("ocr", self.var_ocr),
            ("cleanup", self.var_cleanup),
            ("translate", self.var_translate),
        ) if var.get()}
        if not stages:
            messagebox.showwarning("No stages", "Enable at least one pipeline stage.")
            return

        self.settings_view.apply_to_config()
        output_dir = self.output_var.get() or "output"

        self.run_id = self.history.start_run(
            stages=[s for s in STAGES if s in stages],
            output_dir=output_dir,
            total=len(items),
        )
        self._run_started_at = time.monotonic()
        self._run_items = items

        self.runner = JobRunner(
            items, output_dir,
            stages=stages,
            force=self.var_force.get(),
            events=self.events,
        )
        self.main_view.set_running(True)
        self.main_view.set_progress(0, len(items))
        self.status_var.set(f"Running — 0/{len(items)}")
        self.runner.start()

    def toggle_pause(self):
        if not self.runner or not self.runner.is_running:
            return
        if self.runner.is_paused:
            self.runner.unpause()
            self.main_view.pause_btn.configure(text="⏸  Pause")
        else:
            self.runner.pause()
            self.main_view.pause_btn.configure(text="▶  Resume")

    def cancel_run(self):
        if self.runner and self.runner.is_running:
            self.runner.cancel()
            self.status_var.set("Stopping — waiting for in-flight requests…")

    def skip_item(self, item: JobItem):
        if self.runner and self.runner.is_running:
            self.runner.skip(item)
            self.main_view.log_message(f"[Skip] {item.name} will be skipped", "warning")

    def retry_items(self, items: list[JobItem]):
        if not items:
            return
        if self.runner and self.runner.is_running:
            messagebox.showinfo(
                "Run in progress",
                "Wait for the current run to finish before retrying items.",
            )
            return
        self.main_view.log_message(
            f"Retrying {len(items)} item(s) — completed stages are reused", "accent")
        self.start_run(items)

    # ----------------------------------------------------------- event pump
    def _pump_events(self):
        """Drain runner events on the tk main thread.

        Everything the runner reports arrives here; no worker thread ever
        touches a widget.
        """
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.after(POLL_MS, self._pump_events)

    def _handle_event(self, event):
        kind = event.kind

        if event.message:
            self.main_view.log_message(event.message, event.tag)

        if kind == "run_started":
            self.stage_var.set("")

        elif kind in ("stage_started", "stage_finished", "item_started"):
            self.main_view.queue.refresh(event.item)
            if kind == "stage_started":
                self.main_view.queue.scroll_to(event.item)
                self.stage_var.set(f"{event.stage} · {event.item.name}")

        elif kind == "item_finished":
            self.main_view.queue.refresh(event.item)
            self.main_view.update_counts()
            self._record_item(event.item)
            self._update_progress()
            if self.notebook.index(self.notebook.select()) == 1:
                self.preview_item(event.item)

        elif kind == "paused":
            self.status_var.set("Paused")
        elif kind == "resumed":
            self.status_var.set("Running")

        elif kind == "run_finished":
            self._on_run_finished(event)

    def _update_progress(self):
        items = getattr(self, "_run_items", [])
        finished = sum(
            1 for i in items
            if i.state in (State.DONE, State.FAILED, State.SKIPPED, State.CANCELLED)
        )
        self.main_view.set_progress(finished, len(items))
        self.status_var.set(f"Running — {finished}/{len(items)}")

    def _record_item(self, item: JobItem):
        if self.run_id is None:
            return
        try:
            self.history.record_item(self.run_id, item)
        except Exception as exc:  # history must never break a run
            self.main_view.log_message(f"[History] could not record: {exc}", "warning")

    def _on_run_finished(self, event):
        items = getattr(self, "_run_items", [])
        payload = event.payload
        if self.run_id is not None:
            try:
                self.history.finish_run(
                    self.run_id,
                    succeeded=payload.get("done", 0),
                    failed=payload.get("failed", 0),
                    elapsed=payload.get("elapsed", time.monotonic() - self._run_started_at),
                )
            except Exception as exc:
                self.main_view.log_message(f"[History] could not finalise: {exc}", "warning")

        self.main_view.set_running(False)
        self.main_view.set_progress(len(items), len(items))
        self.main_view.update_counts()
        self.stage_var.set("")
        failed = payload.get("failed", 0)
        self.status_var.set(
            f"Done — {payload.get('done', 0)} ok"
            + (f", {failed} failed" if failed else "")
        )
        self.history_view.refresh()
        self.analytics_view.refresh()
        self.runner = None
        self.run_id = None

    # --------------------------------------------------------------- preview
    def preview_item(self, item: JobItem):
        """Fill the Preview tab from an item's in-memory results."""
        results = item.results
        translated = results.get("translated") or {}
        self.preview_view.show(
            title=f"{item.name}   —   {Path(item.path).parent}",
            raw=(results.get("raw") or {}).get("extracted_text", ""),
            cleaned=(results.get("cleaned") or {}).get("cleaned_text", ""),
            translated=translated.get("translated_text", ""),
            confidence=item.confidence,
            language=item.language,
        )

    def show_in_preview(self, item: JobItem):
        self.preview_item(item)
        self.notebook.select(1)

    def open_output_folder(self, item: JobItem):
        target = Path(self.output_var.get() or "output").resolve()
        if not target.exists():
            messagebox.showinfo("Not found", f"No output directory at {target}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(target)  # noqa: S606 — user-initiated
            elif sys.platform == "darwin":
                subprocess.run(["open", str(target)], check=False)
            else:
                subprocess.run(["xdg-open", str(target)], check=False)
        except Exception as exc:
            messagebox.showerror("Could not open folder", str(exc))

    # ----------------------------------------------------------------- close
    def _on_close(self):
        if self.runner and self.runner.is_running:
            if not messagebox.askyesno(
                "Quit", "A run is still in progress. Stop it and quit?"
            ):
                return
            self.runner.cancel()
        try:
            config.save_user_settings(self.settings_view.collect())
            self.history.close()
        finally:
            self.destroy()


def main():
    App().mainloop()
