"""Redis-backed job queue.

Producer side uses ARQ's enqueue API (``arq.create_pool``) so that the dedicated
``sentinel worker`` process (an ARQ worker, see ``sentinel.worker.main``) consumes jobs.
Idempotency is handled by ARQ's ``_job_id`` (a job with the same id is not enqueued twice
while one is pending). Dead letters are recorded in a capped Redis list.
"""

from __future__ import annotations

import json
import time
from typing import Any

from sentinel.core.logging import get_logger

log = get_logger(__name__)

DLQ_KEY = "sentinel:dlq"
QUEUE_NAME = "sentinel:jobs"


class RedisQueue:
    backend = "redis"

    def __init__(self, redis_url: str, *, job_timeout_s: float = 300, max_retries: int = 3) -> None:
        self._url = redis_url
        self._pool = None
        self._timeout = job_timeout_s
        self._max_retries = max_retries

    async def start(self) -> None:
        from arq import create_pool
        from arq.connections import RedisSettings

        self._pool = await create_pool(RedisSettings.from_dsn(self._url))
        log.info("redis queue connected", url=self._url.split("@")[-1])

    async def stop(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None

    async def enqueue(self, name: str, payload: dict[str, Any], *, idempotency_key: str | None = None, delay_s: float = 0.0) -> str | None:
        assert self._pool is not None, "queue not started"
        job = await self._pool.enqueue_job(
            "dispatch",
            name,
            payload,
            _job_id=idempotency_key,
            _defer_by=delay_s or None,
            _queue_name=QUEUE_NAME,
        )
        return job.job_id if job else None

    async def depth(self) -> int:
        assert self._pool is not None
        return int(await self._pool.zcard(QUEUE_NAME))

    async def dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        assert self._pool is not None
        raw = await self._pool.lrange(DLQ_KEY, -limit, -1)
        return [json.loads(r) for r in raw]


async def record_dead_letter(redis, name: str, payload: dict[str, Any], error: str, attempts: int) -> None:  # type: ignore[no-untyped-def]
    entry = {"name": name, "payload": payload, "error": error, "attempts": attempts, "ts": time.time()}
    await redis.rpush(DLQ_KEY, json.dumps(entry, default=str))
    await redis.ltrim(DLQ_KEY, -500, -1)
