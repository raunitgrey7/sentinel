"""Dependency investigator — blast radius and downstream health on the service graph."""

from __future__ import annotations

from typing import Any

from sentinel.domain.enums import EvidenceKind
from sentinel.investigation.context import InvestigationContext
from sentinel.telemetry.store import latest_metrics, window_avg

NAME = "dependency"
LABEL = "Dependency Investigator"


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    g = ctx.service_graph
    primary = ctx.primary
    w = ctx.windows
    downstream = g.downstream(primary)
    upstream = g.upstream(primary)
    hints = g.candidate_culprits([primary, *ctx.incident.affected_services])

    # Downstream health: which dependencies are themselves degraded during the incident?
    unhealthy: list[dict[str, Any]] = []
    err_now = await window_avg(ctx.session, ctx.project_id, "http_error_rate", w.incident_start, w.incident_end)
    err_base = await window_avg(ctx.session, ctx.project_id, "http_error_rate", w.baseline_start, w.baseline_end)
    lat_now = await window_avg(ctx.session, ctx.project_id, "http_latency_p95_ms", w.incident_start, w.incident_end)
    lat_base = await window_avg(ctx.session, ctx.project_id, "http_latency_p95_ms", w.baseline_start, w.baseline_end)
    for dep, depth in sorted(downstream.items(), key=lambda kv: kv[1]):
        e_now = err_now.get(dep, (0, 0, 0, 0))[0]
        e_base = err_base.get(dep, (0, 0, 0, 0))[0]
        l_now = lat_now.get(dep, (0, 0, 0, 0))[0]
        l_base = lat_base.get(dep, (0, 0, 0, 0))[0]
        err_bad = e_now >= 0.05 and e_now >= 3 * max(e_base, 0.005)
        lat_bad = l_base > 0 and l_now >= 1.8 * l_base
        if err_bad or lat_bad:
            unhealthy.append({"service": dep, "depth": depth, "error_rate": round(e_now, 4), "baseline_error_rate": round(e_base, 4), "p95_ms": round(l_now, 1), "baseline_p95_ms": round(l_base, 1)})
            hints[dep] = min(1.0, hints.get(dep, 0.3) + 0.3)
            parts = []
            if err_bad:
                parts.append(f"error rate {e_base * 100:.1f}% → {e_now * 100:.1f}%")
            if lat_bad:
                parts.append(f"p95 {l_base:.0f}ms → {l_now:.0f}ms")
            ctx.evidence.add(
                EvidenceKind.DEPENDENCY,
                f"dependency:{dep}",
                f"downstream dependency {dep} (depth {depth} from {primary}) is degraded: " + "; ".join(parts),
                service=dep,
                signals=["dependency_error_rate_up"] if err_bad else ["latency_up"],
                weight=min(1.0, 0.5 + (0.3 if err_bad else 0.15) + (0.2 if depth == 1 else 0.0)),
                detail={"depth": depth, "error_rate": e_now, "p95_ms": l_now},
                ts_start=w.incident_start,
                ts_end=w.incident_end,
            )
    healthy_deps = [d for d in downstream if d not in {u["service"] for u in unhealthy}]
    if downstream and not unhealthy:
        ctx.evidence.add(
            EvidenceKind.DEPENDENCY,
            f"dependency:{primary}",
            f"all {len(downstream)} downstream dependencies of {primary} ({', '.join(sorted(downstream))}) show normal error rates and latency",
            service=primary,
            signals=["dependencies_healthy"],
            weight=0.5,
            direction="neutral",
            detail={"dependencies": sorted(downstream)},
        )
    if upstream:
        ctx.evidence.add(
            EvidenceKind.DEPENDENCY,
            f"dependency:{primary}",
            f"blast radius: {len(upstream)} upstream services depend on {primary} ({', '.join(sorted(upstream))})",
            service=primary,
            signals=[],
            weight=0.3,
            direction="neutral",
            detail={"upstream": sorted(upstream)},
        )
    # Infrastructure nodes (database/cache/queue) that the primary depends on
    infra = {d: g.kinds.get(d, "service") for d in downstream if g.kinds.get(d, "service") in ("database", "cache", "queue")}
    latest = await latest_metrics(ctx.session, ctx.project_id, w.incident_start)
    ctx.notes["dependency"] = {
        "downstream": downstream,
        "upstream": upstream,
        "unhealthy": unhealthy,
        "healthy": sorted(healthy_deps),
        "infra": infra,
        "culprit_hints": hints,
        "latest_metrics_services": sorted(latest),
    }
    ctx.notes["culprit_hints"] = hints
    return {"downstream": len(downstream), "upstream": len(upstream), "unhealthy": [u["service"] for u in unhealthy]}
