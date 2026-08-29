"""Ollama provider — local models over ``http://localhost:11434`` with no API key.

Hardening around the model boundary:
* per-call timeout, bounded retries with backoff,
* circuit breaker (repeated failures stop hammering the model host),
* JSON mode + schema validation + repair + re-prompt on invalid output,
* metrics for latency / outcome / tokens.
"""

from __future__ import annotations

import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from sentinel.core.logging import get_logger
from sentinel.core.resilience import CircuitBreaker
from sentinel.llm.base import LLMResult, StructuredOutputError, parse_structured, schema_hint
from sentinel.observability import metrics as m

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        embed_model: str,
        *,
        timeout_s: float = 90.0,
        max_retries: int = 2,
        temperature: float = 0.1,
        circuit_failures: int = 3,
        circuit_reset_s: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.temperature = temperature
        self.breaker = CircuitBreaker("ollama", failure_threshold=circuit_failures, reset_timeout=circuit_reset_s)
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(timeout_s, connect=5.0))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def healthy(self) -> bool:
        try:
            r = await self._client.get("/api/tags", timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def snapshot(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "embed_model": self.embed_model, "circuit": self.breaker.snapshot()}

    async def _chat(self, system: str, user: str, *, temperature: float | None, max_tokens: int, json_mode: bool, op: str) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": self.temperature if temperature is None else temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"

        async def _call() -> LLMResult:
            start = time.perf_counter()
            r = await self._client.post("/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            latency = (time.perf_counter() - start) * 1000
            text = (data.get("message") or {}).get("content", "")
            res = LLMResult(
                text=text,
                provider=self.name,
                model=self.model,
                latency_ms=latency,
                prompt_tokens=int(data.get("prompt_eval_count", 0)),
                completion_tokens=int(data.get("eval_count", 0)),
                raw={k: data.get(k) for k in ("total_duration", "load_duration", "eval_duration")},
            )
            m.LLM_TOKENS.labels(self.name, "prompt").inc(res.prompt_tokens)
            m.LLM_TOKENS.labels(self.name, "completion").inc(res.completion_tokens)
            return res

        last: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                with m.timed(m.LLM_LATENCY, provider=self.name, op=op):
                    res = await self.breaker.call(_call)
                m.LLM_CALLS.labels(self.name, op, "success").inc()
                m.CIRCUIT_STATE.labels("ollama").set(0)
                return res
            except Exception as exc:  # noqa: BLE001
                last = exc
                m.LLM_CALLS.labels(self.name, op, "failure").inc()
                m.CIRCUIT_STATE.labels("ollama").set(1 if self.breaker.state == "open" else 0)
                log.warning("ollama call failed", op=op, attempt=attempt, error=str(exc)[:200])
                if self.breaker.state == "open" or attempt > self.max_retries:
                    break
                await _sleep(0.5 * attempt)
        assert last is not None
        raise last

    async def generate(self, system: str, user: str, *, temperature: float | None = None, max_tokens: int = 1024) -> LLMResult:
        return await self._chat(system, user, temperature=temperature, max_tokens=max_tokens, json_mode=False, op="generate")

    async def structured(self, system: str, user: str, schema: type[T], *, temperature: float | None = None, max_tokens: int = 2048) -> tuple[T, LLMResult]:
        sys_prompt = system + "\n\nRespond with a single JSON object matching this JSON schema exactly:\n" + schema_hint(schema)
        last_err: StructuredOutputError | None = None
        prompt = user
        for attempt in range(2):
            res = await self._chat(sys_prompt, prompt, temperature=temperature, max_tokens=max_tokens, json_mode=True, op="structured")
            try:
                return parse_structured(res.text, schema), res
            except StructuredOutputError as exc:
                last_err = exc
                m.LLM_CALLS.labels(self.name, "structured", "invalid_json").inc()
                prompt = user + f"\n\nYour previous reply was not valid for the schema ({str(exc)[:200]}). Reply with ONLY the JSON object."
                log.warning("structured output invalid; re-prompting", attempt=attempt + 1)
        assert last_err is not None
        raise last_err

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async def _call() -> list[list[float]]:
            r = await self._client.post("/api/embed", json={"model": self.embed_model, "input": texts})
            r.raise_for_status()
            return [list(map(float, v)) for v in r.json().get("embeddings", [])]

        with m.timed(m.LLM_LATENCY, provider=self.name, op="embed"):
            try:
                out = await self.breaker.call(_call)
                m.LLM_CALLS.labels(self.name, "embed", "success").inc()
                return out
            except Exception:
                m.LLM_CALLS.labels(self.name, "embed", "failure").inc()
                raise


async def _sleep(s: float) -> None:
    import asyncio

    await asyncio.sleep(s)
