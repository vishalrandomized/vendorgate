from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sarvam_api_key: str = ""
    sarvam_model: str = "sarvam-105b"
    opensanctions_api_key: str = ""
    database_url: str = "sqlite:///data/app.db"
    ruleset_version: str = "1.2"

    @property
    def data_dir(self) -> Path:
        return ROOT_DIR / "data"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def fixtures_dir(self) -> Path:
        return ROOT_DIR / "fixtures" / "generated"

@lru_cache
def get_settings() -> Settings:
    return Settings()
