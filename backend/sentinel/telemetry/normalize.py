"""Telemetry normalisation.

* Maps OpenTelemetry semantic-convention attributes (``service.name``, ``service.version``,
  ``deployment.environment``, ``exception.*``) onto Sentinel's flat records.
* Mines log templates: a lightweight Drain-style masking that replaces volatile tokens
  (numbers, hex ids, UUIDs, IPs, durations, quoted strings) with placeholders so that
  "failed to acquire connection after 5012ms (pool=40/40)" and
  "failed to acquire connection after 4987ms (pool=40/40)" share one template.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from sentinel.core.timeutil import parse_ts

_MASKS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "<uuid>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b[0-9a-f]{12,64}\b", re.I), "<hex>"),
    (re.compile(r"\b\d+(?:\.\d+)?(?:ms|s|m|h|kb|mb|gb|%)\b", re.I), "<measure>"),
    (re.compile(r"\b\d+(?:\.\d+)?\b"), "<num>"),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "<str>"),
    (re.compile(r"/[\w./-]{6,}"), "<path>"),
]
_WS = re.compile(r"\s+")

LEVEL_ALIASES = {
    "warn": "WARN",
    "warning": "WARN",
    "err": "ERROR",
    "error": "ERROR",
    "fatal": "FATAL",
    "critical": "FATAL",
    "info": "INFO",
    "debug": "DEBUG",
    "trace": "DEBUG",
}


def template_of(message: str) -> tuple[str, str]:
    """Return (template, template_hash) for a log message."""
    t = message
    for pat, repl in _MASKS:
        t = pat.sub(repl, t)
    t = _WS.sub(" ", t).strip()
    h = hashlib.md5(t.encode(), usedforsecurity=False).hexdigest()[:16]
    return t, h


def normalize_level(level: str | int | None) -> str:
    if level is None:
        return "INFO"
    if isinstance(level, int):  # OTel severity number
        if level >= 21:
            return "FATAL"
        if level >= 17:
            return "ERROR"
        if level >= 13:
            return "WARN"
        if level >= 9:
            return "INFO"
        return "DEBUG"
    return LEVEL_ALIASES.get(level.lower(), level.upper())


def _attr(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Look up a value across flat keys, dotted OTel keys and nested ``attributes``."""
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
        attrs = d.get("attributes") or {}
        if k in attrs and attrs[k] not in (None, ""):
            return attrs[k]
        res = d.get("resource") or {}
        if k in res and res[k] not in (None, ""):
            return res[k]
    return default


def normalize_log(raw: dict[str, Any], *, default_service: str | None = None) -> dict[str, Any]:
    message = str(raw.get("message") or raw.get("body") or raw.get("msg") or "")
    template, thash = template_of(message)
    attrs = dict(raw.get("attributes") or {})
    for k in ("exception.type", "exception.message", "http.status_code", "http.route", "db.system", "error.type"):
        v = _attr(raw, k)
        if v is not None:
            attrs[k] = v
    return {
        "service": str(_attr(raw, "service", "service.name", default=default_service or "unknown")),
        "service_version": _attr(raw, "service_version", "service.version"),
        "level": normalize_level(raw.get("level") or raw.get("severity") or raw.get("severity_number")),
        "message": message[:4000],
        "template": template[:1000],
        "template_hash": thash,
        "trace_id": _attr(raw, "trace_id", "traceId"),
        "span_id": _attr(raw, "span_id", "spanId"),
        "attributes": attrs,
        "ts": parse_ts(raw.get("timestamp") or raw.get("ts") or raw.get("time")),
    }


def normalize_metric(raw: dict[str, Any], *, default_service: str | None = None) -> dict[str, Any]:
    return {
        "service": str(_attr(raw, "service", "service.name", default=default_service or "unknown")),
        "name": str(raw.get("name") or raw.get("metric")),
        "labels": dict(raw.get("labels") or raw.get("attributes") or {}),
        "ts": parse_ts(raw.get("timestamp") or raw.get("ts") or raw.get("time")),
        "value": float(raw.get("value", 0.0)),
    }


def normalize_span(raw: dict[str, Any], *, default_service: str | None = None) -> dict[str, Any]:
    start = parse_ts(raw.get("start_time") or raw.get("start") or raw.get("timestamp") or raw.get("ts"))
    duration = raw.get("duration_ms")
    if duration is None and raw.get("end_time"):
        duration = (parse_ts(raw["end_time"]) - start).total_seconds() * 1000
    status = raw.get("status") or "ok"
    if isinstance(status, dict):
        status = "error" if str(status.get("code", "")).lower() in ("error", "2") else "ok"
    return {
        "trace_id": str(_attr(raw, "trace_id", "traceId")),
        "span_id": str(_attr(raw, "span_id", "spanId")),
        "parent_span_id": _attr(raw, "parent_span_id", "parentSpanId"),
        "service": str(_attr(raw, "service", "service.name", default=default_service or "unknown")),
        "operation": str(raw.get("operation") or raw.get("name") or "unknown"),
        "kind": str(raw.get("kind") or "internal").lower(),
        "start_ts": start,
        "duration_ms": float(duration or 0.0),
        "status": "error" if str(status).lower() == "error" else "ok",
        "attributes": dict(raw.get("attributes") or {}),
    }
