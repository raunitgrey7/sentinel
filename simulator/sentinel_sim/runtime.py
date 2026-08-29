"""Service runtime: simulated resources + fault injection for one demo-shop service.

The services talk to each other over real HTTP (one uvicorn server per service). Their
*internal* resources — the database connection pool, the cache, the message queue, the
worker pool, CPU/memory — are simulated in-process so that faults are deterministic and
cheap, while still producing the real telemetry shapes an SRE would see:

* DB pool: an ``asyncio.Semaphore(40)`` with a 2 s acquire timeout and a query latency model
* cache: a hit-rate model with fail-open fallback to the database
* queue: a shared ``asyncio.Queue`` between order-service and notification-worker
* worker pool: an ``asyncio.Semaphore(32)`` guarding request handling

Faults mutate ``FaultState`` and expire on their own. Each fault has a well-defined
telemetry signature (see docs/architecture/simulator.md).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from sentinel_sim.config import settings
from sentinel_sim.telemetry import Emitter, SpanCtx

log = logging.getLogger("sim.runtime")

DB_POOL_SIZE = 40
WORKER_POOL_SIZE = 32
ACQUIRE_TIMEOUT_S = 2.0
FAULT_TYPES = {
    "cpu_saturation",
    "memory_leak",
    "database_latency",
    "db_pool_exhaustion",
    "http_500_spike",
    "network_latency",
    "packet_loss",
    "redis_failure",
    "queue_backlog",
    "bad_deployment",
    "config_regression",
    "dependency_failure",
    "thread_starvation",
    "deadlock",
}


class ServiceError(Exception):
    def __init__(self, status: int, message: str, *, network: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.network = network


@dataclass
class Fault:
    id: str
    type: str
    target: str
    severity: str
    duration_s: int
    params: dict[str, Any]
    started_at: float = field(default_factory=time.time)

    @property
    def intensity(self) -> float:
        return {"low": 0.5, "medium": 0.8, "high": 1.0, "critical": 1.3}.get(self.severity, 1.0) * float(self.params.get("intensity", 1.0))

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    @property
    def progress(self) -> float:
        return min(1.0, self.elapsed / max(1.0, min(self.duration_s, 90)))

    @property
    def expired(self) -> bool:
        return self.elapsed >= self.duration_s

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type, "target": self.target, "severity": self.severity, "duration_s": self.duration_s, "params": self.params, "elapsed_s": round(self.elapsed, 1), "expired": self.expired}


class SharedQueue:
    """The message queue shared by producers and the notification worker."""

    def __init__(self) -> None:
        self.q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.consumer_paused = False
        self.processed = 0
        self.failed = 0
        self.last_enqueued_at: float | None = None
        self.oldest_ts: float | None = None

    def depth(self) -> int:
        return self.q.qsize()

    def lag_s(self) -> float:
        if self.q.empty():
            return 0.0
        return max(0.0, time.time() - (self.oldest_ts or time.time()))


SHARED_QUEUE = SharedQueue()


class ServiceRuntime:
    def __init__(self, name: str, version: str = "2.8.0") -> None:
        self.name = name
        self.version = version
        self.previous_version: str | None = None
        self.em = Emitter(name, version)
        self.db_pool = asyncio.Semaphore(DB_POOL_SIZE)
        self.db_active = 0
        self.db_waiting = 0
        self.db_acquire_ms: list[float] = []
        self.db_query_ms: list[float] = []
        self.workers = asyncio.Semaphore(WORKER_POOL_SIZE)
        self.workers_active = 0
        self.cache_hits = 0
        self.cache_calls = 0
        self.cache_errors = 0
        self.faults: dict[str, Fault] = {}
        self.restart_count = 0
        self.replicas = 1
        self.config: dict[str, Any] = {"payment.timeout_ms": 5000, "transaction.concurrency": 8}
        self._holders: list[asyncio.Task[None]] = []
        self._rng = random.Random(hash(name) & 0xFFFF)
        self._started = time.time()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0))
        self._bg: asyncio.Task[None] | None = None
        self.healthy = True

    # ---- lifecycle ----------------------------------------------------------------------
    async def start(self) -> None:
        self.em.start()
        self._bg = asyncio.create_task(self._housekeeping(), name=f"rt-{self.name}")

    async def stop(self) -> None:
        if self._bg:
            self._bg.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._bg
        for t in self._holders:
            t.cancel()
        await self.em.stop()
        await self._client.aclose()

    async def _housekeeping(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            for fid in [f for f, fault in self.faults.items() if fault.expired]:
                self.clear_fault(fid)
            self._update_gauges()

    def restart(self) -> None:
        self.restart_count += 1
        for fid in list(self.faults):
            if self.faults[fid].type in ("memory_leak", "thread_starvation", "deadlock", "db_pool_exhaustion"):
                self.clear_fault(fid)
        self._started = time.time()
        self.em.log("INFO", f"service restarted (restart #{self.restart_count})")

    # ---- faults ---------------------------------------------------------------------------
    def active(self, fault_type: str) -> Fault | None:
        for f in self.faults.values():
            if f.type == fault_type and not f.expired:
                return f
        return None

    def inject(self, fault: Fault) -> None:
        self.faults[fault.id] = fault
        self.em.log("WARN", f"chaos: fault {fault.type} injected (severity={fault.severity}, duration={fault.duration_s}s)", fault_id=fault.id)
        if fault.type == "db_pool_exhaustion":
            # Runaway transactions grab the whole pool and churn it; a minority of requests
            # squeeze through in the release gaps, the rest wait 2s and fail.
            hold = DB_POOL_SIZE if fault.intensity >= 0.8 else DB_POOL_SIZE - 3
            for _ in range(hold):
                self._holders.append(asyncio.create_task(self._hold_connection(fault)))
        elif fault.type == "thread_starvation":
            for _ in range(WORKER_POOL_SIZE - 1):
                self._holders.append(asyncio.create_task(self._hold_worker(fault)))
        elif fault.type == "queue_backlog":
            SHARED_QUEUE.consumer_paused = True
        elif fault.type == "config_regression":
            self.config["payment.timeout_ms"] = 200
        elif fault.type == "bad_deployment":
            self.config["transaction.concurrency"] = 64
            hold = DB_POOL_SIZE - 1
            for _ in range(hold):
                self._holders.append(asyncio.create_task(self._hold_connection(fault, ramp_s=45)))

    def clear_fault(self, fault_id: str) -> None:
        f = self.faults.pop(fault_id, None)
        if not f:
            return
        self.em.log("INFO", f"chaos: fault {f.type} cleared", fault_id=f.id)
        if f.type == "queue_backlog":
            SHARED_QUEUE.consumer_paused = False
        if f.type == "config_regression":
            self.config["payment.timeout_ms"] = 5000
        if f.type == "bad_deployment":
            self.config["transaction.concurrency"] = 8
        if f.type in ("db_pool_exhaustion", "thread_starvation", "bad_deployment"):
            for t in self._holders:
                t.cancel()
            self._holders = []

    def clear_all(self) -> None:
        for fid in list(self.faults):
            self.clear_fault(fid)

    async def _hold_connection(self, fault: Fault, ramp_s: float = 20.0) -> None:
        """Hold a pool slot for most of the time, releasing it briefly so the pool churns."""
        await asyncio.sleep(self._rng.random() * ramp_s)
        while not fault.expired and fault.id in self.faults:
            await self.db_pool.acquire()
            self.db_active += 1
            try:
                # runaway transactions: each holds its connection far longer than the
                # 2s acquire timeout, so real requests time out on the pool
                await asyncio.sleep(self._rng.uniform(45.0, 90.0))
            finally:
                self.db_active -= 1
                self.db_pool.release()
            await asyncio.sleep(self._rng.uniform(0.01, 0.05))

    async def _hold_worker(self, fault: Fault) -> None:
        await asyncio.sleep(self._rng.random() * 10)
        async with self.workers:
            self.workers_active += 1
            try:
                while not fault.expired and fault.id in self.faults:  # noqa: ASYNC110
                    await asyncio.sleep(1.0)
            finally:
                self.workers_active -= 1

    # ---- gauges -----------------------------------------------------------------------------
    def _update_gauges(self) -> None:
        g = self.em.gauges
        cpu = 28 + self._rng.gauss(0, 2)
        mem = 410 + self._rng.gauss(0, 6) + (time.time() - self._started) * 0.02
        gc_pause = 5 + self._rng.gauss(0, 0.8)
        if (f := self.active("cpu_saturation")) is not None:
            cpu = min(100, 30 + 68 * f.progress * f.intensity)
        if (f := self.active("memory_leak")) is not None:
            mem += 1500 * f.progress * f.intensity
            gc_pause += 130 * f.progress * f.progress * f.intensity
            if f.progress > 0.6 and self._rng.random() < 0.3:
                self.em.log("WARN", f"GC pressure: heap {int(mem)}MB/2048MB, pause {int(gc_pause)}ms")
            if f.progress > 0.9 and self._rng.random() < 0.15:
                self.em.log("FATAL", "java.lang.OutOfMemoryError: Java heap space")
        if (f := self.active("deadlock")) is not None:
            cpu = max(2.0, 30 - 26 * f.progress)
        if (f := self.active("thread_starvation")) is not None:
            cpu = max(5.0, 30 - 8 * f.progress)
        if (f := self.active("cpu_saturation")) is not None and self._rng.random() < 0.3:
            self.em.log("WARN", f"cpu throttled: {int(cpu)}% utilization, request processing delayed")
        acq = self.db_acquire_ms[-200:]
        qry = self.db_query_ms[-200:]
        self.db_acquire_ms = acq
        self.db_query_ms = qry
        g.update(
            {
                "cpu_usage": round(cpu, 2),
                "memory_usage_mb": round(mem, 1),
                "gc_pause_ms": round(max(0.0, gc_pause), 2),
                "restart_count": float(self.restart_count),
                "db_connections_active": float(self.db_active),
                "db_connections_max": float(DB_POOL_SIZE),
                "db_connections_waiting": float(self.db_waiting),
                "db_connection_acquire_ms": (sum(acq) / len(acq)) if acq else 0.0,
                "db_query_latency_ms": (sum(qry) / len(qry)) if qry else 0.0,
                "thread_pool_active": float(self.workers_active),
                "thread_pool_max": float(WORKER_POOL_SIZE),
                "redis_errors_rate": (self.cache_errors / self.cache_calls) if self.cache_calls else 0.0,
                "cache_hit_rate": (self.cache_hits / self.cache_calls) if self.cache_calls else 0.92,
            }
        )
        if self.name in ("order-service", "notification-worker"):
            g["queue_depth"] = float(SHARED_QUEUE.depth())
            g["consumer_lag_s"] = round(SHARED_QUEUE.lag_s(), 2)
            total = SHARED_QUEUE.processed + SHARED_QUEUE.failed
            g["worker_errors_rate"] = (SHARED_QUEUE.failed / total) if total else 0.0
            if (f := self.active("queue_backlog")) is not None and self._rng.random() < 0.4:
                self.em.log("WARN", f"queue backlog: {SHARED_QUEUE.depth()} messages pending, consumer lag {int(SHARED_QUEUE.lag_s())}s")
        self.cache_hits = self.cache_calls = self.cache_errors = 0
        self.healthy = not any(f.type in ("deadlock", "db_pool_exhaustion", "bad_deployment") for f in self.faults.values())

    # ---- simulated resources --------------------------------------------------------------
    async def handle(self, span: SpanCtx) -> None:
        """Common per-request costs: worker slot, CPU/memory pressure, chaos error injection."""
        if (f := self.active("deadlock")) is not None and self._rng.random() < 0.9 * f.intensity:
            if self._rng.random() < 0.3:
                self.em.log("ERROR", f"deadlock detected: worker-{self._rng.randint(1, 32)} waiting on lock 'inventory_reserve' held by worker-{self._rng.randint(1, 32)}", trace_id=span.trace_id)
            await asyncio.sleep(6.0)
            raise ServiceError(504, "request timed out after 6000ms (hung)")
        if (f := self.active("cpu_saturation")) is not None:
            await asyncio.sleep(0.5 * f.progress * f.intensity + self._rng.random() * 0.4 * f.progress)
        if (f := self.active("memory_leak")) is not None:
            await asyncio.sleep(0.4 * f.progress * f.progress * f.intensity)
            if f.progress > 0.7 and self._rng.random() < 0.06 * f.intensity:
                raise ServiceError(503, "service unavailable: GC pause exceeded request deadline")
        if (f := self.active("http_500_spike")) is not None and self._rng.random() < 0.35 * f.intensity:
            self.em.log("ERROR", "Unhandled exception in /checkout: TypeError: cannot read property 'amount' of undefined at PricingService.compute", trace_id=span.trace_id)
            raise ServiceError(500, "internal error")

    @contextlib.asynccontextmanager
    async def worker_slot(self):  # type: ignore[no-untyped-def]
        starve = self.active("thread_starvation")
        try:
            await asyncio.wait_for(self.workers.acquire(), timeout=3.0 if starve else 10.0)
        except TimeoutError as exc:
            self.em.log("ERROR", f"thread pool exhausted: all {WORKER_POOL_SIZE} workers busy, request queued for 3000ms")
            raise ServiceError(503, "worker pool exhausted") from exc
        self.workers_active += 1
        try:
            yield
        finally:
            self.workers_active -= 1
            self.workers.release()

    async def db_query(self, span: SpanCtx, statement: str) -> None:
        # acquire
        t0 = time.perf_counter()
        self.db_waiting += 1
        async with SpanCtx(self.em, "db.acquire_connection", trace_id=span.trace_id, parent_span_id=span.span_id, kind="internal", **{"db.system": "postgresql", "db.operation": "acquire_connection"}) as acq:
            try:
                await asyncio.wait_for(self.db_pool.acquire(), timeout=ACQUIRE_TIMEOUT_S)
            except TimeoutError as exc:
                self.db_waiting -= 1
                acq.error = True
                self.db_acquire_ms.append(ACQUIRE_TIMEOUT_S * 1000)
                self.em.log("ERROR", f"failed to acquire database connection after {int(ACQUIRE_TIMEOUT_S * 1000)}ms (pool={DB_POOL_SIZE}/{DB_POOL_SIZE}, waiting={self.db_waiting})", trace_id=span.trace_id)
                raise ServiceError(500, "failed to acquire database connection") from exc
            self.db_waiting -= 1
            self.db_acquire_ms.append((time.perf_counter() - t0) * 1000)
        self.db_active += 1
        try:
            async with SpanCtx(self.em, "db.query", trace_id=span.trace_id, parent_span_id=span.span_id, kind="client", **{"db.system": "postgresql", "db.statement": statement}) as q:
                latency = max(1.0, self._rng.gauss(8, 2))
                if (f := self.active("database_latency")) is not None:
                    latency += 420 * f.progress * f.intensity
                    if self._rng.random() < 0.3:
                        self.em.log("WARN", f"slow query: {statement[:40]} took {int(latency)}ms", trace_id=span.trace_id)
                    if latency > 380 and self._rng.random() < 0.12 * f.intensity:
                        q.error = True
                        self.em.log("ERROR", "statement timeout: canceling statement due to statement timeout", trace_id=span.trace_id)
                        raise ServiceError(500, "statement timeout")
                await asyncio.sleep(latency / 1000)
                self.db_query_ms.append(latency)
        finally:
            self.db_active -= 1
            self.db_pool.release()

    async def cache_get(self, span: SpanCtx, key: str) -> bool:
        self.cache_calls += 1
        async with SpanCtx(self.em, "cache.get", trace_id=span.trace_id, parent_span_id=span.span_id, kind="client", **{"cache.system": "redis", "cache.key": key}) as c:
            if (f := self.active("redis_failure")) is not None and self._rng.random() < 0.9 * min(1.0, f.intensity):
                self.cache_errors += 1
                c.error = True
                self.em.log("ERROR", "redis connection refused (ECONNREFUSED 10.0.0.5:6379) while fetching session", trace_id=span.trace_id)
                if self._rng.random() < 0.2:
                    raise ServiceError(500, "cache unavailable")
                self.em.log("WARN", "cache unavailable, falling back to database", trace_id=span.trace_id)
                return False
            await asyncio.sleep(0.001)
            hit = self._rng.random() < 0.92
            if hit:
                self.cache_hits += 1
            return hit

    async def call(self, span: SpanCtx, service: str, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        """HTTP call to another demo-shop service with chaos hooks on the network path."""
        t0 = time.perf_counter()
        async with SpanCtx(self.em, f"call {service}", trace_id=span.trace_id, parent_span_id=span.span_id, kind="client", **{"peer.service": service, "http.method": method, "http.route": path}) as c:
            if (f := self.active("network_latency")) is not None:
                extra = 0.38 * f.progress * f.intensity
                await asyncio.sleep(extra)
                if extra > 0.25 and self._rng.random() < 0.25:
                    self.em.log("WARN", f"timeout calling {service} (>{int(extra * 1000)}ms), retrying", trace_id=span.trace_id)
            if (f := self.active("packet_loss")) is not None and self._rng.random() < 0.28 * f.progress * f.intensity:
                c.error = True
                self.em.log("ERROR", f"connection reset by peer while calling {service} (ECONNRESET)", trace_id=span.trace_id)
                self.em.dependency_call((time.perf_counter() - t0) * 1000, False, network_error=True)
                raise ServiceError(502, f"connection reset calling {service}", network=True)
            try:
                r = await self._client.request(method, settings.url_of(service) + path, json=json, headers=c.headers)
            except httpx.HTTPError as exc:
                c.error = True
                self.em.dependency_call((time.perf_counter() - t0) * 1000, False, network_error=True)
                self.em.log("ERROR", f"connection error calling {service}: {exc}", trace_id=span.trace_id)
                raise ServiceError(502, f"connection error calling {service}", network=True) from exc
            ok = r.status_code < 500
            self.em.dependency_call((time.perf_counter() - t0) * 1000, ok)
            if not ok:
                c.error = True
                self.em.log("ERROR", f"upstream {service} returned {r.status_code} for {method} {path}", trace_id=span.trace_id)
                raise ServiceError(502, f"upstream {service} failed ({r.status_code})")
            return r.json() if r.content else {}

    async def call_external(self, span: SpanCtx, provider: str, path: str) -> None:
        """Third-party dependency (not in our topology) — simulated in-process."""
        t0 = time.perf_counter()
        async with SpanCtx(self.em, f"call {provider}", trace_id=span.trace_id, parent_span_id=span.span_id, kind="client", **{"peer.service": provider, "http.route": path}) as c:
            timeout_ms = int(self.config.get("payment.timeout_ms", 5000))
            latency = max(20.0, self._rng.gauss(80, 12))
            if (f := self.active("dependency_failure")) is not None and self._rng.random() < 0.6 * min(1.0, f.intensity):
                c.error = True
                self.em.dependency_call(latency, False)
                self.em.log("ERROR", f"upstream {provider} returned 503 Service Unavailable for POST {path}", trace_id=span.trace_id)
                raise ServiceError(502, f"{provider} unavailable")
            if latency > timeout_ms:
                c.error = True
                self.em.dependency_call(timeout_ms, False)
                self.em.log("ERROR", f"config error: PAYMENT_TIMEOUT_MS={timeout_ms} is below the minimum supported value; upstream call timed out after {timeout_ms}ms", trace_id=span.trace_id)
                raise ServiceError(504, f"{provider} timed out")
            await asyncio.sleep(latency / 1000)
            self.em.dependency_call((time.perf_counter() - t0) * 1000, True)

    async def publish(self, span: SpanCtx, message: dict[str, Any]) -> None:
        async with SpanCtx(self.em, "queue.publish", trace_id=span.trace_id, parent_span_id=span.span_id, kind="producer", **{"messaging.system": "queue"}):
            if SHARED_QUEUE.q.empty():
                SHARED_QUEUE.oldest_ts = time.time()
            await SHARED_QUEUE.q.put({**message, "ts": time.time(), "trace_id": span.trace_id})
            SHARED_QUEUE.last_enqueued_at = time.time()
