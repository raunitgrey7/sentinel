"""Human-in-the-loop remediation: nothing executes without approval; everything is audited."""

import pytest

from sentinel.core.errors import Conflict, Forbidden
from sentinel.db.models import RemediationAction
from sentinel.db.session import session_scope
from sentinel.remediation import service as rem
from sentinel.services import audit
from sentinel.services.incidents import create_incident
from sentinel.services.projects import ensure_project

pytestmark = pytest.mark.integration


class FakeAdapter:
    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, action: RemediationAction) -> dict:
        self.executed.append(action.kind)
        return {"ok": True}

    async def verify(self, action: RemediationAction) -> dict:
        return {"ok": True}


async def _action() -> tuple[str, str]:
    async with session_scope() as s:
        p = await ensure_project(s, "rem-test")
        inc = await create_incident(s, project_id=p.id, title="t", primary_service="payment-service")
        a = RemediationAction(incident_id=inc.id, kind="rollback", title="Roll back", executable=True, target_service="payment-service", params={"service": "payment-service", "to_version": "2.8.0"})
        s.add(a)
        await s.flush()
        return inc.id, a.id


async def test_execute_requires_approval_and_role(db):
    _, aid = await _action()
    adapter = FakeAdapter()
    async with session_scope() as s:
        a = await rem.get_action(s, aid)
        with pytest.raises(Conflict):
            await rem.execute(s, a, adapter, actor_id="sre1", role="SRE")
        with pytest.raises(Forbidden):
            await rem.approve(s, a, actor_id="eng1", role="ENGINEER")
    assert adapter.executed == []


async def test_four_eyes_and_full_flow_is_audited(db):
    _inc_id, aid = await _action()
    adapter = FakeAdapter()
    async with session_scope() as s:
        a = await rem.get_action(s, aid)
        await rem.request(s, a, actor_id="sre1", role="SRE", note="please")
        with pytest.raises(Forbidden):  # requester cannot approve their own request
            await rem.approve(s, a, actor_id="sre1", role="SRE")
        await rem.approve(s, a, actor_id="sre2", role="SRE", note="ok")
        assert a.status == "approved" and a.approved_by == "sre2"
        await rem.execute(s, a, adapter, actor_id="sre2", role="SRE")
        assert a.status == "verified" and adapter.executed == ["rollback"]
    async with session_scope() as s:
        rows = await audit.recent(s, resource_id=aid)
        actions = [r.action for r in rows]
        assert {"remediation.request", "remediation.approve", "remediation.execute"} <= set(actions)


async def test_agents_cannot_execute_privileged_tools(db):
    _, aid = await _action()
    async with session_scope() as s:
        a = await rem.get_action(s, aid)
        await rem.approve(s, a, actor_id="sre2", role="SRE")
        with pytest.raises(Forbidden):
            await rem.execute(s, a, FakeAdapter(), actor_id="agent", role="SRE")
    assert rem.AGENT_TOOL_PERMISSIONS["rollback"] is False and rem.AGENT_TOOL_PERMISSIONS["read_logs"] is True


async def test_advisory_actions_cannot_execute(db):
    async with session_scope() as s:
        p = await ensure_project(s, "rem-test-2")
        inc = await create_incident(s, project_id=p.id, title="t", primary_service="x")
        a = RemediationAction(incident_id=inc.id, kind="manual", title="Look at it", executable=False)
        s.add(a)
        await s.flush()
        await rem.approve(s, a, actor_id="sre2", role="ADMIN")
        with pytest.raises(Conflict):
            await rem.execute(s, a, FakeAdapter(), actor_id="sre2", role="ADMIN")
