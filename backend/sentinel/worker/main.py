"""Worker entrypoint.

* Redis backend → an ARQ worker consuming ``sentinel:jobs`` with graceful shutdown,
  retries and dead-lettering.
* In-process backend → a standalone loop that runs the in-process queue + scheduler
  (useful when the API is deployed separately but Redis is not wanted).
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any

from sentinel.core.config import get_settings
from sentinel.core.logging import configure_logging, get_logger
from sentinel.db.session import init_schema
from sentinel.queue import get_queue
from sentinel.queue.base import Job, execute_job
from sentinel.worker import jobs as _jobs  # noqa: F401  (registers handlers)
from sentinel.worker.scheduler import Scheduler

log = get_logger(__name__)


async def dispatch(ctx: dict[str, Any], name: str, payload: dict[str, Any]) -> Any:
    """ARQ task: route to the registered handler."""
    from arq import Retry

    from sentinel.queue.redis_queue import record_dead_letter

    s = get_settings()
    attempt = int(ctx.get("job_try", 1))
    job = Job(name=name, payload=payload, attempt=attempt, max_retries=s.job_max_retries)
    try:
        return await execute_job(job, timeout_s=s.job_timeout_s)
    except Exception as exc:
        if attempt <= s.job_max_retries:
            raise Retry(defer=s.job_retry_backoff_s * (2 ** (attempt - 1))) from exc
        await record_dead_letter(ctx["redis"], name, payload, str(exc), attempt)
        raise


async def _startup(ctx: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level, get_settings().log_json)
    await init_schema()
    q = get_queue()
    await q.start()
    ctx["scheduler"] = Scheduler()
    await ctx["scheduler"].start()
    log.info("worker started", backend=q.backend)


async def _shutdown(ctx: dict[str, Any]) -> None:
    await ctx["scheduler"].stop()
    await get_queue().stop()
    log.info("worker stopped")


def arq_worker_settings() -> type:
    from arq.connections import RedisSettings

    from sentinel.queue.redis_queue import QUEUE_NAME

    s = get_settings()
    assert s.redis_url, "SENTINEL_REDIS_URL is required for the Redis worker"

    class WorkerSettings:
        functions = [dispatch]
        on_startup = _startup
        on_shutdown = _shutdown
        redis_settings = RedisSettings.from_dsn(s.redis_url)
        queue_name = QUEUE_NAME
        max_jobs = 8
        job_timeout = s.job_timeout_s + 30
        max_tries = s.job_max_retries + 1
        health_check_interval = 30
        retry_jobs = True

    return WorkerSettings


async def run_inprocess_worker() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    await init_schema()
    q = get_queue()
    await q.start()
    sched = Scheduler()
    await sched.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: stop.set())
    log.info("in-process worker running; Ctrl+C to stop")
    await stop.wait()
    await sched.stop()
    await q.stop()


def main() -> None:
    s = get_settings()
    if s.effective_queue_backend == "redis":
        from arq import run_worker

        run_worker(arq_worker_settings())  # type: ignore[arg-type]
    else:
        asyncio.run(run_inprocess_worker())


if __name__ == "__main__":
    main()
