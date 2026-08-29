"""Traffic generator: steady checkout/browse load against the frontend with mild noise."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
import time

import httpx

from sentinel_sim.config import settings

log = logging.getLogger("sim.traffic")


class TrafficGenerator:
    def __init__(self, rps: float | None = None) -> None:
        self.rps = rps or settings.traffic_rps
        self.enabled = settings.traffic_enabled
        self._task: asyncio.Task[None] | None = None
        self._client = httpx.AsyncClient(timeout=15.0)
        self.sent = 0
        self.failed = 0
        self._rng = random.Random(42)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="traffic")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._client.aclose()

    async def _one(self) -> None:
        url = settings.url_of("frontend")
        try:
            if self._rng.random() < 0.6:
                r = await self._client.post(url + "/checkout", json={"user": f"u{self._rng.randint(1, 500)}", "items": [{"sku": "A1", "qty": 1}], "amount": round(self._rng.uniform(5, 200), 2)})
            else:
                r = await self._client.get(url + "/")
            self.sent += 1
            if r.status_code >= 500:
                self.failed += 1
        except httpx.HTTPError:
            self.sent += 1
            self.failed += 1

    async def _loop(self) -> None:
        t0 = time.time()
        while True:
            if not self.enabled:
                await asyncio.sleep(0.5)
                continue
            # diurnal-ish wobble ±20% with a 10-minute period
            rate = self.rps * (1 + 0.2 * math.sin((time.time() - t0) / 95))
            n = max(1, int(self._rng.gauss(rate, rate * 0.15)))
            tasks = [asyncio.create_task(self._one()) for _ in range(n)]
            await asyncio.sleep(1.0)
            for t in tasks:
                if not t.done():
                    t.add_done_callback(lambda _t: None)

    def status(self) -> dict[str, float | int | bool]:
        return {"enabled": self.enabled, "rps": self.rps, "sent": self.sent, "failed": self.failed}
