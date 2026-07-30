# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

"""Adapter between the ArtificeDraft pipeline and the FastAPI web layer.

One `RunState` instance per server process — a local tool run by one person on
their own machine does not need per-session isolation, same rationale the OCR
Pipeline tool's `web/runtime.py` documents for its own `RunState`.

A document moves through: uploaded -> running -> awaiting_review (only if
`enable_review`) -> done, or -> error at any point. The existing CLI review
loop (`src/review.py`'s `cli_review`) blocks on `input()`, which cannot work
inside a web server request — there is no terminal attached. The web review
step replaces it with an explicit two-phase flow: the background thread stops
at `awaiting_review` and waits for `submit_review()` to be called from a
second request once the browser has shown the user every suggested change.
"""

from __future__ import annotations

import json
import logging
import queue
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from artifice_draft._diff import diff_ranges
from artifice_draft.changelog import format_change_log, generate_change_summary
from artifice_draft.config import AppConfig
from artifice_draft.doc_parser import parse_docx
from artifice_draft.doc_writer import apply_edits
from artifice_draft.llm_client import LLMEdit, call_ollama
from artifice_draft.models import (
    EditingStyle,
    ExportFormat,
    LLMProvider,
    PipelineProgress,
    ReviewDecision,
)
from artifice_draft.review import apply_decisions, create_review_items

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path.home() / ".artifice_draft" / "web_settings.json"
_WORK_DIR = Path(tempfile.gettempdir()) / "artifice_draft_web"

_EXT_MAP = {
    ExportFormat.DOCX_TRACK_CHANGES: "_edited.docx",
    ExportFormat.DOCX_PLAIN: "_edited.docx",
    ExportFormat.MARKDOWN: "_edited.md",
    ExportFormat.HTML: "_edited.html",
    ExportFormat.PLAIN_TEXT: "_edited.txt",
}


# --------------------------------------------------------------------------- #
# settings — persisted as JSON at ~/.artifice_draft/web_settings.json.
# Includes api_key alongside non-secret preferences; the file is protected
# by OS-level access controls (POSIX 0o600 / Windows restricted ACL).
# --------------------------------------------------------------------------- #

def load_settings() -> dict:
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(patch: dict) -> dict:
    """Merge `patch` into the persisted settings file — never replace it whole.

    A prior project in this same family (OCR Pipeline) shipped a replace-not-
    merge settings save that silently dropped every other saved key the first
    time the web UI wrote just one field. Don't repeat that here.
    """
    from secure_io import restrict_to_current_user, write_private_json

    current = load_settings()
    current.update(patch)
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_private_json(_SETTINGS_PATH, current)
    restrict_to_current_user(_SETTINGS_PATH)
    return current


def config_from_settings() -> AppConfig:
    """Build an AppConfig from environment variables, then apply saved web
    settings on top — mirrors AppConfig.from_env()'s own precedence, just with
    a second, browser-editable layer for the fields that aren't secrets."""
    cfg = AppConfig.from_env()
    saved = load_settings()

    if "base_url" in saved:
        cfg.base_url = saved["base_url"]
    if "api_key" in saved:
        cfg.api_key = saved["api_key"]
    if "model_name" in saved:
        cfg.model_name = saved["model_name"]
    if "vision_enabled" in saved:
        cfg.vision_enabled = bool(saved["vision_enabled"])
    if v := saved.get("llm_provider"):
        try:
            cfg.llm_provider = LLMProvider(v)
        except ValueError:
            pass
    if v := saved.get("editing_style"):
        try:
            cfg.editing_style = EditingStyle(v)
        except ValueError:
            pass
    if "custom_system_prompt" in saved:
        cfg.custom_system_prompt = saved["custom_system_prompt"]
    if "style_guide" in saved:
        cfg.style_guide = saved["style_guide"]
    if v := saved.get("export_format"):
        try:
            cfg.export_format = ExportFormat(v)
        except ValueError:
            pass
    if "batch_size" in saved:
        try:
            cfg.batch_size = int(saved["batch_size"])
        except (TypeError, ValueError):
            pass
    if "temperature" in saved:
        try:
            cfg.temperature = float(saved["temperature"])
        except (TypeError, ValueError):
            pass
    if "enable_review" in saved:
        cfg.enable_review = bool(saved["enable_review"])
    if "author_name" in saved:
        cfg.author_name = saved["author_name"]

    return cfg


