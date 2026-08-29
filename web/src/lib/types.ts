export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Overview {
  status: "HEALTHY" | "DEGRADED";
  open_incidents: number;
  services: number;
  healthy_services: number;
  risk: "LOW" | "MEDIUM" | "HIGH";
  llm: { provider: string; model: string; circuit?: { state: string }; last_used?: string; fallback?: string };
  queue: { backend: string; depth: number };
  active_faults: number;
  latest_evaluation: EvaluationSummary | null;
}

export interface ServiceHealth {
  name: string;
  kind: string;
  version: string | null;
  healthy: boolean;
  availability: number;
  error_rate: number | null;
  p95_ms: number | null;
  request_rate: number | null;
  open_incidents: number;
  last_seen: string | null;
}

export interface Topology {
  nodes: { id: string; kind: string }[];
  edges: { source: string; target: string }[];
}

export interface Deployment {
  id: string;
  service: string;
  version: string;
  previous_version: string | null;
  commit_sha: string | null;
  commit_message: string;
  author: string;
  changed_files: string[];
  config_changes: Record<string, string>;
  status: string;
  deployed_at: string;
}

export type IncidentStatus =
  | "DETECTED"
  | "TRIAGING"
  | "INVESTIGATING"
  | "INVESTIGATION_FAILED"
  | "RETRYING"
  | "ROOT_CAUSE_IDENTIFIED"
  | "LOW_CONFIDENCE"
  | "HUMAN_REVIEW"
  | "REMEDIATION_PROPOSED"
  | "AWAITING_HUMAN"
  | "RESOLVED"
  | "POSTMORTEM"
  | "CLOSED";

export interface Incident {
  id: string;
  key: string;
  title: string;
  description: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
  status: IncidentStatus;
  primary_service: string;
  affected_services: string[];
  started_at: string;
  detected_at: string;
  resolved_at: string | null;
  root_cause_category: string | null;
  root_cause_summary: string | null;
  confidence: number | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface IncidentEvent {
  id: string;
  ts: string;
  kind: string;
  message: string;
  actor: string;
  data: Record<string, unknown>;
}

export interface Evidence {
  id: string;
  ref: string;
  kind: "metric" | "log" | "trace" | "deployment" | "dependency" | "historical" | "config" | "alert";
  service: string | null;
  source: string;
  summary: string;
  detail: Record<string, unknown>;
  signals: string[];
  weight: number;
  direction: "supports" | "contradicts" | "neutral";
  ts_start: string | null;
  ts_end: string | null;
}

export interface Verification {
  supported: boolean;
  issues: string[];
  supporting: string[];
  contradicting: string[];
  evidence_kinds: string[];
  citation_validity: number;
  contradiction_penalty: number;
  confidence: number;
  model_confidence: number | null;
  model_issues?: string[];
}

export interface Hypothesis {
  id: string;
  category: string;
  title: string;
  description: string;
  culprit_service: string | null;
  score: number;
  confidence: number;
  rank: number;
  status: string;
  score_breakdown: Record<string, number>;
  supporting_evidence: string[];
  contradicting_evidence: string[];
  reasoning: string;
  verification: Verification;
  remediation: { kind: string; title: string; description: string; risk: string; executable: boolean }[];
}

export interface Step {
  name: string;
  label: string;
  order: number;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "SKIPPED";
  attempts: number;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  output: Record<string, unknown>;
  error: string | null;
}

export interface Investigation {
  id: string;
  incident_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  attempt: number;
  trigger: string;
  llm_provider: string;
  llm_model: string | null;
  summary: Record<string, unknown> & { synthesis?: { summary?: string; caveats?: string[]; provider?: string; model?: string } };
  error: string | null;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  llm_ms: number;
  llm_calls: number;
  steps: Step[];
}

export interface ErrorCluster {
  id: string;
  service: string;
  level: string;
  template: string;
  count: number;
  baseline_count: number;
  burst_ratio: number;
  sample: string;
  first_ts: string | null;
  last_ts: string | null;
}

export interface Graph {
  nodes: { key: string; type: string; label: string; data: Record<string, unknown> }[];
  edges: { source: string; target: string; relation: string; weight: number }[];
}

export interface WhyAnswer {
  answer: string;
  conclusion: string;
  supporting: string[];
  counter_evidence: string[];
  invalid_citations_dropped: number;
  hypothesis: { id: string; title: string; category: string; confidence: number; score_breakdown: Record<string, number> };
  evidence: Evidence[];
  provider: string;
  model: string;
  latency_ms: number;
}

export interface Remediation {
  id: string;
  incident_id: string;
  kind: string;
  title: string;
  description: string;
  target_service: string | null;
  params: Record<string, unknown>;
  risk: "low" | "medium" | "high";
  executable: boolean;
  status: "proposed" | "approved" | "rejected" | "executing" | "executed" | "failed" | "verified";
  requested_by: string | null;
  approved_by: string | null;
  approval_note: string;
  executed_at: string | null;
  result: Record<string, unknown>;
  created_at: string;
}

export interface Postmortem {
  id: string;
  version: number;
  sections: { sections: { title: string; body: string; citations: string[] }[] };
  content_md: string;
  citations: string[];
  generated_by: string;
  generated_at: string;
}

export interface Fault {
  id: string;
  target_service: string;
  fault_type: string;
  severity: string;
  duration_s: number;
  params: Record<string, unknown>;
  status: "pending" | "active" | "cleared" | "failed";
  expected_root_cause: string | null;
  linked_incident_id: string | null;
  created_by: string;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

export type FaultCatalog = Record<string, { expected: string; description: string }>;

export interface EvaluationSummary {
  cases: number;
  fault_cases: number;
  control_cases: number;
  detection_rate: number;
  root_cause_accuracy: number;
  root_cause_top3_accuracy: number;
  evidence_precision: number;
  citation_validity: number;
  false_positive_rate: number;
  confident_wrong_rate: number;
  ece: number;
  median_investigation_ms: number;
  p95_investigation_ms: number;
  mean_detection_gap_s: number | null;
  mean_llm_ms: number;
  per_fault: Record<string, { cases: number; correct: number; top3: number; detected: number; accuracy: number; top3_accuracy: number; mean_confidence: number }>;
  confusion: Record<string, Record<string, number>>;
  confidence_threshold: number;
  wall_time_s?: number;
  llm_provider?: string;
  model?: string;
  run_id?: string;
  completed_at?: string;
}

export interface EvaluationRun {
  id: string;
  name: string;
  status: string;
  config: Record<string, unknown>;
  summary: EvaluationSummary;
  started_at: string;
  completed_at: string | null;
}

export interface EvaluationCase {
  id: string;
  scenario: string;
  fault_type: string;
  target_service: string;
  expected: string;
  predicted: string | null;
  top3: string[];
  correct: boolean;
  top3_correct: boolean;
  confidence: number;
  evidence_precision: number;
  citation_validity: number;
  detected: boolean;
  latency_ms: number;
  llm_ms: number;
  incident_id: string | null;
}

export interface AuditEntry {
  id: string;
  ts: string;
  actor_id: string | null;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: string;
  reason: string;
  detail: Record<string, unknown>;
}
