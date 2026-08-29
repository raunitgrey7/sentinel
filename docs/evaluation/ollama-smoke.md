# Sentinel evaluation report

*Run `ac004e1e4ecb4f8e84f992daeae0ad50` · 2026-08-29T20:32:19.954761+00:00 · provider `ollama` / `qwen2.5:3b` · 3 cases (3 faults, 0 healthy controls) · wall time 831.7s*

## Headline metrics

| Metric | Value |
|---|---|
| Root-cause accuracy (top-1) | **100.0%** |
| Root-cause accuracy (top-3) | 100.0% |
| Detection rate | 100.0% |
| Evidence precision | 100.0% |
| Citation validity (evidence-backed claims) | 100.0% |
| False-positive rate (healthy controls) | 0.0% |
| Confident-wrong rate (wrong & ≥ 0.55) | 0.0% |
| Expected calibration error | 0.471 |
| Median investigation time | 260.81s |
| p95 investigation time | 260.81s |
| Mean onset→detection gap | 160.0s |
| Mean model time per investigation | 226.11s |

## Per fault type

| Fault | Cases | Detected | Top-1 | Top-3 | Mean confidence |
|---|---|---|---|---|---|
| db_pool_exhaustion | 1 | 1 | 100% | 100% | 0.48 |
| http_500_spike | 1 | 1 | 100% | 100% | 0.68 |
| redis_failure | 1 | 1 | 100% | 100% | 0.43 |

## Confusion (expected → predicted)

| Expected | Predicted | Count |
|---|---|---|
| database_connection_pool | database_connection_pool | 1 |
| deployment_regression | deployment_regression | 1 |
| redis_unavailable | redis_unavailable | 1 |

## Cases

| Scenario | Expected | Predicted | Conf | Evidence precision | ms |
|---|---|---|---|---|---|
| db_pool_exhaustion/payment-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.48 | 1.00 | 337314 |
| redis_failure/auth-service/v1 | redis_unavailable | redis_unavailable ✓ | 0.43 | 1.00 | 260806 |
| http_500_spike/order-service/v1 | deployment_regression | deployment_regression ✓ | 0.68 | 1.00 | 213523 |

Methodology: `docs/evaluation/methodology.md`.