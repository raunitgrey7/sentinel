from sentinel.domain.enums import EvidenceKind
from sentinel.investigation.catalog import CATALOG, all_signals
from sentinel.investigation.context import EvidenceBag
from sentinel.investigation.scoring import calibrate_confidence, generate_candidates


def pool_exhaustion_bag() -> EvidenceBag:
    bag = EvidenceBag()
    bag.add(EvidenceKind.METRIC, "metrics:db_connections_active", "pool 98%", service="payment-service", signals=["db_pool_saturated"], weight=0.95)
    bag.add(EvidenceKind.METRIC, "metrics:db_connection_acquire_ms", "acquire 8.4x", service="payment-service", signals=["db_acquire_latency_up"], weight=0.9)
    bag.add(EvidenceKind.LOG, "logs:payment-service", "failed to acquire connection", service="payment-service", signals=["log_pool_exhausted"], weight=0.9)
    bag.add(EvidenceKind.TRACE, "traces:payment-service/db.acquire_connection", "acquire slow", service="payment-service", signals=["trace_db_acquire_slow"], weight=0.8)
    bag.add(EvidenceKind.METRIC, "metrics:http_error_rate", "errors up", service="payment-service", signals=["error_rate_up"], weight=0.8)
    bag.add(EvidenceKind.METRIC, "metrics:cpu_usage", "cpu normal", service="payment-service", signals=["cpu_flat"], weight=0.5, direction="contradicts")
    return bag


def test_evidence_bag_mints_sequential_refs():
    bag = pool_exhaustion_bag()
    assert [e.ref for e in bag.items] == ["E1", "E2", "E3", "E4", "E5", "E6"]
    assert bag.signals()["db_pool_saturated"] == 0.95


def test_pool_exhaustion_ranks_first():
    cands = generate_candidates(pool_exhaustion_bag(), primary_service="payment-service", culprit_hints={"payment-service": 0.6, "postgres": 0.9}, deploy_proximity=0.0, historical={})
    assert cands[0].category == "database_connection_pool"
    assert cands[0].culprit_service == "payment-service"
    assert "E1" in cands[0].supporting
    assert cands[0].score > 0.7
    # CPU saturation must not even be generated (required signal absent)
    assert all(c.category != "cpu_saturation" for c in cands)


def test_contradicting_evidence_lowers_score():
    bag = pool_exhaustion_bag()
    base = generate_candidates(bag, primary_service="payment-service", culprit_hints={}, deploy_proximity=0.0, historical={})[0].score
    bag.add(EvidenceKind.METRIC, "metrics:db_query_latency_ms", "queries slow", service="payment-service", signals=["db_query_latency_up"], weight=0.9)
    contra = generate_candidates(bag, primary_service="payment-service", culprit_hints={}, deploy_proximity=0.0, historical={})
    top = next(c for c in contra if c.category == "database_connection_pool")
    assert top.score < base
    assert top.breakdown["contradictory_evidence"] < 0


def test_deployment_proximity_boosts_deploy_sensitive_categories():
    bag = pool_exhaustion_bag()
    bag.add(EvidenceKind.DEPLOYMENT, "deployments:payment-service", "deploy 4m before", service="payment-service", signals=["deploy_recent", "deploy_touches_db_config"], weight=0.8)
    without = generate_candidates(pool_exhaustion_bag(), primary_service="payment-service", culprit_hints={}, deploy_proximity=0.0, historical={})[0].score
    with_dep = generate_candidates(bag, primary_service="payment-service", culprit_hints={}, deploy_proximity=0.8, historical={})[0].score
    assert with_dep > without


def test_single_evidence_kind_is_capped():
    bag = EvidenceBag()
    bag.add(EvidenceKind.METRIC, "m", "cpu 99%", service="x", signals=["cpu_up"], weight=1.0)
    bag.add(EvidenceKind.METRIC, "m", "latency", service="x", signals=["latency_up"], weight=1.0)
    cands = generate_candidates(bag, primary_service="x", culprit_hints={}, deploy_proximity=0.0, historical={})
    assert cands[0].category == "cpu_saturation"
    assert cands[0].score <= 0.6


def test_calibration_bounds():
    assert calibrate_confidence(0.99, verification_ok=True, citation_validity=1.0, contradiction_penalty=0.0, evidence_kinds=4) <= 0.95
    assert calibrate_confidence(0.9, verification_ok=True, citation_validity=1.0, contradiction_penalty=0.0, evidence_kinds=2) <= 0.75
    low = calibrate_confidence(0.9, verification_ok=False, citation_validity=0.5, contradiction_penalty=0.1, evidence_kinds=4)
    assert low < 0.5


def test_catalog_signals_are_consistent():
    sigs = all_signals()
    for rc in CATALOG.values():
        assert any(s.required for s in rc.supports), rc.category
        assert rc.remediation, rc.category
    assert "db_pool_saturated" in sigs
