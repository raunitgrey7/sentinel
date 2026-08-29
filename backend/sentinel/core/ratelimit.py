"""Sliding-window rate limiter with in-memory and Redis backends."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Protocol


class RateLimiter(Protocol):
    async def allow(self, key: str, limit: int, window_s: int = 60) -> tuple[bool, int]: ...


class MemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def allow(self, key: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
        now = time.monotonic()
        q = self._hits[key]
        cutoff = now - window_s
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            return False, 0
        q.append(now)
        return True, limit - len(q)


class RedisRateLimiter:
    def __init__(self, redis) -> None:  # type: ignore[no-untyped-def]
        self._r = redis

    async def allow(self, key: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
        now = time.time()
        rkey = f"sentinel:rl:{key}"
        pipe = self._r.pipeline()
        pipe.zremrangebyscore(rkey, 0, now - window_s)
        pipe.zadd(rkey, {f"{now}": now})
        pipe.zcard(rkey)
        pipe.expire(rkey, window_s)
        _, _, count, _ = await pipe.execute()
        if count > limit:
            return False, 0
        return True, limit - int(count)
