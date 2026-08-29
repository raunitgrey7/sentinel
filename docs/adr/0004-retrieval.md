# ADR-0004: Signature-based retrieval in PostgreSQL; no vector database

**Status:** accepted · **Date:** 2026-08-29

## Context

Historical incidents are a genuinely useful retrieval corpus ("this resembles INC-031,
whose verified cause was pool exhaustion"). The reflex is to add a vector database.

## Decision

* Retrieval is over **incident signatures** — short, vocabulary-controlled strings built
  from Sentinel's own outputs (services, catalog signals, error templates, category) —
  not over free text. Similarity therefore reflects *failure shape*.
* Embeddings are stored on the incident row (`incidents.embedding`, JSON array). Ranking
  is cosine similarity computed in-process over resolved incidents of the same project.
* The default embedder is a deterministic feature-hashing embedder (uni/bi-grams → 256-d,
  L2-normalised). With Ollama configured, `nomic-embed-text` is used instead; both
  produce the same interface and the fallback is automatic.

## Consequences

* Zero extra infrastructure; retrieval is reproducible in CI.
* Corpus size is one row per incident. Linear scan is fine to tens of thousands of
  incidents; the documented upgrade path is `pgvector` on the same column with an HNSW
  index — no API change.
* Retrieval contributes to scoring only through `historical_similarity` (weight 0.25),
  so a mislabelled past incident cannot dominate a fresh investigation.
