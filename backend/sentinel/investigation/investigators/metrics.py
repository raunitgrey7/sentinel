"""Metrics investigator — baseline deviation over every metric of every in-scope service.

Produces evidence tagged with catalog signals. Contradicting "flat" signals are emitted
only when *no* in-scope service shows the corresponding deviation, so that a healthy
neighbour never cancels a saturated culprit.
"""

from __future__ import annotations

from typing import Any

from sentinel.analysis.stats import Deviation, deviation
from sentinel.domain.enums import EvidenceDirection, EvidenceKind
from sentinel.investigation.context import InvestigationContext
from sentinel.telemetry.store import metric_names, metric_series

NAME = "metrics"
LABEL = "Metrics Investigator"

# metric → (signal when up, signal when down, signal when flat/contradiction)
RULES: dict[str, tuple[str | None, str | None, str | None]] = {
    "http_error_rate": ("error_rate_up", None, None),
    "http_latency_p95_ms": ("latency_up", None, None),
    "http_request_rate": ("request_rate_up", "throughput_down", None),
    "http_inflight": ("inflight_requests_up", None, None),
    "cpu_usage": ("cpu_up", None, "cpu_flat"),
    "memory_usage_mb": ("memory_up", None, "memory_flat"),
    "db_connections_waiting": ("db_pool_waiting_up", None, None),
    "db_connection_acquire_ms": ("db_acquire_latency_up", None, None),
    "db_query_latency_ms": ("db_query_latency_up", None, "db_latency_flat"),
    "redis_errors_rate": ("redis_errors_up", None, None),
    "cache_hit_rate": (None, "cache_hit_rate_down", None),
    "queue_depth": ("queue_depth_up", None, "queue_depth_flat"),
    "consumer_lag_s": ("consumer_lag_up", None, None),
    "worker_errors_rate": ("worker_errors_up", None, None),
    "network_latency_ms": ("network_latency_up", None, None),
    "network_errors_rate": ("network_errors_up", None, None),
    "dependency_error_rate": ("dependency_error_rate_up", None, None),
    "restart_count": ("restart_count_up", None, None),
    "gc_pause_ms": ("gc_pause_up", None, None),
}
# Saturation metrics compare against their ceiling instead of the baseline.
SATURATION = {
    "db_connections_active": ("db_connections_max", "db_pool_saturated", 0.9),
    "thread_pool_active": ("thread_pool_max", "thread_pool_saturated", 0.9),
}
UNITS = {"ms": "ms", "rate": "", "usage": "%", "mb": "MB", "s": "s"}


def _fmt(metric: str, v: float) -> str:
    if metric.endswith("_ms"):
        return f"{v:.0f}ms"
    if metric.endswith("_rate") or metric == "cache_hit_rate":
        return f"{v * 100:.1f}%"
    if metric == "cpu_usage":
        return f"{v:.0f}%"
    if metric.endswith("_mb"):
        return f"{v:.0f}MB"
    if metric.endswith("_s"):
        return f"{v:.1f}s"
    return f"{v:.2f}"


def _strength(d: Deviation) -> float:
    """0..1 from magnitude: combine z-score and relative change."""
    z = min(abs(d.z_score) / 8.0, 1.0)
    pct = min(abs(d.pct_change) / 3.0, 1.0)
    return max(0.3, min(1.0, 0.5 * z + 0.5 * pct + 0.2))


