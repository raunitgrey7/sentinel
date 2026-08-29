"""First-run bootstrap: admin user, ingest API key, demo-shop project topology.

Idempotent — safe to run on every start.
"""

from __future__ import annotations

from sqlalchemy import select

from sentinel.core.config import get_settings
from sentinel.core.logging import get_logger
from sentinel.core.security import hash_api_key, hash_password
from sentinel.db.models import ApiKey, User
from sentinel.db.session import session_scope
from sentinel.services.projects import (
    ensure_default_rules,
    ensure_dependency,
    ensure_project,
    ensure_service,
)

log = get_logger(__name__)

DEMO_SERVICES: list[tuple[str, str, str]] = [
    # name, kind, tier
    ("frontend", "service", "standard"),
    ("api-gateway", "service", "critical"),
    ("auth-service", "service", "critical"),
    ("order-service", "service", "critical"),
    ("inventory-service", "service", "standard"),
    ("payment-service", "service", "critical"),
    ("notification-worker", "service", "low"),
    ("postgres", "database", "critical"),
    ("redis", "cache", "standard"),
    ("message-queue", "queue", "standard"),
    ("payment-provider", "external", "critical"),
    ("email-provider", "external", "low"),
]
DEMO_EDGES: list[tuple[str, str, str]] = [
    ("frontend", "api-gateway", "http"),
    ("api-gateway", "auth-service", "http"),
    ("api-gateway", "order-service", "http"),
    ("auth-service", "redis", "cache"),
    ("auth-service", "postgres", "db"),
    ("order-service", "inventory-service", "http"),
    ("order-service", "payment-service", "http"),
    ("order-service", "postgres", "db"),
    ("order-service", "message-queue", "queue"),
    ("inventory-service", "postgres", "db"),
    ("inventory-service", "redis", "cache"),
    ("payment-service", "postgres", "db"),
    ("payment-service", "redis", "cache"),
    ("notification-worker", "message-queue", "queue"),
    ("payment-service", "payment-provider", "external"),
    ("notification-worker", "email-provider", "external"),
]


async def bootstrap() -> None:
    s = get_settings()
    async with session_scope() as session:
        admin = (await session.execute(select(User).where(User.email == s.bootstrap_admin_email))).scalar_one_or_none()
        if admin is None:
            session.add(User(email=s.bootstrap_admin_email, full_name="Sentinel Admin", password_hash=hash_password(s.bootstrap_admin_password), role="ADMIN"))
            log.info("bootstrap admin created", email=s.bootstrap_admin_email)
        if s.bootstrap_ingest_key:
            kh = hash_api_key(s.bootstrap_ingest_key)
            if (await session.execute(select(ApiKey).where(ApiKey.key_hash == kh))).scalar_one_or_none() is None:
                session.add(ApiKey(name="bootstrap-ingest", key_hash=kh, prefix=s.bootstrap_ingest_key[:10], role="ENGINEER", scopes=["ingest", "webhooks"]))
        project = await ensure_project(session, s.simulator_project, "Sentinel Demo Shop")
        await ensure_default_rules(session, project.id)
        for name, kind, tier in DEMO_SERVICES:
            await ensure_service(session, project.id, name, kind=kind, tier=tier)
        for src, tgt, kind in DEMO_EDGES:
            await ensure_dependency(session, project.id, src, tgt, kind)
