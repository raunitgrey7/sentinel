# Chaos scenarios

Sentinel's chaos tooling has two layers: single faults (`POST /api/v1/faults`, the Chaos
Lab page, `sentinel fault inject`) and composed scenarios (`sentinel-sim scenario <name>`)
that stress the platform's *own* behaviour — merging, retries, checkpoints, model outage.

## Single faults

```
sentinel fault inject payment-service --type db_pool_exhaustion --duration 180
sentinel fault inject order-service   --type deadlock            --duration 120 --severity critical
sentinel fault clear
```

All fourteen fault types and their expected root causes are listed in
`docs/architecture/simulator.md`.

## Composed scenarios (`sentinel-sim scenario …`)

| Name | Steps | What it tests |
|---|---|---|
| `payment-pool` | pool exhaustion on payment-service | the canonical demo |
| `bad-deploy` | deploy 2.8.1 (concurrency 8→64) → pool exhaustion | deployment correlation + rollback playbook |
| `17` | bad deploy → 60 s → DB latency on order-service → restart notification-worker → queue backlog | incident merging across the call graph, second incident on an unrelated symptom, competing hypotheses |
| `cascade` | deadlock in inventory-service → 45 s → redis failure in auth-service | two independent incidents open in parallel and stay separate (auth is not on inventory's path) |
| `noise` | 20 s low-severity latency blip, 15 s CPU blip | *no* incident should open (`for` durations and thresholds) |

Expected outcome for `17`: one incident with primary `payment-service` (merged from the
gateway/order symptoms) whose top hypothesis is *database connection-pool exhaustion*
citing the 2.8.1 deployment; queue backlog appears as a separate incident on
`order-service`/`notification-worker` with `queue_backlog` as top hypothesis.

## Platform chaos (`pytest -m chaos`)

* `test_model_outage_degrades_to_deterministic_narrator` — model dead/timeouts →
  narrator, embeddings fall back to hashing.
* `test_step_timeout_fails_stage_not_process` — a hung investigator is bounded by its
  timeout; optional stages are skipped, not fatal.
* Integration: `test_investigation_resumes_from_checkpoint` — crash in the trace stage,
  restart, completed stages are skipped, result is still correct.
* Queue unit tests cover retries with backoff, idempotent de-duplication, dead-lettering
  and job timeouts.

## Manual resilience drills

1. **Kill the worker mid-investigation** (compose: `docker compose kill worker` during an
   investigation, then `docker compose up worker`). Expect: the investigation row shows
   `checkpoint.completed`, the step that was running is retried, the incident completes.
2. **Stop Ollama** (`docker compose stop ollama`). Expect: `sentinel_circuit_open{circuit="ollama"}` = 1 after three failures; investigations still complete with `provider: none` in the synthesis block.
3. **Stop Redis**. Expect: `/ready` still 200 (DB up), enqueue errors logged, detector resumes when Redis returns.
4. **Flood ingestion** (`SIM_TRAFFIC_RPS=200`). Expect: 429s counted in `sentinel_rate_limited_total{scope="ingest"}`; API latency p95 stays below 250 ms.