# Deviations on services *upstream* of the primary are symptoms of the incident, not
# causes: only these generic signals are kept for them, at reduced weight.
SYMPTOM_SIGNALS = {"error_rate_up", "latency_up", "throughput_down", "throughput_collapse"}


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    w = ctx.windows
    deviations: dict[str, dict[str, Deviation]] = {}
    significant = 0
    saturated_seen: set[str] = set()
    up_seen: set[str] = set()
    upstream = set(ctx.service_graph.upstream(ctx.primary))

    for svc in ctx.scope_services:
        is_symptom_service = svc in upstream and svc != ctx.primary
        names = await metric_names(ctx.session, ctx.project_id, svc, w.baseline_start)
        deviations[svc] = {}
        for name in names:
            base = await metric_series(ctx.session, ctx.project_id, svc, name, w.baseline_start, w.baseline_end)
            cur = await metric_series(ctx.session, ctx.project_id, svc, name, w.incident_start, w.incident_end)
            if not cur:
                continue
            d = deviation(name, base, cur)
            deviations[svc][name] = d

            # --- saturation metrics ---------------------------------------------------------
            if name in SATURATION:
                max_name, signal, thr = SATURATION[name]
                mx = await metric_series(ctx.session, ctx.project_id, svc, max_name, w.incident_start, w.incident_end)
                ceiling = mx[-1].value if mx else 0.0
                if ceiling > 0:
                    util = d.incident_max / ceiling
                    base_util = (d.baseline_mean / ceiling) if base else 0.0
                    if util >= thr and is_symptom_service:
                        continue
                    if util >= thr:
                        saturated_seen.add(signal)
                        significant += 1
                        ctx.evidence.add(
                            EvidenceKind.METRIC,
                            f"metrics:{name}",
                            f"{svc} {name.replace('_', ' ')} reached {util * 100:.0f}% of capacity ({d.incident_max:.0f}/{ceiling:.0f}); baseline {base_util * 100:.0f}%",
                            service=svc,
                            signals=[signal],
                            weight=min(1.0, 0.6 + (util - thr) * 4),
                            detail={"deviation": d.to_dict(), "ceiling": ceiling, "utilization": round(util, 3)},
                            ts_start=d.onset or w.incident_start,
                            ts_end=w.incident_end,
                        )
                        if d.onset:
                            ctx.add_timeline(d.onset, "metric", f"{svc} {name.replace('_', ' ')} > {thr * 100:.0f}% of capacity", metric=name, service=svc)
                continue

            rule = RULES.get(name)
            if not rule:
                continue
            up_sig, down_sig, _flat = rule
            if not d.significant():
                continue
            sig = up_sig if d.direction == "up" else down_sig if d.direction == "down" else None
            if not sig:
                continue
            signals = [sig]
            if name == "http_request_rate" and d.direction == "down" and d.baseline_mean > 0 and d.incident_mean < 0.2 * d.baseline_mean:
                signals.append("throughput_collapse")
            if name == "memory_usage_mb" and d.direction == "up" and _monotonic([p.value for p in cur]):
                signals.append("memory_trend_monotonic")
            if name == "cpu_usage" and d.direction == "up" and d.incident_mean < 60:
                # A modest CPU rise is not saturation.
                signals = []
                continue
            if is_symptom_service:
                signals = [sg for sg in signals if sg in SYMPTOM_SIGNALS]
                if not signals:
                    continue
            up_seen.add(name)
            significant += 1
            mult = (d.incident_mean / d.baseline_mean) if d.baseline_mean > 1e-9 else float("inf")
            if mult == float("inf") or abs(d.baseline_mean) < 1e-3:
                change = "from a ~zero baseline"
            elif mult < 100:
                change = f"{mult:.1f}×"
            else:
                change = f"{d.pct_change * 100:+.0f}%"
            summary = (
                f"{svc} {name.replace('_', ' ')} {'increased' if d.direction == 'up' else 'decreased'} "
                f"from {_fmt(name, d.baseline_mean)} → {_fmt(name, d.incident_mean)} (peak {_fmt(name, d.incident_max)}, {change}, z={d.z_score:.1f})"
            )
            ctx.evidence.add(
                EvidenceKind.METRIC,
                f"metrics:{name}",
                summary,
                service=svc,
                signals=signals,
                weight=_strength(d) * (0.5 if is_symptom_service else 1.0),
                detail={"deviation": d.to_dict(), "symptom_of_primary": is_symptom_service},
                ts_start=d.onset or w.incident_start,
                ts_end=w.incident_end,
            )
            if d.onset and (svc == ctx.primary or name in ("http_error_rate", "http_latency_p95_ms")):
                ctx.add_timeline(d.onset, "metric", f"{svc} {name.replace('_', ' ')} deviated ({change})", metric=name, service=svc)

    # --- contradiction ("flat") evidence for the primary service ------------------------------
    primary_devs = deviations.get(ctx.primary, {})
    for name, (_up, _down, flat) in RULES.items():
        if not flat or name in up_seen:
            continue
        d = primary_devs.get(name)
        if d is None or d.samples_incident < 2:
            continue
        ctx.evidence.add(
            EvidenceKind.METRIC,
            f"metrics:{name}",
            f"{ctx.primary} {name.replace('_', ' ')} remained normal ({_fmt(name, d.baseline_mean)} → {_fmt(name, d.incident_mean)})",
            service=ctx.primary,
            signals=[flat],
            weight=0.5,
            direction=EvidenceDirection.CONTRADICTS,
            detail={"deviation": d.to_dict()},
            ts_start=w.incident_start,
            ts_end=w.incident_end,
        )

    ctx.notes["deviations"] = {svc: {n: d.to_dict() for n, d in devs.items() if d.significant()} for svc, devs in deviations.items()}
    return {"services": len(deviations), "significant": significant, "saturated": sorted(saturated_seen)}


def _monotonic(values: list[float], tolerance: float = 0.8) -> bool:
    if len(values) < 4:
        return False
    ups = sum(1 for a, b in zip(values, values[1:], strict=False) if b >= a)
    return ups / (len(values) - 1) >= tolerance
