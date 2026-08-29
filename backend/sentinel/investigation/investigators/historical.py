"""Historical investigator — retrieval-augmented comparison with resolved incidents."""

from __future__ import annotations

from typing import Any

from sentinel.domain.enums import EvidenceKind
from sentinel.investigation.context import InvestigationContext
from sentinel.retrieval.historical import find_similar
from sentinel.retrieval.signature import build_signature

NAME = "historical"
LABEL = "Historical Investigator"


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    signature = build_signature(
        primary_service=ctx.primary,
        affected=list(ctx.incident.affected_services or []),
        signals=ctx.evidence.signals(),
        error_templates=ctx.notes.get("error_templates", []),
        severity=ctx.incident.severity,
    )
    similar, vec = await find_similar(
        ctx.session, ctx.provider, project_id=ctx.project_id, signature=signature, exclude_incident_id=ctx.incident.id, k=5
    )
    ctx.incident.signature = signature
    ctx.incident.embedding = vec
    by_category: dict[str, float] = {}
    for s in similar:
        if s.root_cause_category:
            by_category[s.root_cause_category] = max(by_category.get(s.root_cause_category, 0.0), s.similarity)
        summary = f"resembles {s.key} \"{s.title}\" (similarity {s.similarity:.2f})"
        if s.root_cause_category:
            summary += f", whose verified root cause was {s.root_cause_category.replace('_', ' ')}"
        ctx.evidence.add(
            EvidenceKind.HISTORICAL,
            f"historical:{s.key}",
            summary,
            service=s.primary_service,
            signals=["historical_similar"] if s.similarity >= 0.5 else [],
            weight=min(1.0, s.similarity),
            detail=s.to_dict(),
        )
    ctx.notes["historical"] = [s.to_dict() for s in similar]
    ctx.notes["historical_by_category"] = by_category
    ctx.notes["signature"] = signature
    return {"similar": len(similar), "top": similar[0].key if similar else None}
