"""Structured logging with request/incident correlation.

Two renderers: human-readable for local development, JSON lines for production.
Context (request_id, incident_id, investigation_id) is propagated with contextvars so
every log line emitted inside a request or a job carries the correlation keys without
threading them through function signatures.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any

_ctx: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("log_ctx")


def bind(**kwargs: Any) -> contextvars.Token[dict[str, Any]]:
    current = dict(_ctx.get({}))
    current.update({k: v for k, v in kwargs.items() if v is not None})
    return _ctx.set(current)


def reset(token: contextvars.Token[dict[str, Any]]) -> None:
    _ctx.reset(token)


def context() -> dict[str, Any]:
    return dict(_ctx.get({}))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_ctx.get({}))
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = _ctx.get({})
        ctx_str = " ".join(f"{k}={v}" for k, v in ctx.items())
        extra = getattr(record, "extra_fields", None) or {}
        extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
        base = f"{time.strftime('%H:%M:%S', time.gmtime(record.created))} {record.levelname:<7} {record.name}: {record.getMessage()}"
        tail = " ".join(x for x in (ctx_str, extra_str) if x)
        out = f"{base}  [{tail}]" if tail else base
        if record.exc_info:
            out += "\n" + self.formatException(record.exc_info)
        return out


class _ExtraAdapter(logging.LoggerAdapter):
    """``log.info("msg", key=value)`` → structured extra fields."""

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        std = {k: kwargs.pop(k) for k in ("exc_info", "stack_info", "stacklevel") if k in kwargs}
        extra_fields = {k: v for k, v in kwargs.items()}
        for k in list(kwargs):
            kwargs.pop(k)
        kwargs.update(std)
        kwargs["extra"] = {"extra_fields": extra_fields}
        return msg, kwargs


def get_logger(name: str) -> _ExtraAdapter:
    return _ExtraAdapter(logging.getLogger(name), {})


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else HumanFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "httpx", "httpcore", "aiosqlite", "arq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
