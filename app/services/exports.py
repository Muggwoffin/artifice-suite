from __future__ import annotations

import json
from io import StringIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SpeakerMapping, TranscriptSegment


def _fmt_ts_srt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_ts_vtt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


async def _load_data(
    db: AsyncSession, job_id: str
) -> tuple[list[TranscriptSegment], dict[str, str]]:
    segs = (
        (
            await db.execute(
                select(TranscriptSegment)
                .where(TranscriptSegment.job_id == job_id)
                .order_by(TranscriptSegment.start_time)
            )
        )
        .scalars()
        .all()
    )

    mappings = (
        (await db.execute(select(SpeakerMapping).where(SpeakerMapping.job_id == job_id)))
        .scalars()
        .all()
    )
    name_map = {m.speaker_label: m.custom_name for m in mappings}

    return list(segs), name_map


def _speaker_name(label: str, name_map: dict[str, str]) -> str:
    return name_map.get(label, label)


async def export_json(db: AsyncSession, job_id: str) -> str:
    segs, name_map = await _load_data(db, job_id)
    data = [
        {
            "speaker": _speaker_name(s.speaker_label, name_map),
            "speaker_label": s.speaker_label,
            "start": round(s.start_time, 3),
            "end": round(s.end_time, 3),
            "text": s.text,
        }
        for s in segs
    ]
    return json.dumps({"job_id": job_id, "segments": data}, indent=2, ensure_ascii=False)


async def export_srt(db: AsyncSession, job_id: str) -> str:
    segs, name_map = await _load_data(db, job_id)
    buf = StringIO()
    for i, s in enumerate(segs, 1):
        buf.write(f"{i}\n")
        buf.write(f"{_fmt_ts_srt(s.start_time)} --> {_fmt_ts_srt(s.end_time)}\n")
        buf.write(f"[{_speaker_name(s.speaker_label, name_map)}] {s.text}\n\n")
    return buf.getvalue()


async def export_vtt(db: AsyncSession, job_id: str) -> str:
    segs, name_map = await _load_data(db, job_id)
    buf = StringIO()
    buf.write("WEBVTT\n\n")
    for i, s in enumerate(segs, 1):
        buf.write(f"{i}\n")
        buf.write(f"{_fmt_ts_vtt(s.start_time)} --> {_fmt_ts_vtt(s.end_time)}\n")
        buf.write(f"[{_speaker_name(s.speaker_label, name_map)}] {s.text}\n\n")
    return buf.getvalue()


async def export_txt(db: AsyncSession, job_id: str) -> str:
    segs, name_map = await _load_data(db, job_id)
    buf = StringIO()
    current_speaker = None
    for s in segs:
        name = _speaker_name(s.speaker_label, name_map)
        if name != current_speaker:
            current_speaker = name
            buf.write(f"\n[{name}]\n")
        buf.write(f"{s.text} ")
    return buf.getvalue().strip() + "\n"


async def export_md(db: AsyncSession, job_id: str) -> str:
    segs, name_map = await _load_data(db, job_id)
    buf = StringIO()
    buf.write(f"# Transcript — {job_id}\n\n")
    current_speaker = None
    for s in segs:
        name = _speaker_name(s.speaker_label, name_map)
        if name != current_speaker:
            current_speaker = name
            buf.write(f"\n**{name}**\n\n")
        buf.write(f"{s.text}\n\n")
    return buf.getvalue()


async def export_pdf(db: AsyncSession, job_id: str) -> bytes:
    from fpdf import FPDF

    segs, name_map = await _load_data(db, job_id)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Transcript — {job_id}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    current_speaker = None
    for s in segs:
        name = _speaker_name(s.speaker_label, name_map)
        if name != current_speaker:
            current_speaker = name
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 7, name, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, s.text)
        pdf.ln(2)

    return bytes(pdf.output())
