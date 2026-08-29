"""Telemetry emitter for simulated services.

Every service owns one ``Emitter``. Handlers record requests, logs and spans; a background
flusher ships batches to Sentinel's ingestion API (OpenTelemetry-style attributes) every
few seconds and computes the per-interval gauges (request rate, error ratio, p95...).
The same values are exposed on ``/metrics`` in Prometheus exposition format so the
optional Prometheus → Alertmanager → Sentinel path works unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

import httpx
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

from sentinel_sim.config import settings

log = logging.getLogger("sim.telemetry")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = max(0, min(len(s) - 1, round((len(s) - 1) * p)))
    return s[k]


class Emitter:
    def __init__(self, service: str, version: str) -> None:
        self.service = service
        self.version = version
        self._logs: list[dict[str, Any]] = []
        self._spans: list[dict[str, Any]] = []
        self._latencies: deque[float] = deque(maxlen=2000)
        self._requests = 0
        self._errors = 0
        self._dep_calls = 0
        self._dep_errors = 0
        self._net_errors = 0
        self._net_latencies: deque[float] = deque(maxlen=500)
        self.inflight = 0
        self.gauges: dict[str, float] = {}  # runtime-provided gauges (db pool, cpu...)
        self._task: asyncio.Task[None] | None = None
        self._client = httpx.AsyncClient(base_url=settings.sentinel_url, timeout=10.0, headers={"x-api-key": settings.ingest_key})
        self.registry = CollectorRegistry()
        self._prom_req = Counter("http_requests_total", "requests", ["service", "status"], registry=self.registry)
        self._prom_gauges: dict[str, Gauge] = {}
        self.last_flush_ok = True

    # ---- recording ----------------------------------------------------------------------
    def request(self, latency_ms: float, status: int) -> None:
        self._requests += 1
        if status >= 500:
            self._errors += 1
        self._latencies.append(latency_ms)
        self._prom_req.labels(self.service, str(status // 100) + "xx").inc()

    def dependency_call(self, latency_ms: float, ok: bool, *, network_error: bool = False) -> None:
        self._dep_calls += 1
        if not ok:
            self._dep_errors += 1
        if network_error:
            self._net_errors += 1
        self._net_latencies.append(latency_ms)

    def log(self, level: str, message: str, *, trace_id: str | None = None, span_id: str | None = None, **attrs: Any) -> None:
        self._logs.append(
            {
                "timestamp": now_iso(),
                "service.name": self.service,
                "service.version": self.version,
                "deployment.environment": settings.environment,
                "level": level,
                "message": message,
                "trace_id": trace_id,
                "span_id": span_id,
                "attributes": attrs,
            }
        )
        if len(self._logs) > 5000:
            del self._logs[:1000]

    def span(self, *, trace_id: str, span_id: str, parent_span_id: str | None, operation: str, kind: str, start: float, duration_ms: float, error: bool, **attrs: Any) -> None:
        self._spans.append(
            {
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "service.name": self.service,
                "service.version": self.version,
                "operation": operation,
                "kind": kind,
                "start_time": datetime.fromtimestamp(start, UTC).isoformat(),
                "duration_ms": round(duration_ms, 3),
                "status": "error" if error else "ok",
                "attributes": attrs,
            }
        )
        if len(self._spans) > 20000:
            del self._spans[:5000]

    # ---- flushing -----------------------------------------------------------------------
    def snapshot_metrics(self, interval_s: float) -> dict[str, float]:
        lat = list(self._latencies)
        req = self._requests
        err = self._errors
        dep = self._dep_calls
        dep_err = self._dep_errors
        net_err = self._net_errors
        net_lat = list(self._net_latencies)
        self._requests = self._errors = self._dep_calls = self._dep_errors = self._net_errors = 0
        self._latencies.clear()
        self._net_latencies.clear()
        m: dict[str, float] = {
            "http_request_rate": req / interval_s,
            "http_error_rate": (err / req) if req else 0.0,
            "http_latency_p95_ms": percentile(lat, 0.95),
            "http_latency_p50_ms": percentile(lat, 0.5),
            "http_inflight": float(self.inflight),
            "dependency_error_rate": (dep_err / dep) if dep else 0.0,
            "network_errors_rate": (net_err / dep) if dep else 0.0,
            "network_latency_ms": percentile(net_lat, 0.5) if net_lat else 0.0,
        }
        m.update(self.gauges)
        for k, v in m.items():
            g = self._prom_gauges.get(k)
            if g is None:
                g = Gauge(k, k, ["service"], registry=self.registry)
                self._prom_gauges[k] = g
            g.labels(self.service).set(v)
        return m

    def prometheus(self) -> bytes:
        return generate_latest(self.registry)

    async def flush(self, interval_s: float) -> None:
        ts = now_iso()
        metrics = [{"service.name": self.service, "name": k, "timestamp": ts, "value": v, "labels": {"service.version": self.version}} for k, v in self.snapshot_metrics(interval_s).items()]
        logs, self._logs = self._logs, []
        spans, self._spans = self._spans, []
        payloads = [("/api/v1/ingest/metrics", metrics), ("/api/v1/ingest/logs", logs), ("/api/v1/ingest/traces", spans)]
        for path, records in payloads:
            if not records:
                continue
            for i in range(0, len(records), 2000):
                chunk = records[i : i + 2000]
                try:
                    r = await self._client.post(path, json={"project": settings.project, "service": self.service, "records": chunk})
                    if r.status_code >= 400:
                        log.warning("ingest rejected %s %s: %s", self.service, path, r.text[:200])
                        self.last_flush_ok = False
                    else:
                        self.last_flush_ok = True
                except httpx.HTTPError as exc:
                    self.last_flush_ok = False
                    log.warning("ingest failed %s %s: %s", self.service, path, exc)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(settings.flush_interval_s)
            try:
                await self.flush(settings.flush_interval_s)
            except Exception:
                log.exception("flush loop error")

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name=f"emitter-{self.service}")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        with contextlib.suppress(Exception):
            await self.flush(settings.flush_interval_s)
        await self._client.aclose()


class SpanCtx:
    """Async context manager that records a span and propagates trace context."""

    def __init__(self, emitter: Emitter, operation: str, *, trace_id: str | None, parent_span_id: str | None, kind: str = "internal", **attrs: Any) -> None:
        self.em = emitter
        self.operation = operation
        self.trace_id = trace_id or new_trace_id()
        self.parent_span_id = parent_span_id
        self.span_id = new_span_id()
        self.kind = kind
        self.attrs = attrs
        self.error = False
        self._start = 0.0

    async def __aenter__(self) -> SpanCtx:
        self._start = time.time()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if exc is not None:
            self.error = True
        self.em.span(trace_id=self.trace_id, span_id=self.span_id, parent_span_id=self.parent_span_id, operation=self.operation, kind=self.kind, start=self._start, duration_ms=(time.time() - self._start) * 1000, error=self.error, **self.attrs)

    @property
    def headers(self) -> dict[str, str]:
        return {"x-trace-id": self.trace_id, "x-parent-span-id": self.span_id}
