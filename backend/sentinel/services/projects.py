"""Project / service registry helpers and service-graph loading."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.analysis.dependency_graph import ServiceGraph
from sentinel.core.errors import NotFound
from sentinel.db.models import DetectionRule, Project, Service, ServiceDependency
from sentinel.detection.rules import DEFAULT_RULES


async def get_project(session: AsyncSession, ref: str) -> Project:
    p = await session.get(Project, ref)
    if p is None:
        p = (await session.execute(select(Project).where(Project.slug == ref))).scalar_one_or_none()
    if p is None:
        raise NotFound(f"project {ref} not found")
    return p


async def ensure_project(session: AsyncSession, slug: str, name: str | None = None, environment: str = "production") -> Project:
    p = (await session.execute(select(Project).where(Project.slug == slug))).scalar_one_or_none()
    if p is None:
        p = Project(slug=slug, name=name or slug, environment=environment)
        session.add(p)
        await session.flush()
        await ensure_default_rules(session, p.id)
    return p


async def ensure_service(session: AsyncSession, project_id: str, name: str, *, kind: str = "service", tier: str = "standard", owner: str = "", version: str | None = None) -> Service:
    svc = (await session.execute(select(Service).where(Service.project_id == project_id, Service.name == name))).scalar_one_or_none()
    if svc is None:
        svc = Service(project_id=project_id, name=name, kind=kind, tier=tier, owner=owner, current_version=version)
        session.add(svc)
        await session.flush()
    else:
        if version:
            svc.current_version = version
        if kind != "service":
            svc.kind = kind
    return svc


async def ensure_dependency(session: AsyncSession, project_id: str, source: str, target: str, kind: str = "http", critical: bool = True) -> ServiceDependency:
    dep = (
        await session.execute(
            select(ServiceDependency).where(ServiceDependency.project_id == project_id, ServiceDependency.source == source, ServiceDependency.target == target)
        )
    ).scalar_one_or_none()
    if dep is None:
        dep = ServiceDependency(project_id=project_id, source=source, target=target, kind=kind, critical=critical)
        session.add(dep)
        await session.flush()
    return dep


async def load_service_graph(session: AsyncSession, project_id: str) -> ServiceGraph:
    g = ServiceGraph()
    for svc in (await session.execute(select(Service).where(Service.project_id == project_id))).scalars().all():
        g.add_node(svc.name, svc.kind)
    for dep in (await session.execute(select(ServiceDependency).where(ServiceDependency.project_id == project_id))).scalars().all():
        g.add_edge(dep.source, dep.target)
    return g


async def ensure_default_rules(session: AsyncSession, project_id: str) -> int:
    existing = {r.name for r in (await session.execute(select(DetectionRule).where(DetectionRule.project_id == project_id))).scalars().all()}
    n = 0
    for r in DEFAULT_RULES:
        if r["name"] in existing:
            continue
        session.add(DetectionRule(project_id=project_id, **r))
        n += 1
    return n
