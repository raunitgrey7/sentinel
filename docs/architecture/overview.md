# Architecture overview

Sentinel is a **local-first incident investigation platform**. It ingests telemetry
(logs, metrics, traces), change events (deployments, commits, configuration) and alerts;
detects incidents deterministically; runs a durable, multi-stage investigation; and
produces evidence-backed root-cause hypotheses, remediation proposals and postmortems.

The governing design decision: **the LLM is one component inside a deterministic
system, and the system never trusts it blindly.**

```
Reality → Telemetry → Normalisation → Detection → Correlation → Evidence graph
        → Candidate hypotheses (catalog + scoring) → LLM narration → Verification
        → Calibrated confidence → Human decision → (approved) action → Verification
```

## Components

| Component | Location | Responsibility |
|---|---|---|
| API | `backend/sentinel/api` | FastAPI app: auth, RBAC, projects, ingestion, incidents, chaos lab, evaluation, `/health`, `/ready`, `/metrics` |
| Telemetry | `backend/sentinel/telemetry` | OpenTelemetry-aligned normalisation, log template mining, windowed queries |
| Detection | `backend/sentinel/detection` | Rule engine over metrics (sustained threshold + `for`), Alertmanager webhook mapping, blast-radius incident merging |
| Analysis | `backend/sentinel/analysis` | Dependency-free statistics (baseline deviation, z-score, percentiles), service dependency graph |
| Investigation | `backend/sentinel/investigation` | Durable orchestrator, seven investigators, root-cause catalog, explicit scoring, synthesizer, verifier, evidence graph, persistence |
| LLM | `backend/sentinel/llm` | `LLMProvider` protocol, Ollama provider (circuit breaker, JSON repair, retries), deterministic `NullProvider`, injection-hardened prompts |
| Retrieval | `backend/sentinel/retrieval` | Incident signatures, embeddings (hashed fallback / Ollama), cosine retrieval over resolved incidents |
| Remediation | `backend/sentinel/remediation` | Playbooks, request → approve → execute → verify workflow, agent tool permission boundary |
| Reporting | `backend/sentinel/reporting` | Grounded "Why?" answers, postmortems with per-section citations |
| Queue / worker | `backend/sentinel/queue`, `worker` | Job abstraction with in-process and Redis/ARQ backends; retries, backoff, DLQ; scheduler |
| Observability | `backend/sentinel/observability` | Prometheus metrics for HTTP, DB, queue, investigation stages, LLM |
| Evaluation | `backend/sentinel/evaluation` | Synthetic scenario library (100+ cases) and benchmark runner |
| Simulator | `simulator/sentinel_sim` | Seven-service demo shop over real HTTP, fault engine, release manager, traffic generator |
| Web | `web/` | Next.js dashboard |

## Deployment shapes

* **Zero infrastructure** — `sentinel dev`: SQLite, in-process queue + scheduler inside
  the API process, deterministic narrator. Used for development, CI and the evaluation
  harness.
* **Full stack** — `docker compose up`: PostgreSQL, Redis, separate worker (ARQ),
  simulator, web; `--profile observability` adds Prometheus/Alertmanager/Grafana/OTel
  collector; `--profile llm` adds Ollama.

No code path changes between the two — only `SENTINEL_*` settings.

## Data flow for one incident

1. Simulator services push metrics/logs/spans every 5 s to `/api/v1/ingest/*` (API key
   with `ingest` scope). Deployments arrive on `/api/v1/webhooks/deployments`.
2. The scheduler enqueues a `detector_tick` every 10 s. The detector evaluates every rule
   over the trailing window per service. A rule that is satisfied continuously for `for_s`
   creates an `Alert` (fingerprinted, idempotent).
3. The alert is attached to an open incident if one exists for the same service, for an
   upstream caller (symptom) or for a downstream callee (which then becomes the primary
   suspect). Otherwise a new incident is created with `started_at` set to the first
   threshold crossing, and an `investigate_incident` job is enqueued (idempotent per
   incident, delayed 1 s so the creating transaction commits first).
4. The orchestrator runs eleven stages, checkpointing after each one:
   timeline → metrics → logs → traces → deployments → dependency → historical →
   hypotheses → synthesis → verification → persist.
5. The incident lands in `REMEDIATION_PROPOSED` (confidence ≥ threshold and verified) or
   `HUMAN_REVIEW` (otherwise). Evidence, hypotheses, graph, error clusters, timeline and
   playbook actions are persisted.
6. Humans use the dashboard: read the evidence, ask "Why?", request/approve an action,
   resolve, generate the postmortem.

See `investigation-pipeline.md` for the stages and `../adr/` for the decisions.
