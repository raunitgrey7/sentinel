"""Grounded "Why?" — let an engineer challenge the investigation.

The answer is built from the persisted evidence and the hypothesis under discussion.
The model (if any) only phrases; every handle it cites is validated against the
incident's evidence set before the answer is returned.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.core.timeutil import iso
from sentinel.db.models import Evidence, Hypothesis, Incident
from sentinel.llm import get_provider
from sentinel.llm.prompts import SYSTEM_WHY, why_prompt
from sentinel.llm.schemas import WhyAnswer


async def load_evidence(session: AsyncSession, incident_id: str) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Evidence).where(Evidence.incident_id == incident_id).order_by(Evidence.ref))).scalars().all()
    rows = sorted(rows, key=lambda e: int(e.ref[1:]) if e.ref[1:].isdigit() else 0)
    return [
        {"ref": e.ref, "kind": e.kind, "service": e.service, "source": e.source, "summary": e.summary, "weight": e.weight, "direction": e.direction, "signals": e.signals, "ts_start": iso(e.ts_start)}
        for e in rows
    ]


async def answer(session: AsyncSession, incident: Incident, question: str, *, hypothesis_id: str | None = None) -> dict[str, Any]:
    evidence = await load_evidence(session, incident.id)
    stmt = select(Hypothesis).where(Hypothesis.incident_id == incident.id).order_by(Hypothesis.rank)
    hyps = (await session.execute(stmt)).scalars().all()
    hyp = next((h for h in hyps if h.id == hypothesis_id), hyps[0] if hyps else None)
    if hyp is None:
        return {"answer": "No hypotheses have been generated for this incident yet.", "supporting": [], "counter_evidence": [], "conclusion": "", "provider": "none"}
    ctx = {
        "question": question[:2000],
        "incident": {"key": incident.key, "title": incident.title},
        "hypothesis": {
            "id": hyp.id,
            "category": hyp.category,
            "title": hyp.title,
            "confidence": hyp.confidence,
            "supporting": list(hyp.supporting_evidence or []),
            "contradicting": list(hyp.contradicting_evidence or []),
            "reasoning": hyp.reasoning,
            "breakdown": hyp.score_breakdown,
        },
        "evidence": evidence,
    }
    provider = get_provider()
    out, res = await provider.structured(SYSTEM_WHY, why_prompt(ctx), WhyAnswer)
    valid = {e["ref"] for e in evidence}
    sup = [r for r in out.supporting if r in valid]
    con = [r for r in out.counter_evidence if r in valid]
    return {
        "answer": out.answer,
        "conclusion": out.conclusion,
        "supporting": sup,
        "counter_evidence": con,
        "invalid_citations_dropped": (len(out.supporting) - len(sup)) + (len(out.counter_evidence) - len(con)),
        "hypothesis": {"id": hyp.id, "title": hyp.title, "category": hyp.category, "confidence": hyp.confidence, "score_breakdown": hyp.score_breakdown},
        "evidence": [e for e in evidence if e["ref"] in set(sup) | set(con)],
        "provider": res.provider,
        "model": res.model,
        "latency_ms": round(res.latency_ms, 1),
    }
