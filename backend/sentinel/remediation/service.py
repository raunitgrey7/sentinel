"""Human-in-the-loop remediation workflow.

    proposed → approved (SRE/ADMIN) → executing → executed → verified
                      ↘ rejected                ↘ failed

Sentinel never executes an action that has not been explicitly approved by a human with
the right role, and every state change is audited. Execution is delegated to a *target
adapter*; today the only adapter is the simulator's release manager (rollback / restart /
scale / clear_fault). Real-world adapters (Kubernetes, Argo, feature-flag services) plug
in behind the same interface.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.core.errors import Conflict, Forbidden, NotFound
from sentinel.core.timeutil import utcnow
from sentinel.db.models import RemediationAction
from sentinel.domain.enums import ROLE_RANK, RemediationStatus, Role
from sentinel.services import audit
from sentinel.services.incidents import add_event


class TargetAdapter(Protocol):
    async def execute(self, action: RemediationAction) -> dict[str, Any]: ...

    async def verify(self, action: RemediationAction) -> dict[str, Any]: ...


# Tool permission boundary for automated agents: read-only unless explicitly granted.
AGENT_TOOL_PERMISSIONS: dict[str, bool] = {
    "read_logs": True,
    "read_metrics": True,
    "read_traces": True,
    "read_git": True,
    "read_incidents": True,
    "restart_service": False,
    "rollback": False,
    "scale": False,
    "clear_fault": False,
}


def _require_role(role: str, minimum: Role) -> None:
    if ROLE_RANK[Role(role)] < ROLE_RANK[minimum]:
        raise Forbidden(f"role {role} may not perform this action (requires {minimum})")


async def get_action(session: AsyncSession, action_id: str) -> RemediationAction:
    a = await session.get(RemediationAction, action_id)
    if a is None:
        raise NotFound(f"remediation action {action_id} not found")
    return a


async def request(session: AsyncSession, action: RemediationAction, *, actor_id: str, role: str, note: str = "") -> RemediationAction:
    """An ENGINEER (or above) can *request* that an action be considered."""
    _require_role(role, Role.ENGINEER)
    if action.status != RemediationStatus.PROPOSED:
        raise Conflict(f"action is {action.status}, expected proposed")
    action.requested_by = actor_id
    action.approval_note = note
    await audit.record(session, action="remediation.request", resource_type="remediation_action", resource_id=action.id, actor_id=actor_id, reason=note, detail={"kind": action.kind, "target": action.target_service})
    await add_event(session, action.incident_id, "action", f"Remediation requested: {action.title}", actor=actor_id, action_id=action.id)
    return action


async def approve(session: AsyncSession, action: RemediationAction, *, actor_id: str, role: str, note: str = "") -> RemediationAction:
    _require_role(role, Role.SRE)
    if action.status not in (RemediationStatus.PROPOSED,):
        raise Conflict(f"action is {action.status}, expected proposed")
    if action.requested_by and action.requested_by == actor_id and role != Role.ADMIN:
        raise Forbidden("the requester cannot approve their own action (four-eyes principle)")
    action.status = RemediationStatus.APPROVED
    action.approved_by = actor_id
    action.approval_note = note or action.approval_note
    await audit.record(session, action="remediation.approve", resource_type="remediation_action", resource_id=action.id, actor_id=actor_id, reason=note, detail={"kind": action.kind, "params": action.params})
    await add_event(session, action.incident_id, "action", f"Remediation approved: {action.title}", actor=actor_id, action_id=action.id)
    return action


async def reject(session: AsyncSession, action: RemediationAction, *, actor_id: str, role: str, note: str = "") -> RemediationAction:
    _require_role(role, Role.SRE)
    if action.status not in (RemediationStatus.PROPOSED, RemediationStatus.APPROVED):
        raise Conflict(f"action is {action.status}")
    action.status = RemediationStatus.REJECTED
    action.approval_note = note
    await audit.record(session, action="remediation.reject", resource_type="remediation_action", resource_id=action.id, actor_id=actor_id, reason=note)
    await add_event(session, action.incident_id, "action", f"Remediation rejected: {action.title}", actor=actor_id, action_id=action.id)
    return action


async def execute(session: AsyncSession, action: RemediationAction, adapter: TargetAdapter, *, actor_id: str, role: str) -> RemediationAction:
    """Execute an approved, executable action through the adapter, then verify."""
    _require_role(role, Role.SRE)
    if action.status != RemediationStatus.APPROVED:
        raise Conflict("action must be approved before execution")
    if not action.executable:
        raise Conflict("this action is advisory only and cannot be executed by Sentinel")
    if not AGENT_TOOL_PERMISSIONS.get(action.kind, False) and actor_id == "agent":
        raise Forbidden(f"agents are not permitted to execute '{action.kind}'")
    action.status = RemediationStatus.EXECUTING
    await session.flush()
    try:
        result = await adapter.execute(action)
        action.result = {"execute": result}
        action.executed_at = utcnow()
        action.status = RemediationStatus.EXECUTED
        outcome = "success"
    except Exception as exc:  # noqa: BLE001
        action.result = {"error": str(exc)[:500]}
        action.status = RemediationStatus.FAILED
        outcome = "failure"
    await audit.record(session, action="remediation.execute", resource_type="remediation_action", resource_id=action.id, actor_id=actor_id, outcome=outcome, detail={"kind": action.kind, "params": action.params, "result": action.result})
    await add_event(session, action.incident_id, "action", f"Remediation {'executed' if outcome == 'success' else 'FAILED'}: {action.title}", actor=actor_id, action_id=action.id, result=action.result)
    if outcome == "success":
        try:
            verification = await adapter.verify(action)
            action.result["verify"] = verification
            if verification.get("ok"):
                action.status = RemediationStatus.VERIFIED
                await add_event(session, action.incident_id, "action", f"Remediation verified: {action.title}", actor="system", action_id=action.id)
        except Exception as exc:  # noqa: BLE001
            action.result["verify"] = {"ok": False, "error": str(exc)[:300]}
    return action
