"""``NullProvider`` — deterministic, model-free provider.

This is not a stub. It renders the same structured outputs the model would, using the
evidence and candidate ranking Sentinel already computed. It exists so that:

* the platform is fully functional with zero model dependency (CI, air-gapped installs),
* the evaluation harness can separate "deterministic pipeline quality" from "model lift",
* every LLM-shaped code path has a reference implementation to test against.
"""

from __future__ import annotations

import json
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from sentinel.llm.base import LLMResult
from sentinel.llm.schemas import (
    PostmortemOutput,
    PostmortemSection,
    RankedHypothesis,
    SynthesisOutput,
    VerificationOutput,
    WhyAnswer,
)
from sentinel.retrieval.embeddings import HashedEmbedder

T = TypeVar("T", bound=BaseModel)


class NullProvider:
    name = "none"
    model = "deterministic-narrator"

    def __init__(self, embedding_dim: int = 256) -> None:
        self._embedder = HashedEmbedder(embedding_dim)

    async def healthy(self) -> bool:
        return True

    def snapshot(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "circuit": {"state": "closed"}}

    async def generate(self, system: str, user: str, *, temperature: float | None = None, max_tokens: int = 1024) -> LLMResult:
        ctx = _context(user)
        text = ctx.get("fallback_text") or "Deterministic narrator: see structured evidence."
        return LLMResult(text=text, provider=self.name, model=self.model, latency_ms=0.1)

    async def structured(self, system: str, user: str, schema: type[T], *, temperature: float | None = None, max_tokens: int = 2048) -> tuple[T, LLMResult]:
        start = time.perf_counter()
        ctx = _context(user)
        out: BaseModel
        if schema is SynthesisOutput:
            out = _synthesize(ctx)
        elif schema is VerificationOutput:
            out = VerificationOutput(supported=True, issues=[], adjusted_confidence=float(ctx.get("confidence", 0.5)), missing_evidence=[])
        elif schema is WhyAnswer:
            out = _why(ctx)
        elif schema is PostmortemOutput:
            out = _postmortem(ctx)
        else:
            out = schema.model_validate(ctx.get("default", {}))
        res = LLMResult(text=out.model_dump_json(), provider=self.name, model=self.model, latency_ms=(time.perf_counter() - start) * 1000)
        return out, res  # type: ignore[return-value]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed(texts)


def _context(user: str) -> dict[str, Any]:
    """Prompts embed a machine-readable context block; the narrator reads it back."""
    marker = "<<SENTINEL_CONTEXT>>"
    end = "<<END_SENTINEL_CONTEXT>>"
    if marker in user and end in user:
        raw = user.split(marker, 1)[1].split(end, 1)[0]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _synthesize(ctx: dict[str, Any]) -> SynthesisOutput:
    incident = ctx.get("incident", {})
    cands = ctx.get("candidates", [])
    evidence = {e["ref"]: e for e in ctx.get("evidence", [])}
    hyps: list[RankedHypothesis] = []
    for c in cands:
        sup = [r for r in c.get("supporting", []) if r in evidence]
        con = [r for r in c.get("contradicting", []) if r in evidence]
        lines = [f"{c['title']} is ranked #{c['rank']} with deterministic score {c['score']:.2f}."]
        if sup:
            lines.append("Supporting evidence: " + "; ".join(f"[{r}] {evidence[r]['summary']}" for r in sup[:4]) + ".")
        if con:
            lines.append("Contradicting evidence: " + "; ".join(f"[{r}] {evidence[r]['summary']}" for r in con[:2]) + ".")
        hyps.append(
            RankedHypothesis(
                category=c["category"],
                culprit_service=c.get("culprit_service"),
                reasoning=" ".join(lines),
                evidence=sup,
                contradicting_evidence=con,
                confidence=float(c["score"]),
            )
        )
    top = cands[0] if cands else None
    summary = (
        f"{incident.get('title', 'Incident')} affecting {incident.get('primary_service', 'unknown')}. "
        + (f"Most probable root cause: {top['title']} (score {top['score']:.2f}). " if top else "No hypothesis reached the candidate threshold. ")
        + f"{len(evidence)} evidence items were collected across {len({e['kind'] for e in evidence.values()})} signal types."
    )
    caveats = ["Deterministic narrator: rankings reflect the evidence scorer only; no model reasoning was applied."]
    if top and top.get("contradicting"):
        caveats.append("Contradicting evidence exists for the leading hypothesis; causality is correlational.")
    return SynthesisOutput(summary=summary, hypotheses=hyps, caveats=caveats)


