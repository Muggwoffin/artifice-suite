from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    hf_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/transcribe.db"
    upload_dir: str = "./uploads"
    whisper_model: str = "base"
    device: str = "auto"
    max_upload_size: int = 524_288_000  # 500 MB

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_path(self) -> Path:
        p = Path("./data")
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
