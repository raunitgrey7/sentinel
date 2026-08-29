"""LLM provider abstraction.

Sentinel talks to models through exactly three operations:

* ``generate``   — free text (used for the "Why?" answers and postmortem prose)
* ``structured`` — JSON constrained to a Pydantic schema (used for hypothesis synthesis)
* ``embed``      — vectors for incident-signature retrieval

Providers are swappable via ``SENTINEL_LLM_PROVIDER``. ``NullProvider`` is a real,
fully functional provider that uses deterministic templates — the platform never
*requires* a model to produce a correct, evidence-backed result.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(self, system: str, user: str, *, temperature: float | None = None, max_tokens: int = 1024) -> LLMResult: ...

    async def structured(self, system: str, user: str, schema: type[T], *, temperature: float | None = None, max_tokens: int = 2048) -> tuple[T, LLMResult]: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def healthy(self) -> bool: ...

    def snapshot(self) -> dict[str, Any]: ...


class StructuredOutputError(Exception):
    def __init__(self, message: str, *, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> str:
    """Pull the first JSON object out of a model reply, tolerating fences and prose."""
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start == -1:
        raise StructuredOutputError("no JSON object in response", raw=text)
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise StructuredOutputError("unterminated JSON object", raw=text)


def repair_json(s: str) -> str:
    """Cheap repairs for the most common small-model mistakes."""
    s = re.sub(r",\s*([}\]])", r"\1", s)  # trailing commas
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = re.sub(r"(?<!\\)\bNaN\b", "null", s)
    return s


def parse_structured(text: str, schema: type[T]) -> T:
    candidate = extract_json(text)
    for attempt in (candidate, repair_json(candidate)):
        try:
            data = json.loads(attempt)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last = exc
    raise StructuredOutputError(f"schema validation failed: {last}", raw=text)


def schema_hint(schema: type[BaseModel]) -> str:
    """Compact JSON-schema for the prompt (small models follow examples better than $refs)."""
    js = schema.model_json_schema()
    return json.dumps(js, separators=(",", ":"))