def _why(ctx: dict[str, Any]) -> WhyAnswer:
    hyp = ctx.get("hypothesis", {})
    evidence = {e["ref"]: e for e in ctx.get("evidence", [])}
    sup = [r for r in hyp.get("supporting", []) if r in evidence]
    con = [r for r in hyp.get("contradicting", []) if r in evidence]
    bullets = [f"{i + 1}. [{r}] {evidence[r]['summary']}" for i, r in enumerate(sup)]
    counter = [f"- [{r}] {evidence[r]['summary']}" for r in con]
    answer = "Because:\n" + "\n".join(bullets) if bullets else "No supporting evidence is recorded for this hypothesis."
    if counter:
        answer += "\n\nCounter-evidence:\n" + "\n".join(counter)
    conclusion = (
        f"Therefore the system considers '{hyp.get('title', 'this hypothesis')}' the most likely explanation "
        f"(confidence {float(hyp.get('confidence', 0)):.0%})."
        if sup
        else "The system cannot support this hypothesis from the recorded evidence."
    )
    return WhyAnswer(answer=answer, supporting=sup, counter_evidence=con, conclusion=conclusion)


def _postmortem(ctx: dict[str, Any]) -> PostmortemOutput:
    inc = ctx.get("incident", {})
    top = ctx.get("root_cause", {})
    evidence = ctx.get("evidence", [])
    timeline = ctx.get("timeline", [])
    actions = ctx.get("remediation", [])
    sup = top.get("supporting", [])
    con = top.get("contradicting", [])
    sections = [
        PostmortemSection(title="Incident Summary", body=f"{inc.get('title')} ({inc.get('key')}), severity {inc.get('severity')}, affecting {', '.join(inc.get('affected_services', []))}. Detected at {inc.get('detected_at')}; onset estimated at {inc.get('started_at')}.", citations=[]),
        PostmortemSection(title="Impact", body=inc.get("impact") or f"Primary service {inc.get('primary_service')} degraded; {len(inc.get('affected_services', []))} services in the blast radius.", citations=[e["ref"] for e in evidence if e.get("kind") == "metric"][:3]),
        PostmortemSection(title="Timeline", body="\n".join(f"- {t['ts']} — {t['message']}" for t in timeline), citations=[]),
        PostmortemSection(title="Detection", body=inc.get("detection") or "Detected automatically by Sentinel's deterministic rule engine.", citations=[e["ref"] for e in evidence if e.get("kind") == "alert"][:2]),
        PostmortemSection(title="Root Cause", body=f"{top.get('title', 'Undetermined')}: {top.get('reasoning', '')}", citations=sup),
        PostmortemSection(title="Contributing Factors", body="\n".join(f"- {c}" for c in ctx.get("contributing", [])) or "None identified beyond the primary cause.", citations=[]),
        PostmortemSection(title="Contradicting Evidence", body="\n".join(f"- [{r}]" for r in con) or "None recorded.", citations=con),
        PostmortemSection(title="Resolution", body=inc.get("resolution_notes") or "See remediation actions.", citations=[]),
        PostmortemSection(title="Corrective Actions", body="\n".join(f"- {a['title']} ({a['status']})" for a in actions) or "None recorded.", citations=[]),
        PostmortemSection(title="Preventive Actions", body="\n".join(f"- {p}" for p in ctx.get("preventive", [])) or "Add leading-indicator alerts for the implicated signals.", citations=[]),
        PostmortemSection(title="Detection Gaps", body=ctx.get("detection_gap") or "Time from onset to detection is recorded in the timeline; consider tighter thresholds on leading indicators.", citations=[]),
    ]
    return PostmortemOutput(sections=sections)
