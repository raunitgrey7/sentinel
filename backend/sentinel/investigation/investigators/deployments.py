"""Deployment investigator — change events (versions, commits, files, config) near onset."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from sentinel.domain.enums import EvidenceKind
from sentinel.investigation.context import InvestigationContext
from sentinel.telemetry.store import deployments_window

NAME = "deployments"
LABEL = "Deployment Investigator"

DB_TOUCH = re.compile(r"(pool|connection|concurren|transaction|db|database|sql|worker)", re.I)
CONFIG_FILE = re.compile(r"(\.ya?ml$|\.toml$|\.env|config|settings|flags?)", re.I)
PROXIMITY_WINDOW_MIN = 20.0


def proximity_score(minutes_before_onset: float) -> float:
    """1.0 at onset, linear decay to 0 at PROXIMITY_WINDOW_MIN; deploys *after* onset get a small score."""
    if minutes_before_onset < -3:
        return 0.0
    if minutes_before_onset < 0:
        return 0.3
    return max(0.0, 1.0 - minutes_before_onset / PROXIMITY_WINDOW_MIN)


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    w = ctx.windows
    onset = ctx.incident.started_at
    deployments = await deployments_window(
        ctx.session, ctx.project_id, w.lookback_start, w.incident_end, services=ctx.scope_services
    )
    best_prox = 0.0
    latest: dict[str, Any] | None = None
    records: list[dict[str, Any]] = []
    deploy_services: set[str] = set()
    for d in deployments:
        mins_before = (onset - d.deployed_at).total_seconds() / 60
        prox = proximity_score(mins_before)
        rec = {
            "id": d.id,
            "service": d.service,
            "version": d.version,
            "previous_version": d.previous_version,
            "commit_sha": d.commit_sha,
            "commit_message": d.commit_message,
            "changed_files": list(d.changed_files or []),
            "config_changes": dict(d.config_changes or {}),
            "deployed_at": d.deployed_at.isoformat(),
            "minutes_before_onset": round(mins_before, 1),
            "proximity": round(prox, 3),
        }
        records.append(rec)
        if prox <= 0:
            continue
        deploy_services.add(d.service)
        signals = ["deploy_recent"]
        touched = [f for f in (d.changed_files or []) if DB_TOUCH.search(str(f))]
        if touched or DB_TOUCH.search(d.commit_message or ""):
            signals.append("deploy_touches_db_config")
        cfg_files = [f for f in (d.changed_files or []) if CONFIG_FILE.search(str(f))]
        if d.config_changes or cfg_files:
            signals.append("config_change_recent")
        when = f"{mins_before:.0f} min before onset" if mins_before >= 0 else f"{-mins_before:.0f} min after onset"
        summary = f"deployment {d.service} {d.previous_version or '?'} → {d.version} completed {when}"
        if d.commit_sha:
            summary += f"; commit {d.commit_sha[:8]} \"{(d.commit_message or '')[:80]}\""
        if touched:
            summary += f"; touches {', '.join(touched[:3])}"
        if d.config_changes:
            summary += f"; config changes: {', '.join(f'{k}={v}' for k, v in list(d.config_changes.items())[:3])}"
        weight = max(0.35, prox)
        ctx.evidence.add(
            EvidenceKind.DEPLOYMENT if not d.config_changes else EvidenceKind.CONFIG,
            f"deployments:{d.service}",
            summary,
            service=d.service,
            signals=signals,
            weight=weight,
            detail={"deployment_id": d.id, **rec},
            ts_start=d.deployed_at,
        )
        if prox > best_prox:
            best_prox = prox
            latest = rec
    if latest and len(deploy_services) == 1 and latest["service"] in (ctx.primary, *ctx.incident.affected_services):
        ctx.evidence.add(
            EvidenceKind.DEPLOYMENT,
            "deployments:scope",
            f"{latest['service']} is the only service in scope with a deployment in the last {int((onset - w.lookback_start).total_seconds() // 60)} minutes",
            service=latest["service"],
            signals=["deploy_only_changed_service"],
            weight=0.6,
            detail={"deployment_id": latest["id"]},
        )
    if not deployments:
        ctx.evidence.add(
            EvidenceKind.DEPLOYMENT,
            "deployments:scope",
            f"no deployments or configuration changes in scope during the {int((w.incident_end - w.lookback_start).total_seconds() // 60)} minutes before detection",
            service=ctx.primary,
            signals=["no_recent_change"],
            weight=0.5,
            direction="neutral",
        )
    ctx.notes["deployments"] = records
    ctx.notes["deploy_proximity"] = best_prox
    ctx.notes["latest_deployment"] = latest
    ctx.notes["lookback_from"] = (onset - timedelta(minutes=ctx.settings.incident_lookback_min)).isoformat()
    return {"deployments": len(deployments), "best_proximity": round(best_prox, 3)}
