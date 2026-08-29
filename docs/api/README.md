# API

OpenAPI: `GET /openapi.json`, Swagger UI at `/docs`, ReDoc at `/redoc`. All application
routes are versioned under `/api/v1`. Errors use one envelope:

```json
{ "error": { "code": "invalid_transition", "message": "…", "details": {…} }, "request_id": "…" }
```

Every response carries `x-request-id`; send your own to correlate logs.

## Authentication

* **Users:** `POST /api/v1/auth/login` → `{access_token}`; send `Authorization: Bearer <jwt>`.
* **Machines:** API keys (`snt_…`) via `x-api-key: <key>` or `Authorization: Bearer <key>`.
  Keys have a role and scopes (`ingest`, `webhooks`).
* **Roles:** `VIEWER` < `ENGINEER` < `SRE` < `ADMIN`. Minimum role per endpoint below.

## Endpoints

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/health`, `/ready`, `/metrics` | — | liveness, readiness, Prometheus |
| POST | `/api/v1/auth/login` | — | |
| GET | `/api/v1/auth/me` | VIEWER | |
| GET/POST | `/api/v1/auth/users` | ADMIN | |
| GET/POST/DELETE | `/api/v1/auth/api-keys[/{id}]` | ADMIN | raw key shown once |
| GET/POST | `/api/v1/projects` | VIEWER / ENGINEER | |
| GET/POST | `/api/v1/projects/{ref}/services` | VIEWER / ENGINEER | upsert by name |
| GET/POST | `/api/v1/projects/{ref}/dependencies` | VIEWER / ENGINEER | caller → callee |
| GET | `/api/v1/projects/{ref}/topology` | VIEWER | nodes + edges |
| GET | `/api/v1/projects/{ref}/health` | VIEWER | per-service availability, error rate, p95, open incidents |
| GET | `/api/v1/projects/{ref}/deployments` | VIEWER | |
| GET | `/api/v1/projects/{ref}/metrics/{service}/{metric}?minutes=30` | VIEWER | time series |
| GET | `/api/v1/projects/{ref}/alerts` | VIEWER | |
| GET/POST/DELETE | `/api/v1/projects/{ref}/rules[/{id}]` | VIEWER / ENGINEER | detection rules |
| POST | `/api/v1/ingest/logs` · `/metrics` · `/traces` | key with `ingest` | `{project, service?, records[]}` ≤ 5000; 202 |
| POST | `/api/v1/webhooks/deployments` | key with `ingest` | version, commit, files, config diff |
| POST | `/api/v1/webhooks/alerts?project=` | key with `ingest` | Alertmanager v4 payload |
| GET/POST | `/api/v1/incidents` | VIEWER / ENGINEER | `?project=&status=&open_only=&limit=&offset=`; POST returns 202 and queues an investigation |
| GET | `/api/v1/incidents/{id}` | VIEWER | id or key (`INC-2026-0087`) |
| POST | `/api/v1/incidents/{id}/investigate` | ENGINEER | (re)queue an investigation |
| POST | `/api/v1/incidents/{id}/transition` | ENGINEER | explicit state machine; 409 on illegal |
| GET | `/api/v1/incidents/{id}/transitions` | VIEWER | allowed targets |
| POST | `/api/v1/incidents/{id}/resolve` | ENGINEER | |
| GET | `/api/v1/incidents/{id}/timeline` · `/evidence` · `/hypotheses` · `/clusters` · `/investigations` · `/graph` | VIEWER | |
| POST | `/api/v1/incidents/{id}/why` | VIEWER | `{question, hypothesis_id?}` → grounded answer with citations |
| POST | `/api/v1/incidents/{id}/verify` | ENGINEER | re-run deterministic verification |
| GET | `/api/v1/incidents/{id}/remediation` | VIEWER | |
| POST | `/api/v1/incidents/{id}/remediation/{action}/request` | ENGINEER | |
| POST | `…/approve` · `…/reject` · `…/execute` | SRE | four-eyes enforced |
| GET/POST | `/api/v1/incidents/{id}/postmortem` | VIEWER / ENGINEER | Markdown + sections + citations |
| GET | `/api/v1/faults/catalog` | VIEWER | fault → expected root cause |
| GET/POST/DELETE | `/api/v1/faults[/{id}]` | VIEWER / SRE | chaos lab |
| GET | `/api/v1/evaluation/scenarios` · `/runs` · `/runs/latest` · `/runs/{id}` · `/runs/{id}/cases` | VIEWER | |
| POST | `/api/v1/evaluation/runs?limit=` | SRE | start a benchmark run in the background |
| GET | `/api/v1/system/overview` · `/config` · `/queue` | VIEWER / ENGINEER | |
| GET | `/api/v1/system/audit` | ADMIN | |

## Ingestion record shapes

Records accept both flat keys and OpenTelemetry attribute names:

```json
{"timestamp": "2026-08-29T14:13:42Z", "service.name": "payment-service", "service.version": "2.8.1",
 "level": "ERROR", "message": "failed to acquire database connection after 5012ms (pool=40/40)",
 "trace_id": "…", "span_id": "…", "attributes": {"exception.type": "PoolTimeout"}}
```
```json
{"service": "payment-service", "name": "db_connections_active", "timestamp": 1756476822, "value": 40, "labels": {"pool": "main"}}
```
```json
{"trace_id": "…", "span_id": "…", "parent_span_id": "…", "service": "payment-service", "operation": "db.acquire_connection",
 "kind": "internal", "start_time": "…", "duration_ms": 2001.3, "status": "error", "attributes": {"db.system": "postgresql"}}
```

Metric names the detector and investigators understand are listed in
`backend/sentinel/investigation/investigators/metrics.py` (`RULES`, `SATURATION`).
