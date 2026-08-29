"""Provider factory with automatic degradation.

``FallbackProvider`` wraps the configured model provider and falls back to the
deterministic ``NullProvider`` when the model is unreachable or the circuit is open.
Investigations therefore always complete; the result records which provider produced
the narrative so the UI can label it honestly.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

from sentinel.core.config import get_settings
from sentinel.core.logging import get_logger
from sentinel.llm.base import LLMProvider, LLMResult
from sentinel.llm.none import NullProvider

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)

_provider: LLMProvider | None = None


class FallbackProvider:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name
        self.model = primary.model
        self.last_used: str = primary.name

    async def healthy(self) -> bool:
        return await self.primary.healthy()

    def snapshot(self) -> dict[str, Any]:
        s = self.primary.snapshot()
        s["fallback"] = self.fallback.name
        s["last_used"] = self.last_used
        return s

    async def generate(self, system: str, user: str, **kw: Any) -> LLMResult:
        try:
            res = await self.primary.generate(system, user, **kw)
            self.last_used = self.primary.name
            return res
        except Exception as exc:  # noqa: BLE001
            log.warning("primary provider failed; using deterministic fallback", error=str(exc)[:200])
            self.last_used = self.fallback.name
            return await self.fallback.generate(system, user, **kw)

    async def structured(self, system: str, user: str, schema: type[T], **kw: Any) -> tuple[T, LLMResult]:
        try:
            out = await self.primary.structured(system, user, schema, **kw)
            self.last_used = self.primary.name
            return out
        except Exception as exc:  # noqa: BLE001
            log.warning("primary structured call failed; using deterministic fallback", error=str(exc)[:200])
            self.last_used = self.fallback.name
            return await self.fallback.structured(system, user, schema, **kw)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            return await self.primary.embed(texts)
        except Exception as exc:  # noqa: BLE001
            log.warning("primary embed failed; using hashed embeddings", error=str(exc)[:200])
            return await self.fallback.embed(texts)


def build_provider() -> LLMProvider:
    s = get_settings()
    null = NullProvider(s.embedding_dim)
    if s.llm_provider == "ollama":
        from sentinel.llm.ollama import OllamaProvider

        primary = OllamaProvider(
            s.ollama_base_url,
            s.ollama_model,
            s.ollama_embed_model,
            timeout_s=s.llm_timeout_s,
            max_retries=s.llm_max_retries,
            temperature=s.llm_temperature,
            circuit_failures=s.llm_circuit_failures,
            circuit_reset_s=s.llm_circuit_reset_s,
        )
        return FallbackProvider(primary, null)
    return null


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = build_provider()
    return _provider


def set_provider(p: LLMProvider | None) -> None:
    global _provider
    _provider = p


__all__ = ["FallbackProvider", "LLMProvider", "LLMResult", "NullProvider", "build_provider", "get_provider", "set_provider"]
