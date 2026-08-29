"""Investigation context shared by every investigator.

``EvidenceBag`` mints citation handles (E1, E2, ...) — the only source of handles in the
system. Investigators append ``EvidenceItem``s tagged with catalog *signals*; the
hypothesis generator and scorer consume the bag; the graph builder turns it into nodes
and edges; the persistence step writes it to the ``evidence`` table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.analysis.dependency_graph import ServiceGraph
from sentinel.core.config import Settings
from sentinel.db.models import Incident, Investigation
from sentinel.domain.enums import EvidenceDirection, EvidenceKind
from sentinel.llm.base import LLMProvider


@dataclass
class EvidenceItem:
    ref: str
    kind: str
    source: str
    summary: str
    service: str | None = None
    signals: list[str] = field(default_factory=list)
    weight: float = 1.0
    direction: str = EvidenceDirection.SUPPORTS
    detail: dict[str, Any] = field(default_factory=dict)
    ts_start: datetime | None = None
    ts_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "kind": self.kind,
            "source": self.source,
            "summary": self.summary,
            "service": self.service,
            "signals": list(self.signals),
            "weight": round(self.weight, 3),
            "direction": self.direction,
            "detail": self.detail,
            "ts_start": self.ts_start.isoformat() if self.ts_start else None,
            "ts_end": self.ts_end.isoformat() if self.ts_end else None,
        }


class EvidenceBag:
    def __init__(self) -> None:
        self.items: list[EvidenceItem] = []
        self._n = 0

    def add(
        self,
        kind: EvidenceKind | str,
        source: str,
        summary: str,
        *,
        service: str | None = None,
        signals: list[str] | None = None,
        weight: float = 1.0,
        direction: EvidenceDirection | str = EvidenceDirection.SUPPORTS,
        detail: dict[str, Any] | None = None,
        ts_start: datetime | None = None,
        ts_end: datetime | None = None,
    ) -> EvidenceItem:
        self._n += 1
        item = EvidenceItem(
            ref=f"E{self._n}",
            kind=str(kind),
            source=source,
            summary=summary,
            service=service,
            signals=list(signals or []),
            weight=max(0.0, min(1.0, weight)),
            direction=str(direction),
            detail=detail or {},
            ts_start=ts_start,
            ts_end=ts_end,
        )
        self.items.append(item)
        return item

    def signals(self) -> dict[str, float]:
        """signal → strongest weight observed."""
        out: dict[str, float] = {}
        for it in self.items:
            for s in it.signals:
                out[s] = max(out.get(s, 0.0), it.weight)
        return out

    def by_signal(self, signal: str) -> list[EvidenceItem]:
        return [it for it in self.items if signal in it.signals]

    def refs(self) -> set[str]:
        return {it.ref for it in self.items}

    def get(self, ref: str) -> EvidenceItem | None:
        return next((it for it in self.items if it.ref == ref), None)

    def to_list(self) -> list[dict[str, Any]]:
        return [it.to_dict() for it in self.items]

    def load(self, rows: list[dict[str, Any]]) -> None:
        """Rehydrate from persisted rows (resume after crash)."""
        self.items = []
        for r in rows:
            self.items.append(
                EvidenceItem(
                    ref=r["ref"],
                    kind=r["kind"],
                    source=r["source"],
                    summary=r["summary"],
                    service=r.get("service"),
                    signals=list(r.get("signals") or []),
                    weight=float(r.get("weight", 1.0)),
                    direction=r.get("direction", "supports"),
                    detail=r.get("detail") or {},
                )
            )
        self._n = max((int(it.ref[1:]) for it in self.items), default=0)


@dataclass
class Windows:
    baseline_start: datetime
    baseline_end: datetime
    incident_start: datetime
    incident_end: datetime
    lookback_start: datetime  # for deployments / config changes


@dataclass
class InvestigationContext:
    session: AsyncSession
    settings: Settings
    incident: Incident
    investigation: Investigation
    provider: LLMProvider
    windows: Windows
    service_graph: ServiceGraph
    evidence: EvidenceBag = field(default_factory=EvidenceBag)
    scope_services: list[str] = field(default_factory=list)  # primary + downstream deps
    timeline: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    synthesis: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)  # free-form per-step outputs
    llm_ms: float = 0.0
    llm_calls: int = 0

    @property
    def project_id(self) -> str:
        return self.incident.project_id

    @property
    def primary(self) -> str:
        return self.incident.primary_service

    def add_timeline(self, ts: datetime, kind: str, message: str, **data: Any) -> None:
        self.timeline.append({"ts": ts, "kind": kind, "message": message, "data": data})

    def record_llm(self, latency_ms: float) -> None:
        self.llm_ms += latency_ms
        self.llm_calls += 1
