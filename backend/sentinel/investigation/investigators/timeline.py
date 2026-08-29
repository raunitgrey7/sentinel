"""Timeline investigator — collects change events and detection markers.

Runs first so later investigators can append onset markers via ``ctx.add_timeline``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from sentinel.db.models import Alert
from sentinel.investigation.context import InvestigationContext
from sentinel.telemetry.store import deployments_window

NAME = "timeline"
LABEL = "Timeline"


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    inc = ctx.incident
    w = ctx.windows
    deployments = await deployments_window(ctx.session, ctx.project_id, w.lookback_start, w.incident_end)
    for d in deployments:
        ctx.add_timeline(d.deployed_at, "deployment", f"{d.service} {d.version} deployed" + (f" (commit {d.commit_sha[:8]})" if d.commit_sha else ""), service=d.service, version=d.version, deployment_id=d.id)
    alerts = (await ctx.session.execute(select(Alert).where(Alert.incident_id == inc.id).order_by(Alert.fired_at))).scalars().all()
    for a in alerts:
        ctx.add_timeline(a.fired_at, "alert", f"Alert {a.rule_name} fired on {a.service} ({a.severity})", alert_id=a.id, value=a.value)
    if ctx.investigation.started_at:
        ctx.add_timeline(ctx.investigation.started_at, "investigation", "Investigation started", investigation_id=ctx.investigation.id)
    ctx.notes["alerts"] = [
        {"id": a.id, "rule_name": a.rule_name, "service": a.service, "severity": a.severity, "value": a.value, "fired_at": a.fired_at.isoformat()}
        for a in alerts
    ]
    ctx.notes["deployments_in_lookback"] = len(deployments)
    return {"deployments": len(deployments), "alerts": len(alerts)}
