from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Embat X-Ray API"
    database_url: str = "sqlite:///./xray.db"
    cors_origins: str = "http://localhost:5173"
    scores_path: Path = Path("artifacts/scores.parquet")
    # Static export bundle written by `make export`; the API serves it as-is for local dev.
    bundle_dir: Path = Field(
        default=Path("frontend/static/data/v1"),
        validation_alias=AliasChoices("XRAY_BUNDLE_DIR", "BUNDLE_DIR"),
    )
    data_dir: Path = Field(
        default=Path("data/raw"),
        validation_alias=AliasChoices("XRAY_DATA_DIR", "DATA_DIR"),
    )
    active_dataset_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices("XRAY_ACTIVE_DATASET_HASH", "ACTIVE_DATASET_HASH"),
    )


settings = Settings()
