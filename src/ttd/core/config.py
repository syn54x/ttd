from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    xdg = Path.home() / ".local" / "share" / "ttd"
    xdg.mkdir(parents=True, exist_ok=True)
    return xdg


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TTD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=default_data_dir)
    db_filename: str = "ttd.db"

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def db_dsn(self) -> str:
        return f"sqlite:{self.db_path}?mode=rwc"


def get_settings() -> Settings:
    return Settings()
