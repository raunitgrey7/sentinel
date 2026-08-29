from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from sentinel.api.deps import DB, Engineer, Sre, Viewer
from sentinel.api.schemas import (
    ErrorClusterOut,
    EventOut,
    EvidenceOut,
    HypothesisOut,
    IncidentCreate,
    IncidentOut,
    IncidentResolve,
    IncidentTransition,
    InvestigationOut,
    Page,
    PostmortemOut,
    RemediationDecision,
    RemediationOut,
    WhyRequest,
)
from sentinel.core.errors import Conflict, NotFound
from sentinel.core.timeutil import utcnow
from sentinel.db.models import (
    ErrorCluster,
    Evidence,
    GraphEdge,
    GraphNode,
    Hypothesis,
    Incident,
    Investigation,
    Postmortem,
    RemediationAction,
)
from sentinel.domain.enums import IncidentStatus, RootCauseCategory
from sentinel.domain.state_machine import allowed_targets
from sentinel.remediation import service as remediation
from sentinel.reporting import postmortem as pm_service
from sentinel.reporting import why as why_service
from sentinel.services import audit
from sentinel.services.incidents import (
    add_event,
    create_incident,
    get_incident,
    timeline,
    transition,
)
from sentinel.services.projects import ensure_service, get_project
from sentinel.services.simulator_client import SimulatorClient
from sentinel.worker.jobs import enqueue_investigation

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=Page[IncidentOut])
async def list_incidents(
    _: Viewer,
    session: DB,
    project: str | None = None,
    status: str | None = None,
    open_only: bool = False,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[IncidentOut]:
    stmt = select(Incident)
    if project:
        p = await get_project(session, project)
        stmt = stmt.where(Incident.project_id == p.id)
    if status:
        stmt = stmt.where(Incident.status == status)
    if open_only:
        from sentinel.domain.enums import OPEN_STATUSES

        stmt = stmt.where(Incident.status.in_([s.value for s in OPEN_STATUSES]))
    total = int((await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0)
    rows = (await session.execute(stmt.order_by(Incident.detected_at.desc()).limit(limit).offset(offset))).scalars().all()
    return Page(items=[IncidentOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=IncidentOut, status_code=202)
async def create_incident_ep(body: IncidentCreate, p: Engineer, session: DB) -> Incident:
    proj = await get_project(session, body.project)
    await ensure_service(session, proj.id, body.primary_service)
    inc = await create_incident(
        session,
        project_id=proj.id,
        title=body.title,
        primary_service=body.primary_service,
        severity=body.severity,
        description=body.description,
        affected_services=body.affected_services,
        started_at=body.started_at,
        created_by=p.id,
        trigger={"source": "manual"},
    )
    await session.commit()
    if body.investigate:
        await enqueue_investigation(inc.id, trigger="manual")
    return inc


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident_ep(incident_id: str, _: Viewer, session: DB) -> Incident:
    return await get_incident(session, incident_id)


@router.post("/{incident_id}/investigate", response_model=dict[str, Any], status_code=202)
async def investigate(incident_id: str, p: Engineer, session: DB) -> dict[str, Any]:
    inc = await get_incident(session, incident_id)
    await session.commit()
    job_id = await enqueue_investigation(inc.id, trigger="manual", force_new=True)
    await audit.record(session, action="incident.investigate", resource_type="incident", resource_id=inc.id, actor_id=p.id)
    return {"queued": job_id is not None, "job_id": job_id}


@router.post("/{incident_id}/transition", response_model=IncidentOut)
async def transition_ep(incident_id: str, body: IncidentTransition, p: Engineer, session: DB) -> Incident:
    inc = await get_incident(session, incident_id)
    await transition(session, inc, IncidentStatus(body.status), actor=p.id, note=body.note)
    await audit.record(session, action="incident.transition", resource_type="incident", resource_id=inc.id, actor_id=p.id, detail={"to": body.status}, reason=body.note)
    return inc


@router.get("/{incident_id}/transitions", response_model=list[str])
async def transitions_ep(incident_id: str, _: Viewer, session: DB) -> list[str]:
    inc = await get_incident(session, incident_id)
    return [s.value for s in allowed_targets(inc.status)]


@router.post("/{incident_id}/resolve", response_model=IncidentOut)
async def resolve(incident_id: str, body: IncidentResolve, p: Engineer, session: DB) -> Incident:
    inc = await get_incident(session, incident_id)
    if body.root_cause_category:
        RootCauseCategory(body.root_cause_category)
        inc.root_cause_category = body.root_cause_category
    inc.resolution_notes = body.notes
    await transition(session, inc, IncidentStatus.RESOLVED, actor=p.id, note=body.notes)
    await audit.record(session, action="incident.resolve", resource_type="incident", resource_id=inc.id, actor_id=p.id, reason=body.notes)
    return inc


@router.get("/{incident_id}/timeline", response_model=list[EventOut])
async def timeline_ep(incident_id: str, _: Viewer, session: DB) -> list[Any]:
    inc = await get_incident(session, incident_id)
    return await timeline(session, inc.id)


@router.get("/{incident_id}/evidence", response_model=list[EvidenceOut])
async def evidence_ep(incident_id: str, _: Viewer, session: DB) -> list[Evidence]:
    inc = await get_incident(session, incident_id)
    rows = (await session.execute(select(Evidence).where(Evidence.incident_id == inc.id))).scalars().all()
    return sorted(rows, key=lambda e: int(e.ref[1:]) if e.ref[1:].isdigit() else 0)


@router.get("/{incident_id}/hypotheses", response_model=list[HypothesisOut])
async def hypotheses_ep(incident_id: str, _: Viewer, session: DB) -> list[Hypothesis]:
    inc = await get_incident(session, incident_id)
    return list((await session.execute(select(Hypothesis).where(Hypothesis.incident_id == inc.id).order_by(Hypothesis.rank))).scalars().all())


@router.get("/{incident_id}/clusters", response_model=list[ErrorClusterOut])
async def clusters_ep(incident_id: str, _: Viewer, session: DB) -> list[ErrorCluster]:
    inc = await get_incident(session, incident_id)
    return list((await session.execute(select(ErrorCluster).where(ErrorCluster.incident_id == inc.id).order_by(ErrorCluster.count.desc()))).scalars().all())


@router.get("/{incident_id}/investigations", response_model=list[InvestigationOut])
async def investigations_ep(incident_id: str, _: Viewer, session: DB) -> list[Investigation]:
    inc = await get_incident(session, incident_id)
    stmt = select(Investigation).where(Investigation.incident_id == inc.id).options(selectinload(Investigation.steps)).order_by(Investigation.queued_at.desc())
    return list((await session.execute(stmt)).scalars().all())


@router.get("/{incident_id}/graph")
async def graph_ep(incident_id: str, _: Viewer, session: DB) -> dict[str, Any]:
    inc = await get_incident(session, incident_id)
    nodes = (await session.execute(select(GraphNode).where(GraphNode.incident_id == inc.id))).scalars().all()
    edges = (await session.execute(select(GraphEdge).where(GraphEdge.incident_id == inc.id))).scalars().all()
    return {
        "nodes": [{"key": n.key, "type": n.type, "label": n.label, "data": n.data} for n in nodes],
        "edges": [{"source": e.source, "target": e.target, "relation": e.relation, "weight": e.weight} for e in edges],
    }


@router.post("/{incident_id}/why")
async def why_ep(incident_id: str, body: WhyRequest, p: Viewer, session: DB) -> dict[str, Any]:
    inc = await get_incident(session, incident_id)
    out = await why_service.answer(session, inc, body.question, hypothesis_id=body.hypothesis_id)
    await add_event(session, inc.id, "note", f"Q: {body.question[:120]}", actor=p.id, hypothesis_id=body.hypothesis_id)
    return out


@router.post("/{incident_id}/verify", response_model=list[HypothesisOut])
async def verify_ep(incident_id: str, _: Engineer, session: DB) -> list[Hypothesis]:
    """Re-run deterministic verification over persisted evidence (no model)."""
    from sentinel.investigation.context import EvidenceBag
    from sentinel.investigation.verifier import verify_hypothesis

    inc = await get_incident(session, incident_id)
    ev = (await session.execute(select(Evidence).where(Evidence.incident_id == inc.id))).scalars().all()
    bag = EvidenceBag()
    bag.load([{"ref": e.ref, "kind": e.kind, "source": e.source, "summary": e.summary, "service": e.service, "signals": e.signals, "weight": e.weight, "direction": e.direction, "detail": e.detail} for e in ev])
    hyps = (await session.execute(select(Hypothesis).where(Hypothesis.incident_id == inc.id).order_by(Hypothesis.rank))).scalars().all()

    class _Ctx:
        evidence = bag

    for h in hyps:
        v = verify_hypothesis({"category": h.category, "score": h.score, "llm_supporting": h.supporting_evidence, "llm_contradicting": h.contradicting_evidence, "citation_validity": 1.0}, _Ctx())  # type: ignore[arg-type]
        h.verification = v
        h.confidence = v["confidence"]
        h.supporting_evidence = v["supporting"]
        h.contradicting_evidence = v["contradicting"]
    ordered = sorted(hyps, key=lambda h: h.confidence, reverse=True)
    for i, h in enumerate(ordered, 1):
        h.rank = i
    if ordered:
        inc.confidence = ordered[0].confidence
        inc.root_cause_category = ordered[0].category
    return ordered


# ---- remediation --------------------------------------------------------------------------
@router.get("/{incident_id}/remediation", response_model=list[RemediationOut])
async def remediation_list(incident_id: str, _: Viewer, session: DB) -> list[RemediationAction]:
    inc = await get_incident(session, incident_id)
    return list((await session.execute(select(RemediationAction).where(RemediationAction.incident_id == inc.id).order_by(RemediationAction.created_at))).scalars().all())


@router.post("/{incident_id}/remediation/{action_id}/request", response_model=RemediationOut)
async def remediation_request(incident_id: str, action_id: str, body: RemediationDecision, p: Engineer, session: DB) -> RemediationAction:
    a = await remediation.get_action(session, action_id)
    return await remediation.request(session, a, actor_id=p.id, role=p.role, note=body.note)


@router.post("/{incident_id}/remediation/{action_id}/approve", response_model=RemediationOut)
async def remediation_approve(incident_id: str, action_id: str, body: RemediationDecision, p: Sre, session: DB) -> RemediationAction:
    a = await remediation.get_action(session, action_id)
    inc = await get_incident(session, incident_id)
    out = await remediation.approve(session, a, actor_id=p.id, role=p.role, note=body.note)
    if inc.status in (IncidentStatus.REMEDIATION_PROPOSED, IncidentStatus.ROOT_CAUSE_IDENTIFIED, IncidentStatus.HUMAN_REVIEW):
        await transition(session, inc, IncidentStatus.AWAITING_HUMAN, actor=p.id, note="remediation approved")
    return out


@router.post("/{incident_id}/remediation/{action_id}/reject", response_model=RemediationOut)
async def remediation_reject(incident_id: str, action_id: str, body: RemediationDecision, p: Sre, session: DB) -> RemediationAction:
    a = await remediation.get_action(session, action_id)
    return await remediation.reject(session, a, actor_id=p.id, role=p.role, note=body.note)


@router.post("/{incident_id}/remediation/{action_id}/execute", response_model=RemediationOut)
async def remediation_execute(incident_id: str, action_id: str, p: Sre, session: DB) -> RemediationAction:
    a = await remediation.get_action(session, action_id)
    if a.incident_id != (await get_incident(session, incident_id)).id:
        raise NotFound("action does not belong to this incident")
    return await remediation.execute(session, a, SimulatorClient(), actor_id=p.id, role=p.role)


# ---- postmortem ---------------------------------------------------------------------------
@router.get("/{incident_id}/postmortem", response_model=PostmortemOut)
async def postmortem_get(incident_id: str, _: Viewer, session: DB) -> Postmortem:
    inc = await get_incident(session, incident_id)
    pm = (await session.execute(select(Postmortem).where(Postmortem.incident_id == inc.id).order_by(Postmortem.version.desc()).limit(1))).scalar_one_or_none()
    if pm is None:
        raise NotFound("no postmortem generated yet")
    return pm


@router.post("/{incident_id}/postmortem", response_model=PostmortemOut, status_code=201)
async def postmortem_generate(incident_id: str, p: Engineer, session: DB) -> Postmortem:
    inc = await get_incident(session, incident_id)
    if inc.status in (IncidentStatus.DETECTED, IncidentStatus.INVESTIGATING):
        raise Conflict("investigation has not completed yet")
    pm = await pm_service.generate(session, inc, actor=p.id)
    if inc.status == IncidentStatus.RESOLVED:
        await transition(session, inc, IncidentStatus.POSTMORTEM, actor=p.id)
    await add_event(session, inc.id, "note", f"Postmortem v{pm.version} generated", actor=p.id, ts=utcnow())
    await audit.record(session, action="postmortem.generate", resource_type="incident", resource_id=inc.id, actor_id=p.id)
    return pm
