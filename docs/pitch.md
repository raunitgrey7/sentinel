# Sentinel — pitch & resume notes

## The one-paragraph pitch

Every engineering team already has monitoring that says *"payment-service is unhealthy."*
Nobody has a system that says *why* — and can prove it. Sentinel is a self-hosted incident
investigation platform that turns logs, metrics, traces, deployments and Git history into
an evidence graph, ranks root-cause hypotheses with an explicit, inspectable score, lets a
local model narrate them, and then **verifies the model's claims against the evidence
before reporting a confidence**. Recommendations require human approval; every action is
audited. It runs on a laptop with zero cloud dependencies and no API keys, and it ships with
a benchmark of 119 synthetic production failures on which it names the right root cause
100% of the time (first iteration 96.5%) with 0% false positives and a median investigation
time of 0.39 seconds.

## What makes it defensible

1. **Deterministic core, model at the edge.** Detection, correlation, clustering, scoring
   and verification are code with unit tests. The model can only narrate and cite
   system-minted evidence handles; a verifier discards anything else and re-derives
   confidence. Accuracy is a property of the pipeline and reproducible in CI.
2. **Evidence, contradictions, caveats.** The UI shows what supports a hypothesis, what
   contradicts it, and why the confidence is *not* higher. Engineers can challenge it
   ("Why not CPU saturation?") and get a cited answer.
3. **Local-first by design.** Incident data is the most sensitive data a company has.
   Nothing leaves the host; the model is Ollama on localhost; the fallback is a
   deterministic narrator. The same code runs on SQLite + in-process queue and on
   PostgreSQL + Redis + workers.
4. **Human-in-the-loop remediation** with four-eyes approval, agent tool permission
   boundaries and a full audit trail — the opposite of "AI rolled back production."
5. **Measured.** A scenario library with ground truth, healthy controls, confounders and
   noise; metrics for accuracy, evidence precision, citation validity, false positives,
   confident-wrong rate, calibration and latency; a CI quality gate.

## Demo in one line

Inject a database connection-pool exhaustion into a seven-service shop; watch the error
cascade; Sentinel opens one incident (not three), re-points the primary suspect to the
deepest failing service, ranks *pool exhaustion* first with metric, log and trace evidence,
lists the CPU-stayed-flat contradiction, proposes a rollback that an SRE must approve, and
writes the postmortem with citations.

## Where it goes next

* Adapters for real targets (Kubernetes rollouts, Argo, feature flags) behind the existing
  `TargetAdapter` interface.
* PII redaction at ingestion; per-service ingestion credentials; OIDC.
* pgvector for retrieval at scale; learned (rather than hand-weighted) scoring once
  real incident labels exist.
* A model-lift study: rerun the benchmark with `qwen2.5:7b` / larger local models and
  report citation validity and reordering gains honestly.

---

## Resume entry

**Sentinel — AI Incident Investigation & Response Platform** (open source)
Python · FastAPI · PostgreSQL · Redis · SQLAlchemy · Alembic · OpenTelemetry · Prometheus ·
Grafana · Docker · Next.js/TypeScript · Ollama (local LLMs)

* Built a self-hosted, local-first platform that correlates logs, metrics, distributed
  traces, deployments and Git history into an evidence graph and identifies
  evidence-backed root causes across a multi-service system; every AI claim cites
  system-minted evidence and is re-verified before a calibrated confidence is reported.
* Designed a durable multi-stage investigation runtime (checkpointed, resumable, retried
  with backoff, per-step timeouts) over an in-process or Redis/ARQ job queue with
  dead-lettering and idempotent enqueueing; blast-radius incident merging over the service
  dependency graph.
* Implemented a provider-agnostic LLM layer (Ollama, deterministic fallback, circuit
  breaker, JSON-schema-validated structured outputs, prompt-injection hardening) and
  signature-based retrieval over historical incidents — with zero paid API usage.
* Built a seven-service demo environment over real HTTP with a fourteen-fault chaos
  engine, a release manager with synthetic Git history, and an automated evaluation suite
  of 119 scenarios measuring root-cause accuracy, evidence precision, false-positive rate,
  calibration and latency (100% top-1, 0% false positives, 0.39 s median; first iteration
  96.5%).
* Shipped production controls: JWT + API-key auth with scopes, RBAC, four-eyes remediation
  approval with audit logs, rate limiting, self-observability metrics and Grafana
  dashboard, Alembic migrations, Docker Compose stack, GitHub Actions CI with a benchmark
  quality gate, 67 unit/integration/chaos tests.

## Interview talking points

* *Why not just an LLM agent?* → reproducibility, measurability, injection surface,
  confidence you can defend. Show the verifier rejecting an invented citation.
* *How do you know it works?* → the benchmark, its methodology and its threats to
  validity; the confusion matrix from the first iteration and what changed (symptom
  vs cause handling for upstream services; noise gate on log bursts).
* *What breaks at scale?* → telemetry write volume (partitioning / a columnar store or
  ClickHouse behind the same store interface), retrieval (pgvector), SQLite single-writer
  (PostgreSQL in compose), the model as a latency tail (circuit breaker + fallback).
* *What would you not do again?* → hand-tuned catalog weights; fine for a first system,
  should become learned once labelled real incidents exist.