def serialize_settings(cfg: AppConfig) -> dict:
    from artifice_draft.style_guides import list_guides
    return {
        "llm_provider": cfg.llm_provider.value,
        "editing_style": cfg.editing_style.value,
        "custom_system_prompt": cfg.custom_system_prompt,
        "style_guide": cfg.style_guide,
        "export_format": cfg.export_format.value,
        "batch_size": cfg.batch_size,
        "temperature": cfg.temperature,
        "enable_review": cfg.enable_review,
        "author_name": cfg.author_name,
        "active_model": cfg.active_model,
        "base_url": cfg.base_url,
        "api_key": cfg.api_key,
        "model_name": cfg.model_name,
        "vision_enabled": cfg.vision_enabled,
        "providers": [p.value for p in LLMProvider],
        "styles": [s.value for s in EditingStyle],
        "export_formats": [f.value for f in ExportFormat],
        "style_guides": list_guides(),
    }


# --------------------------------------------------------------------------- #
# per-document state
# --------------------------------------------------------------------------- #

@dataclass
class DocState:
    doc_id: str
    path: Path
    paragraphs: list[dict]
    cfg: AppConfig | None = None
    edits: list[LLMEdit] = field(default_factory=list)
    review_items: list[dict] = field(default_factory=list)
    output_path: Path | None = None
    summary_text: str = ""
    events: queue.Queue = field(default_factory=queue.Queue)
    thread: threading.Thread | None = None
    error: str | None = None
    stage: str = "uploaded"  # uploaded -> running -> awaiting_review -> done -> error
    session_id: str = ""

    def __post_init__(self):
        import uuid
        if not self.session_id:
            self.session_id = f"{self.doc_id}-{uuid.uuid4().hex[:8]}"


def serialize_progress(p: PipelineProgress) -> dict:
    return {
        "stage": p.stage,
        "current": p.current_paragraph,
        "total": p.total_paragraphs,
        "message": p.message,
        "percentage": round(p.percentage, 1),
        "error": p.error,
    }


def serialize_status(doc: DocState) -> dict:
    return {
        "doc_id": doc.doc_id,
        "filename": doc.path.name,
        "paragraph_count": len(doc.paragraphs),
        "stage": doc.stage,
        "error": doc.error,
        "review_enabled": bool(doc.cfg.enable_review) if doc.cfg else False,
        "output_filename": doc.output_path.name if doc.output_path else None,
        "summary": doc.summary_text or None,
    }


def serialize_review_items(doc: DocState) -> list[dict]:
    """Review items for the browser, changed paragraphs only.

    `create_review_items()` returns one entry per paragraph, including every
    unchanged one — fine for `apply_decisions()`, which needs the full set,
    but the wrong thing to show a human: `cli_review()` filters down to
    `edited_text and edited_text != original_text` before displaying anything,
    and the web review screen follows the same rule for the same reason (no
    one wants to page through hundreds of "no change" cards). Paragraphs left
    out here simply have no decision recorded for them, which
    `apply_decisions()` already treats as "keep the model's output as-is" —
    exactly correct, since that's a no-op for anything actually unchanged.
    """
    out = []
    for item in doc.review_items:
        orig = item["original_text"]
        edited = item["edited_text"]
        if not edited or edited == orig:
            continue
        orig_ranges, edit_ranges = diff_ranges(orig, edited)
        out.append({
            "paragraph_index": item["paragraph_index"],
            "original_text": orig,
            "edited_text": edited,
            "status": item["status"],
            "approved": item["approved"],
            "diff": {"original_ranges": orig_ranges, "edited_ranges": edit_ranges},
        })
    return out


