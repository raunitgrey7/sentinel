# Sentinel — Build Milestones

> Evidence-driven incident intelligence for modern software systems.
> Local-first · self-hosted · API-first · model-agnostic · human-in-the-loop.

This document is the execution plan. Each milestone has a definition of done (DoD).
Milestones are ordered so that the system is runnable end-to-end as early as possible,
and every later milestone adds depth rather than breadth.

## Governing principles (non-negotiable)

1. **The LLM is a component, not the system.** Detection, correlation, clustering,
   scoring and verification are deterministic. The model narrates and ranks over
   evidence it is handed; it never invents evidence.
2. **Every claim cites evidence.** A hypothesis without evidence IDs is rejected by the
   verifier. Evidence IDs are minted by the system, never by the model.
3. **Runs with zero infrastructure.** `sentinel dev` boots API + worker + simulator on
   SQLite and an in-process queue. `docker compose up` swaps in PostgreSQL, Redis,
   Prometheus, Alertmanager, Grafana and Ollama with no code changes.
4. **Recommendation-only by default.** Remediation actions require an explicit human
   approval with RBAC + audit trail before anything executes.
5. **Measure, don't claim.** Accuracy numbers come from the evaluation harness, and
   the harness is part of the repo.

---

## M0 — Repository skeleton & tooling
- Monorepo layout: `backend/` (Python modular monolith), `simulator/` (demo shop),
  `web/` (Next.js), `infrastructure/`, `docs/`, `tests/`.
- `pyproject.toml` (uv), ruff, mypy config, pytest config, Makefile, LICENSE, .gitignore.
- **DoD:** `uv sync` succeeds; `make lint` runs.

## M1 — Foundation: config, DB, auth, projects, services, incidents
- Settings (pydantic-settings) with SQLite/Postgres + in-process/Redis switches.
- SQLAlchemy 2 async models for the full schema (users, api keys, projects, services,
  dependencies, deployments, telemetry, alerts, incidents, investigations, steps,
  evidence, hypotheses, graph nodes/edges, error clusters, remediation, postmortems,
  audit logs, fault experiments, evaluation runs/cases).
- Alembic migration (initial).
- JWT auth, password hashing, API keys, RBAC (ADMIN / SRE / ENGINEER / VIEWER).
- Incident state machine with legal transitions and failure branches.
- FastAPI app: `/health`, `/ready`, `/metrics`, `/api/v1/{auth,projects,services,incidents}`.
- Structured JSON logging, request IDs, error envelope, pagination, API versioning.
- **DoD:** create a project, register services + dependencies, create an incident via API.

## M2 — Telemetry ingestion
- `/api/v1/ingest/{logs,metrics,traces}` with OpenTelemetry-aligned attributes
  (`service.name`, `service.version`, `trace_id`, `span_id`, `deployment.environment`).
- `/api/v1/webhooks/alerts` (Alertmanager format) and `/api/v1/webhooks/deployments`.
- Telemetry query layer (windowed reads for metrics/logs/spans).
- **DoD:** simulator telemetry lands in the store and is queryable.

## M3 — Detection
- Rule engine evaluating windowed metric expressions (`threshold`, `for`, severity).
- Periodic detector job; alert → incident mapping with de-duplication and
  affected-service inference; auto-enqueue investigation.
- **DoD:** an error-rate spike opens an incident without human input.

## M4 — Deterministic investigation
- Durable orchestrator: investigation + steps with checkpointing, retries with backoff,
  timeouts, resume-after-crash, idempotent enqueue.
- Investigators: Timeline, Metrics (baseline deviation / z-score), Logs (template
  mining + burst clustering), Traces (critical path latency), Deployment (Git + change
  proximity), Dependency (blast radius over the service graph), Historical (RAG).
- Evidence model with direction (supports / contradicts) and weights.
- Root-cause catalog + hypothesis generator + explicit scoring function.
- Evidence graph (nodes/edges) persisted and exportable.
- **DoD:** DB-pool-exhaustion fault → ranked hypotheses with evidence, no LLM involved.

## M5 — AI layer
- `LLMProvider` abstraction: `generate`, `structured`, `embed`; `OllamaProvider`,
  `NullProvider` (deterministic narration + hashed embeddings), circuit breaker,
  timeouts, JSON repair + schema validation + retry.
- Root Cause Synthesizer prompt (grounded, evidence-ID citations only, injection-hardened).
- Verification agent: citation validity, contradiction check, calibrated confidence,
  LOW_CONFIDENCE → HUMAN_REVIEW branch.
- Historical retrieval over resolved incidents (signature embeddings, cosine ranking).
- "Why?" grounded Q&A endpoint; postmortem generator with per-claim citations.
- **DoD:** same fault produces narrative + verified confidence; unsupported citations rejected.

