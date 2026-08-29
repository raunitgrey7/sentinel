"""Synthesize a fault → detect → investigate → verify root cause, with no model."""

import pytest
from sqlalchemy import select

from sentinel.core.timeutil import utcnow
from sentinel.db.models import Evidence, GraphEdge, Hypothesis, Incident, RemediationAction
from sentinel.db.session import session_scope
from sentinel.detection.engine import evaluate_rules
from sentinel.evaluation.runner import _load_telemetry, _setup_project
from sentinel.evaluation.scenarios import Scenario
from sentinel.investigation.orchestrator import create_investigation, run_investigation
from sentinel.services.incidents import get_incident

pytestmark = pytest.mark.integration


async def _run(scenario: Scenario) -> tuple[str, str]:
    project_id = await _setup_project(f"it-{scenario.fault_type}-{scenario.seed}")
    await _load_telemetry(project_id, scenario, utcnow())
    created: list[str] = []

    async def collect(iid: str) -> None:
        created.append(iid)

    async with session_scope() as s:
        await evaluate_rules(s, project_id, enqueue=collect)
    assert created, "detector did not open an incident"
    async with session_scope() as s:
        inc = await get_incident(s, created[0])
        inv = await create_investigation(s, inc.id, trigger="test")
        inv_id, inc_id = inv.id, inc.id
    async with session_scope() as s:
        inv = await run_investigation(s, inv_id)
        assert inv.status == "COMPLETED", inv.error
    return project_id, inc_id


async def test_db_pool_exhaustion_is_identified_with_evidence(db):
    _, inc_id = await _run(Scenario("it/pool", "db_pool_exhaustion", "payment-service", "database_connection_pool", {"seed": 11}))
    async with session_scope() as s:
        inc = await s.get(Incident, inc_id)
        assert inc.primary_service == "payment-service"  # merged from the api-gateway symptom
        assert inc.root_cause_category == "database_connection_pool"
        assert inc.status in ("REMEDIATION_PROPOSED", "ROOT_CAUSE_IDENTIFIED")
        assert 0.55 <= inc.confidence <= 0.95
        hyps = (await s.execute(select(Hypothesis).where(Hypothesis.incident_id == inc_id).order_by(Hypothesis.rank))).scalars().all()
        top = hyps[0]
        assert top.supporting_evidence and top.verification["supported"]
        ev = {e.ref: e for e in (await s.execute(select(Evidence).where(Evidence.incident_id == inc_id))).scalars().all()}
        assert all(r in ev for r in top.supporting_evidence)
        kinds = {ev[r].kind for r in top.supporting_evidence}
        assert {"metric", "log", "trace"} <= kinds
        assert any("cpu usage remained normal" in e.summary for e in ev.values())  # contradicting evidence recorded
        edges = (await s.execute(select(GraphEdge).where(GraphEdge.incident_id == inc_id))).scalars().all()
        assert any(e.relation == "supports" and e.target == "hypothesis:database_connection_pool" for e in edges)
        actions = (await s.execute(select(RemediationAction).where(RemediationAction.incident_id == inc_id))).scalars().all()
        assert actions and all(a.status == "proposed" for a in actions)


async def test_deployment_regression_cites_the_commit(db):
    _, inc_id = await _run(Scenario("it/deploy", "http_500_spike", "order-service", "deployment_regression", {"seed": 12}))
    async with session_scope() as s:
        inc = await s.get(Incident, inc_id)
        assert inc.root_cause_category == "deployment_regression"
        ev = (await s.execute(select(Evidence).where(Evidence.incident_id == inc_id, Evidence.kind == "deployment"))).scalars().all()
        assert any("c4d1e77b" in e.summary for e in ev)
        actions = (await s.execute(select(RemediationAction).where(RemediationAction.incident_id == inc_id))).scalars().all()
        rb = next(a for a in actions if a.kind == "rollback")
        assert rb.executable and rb.params["from_version"] == "2.8.1"


async def test_healthy_control_opens_no_incident(db):
    project_id = await _setup_project("it-control")
    await _load_telemetry(project_id, Scenario("it/control", "none", "payment-service", "none", {"seed": 100}), utcnow())
    created: list[str] = []

    async def collect(iid: str) -> None:
        created.append(iid)

    async with session_scope() as s:
        out = await evaluate_rules(s, project_id, enqueue=collect)
    assert not created and out["fired"] == []


async def test_investigation_resumes_from_checkpoint(db, monkeypatch):
    """Crash mid-way, re-run: completed stages are skipped, the result is still correct."""
    from sentinel.investigation import orchestrator
    from sentinel.investigation.investigators import traces

    project_id = await _setup_project("it-resume")
    await _load_telemetry(project_id, Scenario("it/resume", "redis_failure", "auth-service", "redis_unavailable", {"seed": 13}), utcnow())
    created: list[str] = []

    async def collect(iid: str) -> None:
        created.append(iid)

    async with session_scope() as s:
        await evaluate_rules(s, project_id, enqueue=collect)
    assert created
    async with session_scope() as s:
        inv = await create_investigation(s, created[0], trigger="test")
        inv_id = inv.id

    boom = {"n": 0}
    original = traces.run

    async def crashing(ctx):  # type: ignore[no-untyped-def]
        boom["n"] += 1
        raise RuntimeError("simulated worker crash")

    monkeypatch.setattr(orchestrator.STAGES[3], "run", crashing) if False else None
    stages = orchestrator.STAGES
    idx = next(i for i, st in enumerate(stages) if st.name == "traces")
    stages[idx] = orchestrator.Stage("traces", "Trace Investigator", crashing)
    monkeypatch.setattr(orchestrator.get_settings(), "investigation_max_attempts", 1, raising=False)
    async with session_scope() as s:
        with pytest.raises(RuntimeError):
            await run_investigation(s, inv_id)
    async with session_scope() as s:
        inv = (await s.execute(select(orchestrator.Investigation).where(orchestrator.Investigation.id == inv_id))).scalar_one()
        assert inv.status == "FAILED"
        assert set(inv.checkpoint["completed"]) >= {"timeline", "metrics", "logs"}
    stages[idx] = orchestrator.Stage("traces", "Trace Investigator", original)
    async with session_scope() as s:
        inv = await run_investigation(s, inv_id)
        assert inv.status == "COMPLETED"
        assert boom["n"] >= 1
        inc = await get_incident(s, inv.incident_id)
        assert inc.root_cause_category == "redis_unavailable"
