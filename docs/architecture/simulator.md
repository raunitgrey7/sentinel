# The Sentinel Demo Shop (simulator)

A deliberately realistic distributed application that Sentinel monitors, so the platform
can be developed, demonstrated and benchmarked without access to anyone's production.

```
frontend:9001 → api-gateway:9002 → auth-service:9003 ──→ redis, postgres
                                 → order-service:9004 ─→ inventory-service:9005 → postgres, redis
                                                       → payment-service:9006   → postgres, redis, payment-provider
                                                       → postgres, message-queue
notification-worker:9007 ← message-queue → email-provider
control plane: 9000
```

## What is real, what is simulated

* **Real:** seven independent HTTP servers (uvicorn), real inter-service calls with trace
  context propagation (`x-trace-id`, `x-parent-span-id`), real telemetry (logs, metrics,
  spans) pushed to Sentinel's ingestion API and exposed on `/metrics` in Prometheus
  exposition format, real deployments announced through the deployment webhook, a real
  traffic generator.
* **Simulated in-process:** the database connection pool (`asyncio.Semaphore(40)` with a
  2 s acquire timeout and a query latency model), the cache (hit-rate model with fail-open
  fallback), the message queue (shared `asyncio.Queue`), the worker pool
  (`asyncio.Semaphore(32)`), CPU/memory gauges, and the two third-party providers.

This split is intentional: the *shapes* of failure are faithful (pool waits become
acquire timeouts that become 5xx that propagate to callers) while runs are deterministic,
cheap and safe. `docs/adr/0007-simulator.md` records the decision.

## Fault engine

| Fault | Mechanism | Telemetry signature | Expected root cause |
|---|---|---|---|
| `db_pool_exhaustion` | 40 runaway transactions hold pool slots for 45–90 s each | `db_connections_active` → 40/40, `db_connections_waiting` ↑, `db_connection_acquire_ms` → 2000, "failed to acquire database connection" logs, slow `db.acquire_connection` spans, 5xx ↑, CPU flat | `database_connection_pool` |
| `bad_deployment` | deploys `2.8.1` (commit *increase transaction concurrency 8→64*, touching `payment/db/pool.py`), then exhausts the pool | as above plus a deployment 0–4 min before onset | `database_connection_pool` |
| `database_latency` | +420 ms on every query | `db_query_latency_ms` ↑, slow-query / statement-timeout logs, slow `db.query` spans | `database_latency` |
| `redis_failure` | 90 % of cache ops fail | `redis_errors_rate` ↑, `cache_hit_rate` ↓, ECONNREFUSED logs, `cache.get` error spans | `redis_unavailable` |
| `memory_leak` | memory gauge climbs monotonically; GC pauses grow; late OOM | `memory_usage_mb` ↑ monotonic, `gc_pause_ms` ↑, OutOfMemoryError logs | `memory_exhaustion` |
| `cpu_saturation` | CPU gauge → 95 %; per-request delay | `cpu_usage` ↑, latency ↑, throttle logs | `cpu_saturation` |
| `http_500_spike` | deploys a version whose handler throws on 35 % of requests | 5xx ↑, new TypeError template, everything else normal | `deployment_regression` |
| `config_regression` | deploys `payment.timeout_ms: 5000 → 200` | upstream timeouts, config error logs, config-change deployment | `config_regression` |
| `network_latency` | +380 ms on calls to a dependency | `network_latency_ms` ↑, client span slow while server span normal | `network_latency` |
| `packet_loss` | 28 % of dependency calls reset | `network_errors_rate` ↑, ECONNRESET logs, client error spans | `network_packet_loss` |
| `queue_backlog` | consumer paused | `queue_depth` ↑, `consumer_lag_s` ↑, backlog logs | `queue_backlog` |
| `thread_starvation` | 31 of 32 workers blocked | `thread_pool_active` → 32/32, queued-request logs, latency ↑, CPU down | `thread_starvation` |
| `deadlock` | 90 % of requests hang 6 s | request rate collapses, in-flight ↑, CPU drops, deadlock logs | `deadlock` |
| `dependency_failure` | payment-provider returns 503 on 60 % | `dependency_error_rate` ↑, "upstream payment-provider returned 503" logs | `dependency_failure` |

Faults expire on their own; `DELETE /faults` clears everything. Severity scales intensity
(`low` 0.5 … `critical` 1.3).

## Control API (`:9000`)

`GET /health`, `GET /topology`, `GET|POST|DELETE /faults`, `POST /releases/deploy`,
`POST /releases/rollback`, `GET /releases`, `GET /services/{name}/status`,
`POST /services/restart`, `POST /services/scale`, `POST /traffic`.

Sentinel's chaos-lab endpoints (`/api/v1/faults`) and the remediation adapter call this API.
