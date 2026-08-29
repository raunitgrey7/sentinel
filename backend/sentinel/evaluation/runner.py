"""Evaluation runner: synthesize → detect → investigate → score.

Every case runs in its own project so cases never interfere. Raw telemetry is purged
after scoring (results, incidents, evidence and hypotheses are kept for inspection).

Metrics reported
----------------
* root-cause accuracy (top-1, top-3)
* detection rate and onset→detection latency
* evidence precision — of the evidence cited for the *predicted* top hypothesis, the
  fraction that carries a signal relevant to the *true* category
* citation validity — fraction of narrator citations that reference real evidence
* false-positive rate — healthy control scenarios that opened an incident
* confident-wrong rate — wrong top-1 with confidence ≥ threshold
* expected calibration error (ECE, 10 bins)
* investigation latency and LLM time
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select

from sentinel.api.bootstrap import DEMO_EDGES, DEMO_SERVICES
from sentinel.core.config import REPO_ROOT, get_settings
from sentinel.core.logging import configure_logging, get_logger
from sentinel.core.timeutil import utcnow
from sentinel.db.models import (
    Deployment,
    EvaluationCase,
    EvaluationRun,
    Evidence,
    Hypothesis,
    Incident,
    LogRecord,
    MetricPoint,
    Span,
)
from sentinel.db.session import init_schema, session_scope
from sentinel.detection.engine import evaluate_rules
from sentinel.domain.enums import IncidentStatus
from sentinel.evaluation.scenarios import SCENARIOS, Scenario, synthesize
from sentinel.investigation.catalog import CATALOG
from sentinel.investigation.orchestrator import create_investigation, run_investigation
from sentinel.services.projects import ensure_dependency, ensure_project, ensure_service
from sentinel.telemetry.normalize import normalize_log, normalize_metric, normalize_span
from sentinel.telemetry.store import write_logs, write_metrics, write_spans

log = get_logger(__name__)


async def _setup_project(slug: str) -> str:
    async with session_scope() as s:
        p = await ensure_project(s, slug, f"eval {slug}")
        for name, kind, tier in DEMO_SERVICES:
            await ensure_service(s, p.id, name, kind=kind, tier=tier, version="2.8.0")
        for src, tgt, kind in DEMO_EDGES:
            await ensure_dependency(s, p.id, src, tgt, kind)
        return p.id


async def _load_telemetry(project_id: str, scenario: Scenario, now: datetime) -> datetime | None:
    tel = synthesize(scenario, now)
    async with session_scope() as s:
        await write_metrics(s, project_id, [normalize_metric(r) for r in tel.metrics])
        await write_logs(s, project_id, [normalize_log(r) for r in tel.logs])
        await write_spans(s, project_id, [normalize_span(r) for r in tel.spans])
        for d in tel.deployments:
            s.add(Deployment(project_id=project_id, **d))
    return tel.onset


async def _purge(project_id: str) -> None:
    async with session_scope() as s:
        for model in (MetricPoint, LogRecord, Span):
            await s.execute(delete(model).where(model.project_id == project_id))


def _relevant_refs(evidence: list[Evidence], expected: str) -> set[str]:
    rc = CATALOG.get(expected)  # type: ignore[call-overload]
    if rc is None:
        return set()
    sigs = {r.signal for r in rc.supports}
    return {e.ref for e in evidence if set(e.signals or []) & sigs}


async def run_case(scenario: Scenario, run_id: str, idx: int) -> dict[str, Any]:
    slug = f"eval-{run_id[:6]}-{idx:03d}"
    project_id = await _setup_project(slug)
    now = utcnow()
    onset = await _load_telemetry(project_id, scenario, now)
    t0 = time.perf_counter()
    created: list[str] = []

    async def _collect(incident_id: str) -> None:
        created.append(incident_id)

    async with session_scope() as s:
        await evaluate_rules(s, project_id, enqueue=_collect)
    detect_ms = (time.perf_counter() - t0) * 1000

    result: dict[str, Any] = {
        "scenario": scenario.name,
        "fault_type": scenario.fault_type,
        "target_service": scenario.target,
        "expected": scenario.expected,
        "detected": bool(created),
        "predicted": None,
        "top3": [],
        "correct": False,
        "top3_correct": False,
        "confidence": 0.0,
        "evidence_precision": 0.0,
        "citation_validity": 1.0,
        "latency_ms": 0.0,
        "llm_ms": 0.0,
        "incident_id": None,
        "detail": {"detect_ms": round(detect_ms, 1), "incidents_opened": len(created)},
    }
    if scenario.expected == "none":
        result["correct"] = not created
        result["predicted"] = "incident" if created else "none"
        await _purge(project_id)
        return result
    if not created:
        await _purge(project_id)
        return result

    # pick the incident whose blast radius contains the target
    async with session_scope() as s:
        incs = (await s.execute(select(Incident).where(Incident.id.in_(created)))).scalars().all()
        chosen = next((i for i in incs if i.primary_service == scenario.target), None) or next((i for i in incs if scenario.target in (i.affected_services or [])), incs[0])
        inc_id = chosen.id
        result["incident_id"] = inc_id
        result["detail"]["primary_service"] = chosen.primary_service
        # time from fault injection until the alert condition was first met (rule "for" and
        # detector interval add to this in wall-clock terms; see methodology)
        result["detail"]["detection_gap_s"] = round((chosen.started_at - onset).total_seconds(), 1) if onset else None
        inv = await create_investigation(s, inc_id, trigger="evaluation")
        inv_id = inv.id
    t1 = time.perf_counter()
    async with session_scope() as s:
        try:
            inv = await run_investigation(s, inv_id)
        except Exception as exc:  # noqa: BLE001
            result["detail"]["error"] = str(exc)[:300]
            await _purge(project_id)
            return result
        result["latency_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        result["llm_ms"] = round(inv.llm_ms, 1)
        hyps = (await s.execute(select(Hypothesis).where(Hypothesis.incident_id == inc_id).order_by(Hypothesis.rank))).scalars().all()
        evidence = (await s.execute(select(Evidence).where(Evidence.incident_id == inc_id))).scalars().all()
        if hyps:
            top = hyps[0]
            result["predicted"] = top.category
            result["top3"] = [h.category for h in hyps[:3]]
            result["correct"] = top.category == scenario.expected
            result["top3_correct"] = scenario.expected in result["top3"]
            result["confidence"] = round(top.confidence, 4)
            relevant = _relevant_refs(evidence, scenario.expected)
            cited = list(top.supporting_evidence or [])
            result["evidence_precision"] = round(len([r for r in cited if r in relevant]) / len(cited), 4) if cited else 0.0
            result["citation_validity"] = round(float((top.verification or {}).get("citation_validity", 1.0)), 4)
            result["detail"]["top_title"] = top.title
            result["detail"]["culprit"] = top.culprit_service
            result["detail"]["breakdown"] = top.score_breakdown
            result["detail"]["issues"] = (top.verification or {}).get("issues", [])
        # mark resolved so the eval project reads cleanly in the UI
        inc = await s.get(Incident, inc_id)
        if inc and inc.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
            inc.status = IncidentStatus.RESOLVED
            inc.resolved_at = utcnow()
            inc.resolution_notes = f"evaluation case {scenario.name}; expected {scenario.expected}"
    await _purge(project_id)
    return result


def summarize(cases: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    faults = [c for c in cases if c["expected"] != "none"]
    controls = [c for c in cases if c["expected"] == "none"]
    detected = [c for c in faults if c["detected"]]
    n = len(faults)
    acc = sum(1 for c in faults if c["correct"]) / n if n else 0.0
    acc3 = sum(1 for c in faults if c["top3_correct"]) / n if n else 0.0
    ev_prec = sum(c["evidence_precision"] for c in detected) / len(detected) if detected else 0.0
    cit = sum(c["citation_validity"] for c in detected) / len(detected) if detected else 0.0
    fpr = sum(1 for c in controls if not c["correct"]) / len(controls) if controls else 0.0
    confident_wrong = sum(1 for c in detected if not c["correct"] and c["confidence"] >= threshold) / len(detected) if detected else 0.0
    lat = sorted(c["latency_ms"] for c in detected)
    med = lat[len(lat) // 2] if lat else 0.0
    p95 = lat[int(len(lat) * 0.95) - 1] if len(lat) >= 2 else (lat[0] if lat else 0.0)
    gaps = [c["detail"].get("detection_gap_s") for c in detected if c["detail"].get("detection_gap_s") is not None]
    # ECE
    bins: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for c in detected:
        bins[min(9, int(c["confidence"] * 10))].append((c["confidence"], c["correct"]))
    ece = 0.0
    for items in bins.values():
        conf = sum(x for x, _ in items) / len(items)
        accb = sum(1 for _, ok in items if ok) / len(items)
        ece += abs(conf - accb) * len(items) / max(1, len(detected))
    per_fault: dict[str, dict[str, Any]] = {}
    for c in faults:
        d = per_fault.setdefault(c["fault_type"], {"cases": 0, "correct": 0, "top3": 0, "detected": 0, "confidence": 0.0})
        d["cases"] += 1
        d["correct"] += int(c["correct"])
        d["top3"] += int(c["top3_correct"])
        d["detected"] += int(c["detected"])
        d["confidence"] += c["confidence"]
    for d in per_fault.values():
        d["accuracy"] = round(d["correct"] / d["cases"], 3)
        d["top3_accuracy"] = round(d["top3"] / d["cases"], 3)
        d["mean_confidence"] = round(d["confidence"] / d["cases"], 3)
        del d["confidence"]
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in faults:
        confusion[c["expected"]][c["predicted"] or "undetected"] += 1
    return {
        "cases": len(cases),
        "fault_cases": n,
        "control_cases": len(controls),
        "detection_rate": round(len(detected) / n, 4) if n else 0.0,
        "root_cause_accuracy": round(acc, 4),
        "root_cause_top3_accuracy": round(acc3, 4),
        "evidence_precision": round(ev_prec, 4),
        "citation_validity": round(cit, 4),
        "false_positive_rate": round(fpr, 4),
        "confident_wrong_rate": round(confident_wrong, 4),
        "ece": round(ece, 4),
        "median_investigation_ms": round(med, 1),
        "p95_investigation_ms": round(p95, 1),
        "mean_detection_gap_s": round(sum(gaps) / len(gaps), 1) if gaps else None,
        "mean_llm_ms": round(sum(c["llm_ms"] for c in detected) / len(detected), 1) if detected else 0.0,
        "per_fault": per_fault,
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "confidence_threshold": threshold,
    }


async def run_evaluation(*, name: str = "cli", limit: int | None = None, scenarios: list[Scenario] | None = None) -> dict[str, Any]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    await init_schema()
    scen = (scenarios or SCENARIOS)[: limit or None]
    async with session_scope() as s:
        run = EvaluationRun(name=name, config={"llm_provider": settings.llm_provider, "model": settings.ollama_model if settings.llm_provider == "ollama" else None, "scenarios": len(scen), "threshold": settings.low_confidence_threshold})
        s.add(run)
        await s.flush()
        run_id = run.id
    cases: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for i, sc in enumerate(scen):
        res = await run_case(sc, run_id, i)
        cases.append(res)
        async with session_scope() as s:
            s.add(EvaluationCase(run_id=run_id, **res))
        log.info("eval case", i=i + 1, n=len(scen), scenario=sc.name, predicted=res["predicted"], correct=res["correct"], confidence=res["confidence"], ms=res["latency_ms"])
    summary = summarize(cases, settings.low_confidence_threshold)
    summary["wall_time_s"] = round(time.perf_counter() - t0, 1)
    summary["llm_provider"] = settings.llm_provider
    summary["model"] = settings.ollama_model if settings.llm_provider == "ollama" else "deterministic"
    summary["run_id"] = run_id
    summary["completed_at"] = utcnow().isoformat()
    async with session_scope() as s:
        run = await s.get(EvaluationRun, run_id)
        assert run is not None
        run.status = "completed"
        run.summary = summary
        run.completed_at = utcnow()
    return {"summary": summary, "cases": cases}


def write_report(result: dict[str, Any], path: str) -> Path:
    s = result["summary"]
    out = Path(path)
    if not out.is_absolute():
        out = REPO_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Sentinel evaluation report",
        "",
        f"*Run `{s['run_id']}` · {s['completed_at']} · provider `{s['llm_provider']}` / `{s['model']}` · {s['cases']} cases ({s['fault_cases']} faults, {s['control_cases']} healthy controls) · wall time {s['wall_time_s']}s*",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Root-cause accuracy (top-1) | **{s['root_cause_accuracy'] * 100:.1f}%** |",
        f"| Root-cause accuracy (top-3) | {s['root_cause_top3_accuracy'] * 100:.1f}% |",
        f"| Detection rate | {s['detection_rate'] * 100:.1f}% |",
        f"| Evidence precision | {s['evidence_precision'] * 100:.1f}% |",
        f"| Citation validity (evidence-backed claims) | {s['citation_validity'] * 100:.1f}% |",
        f"| False-positive rate (healthy controls) | {s['false_positive_rate'] * 100:.1f}% |",
        f"| Confident-wrong rate (wrong & ≥ {s['confidence_threshold']:.2f}) | {s['confident_wrong_rate'] * 100:.1f}% |",
        f"| Expected calibration error | {s['ece']:.3f} |",
        f"| Median investigation time | {s['median_investigation_ms'] / 1000:.2f}s |",
        f"| p95 investigation time | {s['p95_investigation_ms'] / 1000:.2f}s |",
        f"| Mean onset→detection gap | {s['mean_detection_gap_s']}s |",
        f"| Mean model time per investigation | {s['mean_llm_ms'] / 1000:.2f}s |",
        "",
        "## Per fault type",
        "",
        "| Fault | Cases | Detected | Top-1 | Top-3 | Mean confidence |",
        "|---|---|---|---|---|---|",
    ]
    for fault, d in sorted(s["per_fault"].items()):
        lines.append(f"| {fault} | {d['cases']} | {d['detected']} | {d['accuracy'] * 100:.0f}% | {d['top3_accuracy'] * 100:.0f}% | {d['mean_confidence']:.2f} |")
    lines += ["", "## Confusion (expected → predicted)", "", "| Expected | Predicted | Count |", "|---|---|---|"]
    for exp, preds in sorted(s["confusion"].items()):
        for pred, n in sorted(preds.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {exp} | {pred} | {n} |")
    lines += ["", "## Cases", "", "| Scenario | Expected | Predicted | Conf | Evidence precision | ms |", "|---|---|---|---|---|---|"]
    for c in result["cases"]:
        mark = "✓" if c["correct"] else "✗"
        lines.append(f"| {c['scenario']} | {c['expected']} | {c['predicted']} {mark} | {c['confidence']:.2f} | {c['evidence_precision']:.2f} | {c['latency_ms']:.0f} |")
    lines += ["", "Methodology: `docs/evaluation/methodology.md`."]
    out.write_text("\n".join(lines), encoding="utf-8")
    (out.parent / "latest.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return out
