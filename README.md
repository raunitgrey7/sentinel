<p align="center">
  <strong>◆ SENTINEL</strong><br/>
  <em>Evidence-driven incident intelligence for modern software systems.</em><br/>
  Local-first · self-hosted · API-first · model-agnostic · human-in-the-loop
</p>

---

Sentinel is an open-source, self-hosted platform that **detects production incidents,
correlates logs, metrics, traces, deployments and code changes, investigates probable
root causes, and produces evidence-backed incident reports and remediation plans** — with
every AI-generated claim linked to evidence the system itself collected, and a
confidence it can defend.

```
🔴 INC-2026-0001   High error rate on payment-service (impacting api-gateway, order-service, frontend)

Probable root cause      Database connection-pool exhaustion        confidence 87%

Evidence
  E1  payment-service db connections active reached 100% of capacity (40/40); baseline 30%
  E2  payment-service db connection acquire ms increased 2ms → 1863ms (peak 2000ms, z=41.2)
  E5  312 × ERROR on payment-service: "failed to acquire database connection after <num>ms (pool=<num>/<num>…" — new
  E9  span payment-service/db.acquire_connection: p95 2ms → 2001ms (1000×); error rate 0% → 71%
Contradicting evidence
  E3  payment-service cpu usage remained normal (28% → 27%)

Recommended remediation  1. Roll back payment-service 2.8.1 → 2.8.0   2. Reduce transaction concurrency
                         3. Raise the pool ceiling after validating DB capacity   4. Alert on acquisition latency
Confidence caveat        Correlation with the cited evidence is strong; causality has not been independently verified.
```

## Why it exists

Most "AI for ops" is `logs → LLM → "what's wrong?"`. That is unreproducible, unmeasurable,
prompt-injectable through log content, and its confidence is theatre. Sentinel is built the
other way round:

```
Reality → Telemetry → Normalisation → Deterministic detection → Correlation → Evidence graph
        → Candidate hypotheses (catalog + explicit scoring) → LLM narration → Verification
        → Calibrated confidence → Human decision → (approved) action → Verification
```

The model is one component inside a deterministic system — it narrates, reorders and
cites; it never invents evidence, categories or numbers. A verifier re-derives confidence
after the model has spoken. And the whole platform runs **with no model at all** (a
deterministic narrator renders every model-shaped output), which is also how the benchmark
separates pipeline quality from model lift.

## Measured, not claimed

`make eval` runs 119 synthetic production failures (14 root-cause categories × target
services × intensity / noise / confounding-deployment variants + 6 healthy controls)
through the *same* detector and investigation pipeline production uses. Ground truth never
reaches the pipeline. Latest run (`docs/evaluation/latest.md`, deterministic provider):

| Metric | Result |
|---|---|
| Root-cause accuracy (top-1 / top-3) | **100.0% / 100.0%** (first iteration: 96.5% / 99.1%) |
| Detection rate | 100.0% |
| Evidence precision (cited evidence relevant to the *true* cause) | 100.0% |
| Citation validity (claims backed by real evidence) | 100.0% |
| False-positive rate on healthy controls | 0.0% |
| Confident-wrong rate (wrong & confidence ≥ 0.55) | 0.0% |
| Median / p95 investigation time | 0.39 s / 0.63 s |
| Calibration (ECE) | 0.32 — reported confidence is deliberately conservative (0.55–0.87) |

Honesty notes: the telemetry is synthetic and the catalog and scenarios were written by the
same author (see `docs/evaluation/methodology.md` → *threats to validity*). The live
simulator path (real HTTP services, real timing) is exercised end-to-end by the demo and
the e2e test; real services plug in through the same ingestion API / OpenTelemetry
collector.

## What's inside

* **Telemetry** — OpenTelemetry-aligned ingestion (`service.name`, `service.version`,
  `trace_id`…), log template mining, Alertmanager and deployment webhooks.
* **Detection** — rule engine with sustained thresholds, fingerprinted alerts,
  blast-radius merging over the dependency graph (symptoms attach to the incident; the
  deepest failing callee becomes the primary suspect).
* **Investigation** — durable, checkpointed, resumable orchestrator running seven
  investigators (timeline, metrics, logs, traces, deployments, dependencies, historical
  retrieval), a 13-entry root-cause catalog, explicit scoring with stored breakdowns, an
  evidence graph, LLM synthesis with citation handles, and a verifier that rejects
  unsupported claims and calibrates confidence.
* **AI layer** — `LLMProvider` abstraction; Ollama (`localhost:11434`, no API key) with
  circuit breaker, JSON-mode + schema validation + repair; deterministic `NullProvider`;
  automatic degradation; injection-hardened prompts; signature-based RAG over resolved
  incidents. **No paid APIs, ever.**
* **Human in the loop** — playbooks per root cause; request → approve (four-eyes) →
  execute → verify; agents get read-only tools by default; everything audited.
* **"Why?"** — challenge any hypothesis; answers cite evidence handles and show
  counter-evidence. Postmortems with per-section citations.
* **Demo shop + chaos lab** — seven services over real HTTP with simulated internals,
  fourteen injectable faults, a release manager with synthetic Git history, traffic.
* **Production engineering** — retries/backoff, idempotency, timeouts, circuit breakers,
  dead-letter queue, graceful shutdown, worker recovery, rate limiting, RBAC, API keys with
  scopes, audit logs, Prometheus metrics for the platform itself, Grafana dashboard,
  Alembic migrations, Docker Compose, CI with a quality gate.
* **Dashboard** — Next.js/TypeScript/Tailwind: overview, incidents, incident detail (root
  cause, evidence, contradicting evidence, timeline, investigator progress, hypotheses with
  score breakdowns, evidence graph, Why?, remediation, postmortem), services & topology,
  chaos lab, evaluation.

## Quick start (zero infrastructure)

```bash
uv sync --all-extras            # Python ≥ 3.12
uv run sentinel dev             # API :8000 + demo shop :9000–9007 (SQLite, in-process queue, no model)
cd web && npm install && npm run dev      # dashboard :3000 → admin@sentinel.local / admin12345
```

Then: **Chaos Lab → payment-service / db_pool_exhaustion → Inject**. Within ~2 minutes an
incident opens, merges the gateway/order symptoms, and lands on *Database connection-pool
exhaustion* with the evidence above. Follow `docs/demo.md` for the eleven-step demo.

Full stack (PostgreSQL, Redis, worker, simulator, web; optional Prometheus/Alertmanager/
Grafana/OTel and Ollama):

```bash
cp .env.example .env
docker compose up --build -d
docker compose --profile observability --profile llm up -d      # optional
```

Run the benchmark: `make eval` → `docs/evaluation/latest.md`. Tests: `make test`.

## Repository

```
backend/sentinel/   api · telemetry · detection · analysis · investigation · llm · retrieval
                    remediation · reporting · queue · worker · observability · evaluation
simulator/          the demo shop, fault engine, releases, traffic
web/                Next.js dashboard
infrastructure/     Dockerfiles, Prometheus rules, Alertmanager, Grafana, OTel collector
docs/               architecture, ADRs, API, security threat model, runbooks, evaluation, demo, pitch
tests/              unit · integration · e2e · chaos
```

Start with `docs/architecture/overview.md`, then `docs/adr/` for the decisions and
`docs/security/threat-model.md` for what we defend against.

## Status

MVP complete (M0–M10 in `MILESTONES.md`). Known gaps are listed in the threat model and
the runbooks. Licensed under Apache-2.0.
