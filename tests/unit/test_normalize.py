from sentinel.telemetry.normalize import (
    normalize_level,
    normalize_log,
    normalize_metric,
    normalize_span,
    template_of,
)


def test_template_masks_volatile_tokens():
    a, ha = template_of("failed to acquire database connection after 5012ms (pool=40/40)")
    _b, hb = template_of("failed to acquire database connection after 4987ms (pool=40/40)")
    assert ha == hb
    assert "<measure>" in a


def test_template_masks_uuid_ip_hex():
    t, _ = template_of("request 3f2504e0-4f89-11d3-9a0c-0305e82c3301 from 10.0.0.5:6379 trace 9b1c0aa1deadbeef1234")
    assert "<uuid>" in t and "<ip>" in t and "<hex>" in t


def test_normalize_level():
    assert normalize_level("warning") == "WARN"
    assert normalize_level("err") == "ERROR"
    assert normalize_level(17) == "ERROR"
    assert normalize_level(21) == "FATAL"
    assert normalize_level(None) == "INFO"


def test_normalize_log_otel_attributes():
    row = normalize_log({"body": "boom", "severity_number": 17, "resource": {"service.name": "payment-service", "service.version": "2.8.1"}, "attributes": {"exception.type": "TypeError"}, "timestamp": 1700000000000})
    assert row["service"] == "payment-service"
    assert row["service_version"] == "2.8.1"
    assert row["level"] == "ERROR"
    assert row["attributes"]["exception.type"] == "TypeError"
    assert row["ts"].year == 2023


def test_normalize_metric_default_service():
    row = normalize_metric({"name": "cpu_usage", "value": "42.5", "timestamp": "2026-01-01T00:00:00Z"}, default_service="svc")
    assert row["service"] == "svc" and row["value"] == 42.5


def test_normalize_span_status_object():
    row = normalize_span({"traceId": "abc", "spanId": "def", "name": "GET /x", "start_time": "2026-01-01T00:00:00Z", "end_time": "2026-01-01T00:00:01Z", "status": {"code": "ERROR"}}, default_service="svc")
    assert row["duration_ms"] == 1000
    assert row["status"] == "error"
    assert row["operation"] == "GET /x"
