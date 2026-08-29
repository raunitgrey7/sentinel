# ADR-0005: Queue abstraction with in-process and Redis/ARQ backends; checkpointed investigations

**Status:** accepted · **Date:** 2026-08-29

## Context

Investigations take seconds to minutes and call an external model. They must not run
inside an HTTP request, must survive worker crashes, and must not run twice for the same
incident. Kafka would be a resume line, not a requirement.

## Decision

* `JobQueue` protocol with two backends chosen by configuration: `InProcessQueue`
  (asyncio, used by `sentinel dev`, tests and the evaluation harness) and `RedisQueue`
  (ARQ, used by `docker compose`). Same semantics on both: at-least-once, idempotency key
  de-duplication while a job is pending, exponential backoff, bounded retries, dead-letter
  list, graceful shutdown.
* Handlers are idempotent by construction. The investigation orchestrator checkpoints its
  entire context after every stage into the `investigations.checkpoint` column and
  resumes from the last completed stage.
* `enqueue_investigation` touches no database state — it only enqueues `{incident_id}`
  with a 1 s delay so the caller's transaction commits first. The job creates its own
  investigation row. (This also avoids SQLite single-writer deadlocks.)
* Periodic work (detector tick, fault expiry, retention) is scheduled by enqueueing jobs
  with tick idempotency keys, so overlapping ticks collapse instead of piling up.

## Consequences

* The same code runs with zero infrastructure and with Redis; CI needs no broker.
* A worker killed mid-investigation loses at most one stage of work.
* Kafka/Redpanda can be introduced behind the same protocol if ingestion volume ever
  requires a log rather than a queue — there is no such requirement today.
