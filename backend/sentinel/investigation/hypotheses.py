"""Hypothesis generation step — deterministic candidates from evidence signals."""

from __future__ import annotations

from typing import Any

from sentinel.investigation.context import InvestigationContext
from sentinel.investigation.scoring import generate_candidates, unknown_candidate

NAME = "hypotheses"
LABEL = "Hypothesis Generator"


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    cands = generate_candidates(
        ctx.evidence,
        primary_service=ctx.primary,
        culprit_hints=ctx.notes.get("culprit_hints", {}),
        deploy_proximity=float(ctx.notes.get("deploy_proximity", 0.0)),
        historical=ctx.notes.get("historical_by_category", {}),
    )
    if not cands:
        cands = [unknown_candidate()]
    ctx.candidates = [c.to_dict() for c in cands[:6]]
    return {"candidates": [(c["category"], c["score"]) for c in ctx.candidates]}
