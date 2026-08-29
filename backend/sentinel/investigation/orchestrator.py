"""Durable investigation orchestrator.

* One ``Investigation`` row per attempt; one ``InvestigationStep`` row per stage.
* Each stage is checkpointed (evidence, notes, timeline, candidates, synthesis) into the
  investigation row after it completes, so a crashed worker resumes from the last
  completed stage instead of restarting.
* Stages have per-step timeouts and bounded retries with backoff. A stage marked
  ``optional`` may fail without failing the investigation (e.g. historical retrieval).
* The whole run is idempotent on ``incident_id``: the job queue de-duplicates by key and
  a completed investigation is not re-run unless explicitly requested.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.core.config import get_settings
from sentinel.core.logging import bind, get_logger, reset
from sentinel.core.timeutil import utcnow
from sentinel.db.models import Investigation, InvestigationStep
from sentinel.domain.enums import IncidentStatus, InvestigationStatus, StepStatus
from sentinel.investigation import hypotheses, persist, synthesizer, verifier
from sentinel.investigation.context import InvestigationContext, Windows
from sentinel.investigation.investigators import (
    dependency,
    deployments,
    historical,
    logs,
    metrics,
    timeline,
    traces,
)
from sentinel.llm import get_provider
from sentinel.observability import metrics as m
from sentinel.services.incidents import add_event, get_incident, transition
from sentinel.services.projects import load_service_graph

log = get_logger(__name__)


@dataclass(frozen=True)
class Stage:
    name: str
    label: str
    run: Callable[[InvestigationContext], Awaitable[dict[str, Any]]]
    optional: bool = False
    timeout_s: float | None = None


STAGES: list[Stage] = [
    Stage(timeline.NAME, timeline.LABEL, timeline.run),
    Stage(metrics.NAME, metrics.LABEL, metrics.run),
    Stage(logs.NAME, logs.LABEL, logs.run),
    Stage(traces.NAME, traces.LABEL, traces.run),
    Stage(deployments.NAME, deployments.LABEL, deployments.run),
    Stage(dependency.NAME, dependency.LABEL, dependency.run),
    Stage(historical.NAME, historical.LABEL, historical.run, optional=True),
    Stage(hypotheses.NAME, hypotheses.LABEL, hypotheses.run),
    Stage(synthesizer.NAME, synthesizer.LABEL, synthesizer.run, timeout_s=240),
    Stage(verifier.NAME, verifier.LABEL, verifier.run, timeout_s=240),
    Stage(persist.NAME, persist.LABEL, persist.run),
]


async def create_investigation(session: AsyncSession, incident_id: str, *, trigger: str = "auto") -> Investigation:
    settings = get_settings()
    provider = get_provider()
    attempt = 1 + len((await session.execute(select(Investigation.id).where(Investigation.incident_id == incident_id))).all())
    inv = Investigation(incident_id=incident_id, status=InvestigationStatus.QUEUED, attempt=attempt, trigger=trigger, llm_provider=settings.llm_provider, llm_model=getattr(provider, "model", None))
    session.add(inv)
    await session.flush()
    for i, st in enumerate(STAGES):
        session.add(InvestigationStep(investigation_id=inv.id, name=st.name, label=st.label, order=i, status=StepStatus.PENDING))
    return inv


async def latest_investigation(session: AsyncSession, incident_id: str) -> Investigation | None:
    stmt = select(Investigation).where(Investigation.incident_id == incident_id).order_by(Investigation.queued_at.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


def _checkpoint(ctx: InvestigationContext, completed: list[str]) -> dict[str, Any]:
    return {
        "completed": completed,
        "evidence": ctx.evidence.to_list(),
        "notes": ctx.notes,
        "timeline": [{**t, "ts": t["ts"].isoformat()} for t in ctx.timeline],
        "candidates": ctx.candidates,
        "synthesis": ctx.synthesis,
        "verification": ctx.verification,
        "scope": ctx.scope_services,
        "llm_ms": ctx.llm_ms,
        "llm_calls": ctx.llm_calls,
    }


def _restore(ctx: InvestigationContext, cp: dict[str, Any]) -> list[str]:
    from datetime import datetime

    ctx.evidence.load(cp.get("evidence", []))
    ctx.notes = cp.get("notes", {})
    ctx.timeline = [{**t, "ts": datetime.fromisoformat(t["ts"])} for t in cp.get("timeline", [])]
    ctx.candidates = cp.get("candidates", [])
    ctx.synthesis = cp.get("synthesis", {})
    ctx.verification = cp.get("verification", {})
    ctx.scope_services = cp.get("scope", ctx.scope_services)
    ctx.llm_ms = float(cp.get("llm_ms", 0.0))
    ctx.llm_calls = int(cp.get("llm_calls", 0))
    return list(cp.get("completed", []))


async def run_investigation(session: AsyncSession, investigation_id: str) -> Investigation:
    """Execute (or resume) an investigation. Commits after every stage."""
    settings = get_settings()
    inv = await session.get(Investigation, investigation_id)
    if inv is None:
        raise ValueError(f"investigation {investigation_id} not found")
    if inv.status == InvestigationStatus.COMPLETED:
        return inv
    incident = await get_incident(session, inv.incident_id)
    token = bind(incident=incident.key, investigation=inv.id)
    started = time.perf_counter()
    try:
        if inv.started_at is None:
            inv.started_at = utcnow()
        inv.status = InvestigationStatus.RUNNING
        if incident.status in (IncidentStatus.DETECTED, IncidentStatus.TRIAGING, IncidentStatus.RETRYING, IncidentStatus.INVESTIGATION_FAILED):
            if incident.status == IncidentStatus.INVESTIGATION_FAILED:
                await transition(session, incident, IncidentStatus.RETRYING)
            await transition(session, incident, IncidentStatus.INVESTIGATING, note=f"attempt {inv.attempt}")
        elif incident.status != IncidentStatus.INVESTIGATING:
            await transition(session, incident, IncidentStatus.INVESTIGATING, note=f"re-investigation (attempt {inv.attempt})")
        await session.commit()

        graph = await load_service_graph(session, incident.project_id)
        now = utcnow()
        onset = incident.started_at
        pad = timedelta(seconds=30)
        windows = Windows(
            baseline_start=onset - pad - timedelta(minutes=settings.baseline_window_min),
            baseline_end=onset - pad,
            incident_start=onset - pad,
            incident_end=now,
            lookback_start=onset - timedelta(minutes=settings.incident_lookback_min),
        )
        ctx = InvestigationContext(session=session, settings=settings, incident=incident, investigation=inv, provider=get_provider(), windows=windows, service_graph=graph)
        downstream = graph.downstream(incident.primary_service)
        ctx.scope_services = [incident.primary_service, *[s for s in incident.affected_services if s != incident.primary_service], *sorted(downstream, key=lambda k: downstream[k])]
        ctx.scope_services = list(dict.fromkeys(ctx.scope_services))
        completed = _restore(ctx, inv.checkpoint) if inv.checkpoint else []
        if completed:
            log.info("resuming investigation", completed=completed)

        steps = {s.name: s for s in (await session.execute(select(InvestigationStep).where(InvestigationStep.investigation_id == inv.id))).scalars().all()}
        for stage in STAGES:
            step = steps[stage.name]
            if stage.name in completed:
                step.status = StepStatus.COMPLETED
                continue
            await _run_stage(ctx, stage, step)
            if step.status == StepStatus.COMPLETED or (step.status == StepStatus.FAILED and stage.optional):
                completed.append(stage.name)
                inv.checkpoint = _checkpoint(ctx, completed)
                inv.llm_ms = ctx.llm_ms
                inv.llm_calls = ctx.llm_calls
                await session.commit()
            else:
                raise RuntimeError(f"stage '{stage.name}' failed: {step.error}")

        inv.status = InvestigationStatus.COMPLETED
        inv.completed_at = utcnow()
        inv.duration_ms = (time.perf_counter() - started) * 1000
        inv.checkpoint = {"completed": completed}  # drop bulky payload once persisted
        await add_event(session, incident.id, "investigation", f"Investigation completed in {inv.duration_ms / 1000:.1f}s ({inv.llm_provider})", investigation_id=inv.id)
        m.INVESTIGATION_LATENCY.observe(inv.duration_ms / 1000)
        await session.commit()
        log.info("investigation completed", duration_ms=round(inv.duration_ms), top=(inv.summary or {}).get("top"))
        return inv
    except Exception as exc:
        await session.rollback()
        inv = await session.get(Investigation, investigation_id)  # type: ignore[assignment]
        incident = await get_incident(session, inv.incident_id)
        inv.status = InvestigationStatus.FAILED
        inv.error = str(exc)[:2000]
        inv.completed_at = utcnow()
        inv.duration_ms = (time.perf_counter() - started) * 1000
        if incident.status == IncidentStatus.INVESTIGATING:
            await transition(session, incident, IncidentStatus.INVESTIGATION_FAILED, note=str(exc)[:200])
        await session.commit()
        log.error("investigation failed", error=str(exc), exc_info=True)
        raise
    finally:
        reset(token)


async def _run_stage(ctx: InvestigationContext, stage: Stage, step: InvestigationStep) -> None:
    settings = ctx.settings
    timeout = stage.timeout_s or settings.investigation_step_timeout_s
    max_attempts = 1 if stage.optional else settings.investigation_max_attempts
    step.status = StepStatus.RUNNING
    step.started_at = utcnow()
    await ctx.session.commit()
    t0 = time.perf_counter()
    for attempt in range(1, max_attempts + 1):
        step.attempts = attempt
        try:
            with m.timed(m.STEP_LATENCY, step=stage.name):
                out = await asyncio.wait_for(stage.run(ctx), timeout=timeout)
            step.output = out
            step.status = StepStatus.COMPLETED
            step.error = None
            m.STEP_OUTCOMES.labels(stage.name, "success").inc()
            break
        except Exception as exc:  # noqa: BLE001
            step.error = f"{type(exc).__name__}: {str(exc)[:500]}"
            m.STEP_OUTCOMES.labels(stage.name, "failure").inc()
            log.warning("stage failed", stage=stage.name, attempt=attempt, error=step.error)
            if attempt < max_attempts:
                await asyncio.sleep(min(5.0, 0.5 * (2 ** (attempt - 1))))
                continue
            step.status = StepStatus.FAILED
            if stage.optional:
                step.output = {"skipped": True, "error": step.error}
                log.info("optional stage skipped", stage=stage.name)
    step.completed_at = utcnow()
    step.duration_ms = (time.perf_counter() - t0) * 1000
