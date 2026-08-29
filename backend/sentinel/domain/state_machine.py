"""Incident lifecycle state machine.

Transitions are explicit. Anything not listed is illegal and raises ``InvalidTransition``.
The graph mirrors the product lifecycle:

    DETECTED → TRIAGING → INVESTIGATING → ROOT_CAUSE_IDENTIFIED → REMEDIATION_PROPOSED
             → AWAITING_HUMAN → RESOLVED → POSTMORTEM → CLOSED

with failure branches:

    INVESTIGATING → INVESTIGATION_FAILED → RETRYING → INVESTIGATING
    INVESTIGATING → LOW_CONFIDENCE → HUMAN_REVIEW → (ROOT_CAUSE_IDENTIFIED | RESOLVED)
"""

from __future__ import annotations

from sentinel.core.errors import InvalidTransition
from sentinel.domain.enums import IncidentStatus as S

TRANSITIONS: dict[S, frozenset[S]] = {
    S.DETECTED: frozenset({S.TRIAGING, S.INVESTIGATING, S.RESOLVED}),
    S.TRIAGING: frozenset({S.INVESTIGATING, S.RESOLVED}),
    S.INVESTIGATING: frozenset(
        {
            S.ROOT_CAUSE_IDENTIFIED,
            S.LOW_CONFIDENCE,
            S.INVESTIGATION_FAILED,
            S.RESOLVED,
        }
    ),
    S.INVESTIGATION_FAILED: frozenset({S.RETRYING, S.HUMAN_REVIEW, S.RESOLVED}),
    S.RETRYING: frozenset({S.INVESTIGATING, S.HUMAN_REVIEW, S.RESOLVED}),
    S.ROOT_CAUSE_IDENTIFIED: frozenset(
        {S.REMEDIATION_PROPOSED, S.AWAITING_HUMAN, S.RESOLVED, S.INVESTIGATING}
    ),
    S.LOW_CONFIDENCE: frozenset({S.HUMAN_REVIEW, S.INVESTIGATING, S.RESOLVED}),
    S.HUMAN_REVIEW: frozenset(
        {S.ROOT_CAUSE_IDENTIFIED, S.INVESTIGATING, S.REMEDIATION_PROPOSED, S.RESOLVED}
    ),
    S.REMEDIATION_PROPOSED: frozenset({S.AWAITING_HUMAN, S.RESOLVED, S.INVESTIGATING}),
    S.AWAITING_HUMAN: frozenset({S.RESOLVED, S.REMEDIATION_PROPOSED, S.INVESTIGATING}),
    S.RESOLVED: frozenset({S.POSTMORTEM, S.CLOSED, S.INVESTIGATING}),
    S.POSTMORTEM: frozenset({S.CLOSED}),
    S.CLOSED: frozenset(),
}

TERMINAL = {S.CLOSED}


def can_transition(current: S | str, target: S | str) -> bool:
    cur, tgt = S(current), S(target)
    return tgt in TRANSITIONS.get(cur, frozenset())


def assert_transition(current: S | str, target: S | str) -> S:
    cur, tgt = S(current), S(target)
    if cur == tgt:
        return tgt
    if not can_transition(cur, tgt):
        raise InvalidTransition(
            f"cannot move incident from {cur} to {tgt}",
            details={"from": cur, "to": tgt, "allowed": sorted(TRANSITIONS.get(cur, ()))},
        )
    return tgt


def allowed_targets(current: S | str) -> list[S]:
    return sorted(TRANSITIONS.get(S(current), frozenset()))
