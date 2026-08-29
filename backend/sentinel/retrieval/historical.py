"""Historical incident retrieval (RAG over resolved incidents).

Signature → embedding → cosine ranking against stored incident embeddings. Ranking is
done in-process: the corpus is one row per incident (hundreds to low thousands), which is
far below the point where an ANN index pays for itself. pgvector is the documented
upgrade path (docs/adr/0004-retrieval.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.db.models import Incident
from sentinel.domain.enums import IncidentStatus
from sentinel.llm.base import LLMProvider
from sentinel.observability import metrics as m
from sentinel.retrieval.embeddings import cosine

RETRIEVABLE = {IncidentStatus.RESOLVED, IncidentStatus.POSTMORTEM, IncidentStatus.CLOSED}


@dataclass
class Similar:
    incident_id: str
    key: str
    title: str
    similarity: float
    root_cause_category: str | None
    root_cause_summary: str | None
    primary_service: str
    resolved_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "key": self.key,
            "title": self.title,
            "similarity": round(self.similarity, 4),
            "root_cause_category": self.root_cause_category,
            "root_cause_summary": self.root_cause_summary,
            "primary_service": self.primary_service,
            "resolved_at": self.resolved_at,
        }


async def embed_signature(provider: LLMProvider, signature: str) -> list[float]:
    vecs = await provider.embed([signature])
    return vecs[0] if vecs else []


async def find_similar(
    session: AsyncSession,
    provider: LLMProvider,
    *,
    project_id: str,
    signature: str,
    exclude_incident_id: str | None,
    k: int = 5,
    min_similarity: float = 0.25,
) -> tuple[list[Similar], list[float]]:
    with m.timed(m.RETRIEVAL_LATENCY):
        query_vec = await embed_signature(provider, signature)
        stmt = select(Incident).where(
            Incident.project_id == project_id,
            Incident.status.in_([s.value for s in RETRIEVABLE]),
            Incident.embedding.is_not(None),
        )
        rows = (await session.execute(stmt)).scalars().all()
        scored: list[Similar] = []
        for inc in rows:
            if inc.id == exclude_incident_id or not inc.embedding:
                continue
            sim = cosine(query_vec, list(inc.embedding))
            if sim >= min_similarity:
                scored.append(
                    Similar(
                        incident_id=inc.id,
                        key=inc.key,
                        title=inc.title,
                        similarity=sim,
                        root_cause_category=inc.root_cause_category,
                        root_cause_summary=inc.root_cause_summary,
                        primary_service=inc.primary_service,
                        resolved_at=inc.resolved_at.isoformat() if inc.resolved_at else None,
                    )
                )
        scored.sort(key=lambda s: s.similarity, reverse=True)
        return scored[:k], query_vec
