"""API request/response models (Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]
    request_id: str | None = None


# ---- auth ---------------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    email: str


class UserOut(ORM):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=256)
    full_name: str = ""
    role: str = "VIEWER"


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    role: str = "ENGINEER"
    scopes: list[str] = Field(default_factory=lambda: ["ingest"])


class ApiKeyOut(ORM):
    id: str
    name: str
    prefix: str
    role: str
    scopes: list[Any]
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


class ApiKeyCreated(ApiKeyOut):
    key: str


# ---- projects / services -----------------------------------------------------------------
class ProjectCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    name: str = Field(min_length=1, max_length=128)
    environment: str = "production"


class ProjectOut(ORM):
    id: str
    slug: str
    name: str
    environment: str
    created_at: datetime


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = "service"
    tier: str = "standard"
    owner: str = ""
    current_version: str | None = None


class ServiceOut(ORM):
    id: str
    project_id: str
    name: str
    kind: str
    tier: str
    owner: str
    current_version: str | None
    created_at: datetime


class DependencyCreate(BaseModel):
    source: str
    target: str
    kind: str = "http"
    critical: bool = True


class DependencyOut(ORM):
    id: str
    source: str
    target: str
    kind: str
    critical: bool


class ServiceHealth(BaseModel):
    name: str
    kind: str
    version: str | None
    healthy: bool
    availability: float
    error_rate: float | None
    p95_ms: float | None
    request_rate: float | None
    open_incidents: int
    last_seen: datetime | None


class TopologyOut(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


# ---- telemetry ingestion -----------------------------------------------------------------
class IngestBatch(BaseModel):
    project: str = Field(description="project slug")
    service: str | None = Field(default=None, description="default service.name for records lacking one")
    records: list[dict[str, Any]] = Field(max_length=5000)


class IngestResult(BaseModel):
    accepted: int
    rejected: int = 0


class DeploymentWebhook(BaseModel):
    project: str
    service: str
    version: str
    previous_version: str | None = None
    commit_sha: str | None = None
    commit_message: str = ""
    author: str = ""
    changed_files: list[str] = Field(default_factory=list)
    diff_summary: str = ""
    config_changes: dict[str, Any] = Field(default_factory=dict)
    status: str = "completed"
    timestamp: datetime | str | float | None = None


class DeploymentOut(ORM):
    id: str
    service: str
    version: str
    previous_version: str | None
    commit_sha: str | None
    commit_message: str
    author: str
    changed_files: list[Any]
    config_changes: dict[str, Any]
    status: str
    deployed_at: datetime


# ---- incidents ---------------------------------------------------------------------------
class IncidentCreate(BaseModel):
    project: str
    title: str = Field(min_length=3, max_length=255)
    primary_service: str
    severity: str = "HIGH"
    description: str = ""
    affected_services: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    investigate: bool = True


class IncidentOut(ORM):
    id: str
    project_id: str
    key: str
    title: str
    description: str
    severity: str
    status: str
    primary_service: str
    affected_services: list[Any]
    started_at: datetime
    detected_at: datetime
    resolved_at: datetime | None
    root_cause_category: str | None
    root_cause_summary: str | None
    confidence: float | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class IncidentTransition(BaseModel):
    status: str
    note: str = ""


class IncidentResolve(BaseModel):
    notes: str = ""
    root_cause_category: str | None = None


class EventOut(ORM):
    id: str
    ts: datetime
    kind: str
    message: str
    actor: str
    data: dict[str, Any]


class EvidenceOut(ORM):
    id: str
    ref: str
    kind: str
    service: str | None
    source: str
    summary: str
    detail: dict[str, Any]
    signals: list[Any]
    weight: float
    direction: str
    ts_start: datetime | None
    ts_end: datetime | None


class HypothesisOut(ORM):
    id: str
    category: str
    title: str
    description: str
    culprit_service: str | None
    score: float
    confidence: float
    rank: int
    status: str
    score_breakdown: dict[str, Any]
    supporting_evidence: list[Any]
    contradicting_evidence: list[Any]
    reasoning: str
    verification: dict[str, Any]
    remediation: list[Any]


class StepOut(ORM):
    name: str
    label: str
    order: int
    status: str
    attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: float | None
    output: dict[str, Any]
    error: str | None


class InvestigationOut(ORM):
    id: str
    incident_id: str
    status: str
    attempt: int
    trigger: str
    llm_provider: str
    llm_model: str | None
    summary: dict[str, Any]
    error: str | None
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: float | None
    llm_ms: float
    llm_calls: int
    steps: list[StepOut] = Field(default_factory=list)


class ErrorClusterOut(ORM):
    id: str
    service: str
    level: str
    template: str
    count: int
    baseline_count: int
    burst_ratio: float
    sample: str
    first_ts: datetime | None
    last_ts: datetime | None


class WhyRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    hypothesis_id: str | None = None


class RemediationOut(ORM):
    id: str
    incident_id: str
    kind: str
    title: str
    description: str
    target_service: str | None
    params: dict[str, Any]
    risk: str
    executable: bool
    status: str
    requested_by: str | None
    approved_by: str | None
    approval_note: str
    executed_at: datetime | None
    result: dict[str, Any]
    created_at: datetime


class RemediationDecision(BaseModel):
    note: str = ""


class PostmortemOut(ORM):
    id: str
    incident_id: str
    version: int
    sections: dict[str, Any]
    content_md: str
    citations: list[Any]
    generated_by: str
    generated_at: datetime


class AlertOut(ORM):
    id: str
    rule_name: str
    service: str
    severity: str
    status: str
    source: str
    value: float | None
    fired_at: datetime
    resolved_at: datetime | None
    incident_id: str | None


class RuleOut(ORM):
    id: str
    name: str
    description: str
    metric: str
    service: str | None
    aggregation: str
    comparator: str
    threshold: float
    window_s: int
    for_s: int
    severity: str
    enabled: bool


class RuleCreate(BaseModel):
    name: str
    description: str = ""
    metric: str
    service: str | None = None
    aggregation: str = "avg"
    comparator: str = ">"
    threshold: float
    window_s: int = 60
    for_s: int = 30
    severity: str = "HIGH"
    enabled: bool = True


# ---- faults ------------------------------------------------------------------------------
class FaultCreate(BaseModel):
    project: str = "demo-shop"
    target: str
    fault: str
    duration_s: int = Field(default=120, ge=5, le=3600)
    severity: str = "high"
    params: dict[str, Any] = Field(default_factory=dict)


class FaultOut(ORM):
    id: str
    target_service: str
    fault_type: str
    severity: str
    duration_s: int
    params: dict[str, Any]
    status: str
    expected_root_cause: str | None
    linked_incident_id: str | None
    created_by: str
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime


# ---- audit / evaluation / system ---------------------------------------------------------
class AuditOut(ORM):
    id: str
    ts: datetime
    actor_id: str | None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    reason: str
    detail: dict[str, Any]


class EvaluationRunOut(ORM):
    id: str
    name: str
    status: str
    config: dict[str, Any]
    summary: dict[str, Any]
    started_at: datetime
    completed_at: datetime | None


class EvaluationCaseOut(ORM):
    id: str
    scenario: str
    fault_type: str
    target_service: str
    expected: str
    predicted: str | None
    top3: list[Any]
    correct: bool
    top3_correct: bool
    confidence: float
    evidence_precision: float
    citation_validity: float
    detected: bool
    latency_ms: float
    llm_ms: float
    incident_id: str | None


class OverviewOut(BaseModel):
    status: str
    open_incidents: int
    services: int
    healthy_services: int
    risk: str
    llm: dict[str, Any]
    queue: dict[str, Any]
    active_faults: int
    latest_evaluation: dict[str, Any] | None