class RunState:
    """Every uploaded document this server process currently knows about."""

    def __init__(self):
        self._docs: dict[str, DocState] = {}
        self._lock = threading.Lock()

    def add_document(self, filename: str, data: bytes) -> DocState:
        doc_id = uuid.uuid4().hex[:12]
        doc_dir = _WORK_DIR / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        path = doc_dir / Path(filename).name
        path.write_bytes(data)

        paragraphs = parse_docx(str(path))
        doc = DocState(doc_id=doc_id, path=path, paragraphs=paragraphs)
        with self._lock:
            self._docs[doc_id] = doc
        return doc

    def get(self, doc_id: str) -> DocState | None:
        return self._docs.get(doc_id)

    def start_run(self, doc_id: str) -> DocState:
        doc = self.get(doc_id)
        if doc is None:
            raise KeyError(doc_id)
        if doc.thread is not None and doc.thread.is_alive():
            raise RuntimeError("This document is already being processed")
        if not doc.paragraphs:
            raise ValueError("No content found in the document")

        cfg = config_from_settings()
        doc.cfg = cfg
        doc.stage = "running"
        doc.error = None

        def _worker():
            try:
                def on_progress(p: PipelineProgress) -> None:
                    doc.events.put(p)

                doc.edits = call_ollama(
                    paragraphs=doc.paragraphs,
                    batch_size=cfg.batch_size,
                    config=cfg,
                    on_progress=on_progress,
                )

                if cfg.enable_review:
                    doc.review_items = create_review_items(doc.edits, doc.paragraphs)
                    doc.stage = "awaiting_review"
                    doc.events.put(PipelineProgress(
                        total_paragraphs=len(doc.paragraphs),
                        current_paragraph=len(doc.paragraphs),
                        stage="awaiting_review", percentage=100.0,
                        message="LLM processing complete — awaiting review",
                    ))
                else:
                    self._finalize(doc, decisions=None)
            except Exception as exc:  # noqa: BLE001 — reported to the client, not swallowed
                logger.exception("Run failed for %s", doc_id)
                doc.error = str(exc)
                doc.stage = "error"
                doc.events.put(PipelineProgress(
                    stage="error", error=str(exc), message=f"Error: {exc}",
                ))

        doc.thread = threading.Thread(target=_worker, daemon=True)
        doc.thread.start()
        return doc

    def submit_review(self, doc_id: str, decisions_payload: list[dict]) -> DocState:
        doc = self.get(doc_id)
        if doc is None:
            raise KeyError(doc_id)
        if doc.stage != "awaiting_review":
            raise RuntimeError(f"Document is not awaiting review (stage={doc.stage})")

        decisions = [
            ReviewDecision(
                paragraph_index=d["paragraph_index"],
                approved=d["approved"],
                replacement_text=d.get("replacement_text"),
            )
            for d in decisions_payload
        ]
        self._finalize(doc, decisions=decisions)
        return doc

    def _finalize(self, doc: DocState, *, decisions: list[ReviewDecision] | None) -> None:
        cfg = doc.cfg or config_from_settings()

        if decisions is not None:
            edits_dict = apply_decisions(doc.edits, decisions)
        else:
            edits_dict = LLMEdit.to_edits_dict(doc.edits)

        summary = generate_change_summary(doc.edits, doc.paragraphs)
        doc.summary_text = format_change_log(summary)

        base = str(doc.path.with_suffix(""))
        suffix = _EXT_MAP.get(cfg.export_format, "_edited.docx")
        output_path = base + suffix
        if Path(output_path).exists():
            output_path = base + "_2" + suffix

        actual_path = apply_edits(
            input_path=str(doc.path),
            paragraphs=doc.paragraphs,
            edits=edits_dict,
            output_path=output_path,
            export_format=cfg.export_format,
            author=cfg.author_name,
        )
        doc.output_path = Path(actual_path)
        doc.stage = "done"
        doc.events.put(PipelineProgress(
            stage="done", percentage=100.0,
            message=f"Done — saved to {doc.output_path.name}",
        ))


state = RunState()
