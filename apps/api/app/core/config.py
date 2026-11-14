from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: str = "http://localhost:3000"
    openalex_base_url: str = "https://api.openalex.org"
    openalex_api_key: str = Field(default="", repr=False)
    semantic_scholar_base_url: str = "https://api.semanticscholar.org/graph/v1"
    semantic_scholar_api_key: str = Field(default="", repr=False)
    semantic_scholar_enabled: bool = False
    database_url: str = ""
    model_artifact_dir: Path = API_ROOT / "artifacts"

    @field_validator("model_artifact_dir", mode="before")
    @classmethod
    def resolve_artifact_dir(cls, value):
        path = Path(value) if value else API_ROOT / "artifacts"
        return path if path.is_absolute() else API_ROOT / path

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
