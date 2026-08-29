import pytest

from sentinel.core.errors import InvalidTransition
from sentinel.domain.enums import IncidentStatus as S
from sentinel.domain.state_machine import (
    TRANSITIONS,
    allowed_targets,
    assert_transition,
    can_transition,
)


def test_happy_path():
    path = [S.DETECTED, S.TRIAGING, S.INVESTIGATING, S.ROOT_CAUSE_IDENTIFIED, S.REMEDIATION_PROPOSED, S.AWAITING_HUMAN, S.RESOLVED, S.POSTMORTEM, S.CLOSED]
    for a, b in zip(path, path[1:], strict=False):
        assert can_transition(a, b), f"{a} → {b}"


def test_failure_branch_and_retry():
    assert can_transition(S.INVESTIGATING, S.INVESTIGATION_FAILED)
    assert can_transition(S.INVESTIGATION_FAILED, S.RETRYING)
    assert can_transition(S.RETRYING, S.INVESTIGATING)


def test_low_confidence_branch():
    assert can_transition(S.INVESTIGATING, S.LOW_CONFIDENCE)
    assert can_transition(S.LOW_CONFIDENCE, S.HUMAN_REVIEW)
    assert can_transition(S.HUMAN_REVIEW, S.ROOT_CAUSE_IDENTIFIED)


def test_illegal_transition_raises():
    with pytest.raises(InvalidTransition) as exc:
        assert_transition(S.DETECTED, S.POSTMORTEM)
    assert exc.value.details["from"] == S.DETECTED
    assert S.INVESTIGATING in exc.value.details["allowed"]


def test_closed_is_terminal():
    assert allowed_targets(S.CLOSED) == []
    assert not can_transition(S.CLOSED, S.RESOLVED)


def test_same_state_is_noop():
    assert assert_transition(S.INVESTIGATING, S.INVESTIGATING) == S.INVESTIGATING


def test_every_status_has_entry():
    assert set(TRANSITIONS) == set(S)
