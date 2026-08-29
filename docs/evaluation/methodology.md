# Evaluation methodology

The benchmark answers one question honestly: *given a production failure, does Sentinel
detect it, name the right root cause, cite the right evidence, and report a confidence it
deserves?*

## Scenario library

`backend/sentinel/evaluation/scenarios.py` builds the matrix from 14 fault types × target
services × 4 variants (intensity 1.0 / 0.85 / 1.3 + noise / confounding deployment on an
unrelated service 9 min before onset), plus 6 healthy controls (two with noisy transient
errors). 118 cases; every one has a ground-truth `RootCauseCategory`, or `none`.

Telemetry is synthesised for the *entire* topology (10 services + 2 externals): 15 min
baseline + 5 min incident at 10 s resolution, ~15 metrics per service, error/warn logs with
mined-template diversity, two checkout traces per step with parent/child spans, and
realistic propagation of error rate and latency from callee to caller weighted by call
fraction. Seeds are fixed → runs are reproducible.

## Procedure per case

1. Fresh project with the demo topology.
2. Load telemetry and any deployments.
3. Run the detector once (`evaluate_rules`) — the same code path production uses.
4. Pick the incident whose primary/affected set contains the target; run the full
   investigation pipeline synchronously (same orchestrator, same stages, same provider).
5. Compare the top hypothesis against ground truth; record metrics; purge raw telemetry.

Nothing in the harness has special knowledge: no fault labels reach the pipeline.

## Metrics

| Metric | Definition |
|---|---|
| Detection rate | fault cases where the detector opened an incident containing the target |
| Root-cause accuracy (top-1 / top-3) | expected category == rank-1 hypothesis / ∈ top 3 |
| Evidence precision | of the evidence cited as *supporting* the top hypothesis, the fraction carrying a signal that the **true** category lists as support (computed against ground truth, not against the prediction) |
| Citation validity | fraction of narrator citations that reference evidence Sentinel minted (1.0 for the deterministic narrator by construction; measures hallucinated handles for model providers) |
| False-positive rate | healthy controls that opened an incident |
| Confident-wrong rate | detected cases with a wrong top-1 **and** confidence ≥ threshold (0.55) — the number an on-call engineer actually cares about |
| Expected calibration error | 10-bin ECE between reported confidence and empirical accuracy |
| Onset → alert-condition gap | seconds from fault injection until the rule condition was first met (rule `for` + detector interval add to wall-clock detection) |
| Investigation latency | wall time of the pipeline per case (median, p95) and model time separately |

## Reading the numbers

* The deterministic run (`SENTINEL_LLM_PROVIDER=none`) measures the pipeline itself.
  Running with `ollama` measures *lift* (or damage) from narration/reordering, and
  citation validity becomes informative.
* Confusions are reported as a matrix; the interesting ones are the physically adjacent
  pairs (pool exhaustion vs query latency, deadlock vs thread starvation) — these are the
  cases where a human would also want the contradicting evidence shown.
* Latency is measured on SQLite with in-process execution; it is an upper bound relative
  to PostgreSQL.

## Threats to validity

* Synthetic telemetry follows the same failure models the fault engine implements; real
  systems are messier. Mitigation: the live simulator path (real HTTP, real timing) is
  exercised by the e2e test and the demo, and the OTel collector config lets Sentinel
  ingest real services unchanged.
* The catalog and the scenarios were written by the same people. Mitigation: variants
  with confounders, noise, weaker intensities and shifted targets; a healthy control set;
  and a CI quality gate so regressions are visible.

Run it: `make eval` → `docs/evaluation/latest.md` + `latest.json`.
