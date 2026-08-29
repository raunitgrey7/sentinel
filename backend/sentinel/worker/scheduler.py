"""Periodic scheduler: detector tick, retention, fault expiry.

Runs inside the worker process (Redis backend) or inside the API process (in-process
backend). Each tick is enqueued as a job with an idempotency key so overlapping ticks
collapse instead of piling up.
"""

from __future__ import annotations

import asyncio
import contextlib

from sentinel.core.config import get_settings
from sentinel.core.logging import get_logger
from sentinel.queue import get_queue
from sentinel.worker.jobs import JOB_DETECT, JOB_FAULT_EXPIRY, JOB_RETENTION

log = get_logger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []
        self._stop = asyncio.Event()

    async def start(self) -> None:
        s = get_settings()
        self._stop.clear()
        if s.detector_enabled:
            self._tasks.append(asyncio.create_task(self._loop(JOB_DETECT, s.detector_interval_s, "detector"), name="sched-detector"))
        self._tasks.append(asyncio.create_task(self._loop(JOB_FAULT_EXPIRY, 5.0, "fault-expiry"), name="sched-faults"))
        self._tasks.append(asyncio.create_task(self._loop(JOB_RETENTION, 3600.0, "retention"), name="sched-retention"))
        log.info("scheduler started", detector_interval_s=s.detector_interval_s)

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks = []

    async def _loop(self, job: str, interval: float, key: str) -> None:
        await asyncio.sleep(min(interval, 2.0))
        while not self._stop.is_set():
            try:
                await get_queue().enqueue(job, {}, idempotency_key=f"tick:{key}")
            except Exception as exc:  # noqa: BLE001
                log.warning("scheduler enqueue failed", job=job, error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                continue
