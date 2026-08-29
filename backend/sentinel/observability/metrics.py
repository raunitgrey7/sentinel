"""Sentinel's own Prometheus metrics ("Sentinel watches Sentinel").

Exposed at ``GET /metrics``. Every boundary that matters for operating the platform is
instrumented: HTTP, DB, queue, investigation stages, LLM calls, detection loop.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "sentinel_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=REGISTRY
)
HTTP_LATENCY = Histogram(
    "sentinel_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    registry=REGISTRY,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
DB_LATENCY = Histogram(
    "sentinel_db_query_duration_seconds", "DB operation latency", ["op"], registry=REGISTRY
)
INGEST_RECORDS = Counter(
    "sentinel_ingest_records_total", "Telemetry records ingested", ["signal"], registry=REGISTRY
)
QUEUE_DEPTH = Gauge("sentinel_queue_depth", "Jobs waiting", ["queue"], registry=REGISTRY)
JOBS = Counter("sentinel_jobs_total", "Job outcomes", ["job", "outcome"], registry=REGISTRY)
JOB_LATENCY = Histogram(
    "sentinel_job_duration_seconds", "Job duration", ["job"], registry=REGISTRY,
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)
DEAD_LETTERS = Counter("sentinel_dead_letters_total", "Jobs sent to DLQ", ["job"], registry=REGISTRY)
INCIDENTS_CREATED = Counter("sentinel_incidents_created_total", "Incidents opened", ["severity"], registry=REGISTRY)
INCIDENTS_OPEN = Gauge("sentinel_incidents_open", "Open incidents", registry=REGISTRY)
DETECTOR_RUNS = Counter("sentinel_detector_runs_total", "Detector loop iterations", ["outcome"], registry=REGISTRY)
INVESTIGATION_LATENCY = Histogram(
    "sentinel_investigation_duration_seconds", "End-to-end investigation duration", registry=REGISTRY,
    buckets=(0.5, 1, 2, 5, 10, 15, 20, 30, 45, 60, 120, 300),
)
STEP_LATENCY = Histogram(
    "sentinel_investigation_step_duration_seconds", "Investigator step duration", ["step"], registry=REGISTRY,
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
STEP_OUTCOMES = Counter("sentinel_investigation_steps_total", "Step outcomes", ["step", "outcome"], registry=REGISTRY)
LLM_CALLS = Counter("sentinel_llm_calls_total", "LLM calls", ["provider", "op", "outcome"], registry=REGISTRY)
LLM_LATENCY = Histogram(
    "sentinel_llm_duration_seconds", "LLM call latency", ["provider", "op"], registry=REGISTRY,
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 30, 60, 90, 120),
)
LLM_TOKENS = Counter("sentinel_llm_tokens_total", "Tokens (as reported by provider)", ["provider", "direction"], registry=REGISTRY)
CIRCUIT_STATE = Gauge("sentinel_circuit_open", "1 when circuit is open", ["circuit"], registry=REGISTRY)
RETRIEVAL_LATENCY = Histogram("sentinel_retrieval_duration_seconds", "Historical retrieval latency", registry=REGISTRY)
HYPOTHESIS_CONFIDENCE = Histogram(
    "sentinel_hypothesis_confidence", "Top hypothesis confidence", registry=REGISTRY,
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
RATE_LIMITED = Counter("sentinel_rate_limited_total", "Requests rejected by rate limiter", ["scope"], registry=REGISTRY)


def render() -> bytes:
    return generate_latest(REGISTRY)


@contextmanager
def timed(histogram: Histogram, **labels: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        (histogram.labels(**labels) if labels else histogram).observe(time.perf_counter() - start)
