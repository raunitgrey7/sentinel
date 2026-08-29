"""Background jobs. Registered on the shared ``registry``; executed by either backend."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select

from sentinel.core.config import get_settings
from sentinel.core.logging import get_logger
from sentinel.core.timeutil import utcnow
from sentinel.db.models import FaultExperiment, Project
from sentinel.db.session import session_scope
from sentinel.detection.engine import evaluate_rules
from sentinel.investigation.orchestrator import (
    create_investigation,
    latest_investigation,
    run_investigation,
)
from sentinel.queue import JobContext, get_queue, registry
from sentinel.telemetry.store import purge_older_than

log = get_logger(__name__)

JOB_INVESTIGATE = "investigate_incident"
JOB_DETECT = "detector_tick"
JOB_RETENTION = "telemetry_retention"
JOB_FAULT_EXPIRY = "fault_expiry"


async def enqueue_investigation(incident_id: str, *, trigger: str = "auto", force_new: bool = False, delay_s: float = 1.0) -> str | None:
    """Queue an investigation for an incident. Idempotent per incident while one is pending.

    Deliberately touches no database state: callers are usually inside a transaction
    (detector tick, webhook handler) and the job creates its own investigation row in its
    own session once that transaction has committed.
    """
    return await get_queue().enqueue(
        JOB_INVESTIGATE,
        {"incident_id": incident_id, "trigger": trigger, "force_new": force_new},
        idempotency_key=f"investigate:{incident_id}",
        delay_s=delay_s,
    )


@registry.register(JOB_INVESTIGATE)
async def investigate_incident(ctx: JobContext) -> dict[str, Any]:
    incident_id = ctx.payload["incident_id"]
    force_new = bool(ctx.payload.get("force_new", False))
    trigger = ctx.payload.get("trigger", "auto")
    async with session_scope() as s:
        inv = None if force_new else await latest_investigation(s, incident_id)
        if inv is None or (force_new and inv.status in ("COMPLETED", "FAILED", "CANCELLED")) or inv.status in ("COMPLETED", "CANCELLED"):
            if inv is not None and inv.status == "COMPLETED" and not force_new and ctx.attempt == 1:
                return {"incident_id": incident_id, "status": "already_completed"}
            inv = await create_investigation(s, incident_id, trigger=trigger)
        inv_id = inv.id
    async with session_scope() as s:
        inv = await run_investigation(s, inv_id)
        return {"investigation_id": inv.id, "status": inv.status, "duration_ms": inv.duration_ms}


@registry.register(JOB_DETECT)
async def detector_tick(ctx: JobContext) -> dict[str, Any]:
    async def _enqueue(incident_id: str) -> None:
        await enqueue_investigation(incident_id)

    out: dict[str, Any] = {}
    async with session_scope() as s:
        projects = (await s.execute(select(Project))).scalars().all()
        for p in projects:
            out[p.slug] = await evaluate_rules(s, p.id, enqueue=_enqueue)
    return out


@registry.register(JOB_RETENTION)
async def telemetry_retention(ctx: JobContext) -> dict[str, Any]:
    settings = get_settings()
    cutoff = utcnow() - timedelta(hours=settings.telemetry_retention_hours)
    async with session_scope() as s:
        return await purge_older_than(s, cutoff)


@registry.register(JOB_FAULT_EXPIRY)
async def fault_expiry(ctx: JobContext) -> dict[str, Any]:
    """Mark fault experiments as cleared when their duration has elapsed."""
    now = utcnow()
    cleared: list[str] = []
    async with session_scope() as s:
        active = (await s.execute(select(FaultExperiment).where(FaultExperiment.status == "active"))).scalars().all()
        for f in active:
            if f.started_at and (now - f.started_at).total_seconds() >= f.duration_s:
                f.status = "cleared"
                f.ended_at = now
                cleared.append(f.id)
    return {"cleared": cleared}
