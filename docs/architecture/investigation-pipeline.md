# Investigation pipeline

Every investigation is a row in `investigations` with one `investigation_steps` row per
stage. The orchestrator (`sentinel/investigation/orchestrator.py`) checkpoints the whole
in-memory context (evidence, notes, timeline, candidates, synthesis, verification) into
`investigations.checkpoint` after each stage, so a crashed worker resumes at the next
stage rather than restarting. Stages have per-step timeouts and bounded retries; the
historical stage is optional (retrieval failure never fails an investigation).

## Windows

```
lookback_start ─────────── baseline_start ────── baseline_end ─┬─ incident_start ──── now
(onset − 30 min)           (onset − 30s − 20 min)     (onset − 30s)              (onset − 30s)
```

`onset` = incident `started_at`, estimated by the detector from the first threshold
crossing (or supplied by the alert). Baseline vs incident comparisons drive most evidence.

## Stages

| # | Stage | What it does | Evidence produced |
|---|---|---|---|
| 1 | Timeline | Collects deployments in lookback, alerts attached to the incident, investigation start | timeline entries |
| 2 | Metrics Investigator | For every in-scope service and metric: baseline deviation (mean/std/z-score/% change), saturation ratio for pool-style metrics, monotonic-trend check for memory; emits *contradicting* "remained normal" evidence for the primary service when no service shows the deviation | `metric` evidence tagged with signals such as `db_pool_saturated`, `latency_up`, `cpu_flat` |
| 3 | Log Investigator | Groups error/warn logs by mined template; computes burst ratio vs baseline; maps templates to signals with a keyword catalog; flags exception templates absent from the baseline | `log` evidence, `error_clusters` rows |
| 4 | Trace Investigator | Per (service, operation) p95 vs baseline and error rate; `client slow & server ok` → network; db acquire vs query; critical path of the slowest trace | `trace` evidence |
| 5 | Deployment Investigator | Deployments/config changes in lookback with proximity score to onset; commit message/file heuristics (`pool`, `concurrency`, config files) | `deployment`/`config` evidence |
| 6 | Dependency Investigator | Downstream health during the incident window; blast radius (upstream callers); culprit hints from the service graph (shared dependencies score higher) | `dependency` evidence, `culprit_hints` |
| 7 | Historical Investigator | Builds the incident signature (services + signals + error templates), embeds it, ranks resolved incidents by cosine similarity | `historical` evidence, `historical_by_category` |
| 8 | Hypothesis Generator | For each catalog entry whose *required* signals are present: score = squash(signal support + temporal + dependency + historical − contradictions); diversity guard caps single-kind evidence at 0.6 | candidates with score breakdowns |
| 9 | Root Cause Synthesizer | The only reasoning LLM call. Receives evidence with handles + candidate ranking; returns summary, reordered hypotheses with citations, caveats. Unknown categories and unknown handles are dropped | narrative, `citation_validity` |
| 10 | Evidence Verifier | Deterministic: handles exist, cited support carries a relevant signal, required signals present, ignored contradictions surfaced; confidence re-derived via `calibrate_confidence` (never above 0.95; < 3 evidence kinds caps at 0.75). Optional model cross-examination can only lower confidence | verified hypotheses |
| 11 | Persist | Writes evidence, hypotheses, clusters, timeline, evidence graph, playbook actions; transitions the incident | — |

## Root-cause catalog

`investigation/catalog.py` declares thirteen failure modes. Each lists the signals that
support it (with weights and `required` flags), the signals that contradict it, whether a
recent deployment is corroborating, and a remediation playbook. The LLM cannot add
categories; the evaluation harness maps every fault type to exactly one category.

## Scoring

```
raw   = 1.0·signal_support + 0.35·temporal + 0.25·dependency + 0.25·historical − 1.0·contradiction
score = 1 / (1 + e^(−2.2·(raw − 0.75)))          # ≈0.5 at raw 0.75, ≈0.9 at raw 1.8
```

The breakdown is stored on every hypothesis and rendered in the UI, so a number is never
a black box.

## Confidence

`confidence = score × (0.7 + 0.3·citation_validity) − contradiction_penalty`, ×0.6 if the
verifier rejects, capped at 0.75 with fewer than three evidence kinds, and never above
0.95. Confidence below `SENTINEL_LOW_CONFIDENCE_THRESHOLD` (0.55) routes the incident to
`HUMAN_REVIEW`.
