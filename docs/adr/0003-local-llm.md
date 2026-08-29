# ADR-0003: Local models through a provider abstraction; no paid APIs

**Status:** accepted · **Date:** 2026-08-29

## Context

Incident data is among the most sensitive data a company has (stack traces, hostnames,
customer identifiers in logs). Shipping it to a third-party API is a procurement and
compliance problem before it is an engineering one. Also: ₹0 budget.

## Decision

`LLMProvider` exposes exactly three operations (`generate`, `structured`, `embed`).
`OllamaProvider` talks to `localhost:11434` — the local Ollama API requires no
authentication and no account. `NullProvider` is the deterministic fallback and the CI
provider. `FallbackProvider` degrades from Ollama to the narrator on timeout, circuit-open
or invalid output, and records which provider produced each result so the UI can label it.

Model choice is configuration (`SENTINEL_OLLAMA_MODEL`, default `qwen2.5:7b`; embeddings
`nomic-embed-text`). Cloud providers could be added behind the same protocol; none are
required.

## Consequences

* Structured output is enforced with JSON mode + schema validation + repair + one
  re-prompt; the pipeline never depends on the model producing perfect JSON.
* Circuit breaker (3 failures → open for 60 s) prevents a slow local model from stalling
  the worker pool; the evaluation harness reports model time separately.
* Inference cost is measured as latency and tokens, not money.
