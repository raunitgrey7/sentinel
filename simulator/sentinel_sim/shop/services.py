"""The Sentinel Demo Shop — seven services over real HTTP, each with its own runtime.

    frontend → api-gateway → auth-service    (→ redis, postgres)
                          → order-service   (→ inventory-service, payment-service, postgres, queue)
    notification-worker ← queue             (→ email-provider)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from sentinel_sim.runtime import SHARED_QUEUE, ServiceError, ServiceRuntime
from sentinel_sim.telemetry import SpanCtx

log = logging.getLogger("sim.shop")

Handler = Callable[[ServiceRuntime, SpanCtx, dict[str, Any]], Awaitable[dict[str, Any]]]


def make_app(rt: ServiceRuntime, routes: dict[tuple[str, str], Handler]) -> FastAPI:
    app = FastAPI(title=f"demo-shop/{rt.name}", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"service": rt.name, "version": rt.version, "healthy": rt.healthy, "faults": [f.to_dict() for f in rt.faults.values()]}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(rt.em.prometheus(), media_type="text/plain; version=0.0.4")

    for (method, path), handler in routes.items():
        _register(app, rt, method, path, handler)
    return app


def _register(app: FastAPI, rt: ServiceRuntime, method: str, path: str, handler: Handler) -> None:
    async def endpoint(request: Request) -> Response:
        body: dict[str, Any] = {}
        if method == "POST":
            with contextlib.suppress(Exception):
                body = await request.json()
        trace_id = request.headers.get("x-trace-id")
        parent = request.headers.get("x-parent-span-id")
        t0 = time.perf_counter()
        rt.em.inflight += 1
        status = 200
        try:
            async with SpanCtx(rt.em, f"{method} {path}", trace_id=trace_id, parent_span_id=parent, kind="server", **{"http.method": method, "http.route": path}) as span:
                try:
                    async with rt.worker_slot():
                        await rt.handle(span)
                        out = await handler(rt, span, body)
                    return JSONResponse(out, headers={"x-trace-id": span.trace_id})
                except ServiceError as exc:
                    status = exc.status
                    span.error = True
                    return JSONResponse({"error": exc.message, "service": rt.name}, status_code=exc.status, headers={"x-trace-id": span.trace_id})
                except Exception as exc:  # noqa: BLE001
                    status = 500
                    span.error = True
                    rt.em.log("ERROR", f"unhandled error in {method} {path}: {type(exc).__name__}: {exc}", trace_id=span.trace_id)
                    return JSONResponse({"error": "internal error"}, status_code=500)
        finally:
            rt.em.inflight -= 1
            rt.em.request((time.perf_counter() - t0) * 1000, status)

    app.add_api_route(path, endpoint, methods=[method])


# --------------------------------------------------------------------------------------
# handlers
# --------------------------------------------------------------------------------------


async def frontend_home(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    catalog = await rt.call(span, "api-gateway", "GET", "/catalog")
    return {"page": "home", "items": catalog.get("items", 0)}


async def frontend_checkout(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    return await rt.call(span, "api-gateway", "POST", "/checkout", json=body or {"user": "u1", "items": [{"sku": "A1", "qty": 1}], "amount": 42.0})


async def gateway_checkout(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    await rt.call(span, "auth-service", "POST", "/verify", json={"user": body.get("user", "u1")})
    return await rt.call(span, "order-service", "POST", "/orders", json=body)


async def gateway_catalog(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    await rt.call(span, "auth-service", "POST", "/verify", json={"user": "anon"})
    return await rt.call(span, "order-service", "GET", "/catalog")


async def auth_verify(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    hit = await rt.cache_get(span, f"session:{body.get('user', 'anon')}")
    if not hit:
        await rt.db_query(span, "SELECT * FROM sessions WHERE user_id = $1")
    return {"user": body.get("user", "anon"), "ok": True, "cached": hit}


async def order_create(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    await rt.call(span, "inventory-service", "POST", "/reserve", json={"items": body.get("items", [])})
    pay = await rt.call(span, "payment-service", "POST", "/charge", json={"amount": body.get("amount", 42.0), "user": body.get("user", "u1")})
    await rt.db_query(span, "INSERT INTO orders (user_id, amount, status) VALUES ($1, $2, $3)")
    await rt.publish(span, {"type": "order.created", "user": body.get("user", "u1")})
    return {"order_id": pay.get("charge_id", "unknown"), "status": "confirmed"}


async def order_catalog(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    await rt.call(span, "inventory-service", "GET", "/items")
    return {"items": 128}


async def inventory_reserve(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    hit = await rt.cache_get(span, "stock:A1")
    if not hit:
        await rt.db_query(span, "SELECT stock FROM inventory WHERE sku = $1 FOR UPDATE")
    await rt.db_query(span, "UPDATE inventory SET stock = stock - $1 WHERE sku = $2")
    return {"reserved": True}


async def inventory_items(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    hit = await rt.cache_get(span, "catalog:page:1")
    if not hit:
        await rt.db_query(span, "SELECT * FROM inventory LIMIT 100")
    return {"items": 128}


async def payment_charge(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    await rt.cache_get(span, f"customer:{body.get('user', 'u1')}")
    concurrency = int(rt.config.get("transaction.concurrency", 8))
    # the "bad deployment" raises transaction concurrency; each transaction holds a connection
    for _ in range(1 if concurrency <= 8 else 2):
        await rt.db_query(span, "INSERT INTO payments (user_id, amount) VALUES ($1, $2)")
    await rt.call_external(span, "payment-provider", "/v1/charges")
    return {"charge_id": f"ch_{int(time.time() * 1000) % 1_000_000}", "status": "succeeded"}


async def worker_status(rt: ServiceRuntime, span: SpanCtx, body: dict[str, Any]) -> dict[str, Any]:
    return {"depth": SHARED_QUEUE.depth(), "lag_s": SHARED_QUEUE.lag_s(), "processed": SHARED_QUEUE.processed}


async def notification_consumer(rt: ServiceRuntime) -> None:
    """Background consumer for notification-worker; paused by the queue_backlog fault."""
    while True:
        if SHARED_QUEUE.consumer_paused:
            await asyncio.sleep(0.5)
            continue
        try:
            msg = await asyncio.wait_for(SHARED_QUEUE.q.get(), timeout=1.0)
        except TimeoutError:
            continue
        SHARED_QUEUE.oldest_ts = time.time() if SHARED_QUEUE.q.empty() else SHARED_QUEUE.oldest_ts
        t0 = time.perf_counter()
        status = 200
        async with SpanCtx(rt.em, "queue.consume order.created", trace_id=msg.get("trace_id"), parent_span_id=None, kind="consumer") as span:
            try:
                await rt.handle(span)
                await rt.call_external(span, "email-provider", "/v1/send")
                SHARED_QUEUE.processed += 1
            except ServiceError as exc:
                status = exc.status
                SHARED_QUEUE.failed += 1
                span.error = True
                rt.em.log("ERROR", f"consumer failed to process message: {exc.message}", trace_id=span.trace_id)
        rt.em.request((time.perf_counter() - t0) * 1000, status)
        SHARED_QUEUE.q.task_done()
        await asyncio.sleep(0.05)


ROUTES: dict[str, dict[tuple[str, str], Handler]] = {
    "frontend": {("GET", "/"): frontend_home, ("POST", "/checkout"): frontend_checkout},
    "api-gateway": {("POST", "/checkout"): gateway_checkout, ("GET", "/catalog"): gateway_catalog},
    "auth-service": {("POST", "/verify"): auth_verify},
    "order-service": {("POST", "/orders"): order_create, ("GET", "/catalog"): order_catalog},
    "inventory-service": {("POST", "/reserve"): inventory_reserve, ("GET", "/items"): inventory_items},
    "payment-service": {("POST", "/charge"): payment_charge},
    "notification-worker": {("GET", "/status"): worker_status},
}
