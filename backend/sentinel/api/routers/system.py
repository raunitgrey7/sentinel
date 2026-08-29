from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import func, select

from sentinel.api.deps import DB, Admin, Engineer, Viewer
from sentinel.api.schemas import AlertOut, AuditOut, OverviewOut, RuleCreate, RuleOut
from sentinel.core.config import get_settings
from sentinel.core.errors import NotFound
from sentinel.db.models import (
    Alert,
    DetectionRule,
    EvaluationRun,
    FaultExperiment,
    Project,
    Service,
)
from sentinel.db.session import ping
from sentinel.llm import get_provider
from sentinel.observability import metrics as m
from sentinel.queue import get_queue
from sentinel.services import audit
from sentinel.services.incidents import open_count
from sentinel.services.projects import get_project

router = APIRouter(tags=["system"])


@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", include_in_schema=False)
async def ready(response: Response) -> dict[str, Any]:
    db_ok = await ping()
    q = get_queue()
    ok = db_ok
    if not ok:
        response.status_code = 503
    return {"status": "ready" if ok else "degraded", "database": db_ok, "queue": q.backend}


@router.get("/metrics", include_in_schema=False)
async def metrics_ep() -> Response:
    return Response(content=m.render(), media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/api/v1/system/overview", response_model=OverviewOut)
async def overview(_: Viewer, session: DB, project: str | None = None) -> OverviewOut:
    from sentinel.api.routers.projects import service_health

    proj = await get_project(session, project) if project else (await session.execute(select(Project).order_by(Project.created_at))).scalars().first()
    open_n = await open_count(session, proj.id if proj else None)
    services = 0
    healthy = 0
    if proj:
        health_rows = await service_health(proj.slug, _, session)
        services = len(health_rows)
        healthy = sum(1 for h in health_rows if h.healthy)
    active_faults = int((await session.execute(select(func.count(FaultExperiment.id)).where(FaultExperiment.status == "active"))).scalar() or 0)
    q = get_queue()
    try:
        depth = await q.depth()
    except Exception:  # noqa: BLE001
        depth = -1
    latest_eval = (await session.execute(select(EvaluationRun).where(EvaluationRun.status == "completed").order_by(EvaluationRun.completed_at.desc()).limit(1))).scalar_one_or_none()
    unhealthy = services - healthy
    risk = "HIGH" if open_n >= 2 or unhealthy >= 3 else "MEDIUM" if open_n == 1 or unhealthy >= 1 else "LOW"
    status = "DEGRADED" if open_n else "HEALTHY"
    return OverviewOut(
        status=status,
        open_incidents=open_n,
        services=services,
        healthy_services=healthy,
        risk=risk,
        llm=get_provider().snapshot(),
        queue={"backend": q.backend, "depth": depth},
        active_faults=active_faults,
        latest_evaluation=(latest_eval.summary if latest_eval else None),
    )


@router.get("/api/v1/system/config")
async def config_ep(_: Engineer) -> dict[str, Any]:
    s = get_settings()
    return {
        "env": s.env,
        "database": "sqlite" if s.is_sqlite else "postgresql",
        "queue": s.effective_queue_backend,
        "llm_provider": s.llm_provider,
        "llm_model": s.ollama_model if s.llm_provider == "ollama" else None,
        "detector_interval_s": s.detector_interval_s,
        "low_confidence_threshold": s.low_confidence_threshold,
        "auto_investigate": s.auto_investigate,
        "simulator_url": s.simulator_url,
    }


@router.get("/api/v1/system/queue")
async def queue_status(_: Engineer) -> dict[str, Any]:
    q = get_queue()
    return {"backend": q.backend, "depth": await q.depth(), "dead_letters": await q.dead_letters(20)}


@router.get("/api/v1/system/audit", response_model=list[AuditOut])
async def audit_log(_: Admin, session: DB, limit: int = 100, resource_id: str | None = None) -> list[Any]:
    return await audit.recent(session, limit=min(limit, 500), resource_id=resource_id)


@router.get("/api/v1/projects/{ref}/alerts", response_model=list[AlertOut])
async def alerts(ref: str, _: Viewer, session: DB, limit: int = 100) -> list[Alert]:
    p = await get_project(session, ref)
    return list((await session.execute(select(Alert).where(Alert.project_id == p.id).order_by(Alert.fired_at.desc()).limit(limit))).scalars().all())


@router.get("/api/v1/projects/{ref}/rules", response_model=list[RuleOut])
async def rules(ref: str, _: Viewer, session: DB) -> list[DetectionRule]:
    p = await get_project(session, ref)
    return list((await session.execute(select(DetectionRule).where(DetectionRule.project_id == p.id).order_by(DetectionRule.name))).scalars().all())


@router.post("/api/v1/projects/{ref}/rules", response_model=RuleOut, status_code=201)
async def create_rule(ref: str, body: RuleCreate, p: Engineer, session: DB) -> DetectionRule:
    proj = await get_project(session, ref)
    row = DetectionRule(project_id=proj.id, **body.model_dump())
    session.add(row)
    await session.flush()
    await audit.record(session, action="rule.create", resource_type="detection_rule", resource_id=row.id, actor_id=p.id, detail=body.model_dump())
    return row


@router.delete("/api/v1/projects/{ref}/rules/{rule_id}", status_code=204)
async def delete_rule(ref: str, rule_id: str, p: Engineer, session: DB) -> None:
    row = await session.get(DetectionRule, rule_id)
    if row is None:
        raise NotFound("rule not found")
    await session.delete(row)
    await audit.record(session, action="rule.delete", resource_type="detection_rule", resource_id=rule_id, actor_id=p.id)


@router.get("/api/v1/system/services-count", include_in_schema=False)
async def services_count(_: Viewer, session: DB) -> dict[str, int]:
    return {"services": int((await session.execute(select(func.count(Service.id)))).scalar() or 0)}
