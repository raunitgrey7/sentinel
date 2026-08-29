"""Telemetry ingestion and webhooks (Alertmanager, deployments)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from sentinel.api.deps import DB, Ingestor
from sentinel.api.schemas import DeploymentWebhook, IngestBatch, IngestResult
from sentinel.core.logging import get_logger
from sentinel.core.timeutil import parse_ts, utcnow
from sentinel.db.models import Deployment
from sentinel.detection.engine import ingest_alertmanager
from sentinel.services.incidents import add_event, find_open_incident_for
from sentinel.services.projects import ensure_project, ensure_service
from sentinel.telemetry.normalize import normalize_log, normalize_metric, normalize_span
from sentinel.telemetry.store import write_logs, write_metrics, write_spans

log = get_logger(__name__)
router = APIRouter(tags=["ingest"])


async def _normalize_batch(batch: IngestBatch, fn) -> tuple[list[dict[str, Any]], int]:  # type: ignore[no-untyped-def]
    rows: list[dict[str, Any]] = []
    rejected = 0
    for raw in batch.records:
        try:
            rows.append(fn(raw, default_service=batch.service))
        except Exception:  # noqa: BLE001
            rejected += 1
    return rows, rejected


@router.post("/ingest/logs", response_model=IngestResult, status_code=202)
async def ingest_logs(batch: IngestBatch, _: Ingestor, session: DB) -> IngestResult:
    p = await ensure_project(session, batch.project)
    rows, rejected = await _normalize_batch(batch, normalize_log)
    n = await write_logs(session, p.id, rows)
    return IngestResult(accepted=n, rejected=rejected)


@router.post("/ingest/metrics", response_model=IngestResult, status_code=202)
async def ingest_metrics(batch: IngestBatch, _: Ingestor, session: DB) -> IngestResult:
    p = await ensure_project(session, batch.project)
    rows, rejected = await _normalize_batch(batch, normalize_metric)
    seen: set[str] = set()
    for r in rows:
        if r["service"] not in seen:
            seen.add(r["service"])
            await ensure_service(session, p.id, r["service"])
    n = await write_metrics(session, p.id, rows)
    return IngestResult(accepted=n, rejected=rejected)


@router.post("/ingest/traces", response_model=IngestResult, status_code=202)
async def ingest_traces(batch: IngestBatch, _: Ingestor, session: DB) -> IngestResult:
    p = await ensure_project(session, batch.project)
    rows, rejected = await _normalize_batch(batch, normalize_span)
    n = await write_spans(session, p.id, rows)
    return IngestResult(accepted=n, rejected=rejected)


@router.post("/webhooks/deployments", status_code=202)
async def deployment_webhook(body: DeploymentWebhook, _: Ingestor, session: DB) -> dict[str, Any]:
    p = await ensure_project(session, body.project)
    svc = await ensure_service(session, p.id, body.service, version=body.version)
    dep = Deployment(
        project_id=p.id,
        service=body.service,
        version=body.version,
        previous_version=body.previous_version or (svc.current_version if svc.current_version != body.version else None),
        commit_sha=body.commit_sha,
        commit_message=body.commit_message,
        author=body.author,
        changed_files=body.changed_files,
        diff_summary=body.diff_summary,
        config_changes=body.config_changes,
        status=body.status,
        deployed_at=parse_ts(body.timestamp) if body.timestamp is not None else utcnow(),  # type: ignore[arg-type]
    )
    svc.current_version = body.version
    session.add(dep)
    await session.flush()
    open_inc = await find_open_incident_for(session, p.id, body.service)
    if open_inc:
        await add_event(session, open_inc.id, "deployment", f"{body.service} {body.version} deployed during incident ({body.status})", ts=dep.deployed_at, deployment_id=dep.id)
    return {"id": dep.id, "service": dep.service, "version": dep.version}


@router.post("/webhooks/alerts", status_code=202)
async def alertmanager_webhook(request: Request, _: Ingestor, session: DB, project: str = "demo-shop") -> dict[str, Any]:
    payload = await request.json()
    p = await ensure_project(session, payload.get("commonLabels", {}).get("project") or project)

    async def _enqueue(incident_id: str) -> None:
        from sentinel.worker.jobs import enqueue_investigation

        await enqueue_investigation(incident_id)

    return await ingest_alertmanager(session, p.id, payload, enqueue=_enqueue)
