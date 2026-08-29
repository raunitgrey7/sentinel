"""Resilience primitives: retry with exponential backoff, circuit breaker, timeouts.

These are deliberately small and dependency-free. They are used around every boundary
that can fail independently of Sentinel — the LLM, the simulator control API, Redis.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import ParamSpec, TypeVar

from sentinel.core.errors import CircuitOpen
from sentinel.core.logging import get_logger

log = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    jitter: bool = True,
    label: str = "operation",
) -> T:
    """Call ``fn`` until it succeeds or ``attempts`` is exhausted, backing off exponentially."""
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except retry_on as exc:  # type: ignore[misc]
            last = exc
            if attempt == attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            if jitter:
                delay *= 0.5 + random.random()
            log.warning(
                "retrying", op=label, attempt=attempt, max_attempts=attempts, delay_s=round(delay, 2), error=str(exc)
            )
            await asyncio.sleep(delay)
    assert last is not None
    raise last


@dataclass
class CircuitBreaker:
    """Classic three-state breaker (closed → open → half-open).

    * ``failure_threshold`` consecutive failures open the circuit.
    * After ``reset_timeout`` seconds a single trial call is allowed (half-open).
    * A success closes the circuit; a failure re-opens it.
    """

    name: str
    failure_threshold: int = 3
    reset_timeout: float = 60.0
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _half_open: bool = field(default=False, init=False)

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self.reset_timeout:
            return "half_open"
        return "open"

    def _check(self) -> None:
        st = self.state
        if st == "open":
            raise CircuitOpen(f"circuit '{self.name}' is open", details={"retry_after_s": self.retry_after})
        if st == "half_open":
            if self._half_open:
                raise CircuitOpen(f"circuit '{self.name}' is half-open and busy")
            self._half_open = True

    @property
    def retry_after(self) -> float:
        if self._opened_at is None:
            return 0.0
        return max(0.0, self.reset_timeout - (time.monotonic() - self._opened_at))

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._half_open = False

    def record_failure(self) -> None:
        self._failures += 1
        self._half_open = False
        if self._failures >= self.failure_threshold:
            if self._opened_at is None:
                log.warning("circuit opened", circuit=self.name, failures=self._failures)
            self._opened_at = time.monotonic()

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        self._check()
        try:
            result = await fn()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    def snapshot(self) -> dict[str, object]:
        return {"name": self.name, "state": self.state, "failures": self._failures, "retry_after_s": round(self.retry_after, 1)}


async def with_timeout(coro: Awaitable[T], seconds: float, label: str = "operation") -> T:
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except TimeoutError as exc:
        raise TimeoutError(f"{label} timed out after {seconds}s") from exc
