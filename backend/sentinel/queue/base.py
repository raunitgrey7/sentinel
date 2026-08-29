"""Job queue abstraction.

A job is ``(name, payload, idempotency_key)``. Handlers are registered by name in a
``JobRegistry``; the same registry is used by the in-process consumer and the Redis
(ARQ) worker, so the application code never knows which backend is active.

Delivery semantics: at-least-once. Handlers must be idempotent — the investigation
orchestrator, for example, resumes from its checkpoint rather than restarting.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from sentinel.core.ids import new_id
from sentinel.core.logging import bind, get_logger, reset
from sentinel.observability import metrics as m

log = get_logger(__name__)

JobHandler = Callable[["JobContext"], Awaitable[Any]]


@dataclass
class Job:
    name: str
    payload: dict[str, Any]
    id: str = field(default_factory=new_id)
    idempotency_key: str | None = None
    attempt: int = 1
    max_retries: int = 3
    enqueued_at: float = field(default_factory=time.time)


@dataclass
class JobContext:
    job: Job

    @property
    def payload(self) -> dict[str, Any]:
        return self.job.payload

    @property
    def attempt(self) -> int:
        return self.job.attempt


class JobRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, name: str) -> Callable[[JobHandler], JobHandler]:
        def deco(fn: JobHandler) -> JobHandler:
            if name in self._handlers:
                raise ValueError(f"job '{name}' already registered")
            self._handlers[name] = fn
            return fn

        return deco

    def get(self, name: str) -> JobHandler:
        try:
            return self._handlers[name]
        except KeyError as exc:
            raise KeyError(f"no handler registered for job '{name}'") from exc

    def names(self) -> list[str]:
        return sorted(self._handlers)


registry = JobRegistry()


class JobQueue(Protocol):
    backend: str

    async def enqueue(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        delay_s: float = 0.0,
    ) -> str | None: ...

    async def depth(self) -> int: ...

    async def dead_letters(self, limit: int = 50) -> list[dict[str, Any]]: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


async def execute_job(job: Job, *, timeout_s: float) -> Any:
    """Run a handler with timeout + metrics + log correlation. Raises on failure."""
    handler = registry.get(job.name)
    token = bind(job=job.name, job_id=job.id, attempt=job.attempt)
    start = time.perf_counter()
    try:
        result = await asyncio.wait_for(handler(JobContext(job)), timeout=timeout_s)
        m.JOBS.labels(job.name, "success").inc()
        return result
    except TimeoutError:
        m.JOBS.labels(job.name, "timeout").inc()
        raise
    except Exception:
        m.JOBS.labels(job.name, "failure").inc()
        raise
    finally:
        m.JOB_LATENCY.labels(job.name).observe(time.perf_counter() - start)
        reset(token)
