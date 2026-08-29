"""Structured output contracts between Sentinel and the model.

Every schema that carries claims also carries ``evidence`` lists of *citation handles*
(``E1``, ``E7``...). The verifier rejects any handle that Sentinel did not mint.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RankedHypothesis(BaseModel):
    category: str = Field(description="One of the candidate categories given in the prompt")
    culprit_service: str | None = Field(default=None, description="Service most likely at fault")
    reasoning: str = Field(description="2-5 sentences explaining why the evidence supports this")
    evidence: list[str] = Field(default_factory=list, description="Citation handles like E3")
    contradicting_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, description="Model's own confidence 0..1")


class SynthesisOutput(BaseModel):
    summary: str = Field(description="One-paragraph incident summary in plain language")
    hypotheses: list[RankedHypothesis] = Field(description="Ranked best-first")
    caveats: list[str] = Field(default_factory=list, description="What is not verified / unknown")


class VerificationOutput(BaseModel):
    supported: bool
    issues: list[str] = Field(default_factory=list)
    adjusted_confidence: float = Field(ge=0.0, le=1.0)
    missing_evidence: list[str] = Field(default_factory=list)


class WhyAnswer(BaseModel):
    answer: str
    supporting: list[str] = Field(default_factory=list, description="Citation handles")
    counter_evidence: list[str] = Field(default_factory=list, description="Citation handles")
    conclusion: str = ""


class PostmortemSection(BaseModel):
    title: str
    body: str
    citations: list[str] = Field(default_factory=list)


class PostmortemOutput(BaseModel):
    sections: list[PostmortemSection]
