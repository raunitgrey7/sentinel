"""Verification agent.

Deterministic checks (always run):
  1. every cited handle exists;
  2. supporting citations actually carry a signal the catalog lists as *supporting* the
     category (a hypothesis cannot be "supported" by irrelevant evidence);
  3. contradicting evidence the narrator ignored is surfaced and penalised;
  4. the required catalog signals for the category are present;
  5. confidence is re-derived by ``calibrate_confidence`` — the model's own confidence is
     recorded but never trusted directly.

Optional LLM cross-examination (when a model provider is active) can only *lower*
confidence or add issues; it can never raise it.
"""

from __future__ import annotations

from typing import Any

from sentinel.core.timeutil import iso
from sentinel.investigation.catalog import CATALOG
from sentinel.investigation.context import InvestigationContext
from sentinel.investigation.scoring import calibrate_confidence
from sentinel.llm.prompts import SYSTEM_VERIFY, verify_prompt
from sentinel.llm.schemas import VerificationOutput

NAME = "verification"
LABEL = "Evidence Verifier"


def verify_hypothesis(hyp: dict[str, Any], ctx: InvestigationContext) -> dict[str, Any]:
    bag = ctx.evidence
    cat = CATALOG.get(hyp["category"])  # type: ignore[call-overload]
    issues: list[str] = []
    valid_refs = bag.refs()
    sup = [r for r in hyp.get("llm_supporting", hyp.get("supporting", [])) if r in valid_refs]
    con = [r for r in hyp.get("llm_contradicting", hyp.get("contradicting", [])) if r in valid_refs]
    invalid = len(hyp.get("llm_supporting", [])) + len(hyp.get("llm_contradicting", [])) - len(sup) - len(con)
    if invalid:
        issues.append(f"{invalid} cited evidence handle(s) do not exist and were discarded")

    relevant_sup: list[str] = []
    if cat:
        support_signals = {s.signal for s in cat.supports}
        contra_signals = {s.signal for s in cat.contradicts}
        for r in sup:
            item = bag.get(r)
            if item and (set(item.signals) & support_signals):
                relevant_sup.append(r)
            elif item and item.direction != "contradicts":
                issues.append(f"{r} was cited as support but carries no signal relevant to {cat.category}")
        # required signals
        missing = [s.signal for s in cat.supports if s.required and not bag.by_signal(s.signal)]
        if missing:
            issues.append(f"required signal(s) missing: {', '.join(missing)}")
        # ignored contradictions
        ignored = [it.ref for it in bag.items if (set(it.signals) & contra_signals) and it.ref not in con]
        if ignored:
            issues.append(f"contradicting evidence not acknowledged: {', '.join(ignored)}")
            con = list(dict.fromkeys([*con, *ignored]))
    else:
        relevant_sup = sup

    kinds = {bag.get(r).kind for r in relevant_sup if bag.get(r)}  # type: ignore[union-attr]
    citation_validity = float(hyp.get("citation_validity", 1.0))
    contradiction_penalty = 0.0
    if cat:
        weights = {s.signal: s.weight for s in cat.contradicts}
        for r in con:
            item = bag.get(r)
            if item:
                contradiction_penalty += max((weights.get(s, 0.0) for s in item.signals), default=0.0) * item.weight * 0.5
    supported = bool(relevant_sup) and not any(i.startswith("required signal") for i in issues)
    confidence = calibrate_confidence(
        float(hyp["score"]),
        verification_ok=supported,
        citation_validity=citation_validity,
        contradiction_penalty=min(contradiction_penalty, 0.3),
        evidence_kinds=len(kinds),
    )
    return {
        "supported": supported,
        "issues": issues,
        "supporting": relevant_sup,
        "contradicting": con,
        "evidence_kinds": sorted(kinds),
        "citation_validity": round(citation_validity, 3),
        "contradiction_penalty": round(contradiction_penalty, 3),
        "confidence": round(confidence, 4),
        "model_confidence": hyp.get("llm_confidence"),
    }


REORDER_TOLERANCE = 0.10


def _stabilize(verified: list[dict[str, Any]]) -> None:
    """The narrator may reorder hypotheses only within a small deterministic score gap.

    Small local models cite poorly; poor citations lower calibrated confidence, and that
    must not be allowed to promote a clearly weaker hypothesis over the deterministic
    leader. The rejection is recorded on the hypothesis so the UI can show it.
    """
    if len(verified) < 2:
        return
    verified.sort(key=lambda h: h["confidence"], reverse=True)
    det_top = max(verified, key=lambda h: float(h["score"]))
    if verified[0] is det_top:
        return
    gap = float(det_top["score"]) - float(verified[0]["score"])
    if gap > REORDER_TOLERANCE:
        demoted = verified[0]
        verified.remove(det_top)
        verified.insert(0, det_top)
        det_top["verification"]["issues"].append(
            f"narrator preferred '{demoted['title']}' but the deterministic score gap ({gap:.2f}) exceeds the reorder tolerance ({REORDER_TOLERANCE}); deterministic ranking kept"
        )
        det_top["confidence"] = round(max(det_top["confidence"], demoted["confidence"]), 4)


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    hyps = ctx.synthesis.get("hypotheses") or [{**c, "llm_supporting": c["supporting"], "llm_contradicting": c["contradicting"], "citation_validity": 1.0, "reasoning": ""} for c in ctx.candidates]
    verified: list[dict[str, Any]] = []
    for h in hyps:
        v = verify_hypothesis(h, ctx)
        verified.append({**h, "verification": v, "confidence": v["confidence"], "supporting": v["supporting"], "contradicting": v["contradicting"]})

    _stabilize(verified)
    top = verified[0] if verified else None

    # Optional model cross-examination of the leading hypothesis (can only lower confidence).
    llm_note: dict[str, Any] | None = None
    if top and ctx.provider.name != "none" and top["verification"]["supported"]:
        context = {
            "hypothesis": {**{k: top[k] for k in ("category", "title", "culprit_service", "confidence", "reasoning", "supporting", "contradicting")}},
            "evidence": ctx.evidence.to_list(),
            "confidence": top["confidence"],
            "incident": {"key": ctx.incident.key, "started_at": iso(ctx.incident.started_at)},
        }
        try:
            out, res = await ctx.provider.structured(SYSTEM_VERIFY, verify_prompt(context), VerificationOutput)
            ctx.record_llm(res.latency_ms)
            llm_note = out.model_dump()
            if not out.supported:
                top["verification"]["issues"].append("model verifier disagreed: " + "; ".join(out.issues[:3]))
                top["confidence"] = round(min(top["confidence"], max(0.0, out.adjusted_confidence) * 0.8), 4)
            elif out.adjusted_confidence < top["confidence"]:
                top["confidence"] = round(max(top["confidence"] * 0.8, out.adjusted_confidence), 4)
            top["verification"]["model_issues"] = out.issues
            top["verification"]["model_missing_evidence"] = out.missing_evidence
        except Exception as exc:  # noqa: BLE001
            llm_note = {"error": str(exc)[:200]}
        _stabilize(verified)
        top = verified[0]

    for i, h in enumerate(verified, start=1):
        h["rank"] = i
    ctx.verification = {"hypotheses": verified, "model": llm_note}
    return {
        "top": top["category"] if top else None,
        "confidence": top["confidence"] if top else 0.0,
        "supported": top["verification"]["supported"] if top else False,
        "issues": top["verification"]["issues"] if top else [],
    }
