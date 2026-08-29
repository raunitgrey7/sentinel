"""Application settings.

Every deployment knob lives here and is sourced from the environment (``SENTINEL_*``).
Defaults are chosen so that ``sentinel dev`` runs with zero external infrastructure:
SQLite on disk, an in-process job queue, and a deterministic ``none`` LLM provider.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SENTINEL_", env_file=(".env",), env_file_encoding="utf-8", extra="ignore"
    )

    # --- runtime -------------------------------------------------------------------------
    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    log_json: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    cors_origins: str = "http://localhost:3000"  # comma-separated
    public_url: str = "http://localhost:8000"

    # --- persistence ----------------------------------------------------------------------
    database_url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'sentinel.db').as_posix()}"
    database_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    auto_migrate: bool = True  # create_all on startup for sqlite / dev; alembic in prod

    # --- coordination ---------------------------------------------------------------------
    redis_url: str | None = None  # when None → in-process queue + in-memory rate limiter
    queue_backend: Literal["auto", "inprocess", "redis"] = "auto"
    job_timeout_s: int = 300
    job_max_retries: int = 3
    job_retry_backoff_s: float = 2.0

    # --- security -------------------------------------------------------------------------
    secret_key: str = "dev-only-change-me-please-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 12
    bootstrap_admin_email: str = "admin@sentinel.local"
    bootstrap_admin_password: str = "admin12345"
    bootstrap_ingest_key: str | None = "dev-ingest-key"
    rate_limit_per_minute: int = 600
    ingest_rate_limit_per_minute: int = 6000

    # --- detection ------------------------------------------------------------------------
    detector_interval_s: float = 10.0
    detector_enabled: bool = True
    incident_lookback_min: int = 30
    baseline_window_min: int = 20

    # --- investigation --------------------------------------------------------------------
    investigation_step_timeout_s: int = 60
    investigation_max_attempts: int = 3
    auto_investigate: bool = True
    low_confidence_threshold: float = 0.55
    max_evidence_per_kind: int = 25

    # --- llm ------------------------------------------------------------------------------
    llm_provider: Literal["none", "ollama"] = "none"
    ollama_base_url: str = "http://127.0.0.1:11434"  # 127.0.0.1: Ollama binds IPv4 only
    ollama_model: str = "qwen2.5:3b"  # fits CPU-only 16 GB laptops; qwen2.5:7b with a GPU / more RAM
    ollama_embed_model: str = "nomic-embed-text"
    llm_timeout_s: float = 90.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.1
    llm_circuit_failures: int = 3
    llm_circuit_reset_s: float = 60.0
    embedding_dim: int = 256  # for the hashed fallback embedder

    # --- simulator ------------------------------------------------------------------------
    simulator_url: str = "http://localhost:9000"
    simulator_project: str = "demo-shop"

    # --- observability --------------------------------------------------------------------
    otel_exporter_endpoint: str | None = None
    metrics_enabled: bool = True
    telemetry_retention_hours: int = 48

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalise_db_url(cls, v: object) -> object:
        """Accept plain ``postgresql://`` DSNs (Railway, Heroku-style) and use the async driver."""
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = "postgresql+asyncpg://" + v[len("postgres://"):]
            elif v.startswith("postgresql://"):
                v = "postgresql+asyncpg://" + v[len("postgresql://"):]
            v = v.replace("?sslmode=require", "?ssl=require").replace("&sslmode=require", "&ssl=require")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def effective_queue_backend(self) -> str:
        if self.queue_backend != "auto":
            return self.queue_backend
        return "redis" if self.redis_url else "inprocess"

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    # Platform conventions: DATABASE_URL / REDIS_URL / PORT (Railway, Heroku, Render).
    for src, dst in (("DATABASE_URL", "SENTINEL_DATABASE_URL"), ("REDIS_URL", "SENTINEL_REDIS_URL"), ("PORT", "SENTINEL_API_PORT")):
        if os.environ.get(src) and not os.environ.get(dst):
            os.environ[dst] = os.environ[src]
    s = Settings()
    if s.is_sqlite:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    return s
