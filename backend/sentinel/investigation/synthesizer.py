"""Root Cause Synthesizer — the (only) LLM reasoning step in the pipeline.

Input: evidence + deterministic candidates. Output: narrative + re-ranked hypotheses with
citations. The model may reorder candidates but cannot add categories; anything outside
the candidate set or citing unknown handles is dropped here and penalised by the verifier.
"""

from __future__ import annotations

from typing import Any

from sentinel.core.timeutil import iso
from sentinel.investigation.context import InvestigationContext
from sentinel.llm.prompts import SYSTEM_SYNTHESIS, synthesis_prompt
from sentinel.llm.schemas import SynthesisOutput

NAME = "synthesis"
LABEL = "Root Cause Synthesizer"


def build_context(ctx: InvestigationContext) -> dict[str, Any]:
    inc = ctx.incident
    return {
        "incident": {
            "key": inc.key,
            "title": inc.title,
            "severity": inc.severity,
            "primary_service": inc.primary_service,
            "affected_services": list(inc.affected_services or []),
            "started_at": iso(inc.started_at),
            "detected_at": iso(inc.detected_at),
        },
        "timeline": [{"ts": iso(t["ts"]), "message": t["message"]} for t in sorted(ctx.timeline, key=lambda t: t["ts"])],
        "evidence": ctx.evidence.to_list(),
        "candidates": ctx.candidates,
    }


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    context = build_context(ctx)
    prompt = synthesis_prompt(context)
    out, res = await ctx.provider.structured(SYSTEM_SYNTHESIS, prompt, SynthesisOutput)
    ctx.record_llm(res.latency_ms)

    valid_refs = ctx.evidence.refs()
    allowed = {c["category"]: c for c in ctx.candidates}
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    dropped_refs = 0
    for h in out.hypotheses:
        if h.category not in allowed or h.category in seen:
            continue
        seen.add(h.category)
        base = allowed[h.category]
        sup = [r for r in h.evidence if r in valid_refs]
        con = [r for r in h.contradicting_evidence if r in valid_refs]
        dropped_refs += (len(h.evidence) - len(sup)) + (len(h.contradicting_evidence) - len(con))
        cited_total = len(h.evidence) + len(h.contradicting_evidence)
        merged.append(
            {
                **base,
                "culprit_service": h.culprit_service or base.get("culprit_service"),
                "reasoning": h.reasoning,
                "llm_confidence": h.confidence,
                "llm_supporting": sup or base["supporting"],
                "llm_contradicting": con or base["contradicting"],
                "citation_validity": (len(sup) + len(con)) / cited_total if cited_total else 1.0,
                "llm_rank": len(merged) + 1,
            }
        )
    # Candidates the model omitted keep their deterministic ranking beneath the model's picks.
    for c in ctx.candidates:
        if c["category"] not in seen:
            merged.append({**c, "reasoning": "", "llm_confidence": None, "llm_supporting": c["supporting"], "llm_contradicting": c["contradicting"], "citation_validity": 1.0, "llm_rank": None})
    ctx.synthesis = {
        "summary": out.summary,
        "caveats": out.caveats,
        "hypotheses": merged,
        "provider": res.provider,
        "model": res.model,
        "latency_ms": round(res.latency_ms, 1),
        "dropped_invalid_citations": dropped_refs,
    }
    return {"provider": res.provider, "model": res.model, "hypotheses": len(merged), "latency_ms": round(res.latency_ms, 1), "dropped_invalid_citations": dropped_refs}
