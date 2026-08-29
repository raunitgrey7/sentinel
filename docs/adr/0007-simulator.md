# ADR-0007: A real-HTTP demo shop with simulated resources as the benchmark environment

**Status:** accepted · **Date:** 2026-08-29

## Context

We have no production system to monitor. Two bad options: (a) point Sentinel at toy
"hello world" containers that never fail interestingly; (b) run real PostgreSQL/Redis and
inject OS-level faults, which is slow, flaky on laptops, Linux-only and needs privileges.

## Decision

Seven services run as real HTTP servers with real inter-service calls and trace
propagation. Their internal resources (DB pool, cache, queue, worker pool, CPU/memory)
are simulated in-process with faithful failure *shapes* (pool waits become acquire
timeouts become 5xx that propagate upstream). A fault engine exposes fourteen faults with
documented telemetry signatures and expected root causes; a release manager announces
deployments with synthetic Git metadata.

The evaluation harness additionally has a **pure synthesizer** that generates the same
telemetry shapes directly into the store (no HTTP, no waiting), so 100+ scenarios run in
minutes with deterministic seeds.

## Consequences

* Ground truth exists for every incident, which makes accuracy, precision, false-positive
  rate and calibration measurable.
* The environment runs on any laptop and in CI.
* Honesty note for the pitch: the *signals* are realistic, the *systems* are simulated.
  Pointing Sentinel at real services is a matter of shipping telemetry to the same
  ingestion API (the OTel collector config is provided).
