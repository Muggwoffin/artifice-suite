# SPDX-FileCopyrightText: 2026 Maurice Casey
#
# SPDX-License-Identifier: MIT

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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _leaked_outside(upload_dir: Path) -> bool:
    """True if any file was written outside the upload directory."""
    upload = upload_dir.resolve()
    for entry in upload.parent.rglob("*"):
        if entry.is_file() and upload not in entry.resolve().parents:
            # Ignore the test database created by the conftest fixture.
            if entry.suffix == ".db":
                continue
            return True
    return False


# ── Path traversal defences ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "malicious_filename,expected_status,description",
    [
        ("../../etc/passwd", 202, "dot-dot-slash is stripped to safe name"),
        ("..", 400, "bare dot-dot is rejected outright"),
        ("/etc/passwd", 202, "absolute path is stripped to safe name"),
        ("..\\..\\windows\\system32", 202, "backslash traversal is stripped to safe name"),
        ("", 422, "empty filename is rejected by FastAPI validation"),
    ],
)
async def test_transcribe_traversal_sanitisation(
    api, malicious_filename, expected_status, description
):
    """Malicious filenames are either rejected or safely stripped to their
    base name, and the written file stays inside the upload directory."""
    resp = await api.client.post(
        "/api/v1/transcribe",
        files={"file": (malicious_filename, b"fake-audio-data")},
    )
    assert resp.status_code == expected_status, (
        f"Expected {expected_status} for {description}, got {resp.status_code}"
    )
    assert not _leaked_outside(api.upload_dir), (
        f"No files should exist outside upload_dir after {description}"
    )


@pytest.mark.parametrize(
    "name,fname,expected_status,description",
    [
        # Traversal via name is stripped to safe component -> accepted
        ("../../etc", "harmless.wav", 200, "traversal name stripped, file is safe"),
        # Traversal via filename with benign name -> accepted
        ("alice", "../../etc/passwd", 200, "traversal filename stripped, file is safe"),
        # Both fields bare dot-dot -> rejected
        ("..", "..", 400, "both fields are bare dot-dot -> rejected"),
        # Both fields empty -> rejected by FastAPI validation
        ("", "", 422, "both fields empty -> rejected"),
    ],
)
async def test_enroll_traversal_sanitisation(
    api, name, fname, expected_status, description
):
    # Prevent the diarization model download (needs HF token) from
    # interfering with the sanitisation test.
    from unittest.mock import MagicMock, patch

    fake_embedding = MagicMock()
    fake_inference_cls = MagicMock(return_value=MagicMock(return_value=fake_embedding))
    fake_engine = MagicMock()
    fake_engine._diarize_model.model._embedding = MagicMock()

    with (
        patch("pyannote.audio.Inference", fake_inference_cls),
        patch(
            "artifice_transcribe.api.v1.routes._get_engine",
            return_value=fake_engine,
        ),
        patch(
            "artifice_transcribe.api.v1.routes.pack_embedding",
            return_value=b"\x00" * 2048,
        ),
    ):
        resp = await api.client.post(
            "/api/v1/speakers/enroll",
            data={"name": name},
            files={"file": (fname, b"fake-audio")},
        )
    assert resp.status_code == expected_status, (
        f"Expected {expected_status} for {description}, got {resp.status_code}"
    )
    assert not _leaked_outside(api.upload_dir), (
        f"No files should exist outside upload_dir after {description}"
    )


async def test_transcribe_sanitised_filename_written_inside_upload_dir(api):
    """A harmless filename must still round-trip correctly."""
    resp = await api.client.post(
        "/api/v1/transcribe",
        files={"file": ("interview.wav", b"fake-audio-data")},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    written = api.upload_dir / f"{job_id}_interview.wav"
    assert written.exists()
    assert written.read_bytes() == b"fake-audio-data"


# ── Size limit ───────────────────────────────────────────────────────────────


async def test_enroll_rejects_oversized_upload(api, monkeypatch):
    """The enrollment endpoint must enforce the same max_upload_size as /transcribe."""
    monkeypatch.setattr(
        "artifice_transcribe.api.v1.routes.settings.max_upload_size", 10
    )
    resp = await api.client.post(
        "/api/v1/speakers/enroll",
        data={"name": "speaker"},
        files={"file": ("voice.wav", b"x" * 11)},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


async def test_transcribe_rejects_oversized_upload(api, monkeypatch):
    """The /transcribe endpoint must reject uploads larger than max_upload_size."""
    monkeypatch.setattr(
        "artifice_transcribe.api.v1.routes.settings.max_upload_size", 10
    )
    resp = await api.client.post(
        "/api/v1/transcribe",
        files={"file": ("interview.wav", b"x" * 11)},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()
