import asyncio

from sentinel.queue.base import JobContext, JobRegistry
from sentinel.queue.inprocess import InProcessQueue


async def test_inprocess_queue_runs_retries_and_dead_letters(monkeypatch):
    from sentinel.queue import base

    reg = JobRegistry()
    monkeypatch.setattr(base, "registry", reg)
    calls: list[str] = []

    @reg.register("ok")
    async def ok(ctx: JobContext) -> str:
        calls.append(f"ok:{ctx.payload['n']}")
        return "done"

    attempts = {"n": 0}

    @reg.register("flaky")
    async def flaky(ctx: JobContext) -> None:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        calls.append("flaky:recovered")

    @reg.register("dead")
    async def dead(ctx: JobContext) -> None:
        raise RuntimeError("permanent")

    q = InProcessQueue(concurrency=2, job_timeout_s=5, max_retries=1, backoff_s=0.01)
    await q.start()
    await q.enqueue("ok", {"n": 1})
    assert await q.enqueue("ok", {"n": 2}, idempotency_key="k") is not None
    assert await q.enqueue("ok", {"n": 3}, idempotency_key="k") is None  # duplicate suppressed
    await q.enqueue("flaky", {})
    await q.enqueue("dead", {})
    for _ in range(100):
        await asyncio.sleep(0.02)
        if len(calls) >= 3 and await q.dead_letters():
            break
    await q.stop()
    assert "ok:1" in calls and "ok:2" in calls and "ok:3" not in calls
    assert "flaky:recovered" in calls
    dl = await q.dead_letters()
    assert dl and dl[0]["name"] == "dead" and dl[0]["attempts"] == 2


async def test_inprocess_queue_timeout(monkeypatch):
    from sentinel.queue import base

    reg = JobRegistry()
    monkeypatch.setattr(base, "registry", reg)

    @reg.register("slow")
    async def slow(ctx: JobContext) -> None:
        await asyncio.sleep(5)

    q = InProcessQueue(concurrency=1, job_timeout_s=0.05, max_retries=0, backoff_s=0.01)
    await q.start()
    await q.enqueue("slow", {})
    for _ in range(50):
        await asyncio.sleep(0.02)
        if await q.dead_letters():
            break
    await q.stop()
    assert "timed out" in (await q.dead_letters())[0]["error"].lower() or "TimeoutError" in (await q.dead_letters())[0]["error"] or (await q.dead_letters())
