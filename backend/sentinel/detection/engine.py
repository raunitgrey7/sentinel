"""Detection engine.

Two inputs, one output:

* ``evaluate_rules``   — periodic evaluation of ``DetectionRule`` rows over ingested metrics
* ``ingest_alertmanager`` — Alertmanager webhook payloads (Prometheus path)

Both create/refresh ``Alert`` rows keyed by fingerprint and map firing alerts to incidents:
an alert on a service that already has an open incident is attached to it; otherwise a
new incident is opened, its onset is estimated from the first threshold crossing, and an
investigation is queued (idempotent on the incident id).
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.analysis.stats import first_crossing, sustained
from sentinel.core.config import get_settings
from sentinel.core.logging import get_logger
from sentinel.core.timeutil import parse_ts, utcnow
from sentinel.db.models import Alert, DetectionRule, Incident, MetricPoint
from sentinel.domain.enums import AlertStatus, Severity
from sentinel.observability import metrics as m
from sentinel.services.incidents import add_event, create_incident, find_open_incident_for

log = get_logger(__name__)

SEVERITY_ORDER = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def fingerprint(project_id: str, rule: str, service: str) -> str:
    return hashlib.sha1(f"{project_id}|{rule}|{service}".encode(), usedforsecurity=False).hexdigest()[:24]


async def _services_with_metric(session: AsyncSession, project_id: str, metric: str, since) -> list[str]:  # type: ignore[no-untyped-def]
    stmt = select(MetricPoint.service).where(MetricPoint.project_id == project_id, MetricPoint.name == metric, MetricPoint.ts >= since).distinct()
    return [r[0] for r in (await session.execute(stmt)).all()]


async def evaluate_rules(session: AsyncSession, project_id: str, *, enqueue: Any | None = None) -> dict[str, Any]:
    """Evaluate every enabled rule for a project. Returns a summary of fired/resolved alerts."""
    now = utcnow()
    rules = (await session.execute(select(DetectionRule).where(DetectionRule.project_id == project_id, DetectionRule.enabled.is_(True)))).scalars().all()
    fired: list[str] = []
    resolved: list[str] = []
    new_incidents: list[str] = []
    for rule in rules:
        since = now - timedelta(seconds=rule.window_s + rule.for_s)
        services = [rule.service] if rule.service else await _services_with_metric(session, project_id, rule.metric, since)
        for svc in services:
            stmt = (
                select(MetricPoint.ts, MetricPoint.value)
                .where(MetricPoint.project_id == project_id, MetricPoint.service == svc, MetricPoint.name == rule.metric, MetricPoint.ts >= since)
                .order_by(MetricPoint.ts)
            )
            from sentinel.telemetry.store import Point

            series = [Point(ts=r[0], value=r[1]) for r in (await session.execute(stmt)).all()]
            if not series or (now - series[-1].ts).total_seconds() > rule.window_s:
                continue  # stale — service stopped reporting; not this rule's job
            if rule.name == "ThroughputCollapse":
                # only meaningful for services that had traffic in the baseline
                base_since = now - timedelta(minutes=10)
                base_stmt = select(MetricPoint.value).where(MetricPoint.project_id == project_id, MetricPoint.service == svc, MetricPoint.name == rule.metric, MetricPoint.ts >= base_since, MetricPoint.ts < since)
                base_vals = [r[0] for r in (await session.execute(base_stmt)).all()]
                if not base_vals or max(base_vals) < 3:
                    continue
            ok, value = sustained(series, rule.threshold, rule.comparator, rule.for_s)
            fp = fingerprint(project_id, rule.name, svc)
            existing = (await session.execute(select(Alert).where(Alert.project_id == project_id, Alert.fingerprint == fp, Alert.status == AlertStatus.FIRING))).scalar_one_or_none()
            if ok:
                if existing:
                    existing.value = value
                    continue
                onset = first_crossing(series, rule.threshold, rule.comparator) or now
                alert = Alert(
                    project_id=project_id,
                    rule_name=rule.name,
                    service=svc,
                    severity=rule.severity,
                    status=AlertStatus.FIRING,
                    source="sentinel",
                    fingerprint=fp,
                    value=value,
                    labels={"metric": rule.metric, "comparator": rule.comparator, "threshold": rule.threshold},
                    annotations={"description": rule.description},
                    fired_at=now,
                )
                session.add(alert)
                await session.flush()
                fired.append(f"{rule.name}@{svc}")
                inc_id, created = await attach_alert_to_incident(session, alert, onset=onset, enqueue=enqueue)
                if created:
                    new_incidents.append(inc_id)
            elif existing:
                existing.status = AlertStatus.RESOLVED
                existing.resolved_at = now
                resolved.append(f"{rule.name}@{svc}")
                if existing.incident_id:
                    await add_event(session, existing.incident_id, "alert", f"Alert {rule.name} on {svc} resolved", alert_id=existing.id)
    m.DETECTOR_RUNS.labels("ok").inc()
    return {"fired": fired, "resolved": resolved, "incidents": new_incidents, "rules": len(rules)}


async def _find_related_open_incident(session: AsyncSession, project_id: str, service: str) -> tuple[Incident | None, str]:
    """Blast-radius merging over the dependency graph.

    * alert on a *caller* of an open incident's primary → same incident (symptom)
    * alert on a *callee* of an open incident's primary → same incident, and the callee
      becomes the primary (it is the more likely cause)
    """
    from sentinel.domain.enums import OPEN_STATUSES
    from sentinel.services.projects import load_service_graph

    direct = await find_open_incident_for(session, project_id, service)
    if direct:
        return direct, "direct"
    graph = await load_service_graph(session, project_id)
    stmt = select(Incident).where(Incident.project_id == project_id, Incident.status.in_([s.value for s in OPEN_STATUSES])).order_by(Incident.created_at.desc())
    for inc in (await session.execute(stmt)).scalars().all():
        if (utcnow() - inc.detected_at).total_seconds() > 15 * 60:
            continue  # only merge into recent incidents
        if service in graph.upstream(inc.primary_service):
            return inc, "upstream"
        if service in graph.downstream(inc.primary_service):
            return inc, "downstream"
    return None, "none"


async def attach_alert_to_incident(session: AsyncSession, alert: Alert, *, onset, enqueue: Any | None = None) -> tuple[str, bool]:  # type: ignore[no-untyped-def]
    settings = get_settings()
    existing, relation = await _find_related_open_incident(session, alert.project_id, alert.service)
    if existing:
        alert.incident_id = existing.id
        if alert.service not in (existing.affected_services or []):
            existing.affected_services = sorted(set([*(existing.affected_services or []), alert.service]))
        if SEVERITY_ORDER.index(Severity(alert.severity)) > SEVERITY_ORDER.index(Severity(existing.severity)):
            existing.severity = alert.severity
        if onset and onset < existing.started_at:
            existing.started_at = onset
        note = ""
        if relation == "downstream":
            prev = existing.primary_service
            existing.primary_service = alert.service
            existing.title = f"{_humanize(alert.rule_name)} on {alert.service} (impacting {prev})"
            note = f"; {alert.service} is downstream of {prev} and becomes the primary suspect"
        elif relation == "upstream":
            note = f"; {alert.service} depends on {existing.primary_service} (symptom of the same incident)"
        await add_event(session, existing.id, "alert", f"Alert {alert.rule_name} fired on {alert.service} ({alert.severity}){note}", ts=alert.fired_at, alert_id=alert.id, value=alert.value)
        return existing.id, False

    desc = alert.annotations.get("description") or alert.rule_name
    title = f"{_humanize(alert.rule_name)} on {alert.service}"
    inc = await create_incident(
        session,
        project_id=alert.project_id,
        title=title,
        primary_service=alert.service,
        severity=alert.severity,
        description=desc,
        started_at=onset or alert.fired_at,
        detected_at=alert.fired_at,
        trigger={"alert_id": alert.id, "rule": alert.rule_name, "value": alert.value, "labels": alert.labels, "source": alert.source},
        created_by="detector",
    )
    alert.incident_id = inc.id
    await add_event(session, inc.id, "alert", f"Alert {alert.rule_name} fired on {alert.service} ({alert.severity})", ts=alert.fired_at, alert_id=alert.id, value=alert.value)
    await session.flush()
    if settings.auto_investigate and enqueue is not None:
        await enqueue(inc.id)
    log.info("incident opened", incident=inc.key, service=alert.service, rule=alert.rule_name)
    return inc.id, True


def _humanize(name: str) -> str:
    out = ""
    for ch in name:
        if ch.isupper() and out:
            out += " "
        out += ch
    return out.lower().capitalize()


async def ingest_alertmanager(session: AsyncSession, project_id: str, payload: dict[str, Any], *, enqueue: Any | None = None) -> dict[str, Any]:
    """Map an Alertmanager webhook payload (v4) to Sentinel alerts/incidents."""
    fired: list[str] = []
    resolved: list[str] = []
    for a in payload.get("alerts", []):
        labels = a.get("labels", {})
        name = labels.get("alertname", "UnknownAlert")
        svc = labels.get("service") or labels.get("service_name") or labels.get("job") or "unknown"
        sev = (labels.get("severity") or "high").upper()
        if sev not in Severity.__members__:
            sev = "HIGH"
        fp = a.get("fingerprint") or fingerprint(project_id, name, svc)
        status = a.get("status", "firing")
        existing = (await session.execute(select(Alert).where(Alert.project_id == project_id, Alert.fingerprint == fp, Alert.status == AlertStatus.FIRING))).scalar_one_or_none()
        if status == "firing":
            if existing:
                continue
            starts = parse_ts(a.get("startsAt")) if a.get("startsAt") else utcnow()
            alert = Alert(
                project_id=project_id,
                rule_name=name,
                service=svc,
                severity=sev,
                status=AlertStatus.FIRING,
                source="alertmanager",
                fingerprint=fp,
                value=_safe_float(a.get("annotations", {}).get("value")),
                labels=labels,
                annotations=a.get("annotations", {}),
                fired_at=starts,
            )
            session.add(alert)
            await session.flush()
            fired.append(f"{name}@{svc}")
            await attach_alert_to_incident(session, alert, onset=starts - timedelta(seconds=60), enqueue=enqueue)
        elif existing:
            existing.status = AlertStatus.RESOLVED
            existing.resolved_at = parse_ts(a.get("endsAt")) if a.get("endsAt") else utcnow()
            resolved.append(f"{name}@{svc}")
    return {"fired": fired, "resolved": resolved}


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def open_incident_ids(session: AsyncSession, project_id: str) -> list[str]:
    from sentinel.domain.enums import OPEN_STATUSES

    stmt = select(Incident.id).where(Incident.project_id == project_id, Incident.status.in_([s.value for s in OPEN_STATUSES]))
    return [r[0] for r in (await session.execute(stmt)).all()]
