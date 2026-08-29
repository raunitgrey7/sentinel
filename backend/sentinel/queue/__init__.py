"""Queue factory. The active backend is decided by settings, never by application code."""

from __future__ import annotations

from sentinel.core.config import get_settings
from sentinel.queue.base import Job, JobContext, JobQueue, JobRegistry, registry

_queue: JobQueue | None = None


def build_queue() -> JobQueue:
    s = get_settings()
    if s.effective_queue_backend == "redis":
        from sentinel.queue.redis_queue import RedisQueue

        assert s.redis_url
        return RedisQueue(s.redis_url, job_timeout_s=s.job_timeout_s, max_retries=s.job_max_retries)
    from sentinel.queue.inprocess import InProcessQueue

    return InProcessQueue(job_timeout_s=s.job_timeout_s, max_retries=s.job_max_retries, backoff_s=s.job_retry_backoff_s)


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = build_queue()
    return _queue


def set_queue(q: JobQueue | None) -> None:
    global _queue
    _queue = q


__all__ = ["Job", "JobContext", "JobQueue", "JobRegistry", "build_queue", "get_queue", "registry", "set_queue"]
