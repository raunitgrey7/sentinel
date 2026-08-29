"""Trace investigator — per-operation latency deviation, error spans, critical path."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sentinel.analysis.stats import percentile
from sentinel.domain.enums import EvidenceKind
from sentinel.investigation.context import InvestigationContext
from sentinel.telemetry.store import SpanRow, spans_window

NAME = "traces"
LABEL = "Trace Investigator"


def _op_signal(op: str, attrs: dict[str, Any], *, slow: bool, error: bool, kind: str) -> list[str]:
    o = op.lower()
    sig: list[str] = []
    if slow and ("acquire" in o or attrs.get("db.operation") == "acquire_connection"):
        sig.append("trace_db_acquire_slow")
    elif slow and (o.startswith("db.") or attrs.get("db.system")):
        sig.append("trace_db_query_slow")
    if error and (o.startswith("cache.") or attrs.get("cache.system")):
        sig.append("trace_cache_error")
    if error and kind == "client":
        sig.append("trace_client_error")
    return sig


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    w = ctx.windows
    base = await spans_window(ctx.session, ctx.project_id, ctx.scope_services, w.baseline_start, w.baseline_end)
    cur = await spans_window(ctx.session, ctx.project_id, ctx.scope_services, w.incident_start, w.incident_end)
    if not cur:
        return {"spans": 0}

    def group(rows: list[SpanRow]) -> dict[tuple[str, str], list[SpanRow]]:
        g: dict[tuple[str, str], list[SpanRow]] = defaultdict(list)
        for r in rows:
            g[(r.service, r.operation)].append(r)
        return g

    gb, gc = group(base), group(cur)
    findings: list[dict[str, Any]] = []
    signals_hit: set[str] = set()
    upstream = set(ctx.service_graph.upstream(ctx.primary)) - {ctx.primary}

    # Index current spans by id for parent/child reasoning.
    children: dict[str, list[SpanRow]] = defaultdict(list)
    for s in cur:
        if s.parent_span_id:
            children[s.parent_span_id].append(s)

    for (svc, op), rows in gc.items():
        durs = [r.duration_ms for r in rows]
        p95 = percentile(durs, 0.95)
        bdurs = [r.duration_ms for r in gb.get((svc, op), [])]
        bp95 = percentile(bdurs, 0.95) if bdurs else None
        err_rate = sum(1 for r in rows if r.status == "error") / len(rows)
        berr = (sum(1 for r in gb.get((svc, op), []) if r.status == "error") / len(bdurs)) if bdurs else 0.0
        slow = bp95 is not None and bp95 > 0 and p95 >= max(2.0 * bp95, bp95 + 50)
        erroring = err_rate >= 0.1 and err_rate >= berr * 3
        if not slow and not erroring:
            continue
        kind = rows[0].kind
        sig = _op_signal(op, rows[0].attributes, slow=slow, error=erroring, kind=kind)

        # client span slow while callee's server span is fine → network
        if slow and kind == "client":
            child_ok = False
            for r in rows[:200]:
                for ch in children.get(r.span_id, []):
                    if ch.service != svc and ch.kind == "server":
                        cb = [x.duration_ms for x in gb.get((ch.service, ch.operation), [])]
                        if cb and ch.duration_ms <= 1.5 * percentile(cb, 0.95):
                            child_ok = True
                            break
                if child_ok:
                    break
            if child_ok:
                sig.append("trace_client_slow_server_ok")
        if erroring and kind == "server" and svc != ctx.primary and svc not in upstream:
            sig.append("trace_downstream_error")
        if svc in upstream:
            sig = [sg for sg in sig if sg in ("trace_client_slow_server_ok",)]

        mult = (p95 / bp95) if bp95 else None
        parts = []
        if slow:
            parts.append(f"p95 {bp95:.0f}ms → {p95:.0f}ms ({mult:.1f}×)")
        if erroring:
            parts.append(f"error rate {berr * 100:.0f}% → {err_rate * 100:.0f}%")
        summary = f"span {svc}/{op}: " + "; ".join(parts) + f" over {len(rows)} spans"
        weight = 0.5
        if slow and mult:
            weight = min(1.0, 0.5 + min(mult, 10) / 20)
        if erroring:
            weight = max(weight, min(1.0, 0.5 + err_rate))
        findings.append({"service": svc, "operation": op, "p95": p95, "baseline_p95": bp95, "error_rate": err_rate, "signals": sig})
        signals_hit.update(sig)
        ctx.evidence.add(
            EvidenceKind.TRACE,
            f"traces:{svc}/{op}",
            summary,
            service=svc,
            signals=sig or (["latency_up"] if slow else ["error_rate_up"]),
            weight=weight,
            detail={"operation": op, "kind": kind, "p95_ms": round(p95, 1), "baseline_p95_ms": round(bp95, 1) if bp95 else None, "error_rate": round(err_rate, 3), "spans": len(rows)},
            ts_start=rows[0].start_ts,
            ts_end=rows[-1].start_ts,
        )

    # Critical path of the slowest recent root span from the primary service.
    roots = [s for s in cur if s.parent_span_id is None and s.service in ctx.scope_services]
    critical: list[dict[str, Any]] = []
    if roots:
        slowest = max(roots, key=lambda s: s.duration_ms)
        node = slowest
        while node is not None:
            critical.append({"service": node.service, "operation": node.operation, "duration_ms": round(node.duration_ms, 1), "status": node.status})
            kids = children.get(node.span_id, [])
            node = max(kids, key=lambda s: s.duration_ms) if kids else None  # type: ignore[assignment]
        if len(critical) > 1:
            path = " → ".join(f"{c['service']}/{c['operation']} ({c['duration_ms']:.0f}ms)" for c in critical)
            ctx.evidence.add(
                EvidenceKind.TRACE,
                "traces:critical_path",
                f"slowest trace critical path: {path}",
                service=critical[-1]["service"],
                signals=[],
                weight=0.4,
                detail={"path": critical, "trace_id": slowest.trace_id},
                ts_start=slowest.start_ts,
            )
    ctx.notes["trace_findings"] = findings[: ctx.settings.max_evidence_per_kind]
    ctx.notes["critical_path"] = critical
    return {"spans": len(cur), "findings": len(findings), "signals": sorted(signals_hit)}
