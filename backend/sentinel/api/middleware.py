"""HTTP middleware: request IDs, access metrics, rate limiting, security headers."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from sentinel.core.config import get_settings
from sentinel.core.logging import bind, get_logger, reset
from sentinel.core.ratelimit import MemoryRateLimiter, RateLimiter
from sentinel.observability import metrics as m

log = get_logger("sentinel.http")

_limiter: RateLimiter = MemoryRateLimiter()


def set_rate_limiter(limiter: RateLimiter) -> None:
    global _limiter
    _limiter = limiter


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = bind(request_id=rid)
        start = time.perf_counter()
        route = request.url.path
        try:
            response = await call_next(request)
        except Exception:
            m.HTTP_REQUESTS.labels(request.method, _route_label(request, route), "500").inc()
            raise
        finally:
            dur = time.perf_counter() - start
            label = _route_label(request, route)
            m.HTTP_LATENCY.labels(request.method, label).observe(dur)
            reset(token)
        m.HTTP_REQUESTS.labels(request.method, _route_label(request, route), str(response.status_code)).inc()
        response.headers["x-request-id"] = rid
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        if response.status_code >= 500 or dur > 2.0:
            log.warning("request", method=request.method, path=route, status=response.status_code, ms=round(dur * 1000, 1))
        return response


def _route_label(request: Request, fallback: str) -> str:
    r = request.scope.get("route")
    path = getattr(r, "path", None)
    return path or ("/metrics" if fallback == "/metrics" else "unmatched")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        s = get_settings()
        path = request.url.path
        if path in ("/health", "/ready", "/metrics") or request.method == "OPTIONS":
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        key_hint = request.headers.get("x-api-key") or request.headers.get("authorization", "")[-12:]
        scope = "ingest" if path.startswith("/api/v1/ingest") else "api"
        limit = s.ingest_rate_limit_per_minute if scope == "ingest" else s.rate_limit_per_minute
        ok, remaining = await _limiter.allow(f"{scope}:{client}:{key_hint}", limit)
        if not ok:
            m.RATE_LIMITED.labels(scope).inc()
            return Response(
                content='{"error":{"code":"rate_limited","message":"too many requests"}}',
                status_code=429,
                media_type="application/json",
                headers={"retry-after": "60"},
            )
        response = await call_next(request)
        response.headers["x-ratelimit-remaining"] = str(remaining)
        return response
