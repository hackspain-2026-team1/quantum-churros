from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Embat X-Ray API"
    database_url: str = "sqlite:///./xray.db"
    cors_origins: str = "http://localhost:5173"
    scores_path: Path = Path("artifacts/scores.parquet")


settings = Settings()