## M6 — Simulator (Sentinel Demo Shop) & fault injection
- Services over real HTTP: gateway → auth / order → inventory / payment → (db, redis, queue).
- Every service emits logs, metrics, traces to Sentinel and exposes Prometheus `/metrics`.
- Traffic generator with diurnal noise.
- Fault engine: cpu_saturation, memory_leak, database_latency, db_pool_exhaustion,
  http_500_spike, network_latency, packet_loss, redis_failure, queue_backlog,
  bad_deployment, config_regression, dependency_failure, thread_starvation, deadlock.
- Release manager with synthetic Git history (commits, changed files) → deployment webhook.
- **DoD:** `POST /api/v1/faults` degrades the shop; Sentinel detects and investigates.

## M7 — Remediation & human-in-the-loop
- Playbook-based recommendations per root-cause category.
- Action request → approval (SRE/ADMIN) → guarded execution → verification → audit log.
- Agent tool permission boundaries (read-only tools by default).
- **DoD:** rollback request cannot execute without approval; audit row written.

## M8 — Dashboard (Next.js + TypeScript + Tailwind)
- Overview (active incidents, service health, risk), incident list, incident detail
  (root cause card, evidence / contradicting evidence, timeline, investigator progress,
  hypotheses, evidence graph, "Why?" panel, remediation, postmortem), services & topology,
  chaos lab (fault injection), evaluation dashboard, login.
- **DoD:** the 11-step demo in `docs/demo.md` is executable end-to-end from the UI.

## M9 — Evaluation harness
- Scenario library covering all fault categories with parameter variations (100+ cases).
- Runner: synthesize telemetry → detect → investigate → score against expected root cause.
- Metrics: root-cause accuracy (top-1/top-3), evidence precision, false-positive rate,
  confidence calibration (ECE), investigation latency, inference time.
- Results persisted; `sentinel eval run` CLI; report in Markdown + JSON; UI page.
- **DoD:** `make eval` produces `docs/evaluation/latest.md` with real numbers.

## M10 — Production hardening & delivery
- Retries, backoff, idempotency keys, timeouts, circuit breakers, dead-letter queue,
  graceful shutdown, worker recovery, rate limiting, input validation, audit logs.
- Self-observability: Prometheus metrics for investigation latency, LLM latency/failures,
  queue depth, DB latency; Grafana dashboard; OpenTelemetry export (optional).
- Docker images, `docker-compose.yml` (core + `llm` + `observability` profiles),
  Prometheus/Alertmanager rules, GitHub Actions CI.
- Docs: architecture, ADRs, API, security threat model, runbooks, evaluation methodology,
  deployment guide, demo script, resume/pitch summary.
- Tests: unit, integration, e2e (fault → root cause), chaos.
- **DoD:** `make check` is green; `docker compose up` brings up the full stack.

## Status log
| Milestone | Status | Evidence |
|-----------|--------|----------|
| M0 skeleton & tooling | done | `pyproject.toml`, `uv.lock`, ruff clean, Makefile, CI |
| M1 foundation | done | 27-table schema + Alembic migration, JWT/API keys/RBAC, state machine, error envelope; `tests/integration/test_api.py` |
| M2 telemetry ingestion | done | `/api/v1/ingest/*`, Alertmanager + deployment webhooks, OTel-aligned normaliser |
| M3 detection | done | rule engine, fingerprinted alerts, blast-radius merging; live run opened `INC-2026-0001` from a simulator fault |
| M4 deterministic investigation | done | 7 investigators, catalog, scoring, evidence graph, checkpoint/resume (`test_investigation_resumes_from_checkpoint`) |
| M5 AI layer | done | provider abstraction, Ollama + deterministic narrator + fallback, verifier, RAG, Why?, postmortems |
| M6 simulator & faults | done | 7 services over HTTP, 14 faults, release manager, traffic; `docs/architecture/simulator.md` |
| M7 remediation | done | request/approve/execute/verify with four-eyes + audit; agent tool boundary; `test_remediation.py` |
| M8 dashboard | done | Next.js 16 app, 7 pages, lint/typecheck/build clean |
| M9 evaluation | done | 119 scenarios; latest run 100% top-1, 0% FP, 0.39 s median (`docs/evaluation/latest.md`; first run 96.5% in `full-run1.md`) |
| M10 hardening & delivery | done | resilience primitives, self-metrics, Grafana, compose stack, CI quality gate, docs, 67 tests green |

Not done (deliberately): Kubernetes manifests (ADR-0001), pgvector (ADR-0004), OIDC and
PII redaction (threat model → known gaps). The Docker images could not be built on the
authoring machine (Docker Desktop was not running); the Dockerfiles and compose file are
reviewed but unexecuted.
