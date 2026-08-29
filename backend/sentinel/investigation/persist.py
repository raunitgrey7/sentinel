"""Persistence step — write evidence, hypotheses, clusters, graph, timeline and actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete

from sentinel.core.timeutil import parse_ts, utcnow
from sentinel.db.models import (
    ErrorCluster,
    Evidence,
    GraphEdge,
    GraphNode,
    Hypothesis,
    IncidentEvent,
    RemediationAction,
)
from sentinel.domain.enums import HypothesisStatus, IncidentStatus
from sentinel.investigation.context import InvestigationContext
from sentinel.investigation.graph import build_graph
from sentinel.investigation.scoring import Candidate
from sentinel.observability import metrics as m
from sentinel.remediation.playbooks import actions_for
from sentinel.services.incidents import add_event, transition

NAME = "persist"
LABEL = "Persist Results"


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    s = ctx.session
    inc = ctx.incident
    inv = ctx.investigation

    # Idempotent: wipe prior results for this incident (re-investigation replaces them).
    for model in (Evidence, Hypothesis, ErrorCluster, GraphNode, GraphEdge):
        await s.execute(delete(model).where(model.incident_id == inc.id))
    await s.execute(delete(IncidentEvent).where(IncidentEvent.incident_id == inc.id, IncidentEvent.kind.in_(["deployment", "metric", "log", "alert", "investigation"])))
    await s.execute(delete(RemediationAction).where(RemediationAction.incident_id == inc.id, RemediationAction.status == "proposed"))

    for e in ctx.evidence.items:
        s.add(
            Evidence(
                incident_id=inc.id,
                investigation_id=inv.id,
                ref=e.ref,
                kind=e.kind,
                service=e.service,
                source=e.source,
                summary=e.summary,
                detail=e.detail,
                signals=e.signals,
                weight=e.weight,
                direction=e.direction,
                ts_start=e.ts_start,
                ts_end=e.ts_end,
            )
        )

    for c in ctx.notes.get("error_clusters", []):
        row = dict(c)
        for k in ("first_ts", "last_ts"):
            if isinstance(row.get(k), str):
                row[k] = parse_ts(row[k])
        s.add(ErrorCluster(incident_id=inc.id, **row))

    hyps = ctx.verification.get("hypotheses") or []
    top = hyps[0] if hyps else None
    for h in hyps:
        s.add(
            Hypothesis(
                incident_id=inc.id,
                investigation_id=inv.id,
                category=h["category"],
                title=h["title"],
                description=h.get("description", ""),
                culprit_service=h.get("culprit_service"),
                score=float(h["score"]),
                confidence=float(h["confidence"]),
                rank=int(h["rank"]),
                status=HypothesisStatus.VERIFIED if h["verification"]["supported"] else HypothesisStatus.REJECTED,
                score_breakdown=h.get("breakdown", {}),
                supporting_evidence=h.get("supporting", []),
                contradicting_evidence=h.get("contradicting", []),
                reasoning=h.get("reasoning", ""),
                verification=h.get("verification", {}),
                remediation=h.get("remediation", []),
            )
        )

    # timeline
    seen: set[tuple[str, str]] = set()
    for t in sorted(ctx.timeline, key=lambda t: t["ts"]):
        key = (t["kind"], t["message"])
        if key in seen:
            continue
        seen.add(key)
        await add_event(s, inc.id, t["kind"], t["message"], ts=t["ts"], data=t.get("data", {}))

    # graph
    cands = [
        Candidate(
            category=h["category"], title=h["title"], description=h.get("description", ""), culprit_service=h.get("culprit_service"),
            score=float(h["confidence"]), breakdown=h.get("breakdown", {}), supporting=h.get("supporting", []), contradicting=h.get("contradicting", []), rank=int(h["rank"]),
        )
        for h in hyps
    ]
    graph = build_graph(
        incident_key=inc.key,
        incident_title=inc.title,
        primary=inc.primary_service,
        affected=list(inc.affected_services or []),
        service_graph=ctx.service_graph,
        scope=ctx.scope_services,
        bag=ctx.evidence,
        candidates=cands,
        deployments=[d for d in ctx.notes.get("deployments", []) if d.get("proximity", 0) > 0],
        historical=ctx.notes.get("historical", []),
        alerts=ctx.notes.get("alerts", []),
    )
    for n in graph.nodes.values():
        s.add(GraphNode(incident_id=inc.id, key=n["key"], type=n["type"], label=n["label"][:255], data=n["data"]))
    for e in graph.edges:
        s.add(GraphEdge(incident_id=inc.id, source=e["source"], target=e["target"], relation=e["relation"], weight=e["weight"], data=e["data"]))

    # incident outcome + remediation
    now = utcnow()
    if top:
        inc.root_cause_category = top["category"]
        inc.root_cause_summary = f"{top['title']} — {ctx.synthesis.get('summary', '')}".strip(" —")
        inc.confidence = float(top["confidence"])
        m.HYPOTHESIS_CONFIDENCE.observe(float(top["confidence"]))
        for a in actions_for(top["category"], culprit_service=top.get("culprit_service"), latest_deployment=ctx.notes.get("latest_deployment")):
            s.add(RemediationAction(incident_id=inc.id, hypothesis_id=None, **a))
        low = float(top["confidence"]) < ctx.settings.low_confidence_threshold or not top["verification"]["supported"]
        target = IncidentStatus.LOW_CONFIDENCE if low else IncidentStatus.ROOT_CAUSE_IDENTIFIED
        await transition(s, inc, target, note=f"{top['title']} ({top['confidence']:.0%})")
        if low:
            await transition(s, inc, IncidentStatus.HUMAN_REVIEW, note="confidence below threshold or verification failed")
        else:
            await transition(s, inc, IncidentStatus.REMEDIATION_PROPOSED, note="playbook actions proposed; awaiting human approval")
        ctx.add_timeline(now, "investigation", f"Root-cause hypothesis: {top['title']} ({top['confidence']:.0%} confidence)")
    else:
        await transition(s, inc, IncidentStatus.LOW_CONFIDENCE, note="no hypothesis generated")
        await transition(s, inc, IncidentStatus.HUMAN_REVIEW)

    inv.summary = {
        "top": {k: top[k] for k in ("category", "title", "confidence", "culprit_service")} if top else None,
        "evidence": len(ctx.evidence.items),
        "hypotheses": len(hyps),
        "synthesis": {k: ctx.synthesis.get(k) for k in ("summary", "caveats", "provider", "model", "dropped_invalid_citations")},
        "signals": ctx.evidence.signals(),
        "scope": ctx.scope_services,
    }
    return {"evidence": len(ctx.evidence.items), "hypotheses": len(hyps), "graph_nodes": len(graph.nodes), "graph_edges": len(graph.edges)}
