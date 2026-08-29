# ADR-0001: Modular monolith + workers, not microservices

**Status:** accepted · **Date:** 2026-08-29

## Context

The product surface (ingestion, detection, investigation, remediation, reporting) maps
naturally onto services, and it is tempting to ship fifteen containers to look
"distributed". Each boundary costs a network hop, a deployment unit, a failure mode and a
schema contract, and none of the modules currently need independent scaling.

## Decision

One Python package (`sentinel`) organised by domain module with explicit internal
interfaces, deployed as two process types: **API** and **worker**. The queue is the only
asynchronous boundary. The simulator is a separate package because it represents *another*
system, not part of the platform.

## Consequences

* One database schema, one migration history, one test suite; a full investigation is a
  function call in tests.
* Modules can be extracted later along the existing queue/DB seams (ingestion is the first
  candidate if telemetry volume grows).
* The worker can be scaled horizontally today; the API is stateless.
