"""In-process asyncio job queue with retries, backoff and a dead-letter list.

Used when ``SENTINEL_REDIS_URL`` is unset (local-first / tests). Semantics mirror the
Redis backend: at-least-once, idempotency-key de-duplication while a job is pending,
exponential backoff between attempts, dead-letter after ``max_retries``.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from typing import Any

from sentinel.core.logging import get_logger
from sentinel.observability import metrics as m
from sentinel.queue.base import Job, execute_job

log = get_logger(__name__)


class InProcessQueue:
    backend = "inprocess"

    def __init__(self, *, concurrency: int = 4, job_timeout_s: float = 300, max_retries: int = 3, backoff_s: float = 2.0) -> None:
        self._q: asyncio.Queue[Job] = asyncio.Queue()
        self._pending_keys: set[str] = set()
        self._dead: deque[dict[str, Any]] = deque(maxlen=200)
        self._workers: list[asyncio.Task[None]] = []
        self._concurrency = concurrency
        self._timeout = job_timeout_s
        self._max_retries = max_retries
        self._backoff = backoff_s
        self._stopping = False
        self._delayed: set[asyncio.Task[None]] = set()

    async def enqueue(self, name: str, payload: dict[str, Any], *, idempotency_key: str | None = None, delay_s: float = 0.0) -> str | None:
        if idempotency_key and idempotency_key in self._pending_keys:
            log.debug("duplicate job suppressed", job=name, key=idempotency_key)
            return None
        job = Job(name=name, payload=payload, idempotency_key=idempotency_key, max_retries=self._max_retries)
        if idempotency_key:
            self._pending_keys.add(idempotency_key)
        if delay_s > 0:
            t = asyncio.create_task(self._put_later(job, delay_s))
            self._delayed.add(t)
            t.add_done_callback(self._delayed.discard)
        else:
            await self._q.put(job)
        m.QUEUE_DEPTH.labels("default").set(self._q.qsize())
        return job.id

    async def _put_later(self, job: Job, delay_s: float) -> None:
        await asyncio.sleep(delay_s)
        await self._q.put(job)

    async def depth(self) -> int:
        return self._q.qsize()

    async def dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._dead)[-limit:]

    async def start(self) -> None:
        if self._workers:
            return
        self._stopping = False
        self._workers = [asyncio.create_task(self._run(i), name=f"queue-worker-{i}") for i in range(self._concurrency)]
        log.info("in-process queue started", concurrency=self._concurrency)

    async def stop(self) -> None:
        """Graceful shutdown: stop accepting, let in-flight jobs finish (bounded), cancel the rest."""
        self._stopping = True
        for t in self._delayed:
            t.cancel()
        for w in self._workers:
            w.cancel()
        for w in self._workers:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await w
        self._workers = []

    async def drain(self, timeout_s: float = 30.0) -> None:
        """Wait until the queue is empty and idle (tests / CLI)."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._q.empty() and not self._delayed and self._q._unfinished_tasks == 0:
                return
            await asyncio.sleep(0.05)

    async def _run(self, idx: int) -> None:
        while not self._stopping:
            job = await self._q.get()
            try:
                await self._process(job)
            finally:
                self._q.task_done()
                m.QUEUE_DEPTH.labels("default").set(self._q.qsize())

    async def _process(self, job: Job) -> None:
        try:
            await execute_job(job, timeout_s=self._timeout)
            if job.idempotency_key:
                self._pending_keys.discard(job.idempotency_key)
        except Exception as exc:  # noqa: BLE001
            if job.attempt <= job.max_retries:
                delay = self._backoff * (2 ** (job.attempt - 1))
                log.warning("job failed; scheduling retry", job=job.name, attempt=job.attempt, delay_s=delay, error=str(exc))
                job.attempt += 1
                t = asyncio.create_task(self._put_later(job, delay))
                self._delayed.add(t)
                t.add_done_callback(self._delayed.discard)
            else:
                log.error("job dead-lettered", job=job.name, job_id=job.id, error=str(exc))
                m.DEAD_LETTERS.labels(job.name).inc()
                self._dead.append({"id": job.id, "name": job.name, "payload": job.payload, "error": str(exc), "attempts": job.attempt, "ts": time.time()})
                if job.idempotency_key:
                    self._pending_keys.discard(job.idempotency_key)
