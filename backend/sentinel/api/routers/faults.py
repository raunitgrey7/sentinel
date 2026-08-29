"""Chaos lab: controlled fault injection against the demo shop."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from sentinel.api.deps import DB, Sre, Viewer
from sentinel.api.schemas import FaultCreate, FaultOut
from sentinel.core.errors import NotFound, ValidationFailed
from sentinel.core.logging import get_logger
from sentinel.core.timeutil import utcnow
from sentinel.db.models import FaultExperiment
from sentinel.services import audit
from sentinel.services.projects import get_project
from sentinel.services.simulator_client import SimulatorClient

log = get_logger(__name__)
router = APIRouter(prefix="/faults", tags=["chaos"])

# fault type → expected root-cause category (ground truth for evaluation)
FAULT_CATALOG: dict[str, dict[str, Any]] = {
    "cpu_saturation": {"expected": "cpu_saturation", "description": "Burn CPU in the target service"},
    "memory_leak": {"expected": "memory_exhaustion", "description": "Grow heap steadily until GC pressure degrades latency"},
    "database_latency": {"expected": "database_latency", "description": "Slow every DB query in the target"},
    "db_pool_exhaustion": {"expected": "database_connection_pool", "description": "Hold connections so the pool saturates"},
    "http_500_spike": {"expected": "deployment_regression", "description": "Deploy a version that throws on a hot path"},
    "network_latency": {"expected": "network_latency", "description": "Add latency to calls from the target to a dependency"},
    "packet_loss": {"expected": "network_packet_loss", "description": "Reset a fraction of connections to a dependency"},
    "redis_failure": {"expected": "redis_unavailable", "description": "Make the cache unreachable"},
    "queue_backlog": {"expected": "queue_backlog", "description": "Stall consumers so the queue grows"},
    "bad_deployment": {"expected": "database_connection_pool", "description": "Deploy a commit that raises transaction concurrency past the pool"},
    "config_regression": {"expected": "config_regression", "description": "Push a config change that breaks a dependency timeout"},
    "dependency_failure": {"expected": "dependency_failure", "description": "A downstream service starts failing"},
    "thread_starvation": {"expected": "thread_starvation", "description": "Block worker threads"},
    "deadlock": {"expected": "deadlock", "description": "Requests hang on a lock; throughput collapses"},
}


@router.get("/catalog")
async def catalog(_: Viewer) -> dict[str, Any]:
    return FAULT_CATALOG


@router.get("", response_model=list[FaultOut])
async def list_faults(_: Viewer, session: DB, limit: int = 50) -> list[FaultExperiment]:
    return list((await session.execute(select(FaultExperiment).order_by(FaultExperiment.created_at.desc()).limit(limit))).scalars().all())


@router.post("", response_model=FaultOut, status_code=201)
async def inject(body: FaultCreate, p: Sre, session: DB) -> FaultExperiment:
    if body.fault not in FAULT_CATALOG:
        raise ValidationFailed(f"unknown fault '{body.fault}'", details={"known": sorted(FAULT_CATALOG)})
    proj = await get_project(session, body.project)
    exp = FaultExperiment(
        project_id=proj.id,
        target_service=body.target,
        fault_type=body.fault,
        severity=body.severity,
        duration_s=body.duration_s,
        params=body.params,
        expected_root_cause=FAULT_CATALOG[body.fault]["expected"],
        created_by=p.id,
    )
    session.add(exp)
    await session.flush()
    client = SimulatorClient()
    try:
        res = await client.inject_fault(target=body.target, fault=body.fault, duration_s=body.duration_s, severity=body.severity, params={**body.params, "experiment_id": exp.id})
        exp.status = "active"
        exp.started_at = utcnow()
        exp.params = {**exp.params, "simulator_fault_id": res.get("id")}
        outcome = "success"
    except Exception as exc:  # noqa: BLE001
        exp.status = "failed"
        exp.params = {**exp.params, "error": str(exc)[:300]}
        outcome = "failure"
    await audit.record(session, action="fault.inject", resource_type="fault_experiment", resource_id=exp.id, actor_id=p.id, outcome=outcome, detail={"target": body.target, "fault": body.fault, "duration_s": body.duration_s})
    return exp


@router.delete("/{fault_id}", response_model=FaultOut)
async def clear(fault_id: str, p: Sre, session: DB) -> FaultExperiment:
    exp = await session.get(FaultExperiment, fault_id)
    if exp is None:
        raise NotFound("fault experiment not found")
    sim_id = (exp.params or {}).get("simulator_fault_id")
    if sim_id:
        try:
            await SimulatorClient().clear_fault(sim_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("simulator clear failed", fault=sim_id, error=str(exc))
    exp.status = "cleared"
    exp.ended_at = utcnow()
    await audit.record(session, action="fault.clear", resource_type="fault_experiment", resource_id=exp.id, actor_id=p.id)
    return exp


@router.delete("", status_code=200)
async def clear_all(p: Sre, session: DB) -> dict[str, Any]:
    try:
        await SimulatorClient().clear_all()
    except Exception as exc:  # noqa: BLE001
        log.warning("simulator clear_all failed", error=str(exc))
    active = (await session.execute(select(FaultExperiment).where(FaultExperiment.status == "active"))).scalars().all()
    for exp in active:
        exp.status = "cleared"
        exp.ended_at = utcnow()
    await audit.record(session, action="fault.clear_all", resource_type="fault_experiment", resource_id=None, actor_id=p.id, detail={"cleared": len(active)})
    return {"cleared": len(active)}
