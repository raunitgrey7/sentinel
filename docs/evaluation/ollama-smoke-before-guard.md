# Sentinel evaluation report

*Run `98aef6c9ad83467580fe5ca13c4565cd` · 2026-08-29T20:18:23.040856+00:00 · provider `ollama` / `qwen2.5:3b` · 3 cases (3 faults, 0 healthy controls) · wall time 917.5s*

## Headline metrics

| Metric | Value |
|---|---|
| Root-cause accuracy (top-1) | **66.7%** |
| Root-cause accuracy (top-3) | 100.0% |
| Detection rate | 100.0% |
| Evidence precision | 66.7% |
| Citation validity (evidence-backed claims) | 100.0% |
| False-positive rate (healthy controls) | 0.0% |
| Confident-wrong rate (wrong & ≥ 0.55) | 0.0% |
| Expected calibration error | 0.174 |
| Median investigation time | 247.86s |
| p95 investigation time | 247.86s |
| Mean onset→detection gap | 160.0s |
| Mean model time per investigation | 151.41s |

## Per fault type

| Fault | Cases | Detected | Top-1 | Top-3 | Mean confidence |
|---|---|---|---|---|---|
| db_pool_exhaustion | 1 | 1 | 100% | 100% | 0.40 |
| http_500_spike | 1 | 1 | 100% | 100% | 0.67 |
| redis_failure | 1 | 1 | 0% | 100% | 0.41 |

## Confusion (expected → predicted)

| Expected | Predicted | Count |
|---|---|---|
| database_connection_pool | database_connection_pool | 1 |
| deployment_regression | deployment_regression | 1 |
| redis_unavailable | database_latency | 1 |

## Cases

| Scenario | Expected | Predicted | Conf | Evidence precision | ms |
|---|---|---|---|---|---|
| db_pool_exhaustion/payment-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.40 | 1.00 | 406307 |
| redis_failure/auth-service/v1 | redis_unavailable | database_latency ✗ | 0.41 | 0.00 | 245169 |
| http_500_spike/order-service/v1 | deployment_regression | deployment_regression ✓ | 0.67 | 1.00 | 247858 |

Methodology: `docs/evaluation/methodology.md`.