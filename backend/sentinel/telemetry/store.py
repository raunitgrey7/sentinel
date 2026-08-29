"""Telemetry persistence and windowed queries.

Reads are shaped for the analysis layer: a *baseline* window (before onset) and an
*incident* window (around onset → now). Everything returns plain dataclasses/dicts so the
analysis code is trivially unit-testable without a database.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.db.models import Deployment, LogRecord, MetricPoint, Span
from sentinel.observability import metrics as m


@dataclass(slots=True)
class Point:
    ts: datetime
    value: float


@dataclass(slots=True)
class LogRow:
    ts: datetime
    service: str
    level: str
    message: str
    template: str
    template_hash: str
    trace_id: str | None
    attributes: dict[str, Any]


@dataclass(slots=True)
class SpanRow:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    service: str
    operation: str
    start_ts: datetime
    duration_ms: float
    status: str
    attributes: dict[str, Any]
    kind: str = "internal"


async def write_metrics(session: AsyncSession, project_id: str, rows: Iterable[dict[str, Any]]) -> int:
    objs = [MetricPoint(project_id=project_id, **r) for r in rows]
    if not objs:
        return 0
    session.add_all(objs)
    m.INGEST_RECORDS.labels("metrics").inc(len(objs))
    return len(objs)


async def write_logs(session: AsyncSession, project_id: str, rows: Iterable[dict[str, Any]]) -> int:
    objs = [LogRecord(project_id=project_id, **r) for r in rows]
    if not objs:
        return 0
    session.add_all(objs)
    m.INGEST_RECORDS.labels("logs").inc(len(objs))
    return len(objs)


async def write_spans(session: AsyncSession, project_id: str, rows: Iterable[dict[str, Any]]) -> int:
    objs = [Span(project_id=project_id, **r) for r in rows]
    if not objs:
        return 0
    session.add_all(objs)
    m.INGEST_RECORDS.labels("traces").inc(len(objs))
    return len(objs)


async def metric_series(
    session: AsyncSession, project_id: str, service: str, name: str, start: datetime, end: datetime
) -> list[Point]:
    stmt = (
        select(MetricPoint.ts, MetricPoint.value)
        .where(
            MetricPoint.project_id == project_id,
            MetricPoint.service == service,
            MetricPoint.name == name,
            MetricPoint.ts >= start,
            MetricPoint.ts <= end,
        )
        .order_by(MetricPoint.ts)
    )
    with m.timed(m.DB_LATENCY, op="metric_series"):
        rows = (await session.execute(stmt)).all()
    return [Point(ts=r[0], value=r[1]) for r in rows]


async def metric_names(session: AsyncSession, project_id: str, service: str, since: datetime) -> list[str]:
    stmt = (
        select(MetricPoint.name)
        .where(MetricPoint.project_id == project_id, MetricPoint.service == service, MetricPoint.ts >= since)
        .distinct()
    )
    return [r[0] for r in (await session.execute(stmt)).all()]


async def latest_metrics(session: AsyncSession, project_id: str, since: datetime) -> dict[str, dict[str, float]]:
    """Latest value of every (service, metric) since ``since`` → {service: {name: value}}."""
    sub = (
        select(MetricPoint.service, MetricPoint.name, func.max(MetricPoint.ts).label("ts"))
        .where(MetricPoint.project_id == project_id, MetricPoint.ts >= since)
        .group_by(MetricPoint.service, MetricPoint.name)
        .subquery()
    )
    stmt = select(MetricPoint.service, MetricPoint.name, MetricPoint.value).join(
        sub,
        (MetricPoint.service == sub.c.service) & (MetricPoint.name == sub.c.name) & (MetricPoint.ts == sub.c.ts),
    ).where(MetricPoint.project_id == project_id)
    out: dict[str, dict[str, float]] = {}
    for svc, name, val in (await session.execute(stmt)).all():
        out.setdefault(svc, {})[name] = val
    return out


async def window_avg(
    session: AsyncSession, project_id: str, name: str, start: datetime, end: datetime, service: str | None = None
) -> dict[str, tuple[float, float, float, int]]:
    """Per-service (avg, max, last, count) over a window for one metric."""
    stmt = select(
        MetricPoint.service,
        func.avg(MetricPoint.value),
        func.max(MetricPoint.value),
        func.count(MetricPoint.id),
    ).where(
        MetricPoint.project_id == project_id, MetricPoint.name == name, MetricPoint.ts >= start, MetricPoint.ts <= end
    )
    if service:
        stmt = stmt.where(MetricPoint.service == service)
    stmt = stmt.group_by(MetricPoint.service)
    out: dict[str, tuple[float, float, float, int]] = {}
    for svc, avg, mx, cnt in (await session.execute(stmt)).all():
        last_stmt = (
            select(MetricPoint.value)
            .where(MetricPoint.project_id == project_id, MetricPoint.name == name, MetricPoint.service == svc, MetricPoint.ts <= end)
            .order_by(MetricPoint.ts.desc())
            .limit(1)
        )
        last = (await session.execute(last_stmt)).scalar() or 0.0
        out[svc] = (float(avg or 0), float(mx or 0), float(last), int(cnt))
    return out


async def logs_window(
    session: AsyncSession,
    project_id: str,
    services: Sequence[str],
    start: datetime,
    end: datetime,
    *,
    levels: Sequence[str] | None = None,
    limit: int = 5000,
) -> list[LogRow]:
    stmt = (
        select(LogRecord)
        .where(LogRecord.project_id == project_id, LogRecord.ts >= start, LogRecord.ts <= end)
        .order_by(LogRecord.ts)
        .limit(limit)
    )
    if services:
        stmt = stmt.where(LogRecord.service.in_(list(services)))
    if levels:
        stmt = stmt.where(LogRecord.level.in_(list(levels)))
    with m.timed(m.DB_LATENCY, op="logs_window"):
        rows = (await session.execute(stmt)).scalars().all()
    return [
        LogRow(r.ts, r.service, r.level, r.message, r.template, r.template_hash, r.trace_id, r.attributes or {})
        for r in rows
    ]


async def spans_window(
    session: AsyncSession, project_id: str, services: Sequence[str], start: datetime, end: datetime, *, limit: int = 20000
) -> list[SpanRow]:
    stmt = (
        select(Span)
        .where(Span.project_id == project_id, Span.start_ts >= start, Span.start_ts <= end)
        .order_by(Span.start_ts)
        .limit(limit)
    )
    if services:
        stmt = stmt.where(Span.service.in_(list(services)))
    with m.timed(m.DB_LATENCY, op="spans_window"):
        rows = (await session.execute(stmt)).scalars().all()
    return [
        SpanRow(r.trace_id, r.span_id, r.parent_span_id, r.service, r.operation, r.start_ts, r.duration_ms, r.status, r.attributes or {}, r.kind or "internal")
        for r in rows
    ]


async def deployments_window(
    session: AsyncSession, project_id: str, start: datetime, end: datetime, services: Sequence[str] | None = None
) -> list[Deployment]:
    stmt = (
        select(Deployment)
        .where(Deployment.project_id == project_id, Deployment.deployed_at >= start, Deployment.deployed_at <= end)
        .order_by(Deployment.deployed_at)
    )
    if services:
        stmt = stmt.where(Deployment.service.in_(list(services)))
    return list((await session.execute(stmt)).scalars().all())


async def purge_older_than(session: AsyncSession, cutoff: datetime) -> dict[str, int]:
    """Retention job: drop raw telemetry older than ``cutoff``."""
    out = {}
    for model, col, key in ((MetricPoint, MetricPoint.ts, "metrics"), (LogRecord, LogRecord.ts, "logs"), (Span, Span.start_ts, "spans")):
        res = await session.execute(delete(model).where(col < cutoff))
        out[key] = int(res.rowcount or 0)
    return out


def split_windows(onset: datetime, now: datetime, baseline_min: int, pad_s: int = 30) -> tuple[datetime, datetime, datetime, datetime]:
    """Return (baseline_start, baseline_end, incident_start, incident_end)."""
    b_end = onset - timedelta(seconds=pad_s)
    b_start = b_end - timedelta(minutes=baseline_min)
    return b_start, b_end, onset - timedelta(seconds=pad_s), now
