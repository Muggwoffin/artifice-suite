from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from artifice_transcribe.config import settings
from artifice_transcribe.db.models import Base
from artifice_transcribe.db.session import get_db
from artifice_transcribe.main import app


@dataclass
class ApiFixture:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]
    upload_dir: Path


@pytest_asyncio.fixture
async def api(tmp_path, monkeypatch):
    """An AsyncClient + DB session factory wired to an isolated sqlite file
    and upload dir per test.

    Overrides `get_db` directly rather than touching `settings.database_url`,
    since the real engine is already bound to that URL at import time.
    """
    db_path = tmp_path / "test.db"
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    test_session = async_sessionmaker(test_engine, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ApiFixture(client=ac, session_factory=test_session, upload_dir=upload_dir)

    app.dependency_overrides.clear()
    await test_engine.dispose()
