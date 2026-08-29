"""Chaos: the platform itself under failure — model outage, queue dead-letters, step timeouts."""

import asyncio

import pytest

from sentinel.core.errors import CircuitOpen
from sentinel.llm import FallbackProvider, NullProvider
from sentinel.llm.schemas import SynthesisOutput

pytestmark = pytest.mark.chaos


class DeadModel:
    name = "ollama"
    model = "qwen2.5:7b"

    async def healthy(self) -> bool:
        return False

    def snapshot(self) -> dict:
        return {"provider": self.name, "model": self.model, "circuit": {"state": "open"}}

    async def generate(self, *a, **k):  # type: ignore[no-untyped-def]
        raise CircuitOpen("circuit 'ollama' is open")

    async def structured(self, *a, **k):  # type: ignore[no-untyped-def]
        raise TimeoutError("model timed out")

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        raise ConnectionError("refused")


async def test_model_outage_degrades_to_deterministic_narrator():
    p = FallbackProvider(DeadModel(), NullProvider())
    ctx = '<<SENTINEL_CONTEXT>>{"incident": {"title": "t", "primary_service": "p"}, "candidates": [], "evidence": []}<<END_SENTINEL_CONTEXT>>'
    out, res = await p.structured("s", ctx, SynthesisOutput)
    assert res.provider == "none" and p.last_used == "none"
    assert out.caveats and "Deterministic" in out.caveats[0]
    vec = await p.embed(["x"])
    assert len(vec[0]) == 256


async def test_step_timeout_fails_stage_not_process(monkeypatch):
    """A hung investigator must be bounded by the per-step timeout."""
    from types import SimpleNamespace

    from sentinel.investigation import orchestrator

    async def hang(ctx):  # type: ignore[no-untyped-def]
        await asyncio.sleep(10)

    stage = orchestrator.Stage("hang", "Hang", hang, optional=True, timeout_s=0.05)
    step = SimpleNamespace(status="PENDING", attempts=0, started_at=None, completed_at=None, duration_ms=None, output={}, error=None)

    class Sess:
        async def commit(self) -> None:
            pass

    ctx = SimpleNamespace(settings=SimpleNamespace(investigation_step_timeout_s=1, investigation_max_attempts=1), session=Sess())
    await orchestrator._run_stage(ctx, stage, step)  # type: ignore[arg-type]
    assert step.status == "FAILED" and "TimeoutError" in step.error
    assert step.output.get("skipped") is True
