from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from sentinel.api.deps import DB, Sre, Viewer
from sentinel.api.schemas import EvaluationCaseOut, EvaluationRunOut
from sentinel.core.errors import NotFound
from sentinel.db.models import EvaluationCase, EvaluationRun
from sentinel.evaluation.scenarios import SCENARIOS

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/scenarios")
async def scenarios(_: Viewer) -> list[dict[str, Any]]:
    return [{"name": s.name, "fault_type": s.fault_type, "target": s.target, "expected": s.expected, "variant": s.variant} for s in SCENARIOS]


@router.get("/runs", response_model=list[EvaluationRunOut])
async def runs(_: Viewer, session: DB, limit: int = 20) -> list[EvaluationRun]:
    return list((await session.execute(select(EvaluationRun).order_by(EvaluationRun.started_at.desc()).limit(limit))).scalars().all())


@router.get("/runs/latest", response_model=EvaluationRunOut)
async def latest(_: Viewer, session: DB) -> EvaluationRun:
    row = (await session.execute(select(EvaluationRun).where(EvaluationRun.status == "completed").order_by(EvaluationRun.completed_at.desc()).limit(1))).scalar_one_or_none()
    if row is None:
        raise NotFound("no completed evaluation run")
    return row


@router.get("/runs/{run_id}", response_model=EvaluationRunOut)
async def run_detail(run_id: str, _: Viewer, session: DB) -> EvaluationRun:
    row = await session.get(EvaluationRun, run_id)
    if row is None:
        raise NotFound("run not found")
    return row


@router.get("/runs/{run_id}/cases", response_model=list[EvaluationCaseOut])
async def run_cases(run_id: str, _: Viewer, session: DB) -> list[EvaluationCase]:
    return list((await session.execute(select(EvaluationCase).where(EvaluationCase.run_id == run_id).order_by(EvaluationCase.scenario))).scalars().all())


@router.post("/runs", status_code=202)
async def start_run(_: Sre, background: BackgroundTasks, limit: int | None = None, name: str = "api") -> dict[str, Any]:
    from sentinel.evaluation.runner import run_evaluation

    async def _go() -> None:
        await run_evaluation(name=name, limit=limit)

    background.add_task(_go)
    return {"queued": True, "scenarios": limit or len(SCENARIOS)}
