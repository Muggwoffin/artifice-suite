from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from artifice_transcribe.db.models import JobStatus, SpeakerMapping, TranscriptionJob

pytestmark = pytest.mark.asyncio


async def _make_job(
    api, job_id: str, filename: str, *, status=JobStatus.completed, created_at=None
):
    async with api.session_factory() as db:
        db.add(
            TranscriptionJob(
                id=job_id,
                filename=filename,
                status=status,
                progress_percentage=100.0 if status == JobStatus.completed else 0.0,
                created_at=created_at or datetime.now(timezone.utc),
            )
        )
        await db.commit()


# --------------------------------------------------------------- GET /jobs


async def test_list_jobs_empty(api):
    resp = await api.client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_jobs_newest_first(api):
    now = datetime.now(timezone.utc)
    await _make_job(api, "job-older", "older.wav", created_at=now - timedelta(minutes=5))
    await _make_job(api, "job-newer", "newer.wav", created_at=now)

    resp = await api.client.get("/api/v1/jobs")
    assert resp.status_code == 200
    ids = [j["id"] for j in resp.json()]
    assert ids == ["job-newer", "job-older"]


# ------------------------------------------------------------ GET .../audio


async def test_get_audio_streams_file(api):
    await _make_job(api, "job-1", "clip.wav")
    audio_path = api.upload_dir / "job-1_clip.wav"
    audio_path.write_bytes(b"RIFF....WAVEfmt ")

    resp = await api.client.get("/api/v1/jobs/job-1/audio")
    assert resp.status_code == 200
    assert resp.content == b"RIFF....WAVEfmt "


async def test_get_audio_404_missing_job(api):
    resp = await api.client.get("/api/v1/jobs/nonexistent/audio")
    assert resp.status_code == 404


async def test_get_audio_404_missing_file_on_disk(api):
    await _make_job(api, "job-no-file", "ghost.wav")
    resp = await api.client.get("/api/v1/jobs/job-no-file/audio")
    assert resp.status_code == 404


# ---------------------------------------------------------- GET .../speakers


async def test_get_speakers_empty(api):
    await _make_job(api, "job-2", "clip2.wav")
    resp = await api.client.get("/api/v1/jobs/job-2/speakers")
    assert resp.status_code == 200
    assert resp.json() == {"job_id": "job-2", "speakers": []}


async def test_get_speakers_reflects_mappings(api):
    await _make_job(api, "job-3", "clip3.wav")
    async with api.session_factory() as db:
        db.add(SpeakerMapping(job_id="job-3", speaker_label="SPEAKER_00", custom_name="Alice"))
        await db.commit()

    resp = await api.client.get("/api/v1/jobs/job-3/speakers")
    assert resp.status_code == 200
    assert resp.json()["speakers"] == [{"speaker_label": "SPEAKER_00", "custom_name": "Alice"}]


async def test_get_speakers_reflects_patch(api):
    await _make_job(api, "job-4", "clip4.wav")
    await api.client.patch(
        "/api/v1/jobs/job-4/speakers",
        json={"speakers": [{"speaker_label": "SPEAKER_00", "custom_name": "Bob"}]},
    )

    resp = await api.client.get("/api/v1/jobs/job-4/speakers")
    assert resp.json()["speakers"] == [{"speaker_label": "SPEAKER_00", "custom_name": "Bob"}]


async def test_get_speakers_404_missing_job(api):
    resp = await api.client.get("/api/v1/jobs/nonexistent/speakers")
    assert resp.status_code == 404
