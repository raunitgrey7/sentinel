"""The verifier must reject unsupported citations and surface ignored contradictions."""

from types import SimpleNamespace

from sentinel.domain.enums import EvidenceKind
from sentinel.investigation.context import EvidenceBag
from sentinel.investigation.verifier import verify_hypothesis


def _ctx(bag: EvidenceBag):  # type: ignore[no-untyped-def]
    return SimpleNamespace(evidence=bag)


def _bag() -> EvidenceBag:
    bag = EvidenceBag()
    bag.add(EvidenceKind.METRIC, "m", "pool 99%", service="p", signals=["db_pool_saturated"], weight=0.9)
    bag.add(EvidenceKind.LOG, "l", "acquire failed", service="p", signals=["log_pool_exhausted"], weight=0.9)
    bag.add(EvidenceKind.TRACE, "t", "acquire slow", service="p", signals=["trace_db_acquire_slow"], weight=0.8)
    bag.add(EvidenceKind.METRIC, "m", "queries slow", service="p", signals=["db_query_latency_up"], weight=0.7)  # contradicts pool hypothesis
    bag.add(EvidenceKind.HISTORICAL, "h", "resembles INC-1", service="p", signals=[], weight=0.5)
    return bag


def test_invalid_and_irrelevant_citations_are_flagged():
    bag = _bag()
    hyp = {"category": "database_connection_pool", "score": 0.85, "llm_supporting": ["E1", "E2", "E5", "E42"], "llm_contradicting": [], "citation_validity": 0.75}
    v = verify_hypothesis(hyp, _ctx(bag))
    assert v["supported"]
    assert set(v["supporting"]) == {"E1", "E2"}  # E5 has no relevant signal; E42 does not exist
    assert any("do not exist" in i for i in v["issues"])
    assert any("E5" in i for i in v["issues"])
    assert "E4" in v["contradicting"]  # ignored contradiction surfaced
    assert v["confidence"] < 0.85


def test_missing_required_signal_rejects_hypothesis():
    bag = EvidenceBag()
    bag.add(EvidenceKind.METRIC, "m", "latency up", service="p", signals=["latency_up"], weight=0.9)
    hyp = {"category": "cpu_saturation", "score": 0.6, "llm_supporting": ["E1"], "llm_contradicting": [], "citation_validity": 1.0}
    v = verify_hypothesis(hyp, _ctx(bag))
    assert not v["supported"]
    assert any("required signal" in i for i in v["issues"])
    assert v["confidence"] < 0.4


def test_confidence_never_exceeds_cap():
    bag = _bag()
    hyp = {"category": "database_connection_pool", "score": 0.999, "llm_supporting": ["E1", "E2", "E3"], "llm_contradicting": ["E4"], "citation_validity": 1.0}
    v = verify_hypothesis(hyp, _ctx(bag))
    assert v["confidence"] <= 0.95
    assert v["evidence_kinds"] == ["log", "metric", "trace"]
