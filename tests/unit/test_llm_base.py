import pytest
from pydantic import BaseModel

from sentinel.llm.base import StructuredOutputError, extract_json, parse_structured, repair_json
from sentinel.llm.none import NullProvider
from sentinel.llm.prompts import synthesis_prompt
from sentinel.llm.schemas import SynthesisOutput


class Out(BaseModel):
    a: int
    b: list[str]


def test_extract_json_from_prose_and_fences():
    assert extract_json('Sure! ```json\n{"a": 1, "b": ["x"]}\n``` done') == '{"a": 1, "b": ["x"]}'
    assert extract_json('prefix {"a": {"nested": "}"}, "b": []} suffix') == '{"a": {"nested": "}"}, "b": []}'


def test_repair_trailing_commas_and_quotes():
    assert parse_structured('{"a": 1, "b": ["x",],}', Out).b == ["x"]
    assert parse_structured("{“a”: 2, “b”: []}", Out).a == 2


def test_schema_validation_failure():
    with pytest.raises(StructuredOutputError):
        parse_structured('{"a": "not-int", "b": []}', Out)
    with pytest.raises(StructuredOutputError):
        parse_structured("no json here", Out)


def test_repair_json_nan():
    assert repair_json('{"x": NaN}') == '{"x": null}'


async def test_null_provider_synthesis_uses_context_only():
    ctx = {
        "incident": {"key": "INC-1", "title": "t", "severity": "HIGH", "primary_service": "payment-service", "affected_services": [], "started_at": "x", "detected_at": "y"},
        "timeline": [],
        "evidence": [{"ref": "E1", "kind": "metric", "service": "payment-service", "source": "m", "summary": "pool 99%", "weight": 0.9, "direction": "supports", "signals": ["db_pool_saturated"]}],
        "candidates": [{"rank": 1, "category": "database_connection_pool", "title": "Pool", "score": 0.8, "supporting": ["E1", "E99"], "contradicting": [], "culprit_service": "payment-service"}],
    }
    p = NullProvider()
    out, res = await p.structured("sys", synthesis_prompt(ctx), SynthesisOutput)
    assert out.hypotheses[0].category == "database_connection_pool"
    assert out.hypotheses[0].evidence == ["E1"]  # E99 dropped: not real evidence
    assert res.provider == "none"


async def test_null_provider_embeddings_are_deterministic():
    p = NullProvider(64)
    a, b = await p.embed(["service payment signals db_pool_saturated", "service payment signals db_pool_saturated"])
    assert a == b and len(a) == 64
