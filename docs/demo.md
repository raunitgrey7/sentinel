# The demo (11 steps, ~6 minutes)

Preparation: `make dev` (or `docker compose up`) and `make web`. Open http://localhost:3000,
log in as `admin@sentinel.local` / `admin12345`. Let the shop run for two minutes so the
baseline exists.

| # | Do | Say |
|---|---|---|
| 1 | **Overview** page | "Twelve services, all healthy. Sentinel is watching a real seven-service shop over HTTP — logs, metrics, traces, deployments. No cloud, no API keys; the model, if any, runs on this laptop." |
| 2 | **Chaos Lab** → `payment-service` / `db_pool_exhaustion` / 180 s → Inject | "We're going to break production on purpose. This is the fault Sentinel is *not* told about." |
| 3 | Back to **Overview**; watch payment-service go red, then order-service and the gateway | "Failure propagates up the call graph. A naïve system opens three incidents. Watch." |
| 4 | Point at the alert list | "Prometheus-style rules fire — deterministic, no model involved. `HighErrorRate` sustained 30 s." |
| 5 | **Incidents** — one incident, `INC-…`, primary `payment-service`, affected gateway + order | "One incident. The gateway alert was the symptom; Sentinel walked the dependency graph and re-pointed the primary suspect to the deepest failing service." |
| 6 | Open it; **Investigation** panel ticks through Timeline → Metrics → Logs → Traces → Deployments → Dependencies → Historical → Hypotheses → Synthesizer → Verifier | "Seven investigators, each deterministic and checkpointed. Kill the worker here and it resumes at the next stage." |
| 7 | **Root cause card**: *Database connection-pool exhaustion*, confidence ~80 % | "Not 99 %. Confidence is calibrated: three independent evidence kinds, one contradiction, no independent causal verification — the caveat says so." |
| 8 | Click **Why?** → ask "Why not CPU saturation?" | "Every sentence cites evidence handles minted by the system. E3 says CPU stayed flat — that's *contradicting* evidence, and it's on the card, not hidden." |
| 9 | **Evidence graph** tab | "Incident → services → evidence → hypotheses. Edges are `supports`/`contradicts` with weights; this is what the verifier walks." |
| 10 | **Remediation**: request *roll back* as engineer → approve as SRE → execute → verified | "Sentinel proposes; humans approve; four-eyes; every step audited. Agents have read-only tools by default." (If time: resolve → **Generate Postmortem**.) |
| 11 | **Evaluation** page | "This is the part I'd bet on. 118 synthetic incidents across 14 failure modes, healthy controls included: root-cause accuracy, evidence precision, false positives, calibration, latency — all reproducible in CI with `make eval`." |

Close: "The LLM is the least interesting part. The architecture is the product: telemetry
→ evidence → deterministic hypotheses → narration → verification → human decision."

## Fallbacks

* Model offline → the narrative is labelled *deterministic narrator*; everything else is identical.
* Want a deployment story instead → inject `bad_deployment`: the evidence cites commit
  `increase transaction concurrency from 8 to 64` and the playbook's first action is the rollback.
* Want a "no incident" story → `sentinel-sim scenario noise`.
