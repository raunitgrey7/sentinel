# ADR-0006: Recommendation-only by default; approved, audited, verified actions

**Status:** accepted · **Date:** 2026-08-29

## Context

"AI says rollback → production rolls back" is irresponsible: the model can be wrong, the
evidence can be correlational, and a rollback has its own blast radius.

## Decision

* Every investigation produces **playbook actions** from the root-cause catalog. They are
  `proposed`; nothing executes.
* Workflow: `request` (ENGINEER+) → `approve` (SRE+, not the requester — four-eyes) →
  `execute` (SRE+, only actions marked `executable`, only kinds in the small executable
  set) → adapter `verify` → `verified`. `reject` at any point before execution.
* Every transition writes an `audit_logs` row (who, what, when, why, outcome) and a
  timeline event on the incident.
* Automated agents have a **tool permission table**: read tools are allowed, mutating
  tools (`rollback`, `restart`, `scale`, `clear_fault`) are denied unless explicitly
  granted; the remediation service enforces it independently of RBAC.
* Execution goes through a `TargetAdapter`. The shipped adapter targets the simulator's
  release manager; Kubernetes/Argo/feature-flag adapters plug in behind the same
  two-method interface.

## Consequences

* The demo shows an honest loop: hypothesis → human judgement → action → verification.
* Audit and RBAC are exercised by integration tests, not described in a slide.
