from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from sentinel.api.deps import DB, Engineer, Viewer
from sentinel.api.schemas import (
    DependencyCreate,
    DependencyOut,
    DeploymentOut,
    ProjectCreate,
    ProjectOut,
    ServiceCreate,
    ServiceHealth,
    ServiceOut,
    TopologyOut,
)
from sentinel.core.errors import Conflict
from sentinel.core.timeutil import utcnow
from sentinel.db.models import (
    Deployment,
    Incident,
    MetricPoint,
    Project,
    Service,
    ServiceDependency,
)
from sentinel.domain.enums import OPEN_STATUSES
from sentinel.services.projects import (
    ensure_default_rules,
    ensure_dependency,
    ensure_service,
    get_project,
    load_service_graph,
)
from sentinel.telemetry.store import latest_metrics

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(_: Viewer, session: DB) -> list[Project]:
    return list((await session.execute(select(Project).order_by(Project.created_at))).scalars().all())


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, _: Engineer, session: DB) -> Project:
    if (await session.execute(select(Project).where(Project.slug == body.slug))).scalar_one_or_none():
        raise Conflict("project slug exists")
    p = Project(slug=body.slug, name=body.name, environment=body.environment)
    session.add(p)
    await session.flush()
    await ensure_default_rules(session, p.id)
    return p


@router.get("/projects/{ref}", response_model=ProjectOut)
async def get_project_ep(ref: str, _: Viewer, session: DB) -> Project:
    return await get_project(session, ref)


@router.get("/projects/{ref}/services", response_model=list[ServiceOut])
async def list_services(ref: str, _: Viewer, session: DB) -> list[Service]:
    p = await get_project(session, ref)
    return list((await session.execute(select(Service).where(Service.project_id == p.id).order_by(Service.name))).scalars().all())


@router.post("/projects/{ref}/services", response_model=ServiceOut, status_code=201)
async def upsert_service(ref: str, body: ServiceCreate, _: Engineer, session: DB) -> Service:
    p = await get_project(session, ref)
    return await ensure_service(session, p.id, body.name, kind=body.kind, tier=body.tier, owner=body.owner, version=body.current_version)


@router.get("/projects/{ref}/dependencies", response_model=list[DependencyOut])
async def list_dependencies(ref: str, _: Viewer, session: DB) -> list[ServiceDependency]:
    p = await get_project(session, ref)
    return list((await session.execute(select(ServiceDependency).where(ServiceDependency.project_id == p.id))).scalars().all())


@router.post("/projects/{ref}/dependencies", response_model=DependencyOut, status_code=201)
async def upsert_dependency(ref: str, body: DependencyCreate, _: Engineer, session: DB) -> ServiceDependency:
    p = await get_project(session, ref)
    await ensure_service(session, p.id, body.source)
    await ensure_service(session, p.id, body.target, kind={"db": "database", "cache": "cache", "queue": "queue"}.get(body.kind, "service"))
    return await ensure_dependency(session, p.id, body.source, body.target, body.kind, body.critical)


@router.get("/projects/{ref}/topology", response_model=TopologyOut)
async def topology(ref: str, _: Viewer, session: DB) -> TopologyOut:
    p = await get_project(session, ref)
    g = await load_service_graph(session, p.id)
    d = g.to_dict()
    return TopologyOut(nodes=d["nodes"], edges=d["edges"])  # type: ignore[arg-type]


@router.get("/projects/{ref}/health", response_model=list[ServiceHealth])
async def service_health(ref: str, _: Viewer, session: DB) -> list[ServiceHealth]:
    p = await get_project(session, ref)
    now = utcnow()
    services = (await session.execute(select(Service).where(Service.project_id == p.id).order_by(Service.name))).scalars().all()
    latest = await latest_metrics(session, p.id, now - timedelta(minutes=2))
    last_seen_rows = (
        await session.execute(
            select(MetricPoint.service, func.max(MetricPoint.ts)).where(MetricPoint.project_id == p.id, MetricPoint.ts >= now - timedelta(hours=1)).group_by(MetricPoint.service)
        )
    ).all()
    last_seen = {r[0]: r[1] for r in last_seen_rows}
    open_incs = (await session.execute(select(Incident).where(Incident.project_id == p.id, Incident.status.in_([s.value for s in OPEN_STATUSES])))).scalars().all()
    # availability over the last 15 minutes = 1 - avg error rate
    avail_rows = (
        await session.execute(
            select(MetricPoint.service, func.avg(MetricPoint.value)).where(MetricPoint.project_id == p.id, MetricPoint.name == "http_error_rate", MetricPoint.ts >= now - timedelta(minutes=15)).group_by(MetricPoint.service)
        )
    ).all()
    avail = {r[0]: 1.0 - float(r[1] or 0.0) for r in avail_rows}
    out: list[ServiceHealth] = []
    for svc in services:
        mtr = latest.get(svc.name, {})
        err = mtr.get("http_error_rate")
        p95 = mtr.get("http_latency_p95_ms")
        inc_count = sum(1 for i in open_incs if svc.name == i.primary_service or svc.name in (i.affected_services or []))
        healthy = (err is None or err < 0.03) and (p95 is None or p95 < 1500) and inc_count == 0
        out.append(
            ServiceHealth(
                name=svc.name,
                kind=svc.kind,
                version=svc.current_version,
                healthy=healthy,
                availability=round(avail.get(svc.name, 1.0), 4),
                error_rate=err,
                p95_ms=p95,
                request_rate=mtr.get("http_request_rate"),
                open_incidents=inc_count,
                last_seen=last_seen.get(svc.name),
            )
        )
    return out


@router.get("/projects/{ref}/deployments", response_model=list[DeploymentOut])
async def list_deployments(ref: str, _: Viewer, session: DB, limit: int = 50) -> list[Deployment]:
    p = await get_project(session, ref)
    return list((await session.execute(select(Deployment).where(Deployment.project_id == p.id).order_by(Deployment.deployed_at.desc()).limit(min(limit, 500)))).scalars().all())


@router.get("/projects/{ref}/metrics/{service}/{metric}")
async def metric_series_ep(ref: str, service: str, metric: str, _: Viewer, session: DB, minutes: int = 30) -> list[dict[str, float | str]]:
    from sentinel.telemetry.store import metric_series

    p = await get_project(session, ref)
    now = utcnow()
    pts = await metric_series(session, p.id, service, metric, now - timedelta(minutes=min(minutes, 24 * 60)), now)
    return [{"ts": pt.ts.isoformat(), "value": pt.value} for pt in pts]
