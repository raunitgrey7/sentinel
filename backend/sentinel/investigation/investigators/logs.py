"""Log investigator — template clustering, burst detection, keyword→signal mapping."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sentinel.domain.enums import EvidenceKind
from sentinel.investigation.context import InvestigationContext
from sentinel.telemetry.store import LogRow, logs_window

NAME = "logs"
LABEL = "Log Investigator"

ERROR_LEVELS = ("ERROR", "FATAL", "WARN")

# (compiled pattern, signal, weight)
KEYWORDS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"(connection pool|pool exhaust|acquire (a )?(database |db )?connection|no connection available|pool=\S+/\S+|waiting for connection)", re.I), "log_pool_exhausted", 0.9),
    (re.compile(r"(slow query|statement timeout|lock wait|query took|canceling statement)", re.I), "log_db_slow", 0.8),
    (re.compile(r"redis.*(error|timeout|refused|unavailable|connection)|(error|timeout|refused).*redis", re.I), "log_redis_error", 0.9),
    (re.compile(r"(out of memory|\boom\b|heap (space|exhausted)|memory (limit|pressure)|killed process)", re.I), "log_oom", 0.9),
    (re.compile(r"(cpu (throttl|saturat)|throttled)", re.I), "log_cpu_throttle", 0.7),
    (re.compile(r"\bdeadlock\b", re.I), "log_deadlock", 0.95),
    (re.compile(r"(thread pool|worker pool|no available worker|threads? (exhaust|starv)|all workers busy)", re.I), "log_thread_starvation", 0.85),
    (re.compile(r"(queue (backlog|full|depth)|consumer lag|messages? pending)", re.I), "log_queue_backlog", 0.8),
    (re.compile(r"(connection reset|econnreset|broken pipe|unexpected eof|connection refused|econnrefused)", re.I), "log_connection_reset", 0.8),
    (re.compile(r"(timed? ?out|timeout)", re.I), "log_timeout", 0.5),
    (re.compile(r"(upstream|dependency|downstream).*(fail|error|5\d\d)|bad gateway|service unavailable|\b50[23]\b", re.I), "log_upstream_5xx", 0.7),
    (re.compile(r"(invalid (config|setting|value)|config(uration)? (error|reload)|feature flag)", re.I), "log_config_error", 0.8),
]
EXCEPTION = re.compile(r"(exception|traceback|nullpointer|typeerror|keyerror|panic|unhandled)", re.I)


async def run(ctx: InvestigationContext) -> dict[str, Any]:
    w = ctx.windows
    baseline = await logs_window(ctx.session, ctx.project_id, ctx.scope_services, w.baseline_start, w.baseline_end, levels=ERROR_LEVELS)
    current = await logs_window(ctx.session, ctx.project_id, ctx.scope_services, w.incident_start, w.incident_end, levels=ERROR_LEVELS)

    base_counts: dict[tuple[str, str], int] = defaultdict(int)
    for r in baseline:
        base_counts[(r.service, r.template_hash)] += 1

    clusters: dict[tuple[str, str], list[LogRow]] = defaultdict(list)
    for r in current:
        clusters[(r.service, r.template_hash)].append(r)

    base_minutes = max((w.baseline_end - w.baseline_start).total_seconds() / 60, 1)
    cur_minutes = max((w.incident_end - w.incident_start).total_seconds() / 60, 1)

    persisted: list[dict[str, Any]] = []
    templates_for_signature: list[str] = []
    signals_hit: set[str] = set()
    upstream = set(ctx.service_graph.upstream(ctx.primary)) - {ctx.primary}
    for (svc, thash), rows in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        count = len(rows)
        bcount = base_counts.get((svc, thash), 0)
        rate_now = count / cur_minutes
        rate_base = bcount / base_minutes
        burst = (rate_now + 0.1) / (rate_base + 0.1)
        template = rows[0].template or rows[0].message
        level = max((r.level for r in rows), key=lambda lv: ("WARN", "ERROR", "FATAL").index(lv) if lv in ("WARN", "ERROR", "FATAL") else 0)
        first, last = rows[0].ts, rows[-1].ts
        persisted.append(
            {
                "service": svc,
                "level": level,
                "template": template,
                "template_hash": thash,
                "count": count,
                "baseline_count": bcount,
                "burst_ratio": round(burst, 2),
                "sample": rows[0].message,
                "first_ts": first,
                "last_ts": last,
            }
        )
        if burst < 3:
            continue  # steady background noise, however loud
        matched: list[str] = []
        weight = 0.4
        for pat, sig, wgt in KEYWORDS:
            if pat.search(template) or pat.search(rows[0].message):
                matched.append(sig)
                weight = max(weight, wgt)
        is_new = bcount == 0 and level in ("ERROR", "FATAL")
        if is_new and EXCEPTION.search(template):
            matched.append("log_exception_new")
            weight = max(weight, 0.7)
        if not matched:
            if level in ("ERROR", "FATAL") and burst >= 5:
                matched = ["error_rate_up"]
                weight = 0.5
            else:
                continue
        if svc in upstream:
            # errors logged by callers of the primary are symptoms ("upstream X returned 502")
            matched = [sg for sg in matched if sg in ("error_rate_up",)] or ["error_rate_up"]
            weight = min(weight, 0.4)
        signals_hit.update(matched)
        templates_for_signature.append(template)
        burst_txt = f"{burst:.0f}× baseline" if bcount else "new (absent from baseline)"
        ctx.evidence.add(
            EvidenceKind.LOG,
            f"logs:{svc}",
            f"{count} × {level} on {svc}: \"{template[:110]}\" — {burst_txt}",
            service=svc,
            signals=matched,
            weight=min(1.0, weight * min(1.0, 0.6 + burst / 20)),
            detail={"template_hash": thash, "count": count, "baseline_count": bcount, "burst_ratio": round(burst, 2), "sample": rows[0].message[:500], "level": level},
            ts_start=first,
            ts_end=last,
        )
        if svc == ctx.primary and level in ("ERROR", "FATAL"):
            ctx.add_timeline(first, "log", f"{svc}: first \"{template[:60]}\" error", service=svc)

    ctx.notes["error_clusters"] = persisted[: ctx.settings.max_evidence_per_kind]
    ctx.notes["error_templates"] = templates_for_signature[:8]
    return {"clusters": len(clusters), "signals": sorted(signals_hit), "records": len(current)}
