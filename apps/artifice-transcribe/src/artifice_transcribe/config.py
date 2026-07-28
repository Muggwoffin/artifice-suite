from __future__ import annotations

import logging
import shutil
from pathlib import Path

from platformdirs import user_data_dir
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ── Per-user data directory (uses platformdirs to resolve the canonical path) ──
_USER_DATA_PATH = Path(user_data_dir("artifice-transcribe", "ArtificeSuite", ensure_exists=True))
_DEFAULT_DB_PATH = _USER_DATA_PATH / "transcribe.db"
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{_DEFAULT_DB_PATH}"
_LEGACY_DB_PATH = Path("./data/transcribe.db").resolve()

_DEFAULT_UPLOAD_PATH = _USER_DATA_PATH / "uploads"
_LEGACY_UPLOAD_PATH = Path("./uploads").resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    hf_token: str = ""
    database_url: str = _DEFAULT_DB_URL
    upload_dir: str = str(_DEFAULT_UPLOAD_PATH)
    whisper_model: str = "base"
    device: str = "auto"
    max_upload_size: int = 524_288_000  # 500 MB

    # Model selection and configuration
    default_whisper_model: str = "base"
    default_device: str = "auto"
    default_hf_token: str = ""
    diarization_provider: str = "pyannote"
    diarization_model: str = "pyannote/speaker-diarization-3.0"
    enable_alignment_model_cache: bool = True

    def model_post_init(self, __context: object) -> None:
        """Run after field population — handles legacy data migration."""
        self._migrate_legacy_db()
        self._migrate_legacy_uploads()

    def _migrate_legacy_db(self) -> None:
        """Move a legacy ``./data/transcribe.db`` to the platform data directory.

        Only runs when ``database_url`` was *not* overridden by the user
        (i.e. when it still equals the computed default).  A user-set
        ``DATABASE_URL`` is left untouched.
        """
        if self.database_url != _DEFAULT_DB_URL:
            return  # User pointed the database elsewhere — do not relocate

        if _DEFAULT_DB_PATH.exists():
            if _LEGACY_DB_PATH.exists():
                logger.warning(
                    "Legacy database found at %s but database already exists at %s. "
                    "Using the existing database. To recover data from the legacy "
                    "file, copy it manually to the new location.",
                    _LEGACY_DB_PATH,
                    _DEFAULT_DB_PATH,
                )
            return

        if _LEGACY_DB_PATH.exists():
            logger.info("Migrating legacy database from %s to %s", _LEGACY_DB_PATH, _DEFAULT_DB_PATH)
            _DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(_LEGACY_DB_PATH), str(_DEFAULT_DB_PATH))
            logger.info("Migration complete — database is now at %s", _DEFAULT_DB_PATH)

    def _migrate_legacy_uploads(self) -> None:
        """Move files from a legacy ``./uploads/`` directory to the platform
        data directory.

        Only runs when ``upload_dir`` was *not* overridden by the user
        (i.e. when it still equals the computed default).  A user-set
        ``UPLOAD_DIR`` is left untouched.
        """
        if self.upload_dir != str(_DEFAULT_UPLOAD_PATH):
            return  # User pointed uploads elsewhere — do not relocate

        default_exists = _DEFAULT_UPLOAD_PATH.exists() and any(_DEFAULT_UPLOAD_PATH.iterdir())
        legacy_exists = _LEGACY_UPLOAD_PATH.exists()
        legacy_files = (
            [f for f in _LEGACY_UPLOAD_PATH.iterdir() if f.is_file()]
            if legacy_exists
            else []
        )

        if default_exists:
            if legacy_files:
                logger.warning(
                    "Legacy upload directory found at %s but uploads already exist at %s. "
                    "Using the existing upload directory. To recover data from the legacy "
                    "directory, copy files manually to the new location.",
                    _LEGACY_UPLOAD_PATH,
                    _DEFAULT_UPLOAD_PATH,
                )
            return

        if not legacy_files:
            # Empty or absent — nothing to migrate.
            # Clean up an empty legacy directory silently.
            if legacy_exists:
                try:
                    _LEGACY_UPLOAD_PATH.rmdir()
                except OSError:
                    pass
            return

        _DEFAULT_UPLOAD_PATH.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Migrating legacy uploads from %s to %s",
            _LEGACY_UPLOAD_PATH,
            _DEFAULT_UPLOAD_PATH,
        )

        migrated = 0
        skipped = 0
        for src in legacy_files:
            dst = _DEFAULT_UPLOAD_PATH / src.name
            if dst.exists():
                logger.warning(
                    "File %s already exists at destination %s — leaving legacy copy in place",
                    src.name,
                    dst,
                )
                skipped += 1
                continue
            shutil.move(str(src), str(dst))
            migrated += 1

        if migrated > 0:
            logger.info(
                "Migration complete — moved %d file(s) to %s",
                migrated,
                _DEFAULT_UPLOAD_PATH,
            )
        if skipped > 0:
            logger.warning(
                "Skipped %d file(s) due to name collisions. Legacy copies remain at %s",
                skipped,
                _LEGACY_UPLOAD_PATH,
            )

        # Tidy up the legacy directory if we emptied it
        remaining = list(_LEGACY_UPLOAD_PATH.iterdir()) if _LEGACY_UPLOAD_PATH.exists() else []
        if not remaining:
            try:
                _LEGACY_UPLOAD_PATH.rmdir()
            except OSError:
                pass

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_path(self) -> Path:
        return _USER_DATA_PATH


settings = Settings()
