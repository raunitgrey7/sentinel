"""Evaluation scenario library and synthetic telemetry generator.

Each scenario is a fault injected into a synthetic copy of the demo shop. The generator
produces baseline + incident telemetry (metrics, logs, spans, deployments) for *every*
service in the topology, including realistic propagation of failures to upstream callers,
so the investigator has to separate cause from symptom.

Ground truth is the expected ``RootCauseCategory``. Variants change intensity, whether a
confounding deployment is present, noise, and the target service, giving 100+ cases.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sentinel.api.bootstrap import DEMO_EDGES, DEMO_SERVICES

STEP_S = 10
BASELINE_MIN = 15
INCIDENT_MIN = 5

DB_SERVICES = {"auth-service", "order-service", "inventory-service", "payment-service"}
CACHE_SERVICES = {"auth-service", "inventory-service", "payment-service"}
QUEUE_SERVICES = {"order-service", "notification-worker"}
HTTP_SERVICES = {"frontend", "api-gateway", "auth-service", "order-service", "inventory-service", "payment-service"}
EXTERNAL = {"payment-service": "payment-provider", "notification-worker": "email-provider"}

# caller → callee edges among HTTP services (for propagation)
CALLS = [(s, t) for s, t, k in DEMO_EDGES if k == "http"]
# fraction of caller traffic that touches the callee
CALL_FRACTION = {("frontend", "api-gateway"): 1.0, ("api-gateway", "auth-service"): 0.9, ("api-gateway", "order-service"): 0.6, ("order-service", "inventory-service"): 0.9, ("order-service", "payment-service"): 0.8}

BASE_RATE = {"frontend": 60.0, "api-gateway": 60.0, "auth-service": 54.0, "order-service": 36.0, "inventory-service": 32.0, "payment-service": 29.0, "notification-worker": 10.0}


@dataclass(frozen=True)
class Scenario:
    name: str
    fault_type: str
    target: str
    expected: str
    variant: dict[str, Any] = field(default_factory=dict)

    @property
    def intensity(self) -> float:
        return float(self.variant.get("intensity", 1.0))

    @property
    def with_deploy(self) -> bool:
        return bool(self.variant.get("with_deploy", False))

    @property
    def seed(self) -> int:
        return int(self.variant.get("seed", 0))


@dataclass
class Telemetry:
    metrics: list[dict[str, Any]] = field(default_factory=list)
    logs: list[dict[str, Any]] = field(default_factory=list)
    spans: list[dict[str, Any]] = field(default_factory=list)
    deployments: list[dict[str, Any]] = field(default_factory=list)
    onset: datetime | None = None


def _base_metrics(svc: str, rng: random.Random) -> dict[str, float]:
    n = lambda mu, sd: max(0.0, rng.gauss(mu, sd))  # noqa: E731
    m: dict[str, float] = {"cpu_usage": n(30, 4), "memory_usage_mb": n(420, 15), "gc_pause_ms": n(5, 1), "restart_count": 0.0}
    if svc in HTTP_SERVICES:
        m.update(
            {
                "http_request_rate": n(BASE_RATE.get(svc, 20), 2),
                "http_error_rate": max(0.0, rng.gauss(0.005, 0.002)),
                "http_latency_p95_ms": n(120 if svc != "frontend" else 180, 10),
                "http_latency_p50_ms": n(40, 4),
                "http_inflight": n(5, 1),
                "thread_pool_active": n(8, 1.5),
                "thread_pool_max": 32.0,
                "network_latency_ms": n(5, 1),
                "network_errors_rate": 0.0,
                "dependency_error_rate": max(0.0, rng.gauss(0.003, 0.001)),
            }
        )
    if svc in DB_SERVICES:
        m.update({"db_connections_active": n(12, 2), "db_connections_max": 40.0, "db_connections_waiting": 0.0, "db_connection_acquire_ms": n(2, 0.5), "db_query_latency_ms": n(8, 1.5)})
    if svc in CACHE_SERVICES:
        m.update({"redis_errors_rate": 0.0, "cache_hit_rate": min(1.0, n(0.92, 0.02))})
    if svc in QUEUE_SERVICES:
        m.update({"queue_depth": n(20, 5), "consumer_lag_s": n(0.5, 0.1), "worker_errors_rate": 0.0})
    return m


def _ramp(t: float, shape: str = "fast") -> float:
    """0..1 progression over the incident window."""
    if shape == "fast":
        return min(1.0, t * 4)
    if shape == "linear":
        return t
    if shape == "step":
        return 1.0
    return 1 - math.exp(-5 * t)


# --------------------------------------------------------------------------------------
# Fault effect models. Each returns (metric overrides, log templates, span effects) for the
# *target* at progression p (0..1) with intensity k.
# --------------------------------------------------------------------------------------


def _fx(fault: str, p: float, k: float, base: dict[str, float], rng: random.Random) -> tuple[dict[str, float], list[tuple[str, str, float]], dict[str, Any]]:
    """Returns (metric overrides, [(level, message, per-sample rate)], span effects)."""
    o: dict[str, float] = {}
    logs: list[tuple[str, str, float]] = []
    spans: dict[str, Any] = {}
    j = lambda mu, sd: rng.gauss(mu, sd)  # noqa: E731
    if fault in ("db_pool_exhaustion", "bad_deployment"):
        util = min(1.0, 0.3 + 0.75 * p * k)
        o["db_connections_active"] = 40 * util
        o["db_connections_waiting"] = max(0.0, (util - 0.85) * 120 * k)
        o["db_connection_acquire_ms"] = 2 + 2400 * max(0.0, util - 0.8) * 5 * k
        o["http_error_rate"] = min(0.9, 0.35 * max(0.0, util - 0.85) * 6 * k + j(0, 0.01))
        o["http_latency_p95_ms"] = 120 + 2600 * max(0.0, util - 0.8) * 5
        o["http_inflight"] = 5 + 60 * max(0.0, util - 0.85) * 6
        if util > 0.92:
            logs.append(("ERROR", f"failed to acquire database connection after {int(j(5000, 300))}ms (pool=40/40, waiting={int(o['db_connections_waiting'])})", 6 * k))
            logs.append(("WARN", f"connection acquisition slow: {int(o['db_connection_acquire_ms'])}ms", 3))
            spans["db.acquire_connection"] = {"mult": 40 * k, "error": 0.3}
    elif fault == "database_latency":
        o["db_query_latency_ms"] = 8 + 420 * p * k
        o["db_connection_acquire_ms"] = 2 + 30 * p
        o["http_latency_p95_ms"] = 120 + 1700 * p * k
        o["http_error_rate"] = min(0.5, 0.09 * p * k + j(0, 0.005))
        o["db_connections_active"] = 12 + 14 * p
        if p > 0.2:
            logs.append(("WARN", f"slow query: SELECT * FROM orders WHERE user_id = 1 took {int(j(800, 120))}ms", 5 * k))
            logs.append(("ERROR", "statement timeout: canceling statement due to statement timeout", 2 * k))
            spans["db.query"] = {"mult": 30 * k, "error": 0.1}
    elif fault == "redis_failure":
        o["redis_errors_rate"] = min(1.0, 0.9 * p * k)
        o["cache_hit_rate"] = max(0.0, 0.92 * (1 - p))
        o["http_error_rate"] = min(0.6, 0.18 * p * k + j(0, 0.005))
        o["http_latency_p95_ms"] = 120 + 900 * p
        o["db_query_latency_ms"] = 8 + 6 * p  # cache misses hit DB harder
        if p > 0.1:
            logs.append(("ERROR", "redis connection refused (ECONNREFUSED 10.0.0.5:6379) while fetching session", 8 * k))
            logs.append(("WARN", "cache unavailable, falling back to database", 4))
            spans["cache.get"] = {"mult": 1.0, "error": 0.9}
    elif fault == "memory_leak":
        o["memory_usage_mb"] = 420 + 1500 * p * k
        o["gc_pause_ms"] = 5 + 130 * p * p * k
        o["http_latency_p95_ms"] = 120 + 1500 * p * p * k
        o["http_error_rate"] = min(0.4, 0.07 * p * p * k + j(0, 0.003))
        if p > 0.9:
            o["restart_count"] = 1.0
        if p > 0.5:
            logs.append(("WARN", f"GC pressure: heap {int(o['memory_usage_mb'])}MB/2048MB, pause {int(o['gc_pause_ms'])}ms", 4 * k))
        if p > 0.85:
            logs.append(("FATAL", "java.lang.OutOfMemoryError: Java heap space", 2 * k))
    elif fault == "cpu_saturation":
        o["cpu_usage"] = min(100.0, 30 + 68 * p * k)
        o["http_latency_p95_ms"] = 120 + 1600 * p * k
        o["http_error_rate"] = min(0.3, 0.06 * p * k + j(0, 0.003))
        o["http_request_rate"] = base.get("http_request_rate", 20) * (1 - 0.15 * p)
        if p > 0.4:
            logs.append(("WARN", f"cpu throttled: {int(o['cpu_usage'])}% utilization, request processing delayed", 4 * k))
            logs.append(("ERROR", "request timed out after 3000ms (worker busy)", 2 * k))
    elif fault == "http_500_spike":
        o["http_error_rate"] = min(0.9, 0.35 * min(1.0, p * 3) * k + j(0, 0.01))
        logs.append(("ERROR", "Unhandled exception in /checkout: TypeError: cannot read property 'amount' of undefined at PricingService.compute", 12 * k))
        spans["http.checkout"] = {"mult": 1.0, "error": 0.35 * k}
    elif fault == "config_regression":
        o["http_error_rate"] = min(0.8, 0.28 * min(1.0, p * 3) * k + j(0, 0.01))
        o["dependency_error_rate"] = min(0.8, 0.3 * min(1.0, p * 3) * k)
        o["http_latency_p95_ms"] = 120 + 100 * p
        logs.append(("ERROR", "config error: PAYMENT_TIMEOUT_MS=200 is below the minimum supported value; upstream call timed out after 200ms", 10 * k))
        spans["call payment-provider"] = {"mult": 1.0, "error": 0.3 * k}
    elif fault == "network_latency":
        o["network_latency_ms"] = 5 + 380 * p * k
        o["http_latency_p95_ms"] = 120 + 1500 * p * k
        o["http_error_rate"] = min(0.3, 0.045 * p * k + j(0, 0.003))
        if p > 0.2:
            logs.append(("WARN", f"timeout calling inventory-service (>{int(j(1000, 50))}ms), retrying", 5 * k))
            spans["call inventory-service"] = {"mult": 25 * k, "error": 0.05, "server_ok": True}
    elif fault == "packet_loss":
        o["network_errors_rate"] = min(0.8, 0.28 * p * k)
        o["http_error_rate"] = min(0.7, 0.22 * p * k + j(0, 0.01))
        o["dependency_error_rate"] = min(0.8, 0.26 * p * k)
        if p > 0.1:
            logs.append(("ERROR", "connection reset by peer while calling payment-service (ECONNRESET)", 8 * k))
            logs.append(("WARN", "unexpected EOF from upstream, retrying request", 3))
            spans["call payment-service"] = {"mult": 1.0, "error": 0.25 * k}
    elif fault == "queue_backlog":
        o["queue_depth"] = 20 + 3200 * p * k
        o["consumer_lag_s"] = 0.5 + 130 * p * k
        o["worker_errors_rate"] = min(0.5, 0.12 * p * k)
        o["http_error_rate"] = min(0.1, 0.012 * p + j(0, 0.002))
        if p > 0.2:
            logs.append(("WARN", f"queue backlog: {int(o['queue_depth'])} messages pending, consumer lag {int(o['consumer_lag_s'])}s", 5 * k))
            logs.append(("ERROR", "consumer failed to process message: handler timeout", 2 * k))
    elif fault == "thread_starvation":
        o["thread_pool_active"] = min(32.0, 8 + 26 * min(1.0, p * 2) * k)
        o["http_latency_p95_ms"] = 120 + 2200 * p * k
        o["http_error_rate"] = min(0.5, 0.12 * p * k + j(0, 0.005))
        o["http_request_rate"] = base.get("http_request_rate", 20) * (1 - 0.4 * p)
        o["cpu_usage"] = 30 - 8 * p
        if p > 0.3:
            logs.append(("ERROR", "thread pool exhausted: all 32 workers busy, request queued for 4200ms", 7 * k))
    elif fault == "deadlock":
        o["http_request_rate"] = base.get("http_request_rate", 20) * max(0.02, 1 - 1.3 * p * k)
        o["http_inflight"] = 5 + 250 * p * k
        o["http_latency_p95_ms"] = 120 + 8000 * p
        o["http_error_rate"] = min(0.9, 0.4 * p * k + j(0, 0.01))
        o["cpu_usage"] = max(2.0, 30 - 26 * p)
        if p > 0.2:
            logs.append(("ERROR", "deadlock detected: worker-7 waiting on lock 'inventory_reserve' held by worker-3", 4 * k))
            logs.append(("ERROR", "request timed out after 30000ms (hung)", 5 * k))
    elif fault == "dependency_failure":
        ext = EXTERNAL.get("payment-service", "payment-provider")
        o["dependency_error_rate"] = min(0.9, 0.6 * min(1.0, p * 3) * k)
        o["http_error_rate"] = min(0.8, 0.32 * min(1.0, p * 3) * k + j(0, 0.01))
        logs.append(("ERROR", f"upstream {ext} returned 503 Service Unavailable for POST /v1/charges", 10 * k))
        spans[f"call {ext}"] = {"mult": 1.0, "error": 0.6 * k}
    return o, logs, spans


def _propagate(metrics: dict[str, dict[str, float]], bases: dict[str, dict[str, float]]) -> None:
    """Push error rate / latency from callees up to callers, attenuated by call fraction."""
    for caller, callee in reversed(CALLS):
        if callee not in metrics or caller not in metrics:
            continue
        frac = CALL_FRACTION.get((caller, callee), 0.5)
        b_err = bases[callee].get("http_error_rate", 0.005)
        c_err = metrics[callee].get("http_error_rate", 0.0)
        excess_err = max(0.0, c_err - b_err)
        metrics[caller]["http_error_rate"] = min(0.95, metrics[caller].get("http_error_rate", 0.005) + excess_err * frac * 0.9)
        metrics[caller]["dependency_error_rate"] = min(0.95, metrics[caller].get("dependency_error_rate", 0.003) + excess_err * frac)
        b_lat = bases[callee].get("http_latency_p95_ms", 120)
        c_lat = metrics[callee].get("http_latency_p95_ms", 120)
        excess_lat = max(0.0, c_lat - b_lat)
        metrics[caller]["http_latency_p95_ms"] = metrics[caller].get("http_latency_p95_ms", 120) + excess_lat * frac * 0.85
        # Callers of a stalled callee see their own request rate drop only slightly
        b_rate = bases[callee].get("http_request_rate", 20)
        c_rate = metrics[callee].get("http_request_rate", 20)
        if b_rate > 0 and c_rate < 0.3 * b_rate:
            metrics[caller]["http_latency_p95_ms"] += 3000 * frac


def synthesize(scenario: Scenario, now: datetime) -> Telemetry:
    rng = random.Random(scenario.seed * 7919 + hash(scenario.name) % 10_000)
    t = Telemetry()
    total_min = BASELINE_MIN + INCIDENT_MIN
    start = now - timedelta(minutes=total_min)
    onset = now - timedelta(minutes=INCIDENT_MIN)
    t.onset = onset
    services = [s for s, _, _ in DEMO_SERVICES]
    bases = {s: _base_metrics(s, rng) for s in services}
    k = scenario.intensity

    # confounding / causal deployments
    if scenario.fault_type in ("bad_deployment", "http_500_spike", "config_regression") or scenario.with_deploy:
        dep_svc = scenario.target if scenario.fault_type in ("bad_deployment", "http_500_spike", "config_regression") else scenario.variant.get("deploy_service", "inventory-service")
        mins_before = float(scenario.variant.get("deploy_minutes_before", 4.0))
        commit = {
            "bad_deployment": ("a81f2c9d", "increase transaction concurrency from 8 to 64 for faster checkout", ["payment/db/pool.py", "payment/checkout/worker.py"], {}),
            "http_500_spike": ("c4d1e77b", "refactor pricing service to new amount model", ["order/pricing/service.py", "order/handlers/checkout.py"], {}),
            "config_regression": ("f00dbabe", "tune payment timeout for faster failure", ["config/payment.yaml"], {"payment.timeout_ms": "5000 -> 200"}),
        }.get(scenario.fault_type, ("9b1c0aa1", "update dependency versions and docs", ["requirements.txt", "README.md"], {}))
        t.deployments.append(
            {
                "service": dep_svc,
                "version": "2.8.1",
                "previous_version": "2.8.0",
                "commit_sha": commit[0],
                "commit_message": commit[1],
                "author": "dev@example.com",
                "changed_files": commit[2],
                "config_changes": commit[3],
                "deployed_at": onset - timedelta(minutes=mins_before),
            }
        )

    n_steps = int(total_min * 60 / STEP_S)
    trace_counter = 0
    for i in range(n_steps):
        ts = start + timedelta(seconds=i * STEP_S)
        in_incident = ts >= onset
        p = ((ts - onset).total_seconds() / (INCIDENT_MIN * 60)) if in_incident else 0.0
        prog = _ramp(p, scenario.variant.get("ramp", "fast")) if in_incident else 0.0
        step_metrics: dict[str, dict[str, float]] = {}
        step_logs: list[dict[str, Any]] = []
        step_spans: dict[str, dict[str, Any]] = {}
        for svc in services:
            b = bases[svc]
            cur = {kname: max(0.0, v + rng.gauss(0, 0.03 * abs(v) if v else 0.0)) for kname, v in b.items()}
            # diurnal-ish drift on request rate
            if "http_request_rate" in cur:
                cur["http_request_rate"] *= 1 + 0.05 * math.sin(i / 25)
            if in_incident and svc == scenario.target and prog > 0:
                over, flogs, fspans = _fx(scenario.fault_type, prog, k, b, rng)
                cur.update(over)
                for level, msg, rate in flogs:
                    for _ in range(max(0, int(rng.gauss(rate, rate * 0.3)))):
                        step_logs.append({"service": svc, "level": level, "message": msg, "timestamp": (ts + timedelta(seconds=rng.random() * STEP_S)).isoformat()})
                step_spans[svc] = fspans
            # noise: occasional benign warnings everywhere
            if rng.random() < 0.15:
                step_logs.append({"service": svc, "level": "WARN", "message": f"slow request /api/items/{rng.randint(1, 900)} took {rng.randint(300, 600)}ms", "timestamp": ts.isoformat()})
            if scenario.variant.get("noise") and rng.random() < 0.3:
                step_logs.append({"service": svc, "level": "ERROR", "message": f"transient error fetching feature flags: status {rng.choice([502, 504])}", "timestamp": ts.isoformat()})
            step_metrics[svc] = cur
        if in_incident:
            _propagate(step_metrics, bases)
        for svc, cur in step_metrics.items():
            for name, v in cur.items():
                t.metrics.append({"service": svc, "name": name, "timestamp": ts.isoformat(), "value": round(v, 4)})
        t.logs.extend(step_logs)
        # a few traces per step through the checkout path
        for _ in range(2):
            trace_counter += 1
            t.spans.extend(_trace(trace_counter, ts, step_metrics, step_spans, bases, rng, scenario.target))
    return t


def _trace(n: int, ts: datetime, metrics: dict[str, dict[str, float]], fx: dict[str, dict[str, Any]], bases: dict[str, dict[str, float]], rng: random.Random, target: str) -> list[dict[str, Any]]:
    tid = f"{n:016x}"
    out: list[dict[str, Any]] = []

    def span(service: str, op: str, parent: str | None, dur: float, kind: str = "server", err: bool = False, attrs: dict[str, Any] | None = None) -> str:
        sid = f"{rng.getrandbits(64):016x}"
        out.append({"trace_id": tid, "span_id": sid, "parent_span_id": parent, "service": service, "operation": op, "kind": kind, "start_time": ts.isoformat(), "duration_ms": round(max(0.5, dur), 2), "status": "error" if err else "ok", "attributes": attrs or {}})
        return sid

    def lat(svc: str) -> float:
        m = metrics.get(svc, {})
        return max(1.0, rng.gauss(m.get("http_latency_p50_ms", 40), 5) + (m.get("http_latency_p95_ms", 120) - bases[svc].get("http_latency_p95_ms", 120)) * 0.6)

    def errp(svc: str) -> bool:
        return rng.random() < metrics.get(svc, {}).get("http_error_rate", 0.005)

    root = span("api-gateway", "POST /checkout", None, lat("api-gateway") + 20, err=errp("api-gateway"))
    span("auth-service", "POST /verify", span("api-gateway", "call auth-service", root, lat("auth-service") + 2, kind="client"), lat("auth-service"))
    order_client = span("api-gateway", "call order-service", root, lat("order-service") + 3, kind="client", err=errp("order-service"))
    order = span("order-service", "POST /orders", order_client, lat("order-service"), err=errp("order-service"))
    # order → inventory
    inv_fx = fx.get("order-service", {}).get("call inventory-service")
    inv_client_dur = lat("inventory-service") + 2
    if inv_fx:
        inv_client_dur *= inv_fx["mult"]
    inv_client = span("order-service", "call inventory-service", order, inv_client_dur, kind="client", err=bool(inv_fx and rng.random() < inv_fx["error"]))
    span("inventory-service", "POST /reserve", inv_client, lat("inventory-service") if not (inv_fx and inv_fx.get("server_ok")) else rng.gauss(30, 4))
    # order → payment
    pay_fx_client = fx.get("order-service", {}).get("call payment-service")
    pay_client = span("order-service", "call payment-service", order, lat("payment-service") + 3, kind="client", err=bool(pay_fx_client and rng.random() < pay_fx_client["error"]) or errp("payment-service"))
    pay = span("payment-service", "POST /charge", pay_client, lat("payment-service"), err=errp("payment-service"))
    pfx = fx.get("payment-service", {})
    # payment internals
    acq = pfx.get("db.acquire_connection")
    acq_dur = max(0.5, rng.gauss(2, 0.5)) * (acq["mult"] if acq else 1)
    span("payment-service", "db.acquire_connection", pay, acq_dur, kind="internal", err=bool(acq and rng.random() < acq["error"]), attrs={"db.system": "postgresql", "db.operation": "acquire_connection"})
    q = pfx.get("db.query")
    span("payment-service", "db.query", pay, max(0.5, rng.gauss(metrics.get("payment-service", {}).get("db_query_latency_ms", 8), 2)) * (q["mult"] if q else 1) / (30 if q else 1), kind="client", err=bool(q and rng.random() < q["error"]), attrs={"db.system": "postgresql", "db.statement": "INSERT INTO payments"})
    c = pfx.get("cache.get")
    span("payment-service", "cache.get", pay, max(0.3, rng.gauss(1, 0.2)), kind="client", err=bool(c and rng.random() < c["error"]), attrs={"cache.system": "redis"})
    ext = pfx.get("call payment-provider")
    span("payment-service", "call payment-provider", pay, max(5.0, rng.gauss(80, 10)), kind="client", err=bool(ext and rng.random() < ext["error"]), attrs={"peer.service": "payment-provider"})
    # generic fault spans on other targets
    for svc, effects in fx.items():
        if svc in ("payment-service", "order-service"):
            continue
        for op, e in effects.items():
            parent = order if svc == "order-service" else root
            span(svc, op, parent, max(0.5, rng.gauss(10, 2)) * e["mult"], kind="internal", err=rng.random() < e["error"])
    return out


# --------------------------------------------------------------------------------------
# Scenario matrix
# --------------------------------------------------------------------------------------

_FAULTS: list[tuple[str, str, list[str]]] = [
    ("db_pool_exhaustion", "database_connection_pool", ["payment-service", "order-service", "inventory-service", "auth-service"]),
    ("bad_deployment", "database_connection_pool", ["payment-service", "order-service"]),
    ("database_latency", "database_latency", ["payment-service", "order-service", "inventory-service", "auth-service"]),
    ("redis_failure", "redis_unavailable", ["auth-service", "inventory-service", "payment-service"]),
    ("memory_leak", "memory_exhaustion", ["order-service", "payment-service", "api-gateway", "inventory-service"]),
    ("cpu_saturation", "cpu_saturation", ["api-gateway", "order-service", "inventory-service", "auth-service"]),
    ("http_500_spike", "deployment_regression", ["order-service", "payment-service", "api-gateway"]),
    ("config_regression", "config_regression", ["payment-service", "order-service"]),
    ("network_latency", "network_latency", ["order-service"]),
    ("packet_loss", "network_packet_loss", ["order-service"]),
    ("queue_backlog", "queue_backlog", ["order-service", "notification-worker"]),
    ("thread_starvation", "thread_starvation", ["order-service", "api-gateway", "payment-service"]),
    ("deadlock", "deadlock", ["inventory-service", "order-service", "payment-service"]),
    ("dependency_failure", "dependency_failure", ["payment-service"]),
]

_VARIANTS: list[dict[str, Any]] = [
    {"intensity": 1.0, "seed": 1},
    {"intensity": 0.85, "seed": 2},
    {"intensity": 1.3, "seed": 3, "noise": True},
    {"intensity": 1.0, "seed": 4, "with_deploy": True, "deploy_service": "inventory-service", "deploy_minutes_before": 9},
]


def build_scenarios() -> list[Scenario]:
    out: list[Scenario] = []
    for fault, expected, targets in _FAULTS:
        for ti, target in enumerate(targets):
            for vi, var in enumerate(_VARIANTS):
                if ti > 0 and vi == 3:
                    continue  # confounding deploy variant only on the primary target
                if ti > 1 and vi == 2:
                    continue
                out.append(Scenario(name=f"{fault}/{target}/v{vi + 1}", fault_type=fault, target=target, expected=expected, variant=var))
    # healthy controls for the false-positive rate
    for i in range(6):
        out.append(Scenario(name=f"control/healthy/v{i + 1}", fault_type="none", target="payment-service", expected="none", variant={"seed": 100 + i, "noise": i % 2 == 1}))
    return out


SCENARIOS: list[Scenario] = build_scenarios()
