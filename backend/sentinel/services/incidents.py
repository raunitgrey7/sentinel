"""Incident service: creation, keys, lifecycle transitions, timeline events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.core.errors import NotFound
from sentinel.core.timeutil import utcnow
from sentinel.db.models import Incident, IncidentEvent
from sentinel.domain.enums import OPEN_STATUSES, IncidentStatus, Severity
from sentinel.domain.state_machine import assert_transition
from sentinel.observability import metrics as m


async def next_key(session: AsyncSession, project_id: str) -> tuple[str, int]:
    """Incident keys are globally unique and monotonic (INC-<year>-<seq>)."""
    year = utcnow().year
    seq = (await session.execute(select(func.max(Incident.sequence)))).scalar() or 0
    seq += 1
    return f"INC-{year}-{seq:04d}", seq


async def get_incident(session: AsyncSession, incident_id: str) -> Incident:
    inc = await session.get(Incident, incident_id)
    if inc is None:
        # allow lookup by key
        inc = (await session.execute(select(Incident).where(Incident.key == incident_id))).scalar_one_or_none()
    if inc is None:
        raise NotFound(f"incident {incident_id} not found")
    return inc


async def find_open_incident_for(session: AsyncSession, project_id: str, service: str) -> Incident | None:
    stmt = (
        select(Incident)
        .where(Incident.project_id == project_id, Incident.status.in_([s.value for s in OPEN_STATUSES]))
        .order_by(Incident.created_at.desc())
    )
    for inc in (await session.execute(stmt)).scalars().all():
        if inc.primary_service == service or service in (inc.affected_services or []):
            return inc
    return None


async def create_incident(
    session: AsyncSession,
    *,
    project_id: str,
    title: str,
    primary_service: str,
    severity: str = Severity.HIGH,
    description: str = "",
    affected_services: list[str] | None = None,
    started_at: datetime | None = None,
    detected_at: datetime | None = None,
    trigger: dict[str, Any] | None = None,
    created_by: str = "system",
    labels: dict[str, Any] | None = None,
) -> Incident:
    key, seq = await next_key(session, project_id)
    now = utcnow()
    inc = Incident(
        project_id=project_id,
        key=key,
        sequence=seq,
        title=title,
        description=description,
        severity=str(severity),
        status=IncidentStatus.DETECTED,
        primary_service=primary_service,
        affected_services=sorted(set([primary_service, *(affected_services or [])])),
        trigger=trigger or {},
        started_at=started_at or now,
        detected_at=detected_at or now,
        created_by=created_by,
        labels=labels or {},
    )
    session.add(inc)
    await session.flush()
    await add_event(session, inc.id, "status", f"Incident {key} created ({inc.severity})", actor=created_by, ts=inc.detected_at, status=inc.status)
    m.INCIDENTS_CREATED.labels(inc.severity).inc()
    return inc


async def add_event(session: AsyncSession, incident_id: str, kind: str, message: str, *, actor: str = "system", ts: datetime | None = None, data: dict[str, Any] | None = None, **extra: Any) -> IncidentEvent:
    ev = IncidentEvent(incident_id=incident_id, kind=kind, message=message, actor=actor, ts=ts or utcnow(), data={**(data or {}), **extra})
    session.add(ev)
    return ev


async def transition(session: AsyncSession, incident: Incident, target: IncidentStatus | str, *, actor: str = "system", note: str = "") -> Incident:
    tgt = assert_transition(incident.status, target)
    if tgt == incident.status:
        return incident
    prev = incident.status
    incident.status = tgt
    if tgt == IncidentStatus.RESOLVED and incident.resolved_at is None:
        incident.resolved_at = utcnow()
    await add_event(session, incident.id, "status", f"{prev} → {tgt}" + (f": {note}" if note else ""), actor=actor, **{"from": prev, "to": tgt})
    return incident


async def open_count(session: AsyncSession, project_id: str | None = None) -> int:
    stmt = select(func.count(Incident.id)).where(Incident.status.in_([s.value for s in OPEN_STATUSES]))
    if project_id:
        stmt = stmt.where(Incident.project_id == project_id)
    n = int((await session.execute(stmt)).scalar() or 0)
    m.INCIDENTS_OPEN.set(n)
    return n


async def timeline(session: AsyncSession, incident_id: str) -> list[IncidentEvent]:
    stmt = select(IncidentEvent).where(IncidentEvent.incident_id == incident_id).order_by(IncidentEvent.ts, IncidentEvent.id)
    return list((await session.execute(stmt)).scalars().all())
