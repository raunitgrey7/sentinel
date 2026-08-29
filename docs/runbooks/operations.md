# Operations runbook

## Health

| Check | Endpoint / command | Healthy when |
|---|---|---|
| Liveness | `GET /health` | `{"status":"ok"}` |
| Readiness | `GET /ready` | 200 with `database: true` (503 otherwise) |
| Metrics | `GET /metrics` | Prometheus exposition |
| Queue | `GET /api/v1/system/queue` (ENGINEER) | `depth` small and stable, `dead_letters` empty |
| Model | `GET /api/v1/system/overview` → `llm.circuit.state` | `closed` |
| Simulator | `GET :9000/health` | every service `ingest_ok: true` |

## Symptoms → actions

**Incidents are not being opened although the shop is degraded**
1. `GET /api/v1/projects/demo-shop/health` — are metrics fresh (`last_seen` within 30 s)? If not, the simulator cannot reach the API: check `SIM_SENTINEL_URL`, the ingestion key (`SIM_INGEST_KEY` must equal `SENTINEL_BOOTSTRAP_INGEST_KEY`) and `sentinel_rate_limited_total{scope="ingest"}`.
2. `GET /api/v1/projects/demo-shop/metrics/payment-service/http_error_rate?minutes=5` — is the error ratio actually above the rule threshold for `for_s`? Rules are in `GET /api/v1/projects/demo-shop/rules`.
3. Is the scheduler running? In the in-process mode it lives in the API (`scheduler started` log line); with Redis it lives in the worker. `sentinel_detector_runs_total` must increase.

**Investigation stuck in `INVESTIGATING`**
1. `GET /api/v1/incidents/{id}/investigations` — look at the step with `status: RUNNING` and its `attempts`/`error`.
2. A stage is bounded by `SENTINEL_INVESTIGATION_STEP_TIMEOUT_S` (60 s; synthesis/verification 240 s). If the model is slow, the circuit opens and the narrator takes over — check `sentinel_circuit_open{circuit="ollama"}`.
3. A worker crash resumes from the checkpoint on the next attempt; the job is retried by the queue (backoff 2 s, 4 s, 8 s). After `SENTINEL_JOB_MAX_RETRIES` it is dead-lettered: `GET /api/v1/system/queue`. Re-queue with `POST /api/v1/incidents/{id}/investigate`.

**Model output rejected (`dropped_invalid_citations` > 0 or `LOW_CONFIDENCE`)**
This is the system working: the verifier discarded handles that do not exist or do not
support the category. Read `hypotheses[].verification.issues`. Consider a larger model or
lower temperature; the deterministic ranking is unaffected.

**Database locked (SQLite)**
Single-writer engine. Use PostgreSQL for anything beyond one API process and the
evaluation harness. Never run two API processes against one SQLite file.

**Redis unavailable**
API keeps serving reads; enqueues fail with 503 and are logged. Worker reconnects; ARQ
jobs are durable in Redis. Rate limiting degrades to in-memory.

**Ollama unavailable**
Investigations complete with `llm_provider: none` semantics via `FallbackProvider`;
`sentinel_llm_calls_total{outcome="failure"}` increases; the UI labels the narrative as
deterministic. No action required for correctness.

## Routine

* **Retention:** `telemetry_retention` job hourly, `SENTINEL_TELEMETRY_RETENTION_HOURS` (48 h default).
* **Migrations:** `sentinel migrate` (Alembic). The compose stack runs it in the `migrate` job before the API starts.
* **Backups:** PostgreSQL `pg_dump` of the `sentinel` database; evidence and postmortems are relational rows, no external blobs.
* **Rotating the ingestion key:** create a new key (`POST /api/v1/auth/api-keys`, scopes `["ingest","webhooks"]`), roll producers, revoke the old one (`DELETE /api/v1/auth/api-keys/{id}`).
* **Upgrading the model:** change `SENTINEL_OLLAMA_MODEL`, `ollama pull`, restart the worker; run `sentinel eval run --limit 20` and compare with `docs/evaluation/latest.md`.
