from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    DATABASE_URL: str | None = Field(
        default=None,
        description="Postgres connection string — MUST be set via env or .env file"
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    MINIO_ENDPOINT: str = Field(default="localhost:9000")
    MINIO_ACCESS_KEY: str | None = Field(
        default=None,
        description="MinIO/S3 access key — MUST be set via env or .env file"
    )
    MINIO_SECRET_KEY: str | None = Field(
        default=None,
        description="MinIO/S3 secret key — MUST be set via env or .env file"
    )
    MINIO_BUCKET: str = Field(default="civicproof-artifacts")
    MINIO_USE_SSL: bool = Field(default=False)

    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(default=None)
    LOG_LEVEL: str = Field(default="INFO")

    API_SECRET_KEY: str | None = Field(
        default=None,
        description="API signing key — MUST be set via env or .env file"
    )
    API_RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    DEBUG: bool = Field(default=False)

    GCP_PROJECT_ID: str | None = Field(default=None)
    GCP_REGION: str = Field(default="us-central1")

    VERTEX_AI_LOCATION: str = Field(default="us-central1")
    VERTEX_AI_MODEL: str = Field(default="gemini-2.0-flash")

    GEMINI_API_KEY: str | None = Field(default=None)

    OPENROUTER_API_KEY: str | None = Field(default=None)
    OPENROUTER_DEFAULT_MODEL: str = Field(default="anthropic/claude-3-5-sonnet")

    VLLM_BASE_URL: str = Field(default="http://localhost:8000/v1")
    VLLM_MODEL: str = Field(default="mistralai/Mistral-7B-Instruct-v0.2")

    SAM_GOV_API_KEY: str | None = Field(default=None)
    OPENFEC_API_KEY: str | None = Field(default=None)

    MAX_COST_PER_CASE_USD: float = Field(default=0.50)
    ENABLE_PUBLIC_RISK_SIGNAL_MODE: bool = Field(default=True)
    ENABLE_LEGAL_PACK_MODE: bool = Field(default=False)
    PII_REDACTION_ENABLED: bool = Field(default=True)
    EVIDENCE_RETENTION_DAYS: int = Field(default=365)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
