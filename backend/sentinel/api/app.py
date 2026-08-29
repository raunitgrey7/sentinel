"""FastAPI application factory."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sentinel.api.bootstrap import bootstrap
from sentinel.api.middleware import RateLimitMiddleware, RequestContextMiddleware, set_rate_limiter
from sentinel.api.routers import auth, evaluation, faults, incidents, ingest, projects, system
from sentinel.core.config import get_settings
from sentinel.core.errors import SentinelError
from sentinel.core.logging import configure_logging, context, get_logger
from sentinel.db.session import dispose, init_schema
from sentinel.queue import get_queue
from sentinel.worker import jobs as _jobs  # noqa: F401  (registers job handlers)
from sentinel.worker.scheduler import Scheduler

log = get_logger(__name__)

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    if s.auto_migrate:
        await init_schema()
    await bootstrap()
    q = get_queue()
    await q.start()
    scheduler: Scheduler | None = None
    if q.backend == "inprocess":
        # No separate worker process: run the scheduler inside the API.
        scheduler = Scheduler()
        await scheduler.start()
    if s.redis_url:
        try:
            import redis.asyncio as aioredis

            from sentinel.core.ratelimit import RedisRateLimiter

            set_rate_limiter(RedisRateLimiter(aioredis.from_url(s.redis_url)))
        except Exception as exc:  # noqa: BLE001
            log.warning("redis rate limiter unavailable; using in-memory", error=str(exc))
    log.info("sentinel api started", env=s.env, db="sqlite" if s.is_sqlite else "postgresql", queue=q.backend, llm=s.llm_provider)
    try:
        yield
    finally:
        if scheduler:
            await scheduler.stop()
        await q.stop()
        await dispose()
        log.info("sentinel api stopped")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Sentinel",
        version="0.1.0",
        description="Evidence-driven incident intelligence for modern software systems.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["x-request-id"])

    @app.exception_handler(SentinelError)
    async def _sentinel_error(request: Request, exc: SentinelError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.to_dict(), "request_id": context().get("request_id")})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "validation_failed", "message": "request validation failed", "details": exc.errors()}, "request_id": context().get("request_id")})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error", error=str(exc), exc_info=True)
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "internal error"}, "request_id": context().get("request_id")})

    app.include_router(system.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(projects.router, prefix=API_PREFIX)
    app.include_router(ingest.router, prefix=API_PREFIX)
    app.include_router(incidents.router, prefix=API_PREFIX)
    app.include_router(faults.router, prefix=API_PREFIX)
    app.include_router(evaluation.router, prefix=API_PREFIX)
    return app


app = create_app()
