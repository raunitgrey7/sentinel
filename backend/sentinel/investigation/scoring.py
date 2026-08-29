"""Hypothesis generation and explicit, inspectable scoring.

    RootCauseScore =
        signal_support            (catalog signal weights × evidence strength)
      + temporal_correlation      (change event proximity to onset)
      + dependency_relevance      (culprit lies on the dependency path of the primary service)
      + historical_similarity     (similar resolved incidents share the category)
      - contradictory_evidence    (catalog contradiction weights × evidence strength)

Each component is bounded, the sum is squashed into [0,1], and the breakdown is stored on
the hypothesis so the UI and the "Why?" endpoint can show exactly how a number was made.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from sentinel.domain.enums import RootCauseCategory as RC
from sentinel.investigation.catalog import CATALOG, RootCause
from sentinel.investigation.context import EvidenceBag

WEIGHTS = {
    "signal_support": 1.0,
    "temporal_correlation": 0.35,
    "dependency_relevance": 0.25,
    "historical_similarity": 0.25,
    "contradictory_evidence": 1.0,
}


@dataclass
class Candidate:
    category: str
    title: str
    description: str
    culprit_service: str | None
    score: float
    breakdown: dict[str, float]
    supporting: list[str]
    contradicting: list[str]
    rank: int = 0
    remediation: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "culprit_service": self.culprit_service,
            "score": round(self.score, 4),
            "breakdown": {k: round(v, 4) for k, v in self.breakdown.items()},
            "supporting": list(self.supporting),
            "contradicting": list(self.contradicting),
            "rank": self.rank,
            "remediation": self.remediation,
        }


def _squash(x: float) -> float:
    """Map an unbounded evidence sum to (0,1); ~0.5 at x=0.75, ~0.9 at x=1.8."""
    return 1.0 / (1.0 + math.exp(-2.2 * (x - 0.75)))


def _signal_component(rc: RootCause, bag: EvidenceBag) -> tuple[float, list[str], float, list[str]]:
    present = bag.signals()
    support = 0.0
    sup_refs: list[str] = []
    for rule in rc.supports:
        strength = present.get(rule.signal, 0.0)
        if strength > 0:
            support += rule.weight * strength
            sup_refs.extend(it.ref for it in bag.by_signal(rule.signal))
    contra = 0.0
    con_refs: list[str] = []
    for rule in rc.contradicts:
        strength = present.get(rule.signal, 0.0)
        if strength > 0:
            contra += rule.weight * strength
            con_refs.extend(it.ref for it in bag.by_signal(rule.signal))
    return support, _dedupe(sup_refs), contra, _dedupe(con_refs)


def _dedupe(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def generate_candidates(
    bag: EvidenceBag,
    *,
    primary_service: str,
    culprit_hints: dict[str, float],
    deploy_proximity: float,
    historical: dict[str, float],
) -> list[Candidate]:
    """Build and rank candidates.

    :param culprit_hints: service → relevance from the dependency investigator (0..1)
    :param deploy_proximity: 0..1, how close the nearest relevant deployment is to onset
    :param historical: category → best similarity among retrieved incidents (0..1)
    """
    present = bag.signals()
    out: list[Candidate] = []
    for rc in CATALOG.values():
        required = {s.signal for s in rc.supports if s.required}
        if required and not all(present.get(s, 0) > 0 for s in required):
            continue
        support, sup_refs, contra, con_refs = _signal_component(rc, bag)
        temporal = deploy_proximity if rc.deployment_sensitive else deploy_proximity * 0.3
        culprit = _pick_culprit(rc, bag, primary_service, culprit_hints)
        dep_rel = culprit_hints.get(culprit or primary_service, 0.5)
        hist = historical.get(rc.category, 0.0)
        raw = (
            WEIGHTS["signal_support"] * support
            + WEIGHTS["temporal_correlation"] * temporal
            + WEIGHTS["dependency_relevance"] * dep_rel
            + WEIGHTS["historical_similarity"] * hist
            - WEIGHTS["contradictory_evidence"] * contra
        )
        score = _squash(raw)
        # Evidence-diversity guard: a single signal kind cannot carry a hypothesis above 0.6.
        kinds = {bag.get(r).kind for r in sup_refs if bag.get(r)}  # type: ignore[union-attr]
        if len(kinds) < 2:
            score = min(score, 0.6)
        out.append(
            Candidate(
                category=rc.category,
                title=rc.title,
                description=rc.description,
                culprit_service=culprit,
                score=score,
                breakdown={
                    "signal_support": support,
                    "temporal_correlation": temporal,
                    "dependency_relevance": dep_rel,
                    "historical_similarity": hist,
                    "contradictory_evidence": -contra,
                    "raw": raw,
                    "evidence_kinds": float(len(kinds)),
                },
                supporting=sup_refs,
                contradicting=con_refs,
                remediation=[
                    {"kind": r.kind, "title": r.title, "description": r.description, "risk": r.risk, "executable": r.executable}
                    for r in rc.remediation
                ],
            )
        )
    out.sort(key=lambda c: c.score, reverse=True)
    for i, c in enumerate(out, start=1):
        c.rank = i
    return out


def _pick_culprit(rc: RootCause, bag: EvidenceBag, primary: str, hints: dict[str, float]) -> str | None:
    """Prefer the service that produced the required signals; else the strongest dependency hint."""
    svc_weight: dict[str, float] = {}
    for rule in rc.supports:
        for it in bag.by_signal(rule.signal):
            if it.service:
                svc_weight[it.service] = svc_weight.get(it.service, 0.0) + rule.weight * it.weight
    if svc_weight:
        return max(svc_weight.items(), key=lambda kv: kv[1])[0]
    if rc.component in ("database", "cache", "queue") and hints:
        deps = {k: v for k, v in hints.items() if k != primary}
        if deps:
            return max(deps.items(), key=lambda kv: kv[1])[0]
    return primary


def calibrate_confidence(score: float, *, verification_ok: bool, citation_validity: float, contradiction_penalty: float, evidence_kinds: int) -> float:
    """Turn a deterministic score into a reported confidence.

    * invalid citations from the narrator reduce confidence proportionally,
    * unresolved contradictions subtract,
    * fewer than 3 independent evidence kinds caps confidence at 0.75,
    * nothing is ever reported above 0.95 — causality is never independently verified.
    """
    c = score * (0.7 + 0.3 * citation_validity)
    c -= contradiction_penalty
    if not verification_ok:
        c *= 0.6
    if evidence_kinds < 3:
        c = min(c, 0.75)
    return max(0.0, min(0.95, c))


def unknown_candidate() -> Candidate:
    return Candidate(
        category=RC.UNKNOWN,
        title="Undetermined root cause",
        description="No catalog hypothesis met its required signals.",
        culprit_service=None,
        score=0.1,
        breakdown={},
        supporting=[],
        contradicting=[],
        rank=1,
    )
