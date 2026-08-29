"""Remediation playbooks derived from the root-cause catalog.

Only a small, explicit set of action kinds is *executable* by Sentinel, and only against
targets that expose a control API (today: the simulator's release manager). Everything
else is a recommendation for a human.
"""

from __future__ import annotations

from typing import Any

from sentinel.investigation.catalog import CATALOG

EXECUTABLE_KINDS = {"rollback", "restart", "scale", "clear_fault"}


def actions_for(category: str, *, culprit_service: str | None, latest_deployment: dict[str, Any] | None) -> list[dict[str, Any]]:
    rc = CATALOG.get(category)  # type: ignore[call-overload]
    if rc is None:
        return [
            {
                "kind": "manual",
                "title": "Escalate to on-call for manual investigation",
                "description": "No catalog playbook matched; evidence is attached to the incident.",
                "risk": "low",
                "executable": False,
                "target_service": culprit_service,
                "params": {},
            }
        ]
    out: list[dict[str, Any]] = []
    for step in rc.remediation:
        params: dict[str, Any] = {}
        executable = step.executable and step.kind in EXECUTABLE_KINDS
        if step.kind == "rollback":
            if not latest_deployment:
                executable = False
            else:
                params = {
                    "service": latest_deployment["service"],
                    "from_version": latest_deployment["version"],
                    "to_version": latest_deployment.get("previous_version"),
                    "deployment_id": latest_deployment["id"],
                }
        elif step.kind in ("restart", "scale"):
            params = {"service": culprit_service}
        title = step.title
        if step.kind == "rollback" and latest_deployment:
            title = f"Roll back {latest_deployment['service']} {latest_deployment['version']} → {latest_deployment.get('previous_version') or 'previous'}"
        out.append(
            {
                "kind": step.kind,
                "title": title,
                "description": step.description,
                "risk": step.risk,
                "executable": executable,
                "target_service": params.get("service") or culprit_service,
                "params": params,
            }
        )
    return out
