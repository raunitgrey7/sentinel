"""Default detection rules, mirrored by ``infrastructure/prometheus/rules.yml``.

Sentinel evaluates these itself over ingested metrics so that detection works with zero
external infrastructure; when Prometheus + Alertmanager are deployed, the same
conditions fire there and arrive through the Alertmanager webhook. Both paths produce the
same ``Alert`` rows and de-duplicate by fingerprint.
"""

from __future__ import annotations

DEFAULT_RULES: list[dict] = [
    {
        "name": "HighErrorRate",
        "description": "HTTP 5xx error ratio above 10% for 30s",
        "metric": "http_error_rate",
        "aggregation": "avg",
        "comparator": ">",
        "threshold": 0.10,
        "window_s": 60,
        "for_s": 30,
        "severity": "CRITICAL",
    },
    {
        "name": "ElevatedErrorRate",
        "description": "HTTP 5xx error ratio above 3% for 60s",
        "metric": "http_error_rate",
        "aggregation": "avg",
        "comparator": ">",
        "threshold": 0.03,
        "window_s": 90,
        "for_s": 60,
        "severity": "HIGH",
    },
    {
        "name": "HighLatencyP95",
        "description": "p95 latency above 1500ms for 45s",
        "metric": "http_latency_p95_ms",
        "aggregation": "avg",
        "comparator": ">",
        "threshold": 1500,
        "window_s": 60,
        "for_s": 45,
        "severity": "HIGH",
    },
    {
        "name": "DbPoolNearExhaustion",
        "description": "Waiting DB connection requests above 5 for 30s",
        "metric": "db_connections_waiting",
        "aggregation": "avg",
        "comparator": ">",
        "threshold": 5,
        "window_s": 60,
        "for_s": 30,
        "severity": "HIGH",
    },
    {
        "name": "QueueBacklog",
        "description": "Queue depth above 500 for 60s",
        "metric": "queue_depth",
        "aggregation": "avg",
        "comparator": ">",
        "threshold": 500,
        "window_s": 90,
        "for_s": 60,
        "severity": "MEDIUM",
    },
    {
        "name": "ThroughputCollapse",
        "description": "Request rate under 0.5 req/s for 60s on a service that normally serves traffic",
        "metric": "http_request_rate",
        "aggregation": "avg",
        "comparator": "<",
        "threshold": 0.5,
        "window_s": 90,
        "for_s": 60,
        "severity": "HIGH",
    },
]
