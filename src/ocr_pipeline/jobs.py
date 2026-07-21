"""Job runner: per-file pipeline execution with live status, pause and skip.

The runner owns the threading; it knows nothing about tkinter. Progress is
published as :class:`JobEvent` objects on a ``queue.Queue`` which the caller
drains at its own pace (the GUI polls it from the tk main loop).

Retry is deliberately *not* handled here — a retry is simply a fresh runner
over the selected items. Because completed stages leave outputs on disk,
``resume`` makes the retry pick up where the failure happened.
"""

import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ._logging import get_logger
from .config import get as cfg
from .pipeline import run_cleanup_step, run_ocr_step, run_translate_step

log = get_logger("jobs")

STAGES = ("ocr", "cleanup", "translate")

STAGE_LABELS = {
    "ocr": "OCR",
    "cleanup": "Cleanup",
    "translate": "Translate",
}


class State(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StageStatus:
    state: State = State.PENDING
    elapsed: float = 0.0
    chars: int = 0
    error: str = ""


@dataclass
class JobItem:
    """One file moving through the pipeline."""

    path: str
    stages: dict[str, StageStatus] = field(default_factory=dict)
    state: State = State.PENDING
    confidence: int | None = None
    language: str = ""
    attempts: int = 0
    results: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def __post_init__(self):
        if not self.stages:
            self.stages = {s: StageStatus() for s in STAGES}

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def stem(self) -> str:
        return Path(self.path).stem

    @property
    def elapsed(self) -> float:
        return sum(s.elapsed for s in self.stages.values())

    def reset(self, enabled_stages: set[str]) -> None:
        """Prepare for a (re)run, clearing prior state."""
        self.state = State.PENDING
        self.error = ""
        self.results = {}
        self.confidence = None
        self.language = ""
        for name, status in self.stages.items():
            status.state = State.PENDING if name in enabled_stages else State.SKIPPED
            status.elapsed = 0.0
            status.chars = 0
            status.error = ""


@dataclass
class JobEvent:
    """Something the runner wants the UI to know about."""

    kind: str  # run_started | item_started | stage_started | stage_finished
    #            item_finished | run_finished | paused | resumed | log
    item: JobItem | None = None
    stage: str = ""
    message: str = ""
    tag: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class JobRunner:
    """Runs a batch of :class:`JobItem` through the pipeline.

    OCR runs concurrently across ``max_workers``; cleanup and translate run
    serially behind it, mirroring :func:`pipeline.run_pipeline_batch` so both
    entry points behave identically.
    """

    def __init__(
        self,
        items: list[JobItem],
        output_dir: str,
        *,
        stages: set[str],
        force: bool = False,
        events: queue.Queue | None = None,
        max_workers: int | None = None,
    ):
        self.items = items
        self.output_dir = output_dir
        self.stages = set(stages)
        self.force = force
        self.events: queue.Queue = events or queue.Queue()
        self.max_workers = max_workers or cfg("max_ocr_workers")

        self._resume_gate = threading.Event()
        self._resume_gate.set()
        self._cancelled = False
        self._skip_ids: set[int] = set()
        self._thread: threading.Thread | None = None
        self._downstream: queue.Queue = queue.Queue()

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        for item in self.items:
            item.reset(self.stages)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_paused(self) -> bool:
        return not self._resume_gate.is_set()

    def pause(self) -> None:
        """Pause between stages. An in-flight model call is allowed to finish."""
        if not self.is_paused:
            self._resume_gate.clear()
            self._emit("paused", message="Paused — finishing in-flight requests")

    def unpause(self) -> None:
        if self.is_paused:
            self._resume_gate.set()
            self._emit("resumed", message="Resumed")

    def cancel(self) -> None:
        self._cancelled = True
        self._resume_gate.set()  # release anything blocked at the gate

    def skip(self, item: JobItem) -> None:
        """Skip an item that has not finished yet."""
        self._skip_ids.add(id(item))

    # ---------------------------------------------------------------- events
    def _emit(self, kind: str, **kwargs) -> None:
        self.events.put(JobEvent(kind=kind, **kwargs))

    def _gate(self) -> bool:
        """Block while paused. Returns False if the run was cancelled."""
        self._resume_gate.wait()
        return not self._cancelled

    def _should_skip(self, item: JobItem) -> bool:
        return self._cancelled or id(item) in self._skip_ids

    # ------------------------------------------------------------------- run
    def _run(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        t0 = time.monotonic()
        self._emit(
            "run_started",
            message=f"Pipeline start — {len(self.items)} file(s), "
                    f"stages: {', '.join(s for s in STAGES if s in self.stages)}",
            tag="accent",
        )

        consumer = threading.Thread(target=self._downstream_loop, daemon=True)
        consumer.start()

        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                for item in self.items:
                    pool.submit(self._ocr_worker, item)
        finally:
            self._downstream.put(None)
            consumer.join()

        elapsed = time.monotonic() - t0
        done = sum(1 for i in self.items if i.state is State.DONE)
        failed = sum(1 for i in self.items if i.state is State.FAILED)
        self._emit(
            "run_finished",
            message=f"Run finished in {elapsed:.1f}s — {done} ok, {failed} failed",
            tag="success" if not failed else "warning",
            payload={"elapsed": elapsed, "done": done, "failed": failed},
        )

    # ------------------------------------------------------------ OCR phase
    def _ocr_worker(self, item: JobItem) -> None:
        if self._should_skip(item) or not self._gate():
            self._finish_item(item, State.CANCELLED if self._cancelled else State.SKIPPED)
            return

        item.state = State.RUNNING
        item.attempts += 1
        self._emit("item_started", item=item)

        raw = self._run_stage(
            item, "ocr",
            lambda: run_ocr_step(
                item.path, self.output_dir,
                skip_ocr="ocr" not in self.stages,
                resume=self._resume_enabled,
                force=self.force,
            ),
            chars_key="extracted_text",
        )
        if raw is None:
            self._finish_item(item, State.FAILED)
            return

        item.results["raw"] = raw
        self._downstream.put(item)

    # ----------------------------------------------- cleanup/translate phase
    def _downstream_loop(self) -> None:
        while True:
            item = self._downstream.get()
            if item is None:
                return
            self._process_downstream(item)

    def _process_downstream(self, item: JobItem) -> None:
        if self._should_skip(item) or not self._gate():
            self._finish_item(item, State.CANCELLED if self._cancelled else State.SKIPPED)
            return

        raw = item.results["raw"]
        cleaned = self._run_stage(
            item, "cleanup",
            lambda: run_cleanup_step(
                raw, item.stem, self.output_dir,
                skip_cleanup="cleanup" not in self.stages,
                resume=self._resume_enabled,
                force=self.force,
            ),
            chars_key="cleaned_text",
        )
        if cleaned is None:
            self._finish_item(item, State.FAILED)
            return
        item.results["cleaned"] = cleaned

        if "translate" in self.stages:
            if self._should_skip(item) or not self._gate():
                self._finish_item(item, State.CANCELLED if self._cancelled else State.SKIPPED)
                return

            translated = self._run_stage(
                item, "translate",
                lambda: run_translate_step(
                    cleaned, item.stem, self.output_dir,
                    resume=self._resume_enabled,
                    force=self.force,
                ),
                chars_key="translated_text",
            )
            if translated is None:
                self._finish_item(item, State.FAILED)
                return
            item.results["translated"] = translated
            item.language = translated.get("source_language_name", "")
            conf = translated.get("confidence") or {}
            item.confidence = conf.get("overall_score")

        self._finish_item(item, State.DONE)

    # --------------------------------------------------------------- helpers
    @property
    def _resume_enabled(self) -> bool:
        return bool(cfg("resume")) and not self.force

    def _run_stage(self, item: JobItem, stage: str, fn, *, chars_key: str) -> dict | None:
        """Run one stage, updating status and emitting events. None on failure."""
        status = item.stages[stage]
        status.state = State.RUNNING
        self._emit("stage_started", item=item, stage=stage)

        try:
            data = fn()
        except Exception as exc:
            status.state = State.FAILED
            status.error = f"{exc.__class__.__name__}: {exc}"
            item.error = status.error
            log.warning("%s failed for %s: %s", STAGE_LABELS[stage], item.name, exc)
            self._emit(
                "stage_finished", item=item, stage=stage,
                message=f"[{STAGE_LABELS[stage]}] {item.name} — {status.error}",
                tag="error",
            )
            return None

        status.elapsed = data.get("_elapsed", 0.0)
        status.chars = len(data.get(chars_key) or "")
        skipped = data.get("_skipped", False)
        status.state = State.SKIPPED if skipped else State.DONE

        suffix = " [skipped]" if skipped else f" -> {status.chars} chars ({status.elapsed:.1f}s)"
        self._emit(
            "stage_finished", item=item, stage=stage,
            message=f"[{STAGE_LABELS[stage]}] {item.name}{suffix}",
            tag="warning" if skipped else "success",
        )
        return data

    def _finish_item(self, item: JobItem, state: State) -> None:
        item.state = state
        for status in item.stages.values():
            if status.state in (State.PENDING, State.RUNNING):
                status.state = State.SKIPPED if state is not State.FAILED else State.PENDING
        self._emit("item_finished", item=item, payload={"state": state.value})
