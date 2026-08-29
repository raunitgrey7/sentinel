# ADR-0002: Deterministic analysis first; the model narrates, it does not decide

**Status:** accepted · **Date:** 2026-08-29

## Context

The naïve architecture is *logs → LLM → "what's wrong?"*. It is unreproducible,
unmeasurable, prompt-injectable through log content, and its confidence is theatre.

## Decision

* Detection, correlation, clustering, deployment proximity, dependency reasoning,
  hypothesis generation and scoring are deterministic code with unit tests.
* The model receives **evidence with system-minted handles** and a **candidate ranking**
  and may only narrate, reorder and cite. It cannot introduce categories, evidence,
  services or numbers.
* A verifier re-derives confidence from the evidence after the model has spoken; model
  output can lower confidence but never raise it above the deterministic ceiling.
* A deterministic `NullProvider` renders every model-shaped output, so the platform is
  fully functional with no model and the benchmark can measure model *lift* separately.

## Consequences

* Root-cause accuracy is a property of the pipeline, reproducible in CI (100 % top-1 on
  the 119-case synthetic benchmark with no model at all; 96.5 % on the first iteration —
  see `docs/evaluation/`).
* Adding a failure mode means adding a catalog entry with signals and a playbook — a code
  review, not a prompt tweak.
* The model's contribution is legible: narrative quality, caveats, reordering when
  evidence conflicts. That is where an LLM is genuinely useful.
