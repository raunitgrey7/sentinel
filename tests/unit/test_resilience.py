import pytest

from sentinel.core.errors import CircuitOpen
from sentinel.core.resilience import CircuitBreaker, retry_async, with_timeout


async def test_retry_eventually_succeeds():
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("nope")
        return "ok"

    assert await retry_async(flaky, attempts=3, base_delay=0.001, jitter=False) == "ok"
    assert calls["n"] == 3


async def test_retry_exhausts():
    async def always() -> None:
        raise ValueError("bad")

    with pytest.raises(ValueError):
        await retry_async(always, attempts=2, base_delay=0.001)


async def test_circuit_breaker_opens_and_recovers():
    cb = CircuitBreaker("t", failure_threshold=2, reset_timeout=0.05)

    async def fail() -> None:
        raise RuntimeError("x")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(fail)
    assert cb.state == "open"
    with pytest.raises(CircuitOpen):
        await cb.call(fail)
    import asyncio

    await asyncio.sleep(0.06)
    assert cb.state == "half_open"

    async def ok() -> str:
        return "ok"

    assert await cb.call(ok) == "ok"
    assert cb.state == "closed"


async def test_with_timeout():
    import asyncio

    with pytest.raises(TimeoutError):
        await with_timeout(asyncio.sleep(1), 0.01, "sleep")
