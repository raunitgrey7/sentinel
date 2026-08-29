"""Simulator configuration (``SIM_*`` environment variables)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SimSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIM_", extra="ignore")

    sentinel_url: str = "http://localhost:8000"
    ingest_key: str = "dev-ingest-key"
    project: str = "demo-shop"
    environment: str = "production"
    control_port: int = 9000
    base_port: int = 9001  # services take base_port, base_port+1, ...
    host: str = "127.0.0.1"
    flush_interval_s: float = 5.0
    traffic_rps: float = 12.0
    traffic_enabled: bool = True
    log_level: str = "INFO"
    services: list[str] = Field(
        default_factory=lambda: [
            "frontend",
            "api-gateway",
            "auth-service",
            "order-service",
            "inventory-service",
            "payment-service",
            "notification-worker",
        ]
    )

    def port_of(self, service: str) -> int:
        return self.base_port + self.services.index(service)

    def url_of(self, service: str) -> str:
        return f"http://{self.host}:{self.port_of(service)}"


settings = SimSettings()
