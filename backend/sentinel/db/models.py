"""SQLAlchemy 2.0 models — the relational backbone of Sentinel.

Conventions
-----------
* Primary keys are UUID4 hex strings (portable across SQLite/PostgreSQL).
* All timestamps are UTC (``UTCDateTime``).
* JSON columns hold *unstructured* payloads only (labels, attributes, score breakdowns).
  Anything the engine reasons over structurally has its own column.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sentinel.core.ids import new_id
from sentinel.core.timeutil import utcnow
from sentinel.db.base import Base

# --------------------------------------------------------------------------------------
# Identity & tenancy
# --------------------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="VIEWER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(12))
    role: Mapped[str] = mapped_column(String(16), default="ENGINEER")
    scopes: Mapped[list[Any]] = mapped_column(default=list)  # e.g. ["ingest", "webhooks"]
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    environment: Mapped[str] = mapped_column(String(32), default="production")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_service_project_name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32), default="service")  # service|database|cache|queue
    tier: Mapped[str] = mapped_column(String(16), default="standard")  # critical|standard|low
    owner: Mapped[str] = mapped_column(String(128), default="")
    current_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ServiceDependency(Base):
    __tablename__ = "service_dependencies"
    __table_args__ = (UniqueConstraint("project_id", "source", "target", name="uq_dep_edge"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(128))  # caller service name
    target: Mapped[str] = mapped_column(String(128))  # callee service name
    kind: Mapped[str] = mapped_column(String(32), default="http")  # http|db|cache|queue
    critical: Mapped[bool] = mapped_column(Boolean, default=True)


# --------------------------------------------------------------------------------------
# Change events
# --------------------------------------------------------------------------------------


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (Index("ix_deploy_proj_svc_ts", "project_id", "service", "deployed_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    service: Mapped[str] = mapped_column(String(128))
    version: Mapped[str] = mapped_column(String(64))
    previous_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit_message: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(128), default="")
    changed_files: Mapped[list[Any]] = mapped_column(default=list)
    diff_summary: Mapped[str] = mapped_column(Text, default="")
    config_changes: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default="completed")  # started|completed|rolled_back
    deployed_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


# --------------------------------------------------------------------------------------
# Telemetry (OpenTelemetry-aligned)
# --------------------------------------------------------------------------------------


class MetricPoint(Base):
    __tablename__ = "metric_points"
    __table_args__ = (Index("ix_metric_lookup", "project_id", "service", "name", "ts"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32))
    service: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(128))
    labels: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ts: Mapped[datetime] = mapped_column()
    value: Mapped[float] = mapped_column(Float)


class LogRecord(Base):
    __tablename__ = "log_records"
    __table_args__ = (Index("ix_log_lookup", "project_id", "service", "ts"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32))
    service: Mapped[str] = mapped_column(String(128))
    service_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(Text, default="")
    template_hash: Mapped[str] = mapped_column(String(32), default="", index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    span_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ts: Mapped[datetime] = mapped_column()


class Span(Base):
    __tablename__ = "spans"
    __table_args__ = (
        Index("ix_span_lookup", "project_id", "service", "start_ts"),
        Index("ix_span_trace", "trace_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(32))
    trace_id: Mapped[str] = mapped_column(String(64))
    span_id: Mapped[str] = mapped_column(String(32))
    parent_span_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    service: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="internal")  # server|client|internal
    start_ts: Mapped[datetime] = mapped_column()
    duration_ms: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(8), default="ok")  # ok|error
    attributes: Mapped[dict[str, Any]] = mapped_column(default=dict)


# --------------------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------------------


class DetectionRule(Base):
    __tablename__ = "detection_rules"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_rule_name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    metric: Mapped[str] = mapped_column(String(128))
    service: Mapped[str | None] = mapped_column(String(128), nullable=True)  # None → all services
    aggregation: Mapped[str] = mapped_column(String(16), default="avg")  # avg|max|min|last
    comparator: Mapped[str] = mapped_column(String(4), default=">")  # > < >= <=
    threshold: Mapped[float] = mapped_column(Float)
    window_s: Mapped[int] = mapped_column(Integer, default=60)
    for_s: Mapped[int] = mapped_column(Integer, default=30)
    severity: Mapped[str] = mapped_column(String(16), default="HIGH")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_fp", "project_id", "fingerprint"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(128))
    service: Mapped[str] = mapped_column(String(128))
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="firing")
    source: Mapped[str] = mapped_column(String(32), default="sentinel")  # sentinel|alertmanager
    fingerprint: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    labels: Mapped[dict[str, Any]] = mapped_column(default=dict)
    annotations: Mapped[dict[str, Any]] = mapped_column(default=dict)
    fired_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)


# --------------------------------------------------------------------------------------
# Incidents
# --------------------------------------------------------------------------------------


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incident_proj_status", "project_id", "status"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # INC-2026-0087
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="HIGH")
    status: Mapped[str] = mapped_column(String(32), default="DETECTED")
    primary_service: Mapped[str] = mapped_column(String(128))
    affected_services: Mapped[list[Any]] = mapped_column(default=list)
    trigger: Mapped[dict[str, Any]] = mapped_column(default=dict)  # alert payload snapshot
    started_at: Mapped[datetime] = mapped_column(default=utcnow)  # estimated onset
    detected_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    root_cause_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    root_cause_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    signature: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[Any] | None] = mapped_column(nullable=True)
    resolution_notes: Mapped[str] = mapped_column(Text, default="")
    labels: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    investigations: Mapped[list[Investigation]] = relationship(back_populates="incident", cascade="all, delete-orphan")


class IncidentEvent(Base):
    """Timeline entries. ``kind`` is a small vocabulary consumed by the UI."""

    __tablename__ = "incident_events"
    __table_args__ = (Index("ix_event_incident_ts", "incident_id", "ts"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(default=utcnow)
    kind: Mapped[str] = mapped_column(String(32))  # deployment|metric|log|alert|status|investigation|action|note
    message: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    trigger: Mapped[str] = mapped_column(String(32), default="auto")
    llm_provider: Mapped[str] = mapped_column(String(32), default="none")
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_ms: Mapped[float] = mapped_column(Float, default=0.0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)

    incident: Mapped[Incident] = relationship(back_populates="investigations")
    steps: Mapped[list[InvestigationStep]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", order_by="InvestigationStep.order"
    )


class InvestigationStep(Base):
    __tablename__ = "investigation_steps"
    __table_args__ = (UniqueConstraint("investigation_id", "name", name="uq_step_name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128), default="")
    order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    output: Mapped[dict[str, Any]] = mapped_column(default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    investigation: Mapped[Investigation] = relationship(back_populates="steps")


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_incident", "incident_id", "kind"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True)
    ref: Mapped[str] = mapped_column(String(16), index=True)  # short citation handle, e.g. E7
    kind: Mapped[str] = mapped_column(String(16))
    service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(128))  # e.g. metrics:db_connections_active
    summary: Mapped[str] = mapped_column(Text)  # human-readable, citable
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    signals: Mapped[list[Any]] = mapped_column(default=list)  # tags matched by the catalog
    weight: Mapped[float] = mapped_column(Float, default=1.0)  # 0..1 strength
    direction: Mapped[str] = mapped_column(String(16), default="supports")  # about the *incident*
    ts_start: Mapped[datetime | None] = mapped_column(nullable=True)
    ts_end: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    __table_args__ = (Index("ix_hyp_incident_rank", "incident_id", "rank"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"))
    investigation_id: Mapped[str | None] = mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True)
    category: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    culprit_service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)  # raw deterministic score 0..1
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # calibrated after verification
    rank: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="candidate")
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict)
    supporting_evidence: Mapped[list[Any]] = mapped_column(default=list)  # evidence refs
    contradicting_evidence: Mapped[list[Any]] = mapped_column(default=list)
    reasoning: Mapped[str] = mapped_column(Text, default="")  # LLM/narrator explanation
    verification: Mapped[dict[str, Any]] = mapped_column(default=dict)
    remediation: Mapped[list[Any]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ErrorCluster(Base):
    __tablename__ = "error_clusters"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    service: Mapped[str] = mapped_column(String(128))
    level: Mapped[str] = mapped_column(String(16))
    template: Mapped[str] = mapped_column(Text)
    template_hash: Mapped[str] = mapped_column(String(32))
    count: Mapped[int] = mapped_column(Integer)
    baseline_count: Mapped[int] = mapped_column(Integer, default=0)
    burst_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    sample: Mapped[str] = mapped_column(Text, default="")
    first_ts: Mapped[datetime | None] = mapped_column(nullable=True)
    last_ts: Mapped[datetime | None] = mapped_column(nullable=True)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("incident_id", "key", name="uq_graph_node"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(32))  # incident|service|deployment|commit|evidence|hypothesis|alert|cluster|historical
    label: Mapped[str] = mapped_column(String(255))
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(160))
    target: Mapped[str] = mapped_column(String(160))
    relation: Mapped[str] = mapped_column(String(48))  # affects|depends_on|triggered_by|correlated_with|supports|contradicts|resembles|deployed_version|contains
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)


# --------------------------------------------------------------------------------------
# Remediation & reporting
# --------------------------------------------------------------------------------------


class RemediationAction(Base):
    __tablename__ = "remediation_actions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(48))  # rollback|scale|config|restart|alert|manual
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    target_service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    risk: Mapped[str] = mapped_column(String(8), default="medium")
    executable: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_note: Mapped[str] = mapped_column(Text, default="")
    executed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Postmortem(Base):
    __tablename__ = "postmortems"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    sections: Mapped[dict[str, Any]] = mapped_column(default=dict)
    content_md: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list[Any]] = mapped_column(default=list)
    generated_by: Mapped[str] = mapped_column(String(64), default="system")
    generated_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_ts", "ts"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(default=utcnow)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), default="user")  # user|api_key|system|agent
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="success")
    reason: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


# --------------------------------------------------------------------------------------
# Chaos & evaluation
# --------------------------------------------------------------------------------------


class FaultExperiment(Base):
    __tablename__ = "fault_experiments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    target_service: Mapped[str] = mapped_column(String(128))
    fault_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16), default="high")
    duration_s: Mapped[int] = mapped_column(Integer, default=120)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expected_root_cause: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_incident_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="running")
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(default=dict)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True)
    scenario: Mapped[str] = mapped_column(String(128))
    fault_type: Mapped[str] = mapped_column(String(64))
    target_service: Mapped[str] = mapped_column(String(128))
    expected: Mapped[str] = mapped_column(String(64))
    predicted: Mapped[str | None] = mapped_column(String(64), nullable=True)
    top3: Mapped[list[Any]] = mapped_column(default=list)
    correct: Mapped[bool] = mapped_column(Boolean, default=False)
    top3_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_precision: Mapped[float] = mapped_column(Float, default=0.0)
    citation_validity: Mapped[float] = mapped_column(Float, default=0.0)
    detected: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    llm_ms: Mapped[float] = mapped_column(Float, default=0.0)
    incident_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(default=dict)
