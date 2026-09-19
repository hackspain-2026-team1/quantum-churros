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
    database_url: str | None = None
    cors_origins: str = "http://localhost:5173"
    scores_path: Path = Path("artifacts/scores.parquet")
    # Static export bundle written by `make export`; the API serves it as-is for local dev.
    bundle_dir: Path = Field(
        default=Path("bundle"),
        validation_alias=AliasChoices("XRAY_BUNDLE_DIR", "BUNDLE_DIR"),
    )
    # Rumbo's score forecast (horizons/), trained by the sync cycle; unset = not computed.
    horizons_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("XRAY_HORIZONS_DIR", "HORIZONS_DIR"),
    )
    data_dir: Path = Field(
        default=Path("data/raw"),
        validation_alias=AliasChoices("XRAY_DATA_DIR", "DATA_DIR"),
    )
    active_dataset_hash: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "XRAY_ACTIVE_DATASET_HASH", "ACTIVE_DATASET_HASH"
        ),
    )
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    notification_from: str = "Embat X-Ray <xray@embat.test>"
    frontend_base_url: str = "http://localhost:3000"
    mailpit_api_url: str = "http://localhost:8025"

    def require_database_url(self) -> str:
        if self.database_url is None or not self.database_url.strip():
            raise RuntimeError(
                "DATABASE_URL is required; use PostgreSQL for the application or set an explicit SQLite URL in isolated tests"
            )
        return self.database_url


settings = Settings()
