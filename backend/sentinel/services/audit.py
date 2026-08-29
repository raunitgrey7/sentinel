"""Audit trail for sensitive actions: who, what, when, why, result."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.db.models import AuditLog


async def record(
    session: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None,
    actor_id: str | None,
    actor_type: str = "user",
    outcome: str = "success",
    reason: str = "",
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
) -> AuditLog:
    row = AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_id=actor_id,
        actor_type=actor_type,
        outcome=outcome,
        reason=reason,
        detail=detail or {},
        ip=ip,
    )
    session.add(row)
    return row


async def recent(session: AsyncSession, *, limit: int = 100, resource_id: str | None = None) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    return list((await session.execute(stmt)).scalars().all())
