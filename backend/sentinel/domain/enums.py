"""Domain enumerations shared by the DB layer, API schemas and the investigation engine."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    SRE = "SRE"
    ENGINEER = "ENGINEER"
    VIEWER = "VIEWER"


ROLE_RANK = {Role.VIEWER: 0, Role.ENGINEER: 1, Role.SRE: 2, Role.ADMIN: 3}


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class IncidentStatus(StrEnum):
    DETECTED = "DETECTED"
    TRIAGING = "TRIAGING"
    INVESTIGATING = "INVESTIGATING"
    INVESTIGATION_FAILED = "INVESTIGATION_FAILED"
    RETRYING = "RETRYING"
    ROOT_CAUSE_IDENTIFIED = "ROOT_CAUSE_IDENTIFIED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REMEDIATION_PROPOSED = "REMEDIATION_PROPOSED"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    RESOLVED = "RESOLVED"
    POSTMORTEM = "POSTMORTEM"
    CLOSED = "CLOSED"


OPEN_STATUSES = {
    IncidentStatus.DETECTED,
    IncidentStatus.TRIAGING,
    IncidentStatus.INVESTIGATING,
    IncidentStatus.INVESTIGATION_FAILED,
    IncidentStatus.RETRYING,
    IncidentStatus.ROOT_CAUSE_IDENTIFIED,
    IncidentStatus.LOW_CONFIDENCE,
    IncidentStatus.HUMAN_REVIEW,
    IncidentStatus.REMEDIATION_PROPOSED,
    IncidentStatus.AWAITING_HUMAN,
}


class InvestigationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class EvidenceKind(StrEnum):
    METRIC = "metric"
    LOG = "log"
    TRACE = "trace"
    DEPLOYMENT = "deployment"
    DEPENDENCY = "dependency"
    HISTORICAL = "historical"
    CONFIG = "config"
    ALERT = "alert"


class EvidenceDirection(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class HypothesisStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class RemediationStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"
    VERIFIED = "verified"


class RemediationRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FaultStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    CLEARED = "cleared"
    FAILED = "failed"


class AlertStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"


class RootCauseCategory(StrEnum):
    """Canonical root-cause taxonomy. Evaluation scenarios map to exactly one of these."""

    DATABASE_CONNECTION_POOL = "database_connection_pool"
    DATABASE_LATENCY = "database_latency"
    REDIS_UNAVAILABLE = "redis_unavailable"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    CPU_SATURATION = "cpu_saturation"
    DEPLOYMENT_REGRESSION = "deployment_regression"
    NETWORK_LATENCY = "network_latency"
    NETWORK_PACKET_LOSS = "network_packet_loss"
    DEPENDENCY_FAILURE = "dependency_failure"
    QUEUE_BACKLOG = "queue_backlog"
    THREAD_STARVATION = "thread_starvation"
    CONFIG_REGRESSION = "config_regression"
    DEADLOCK = "deadlock"
    UNKNOWN = "unknown"
