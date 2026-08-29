# Sentinel evaluation report

*Run `053e8c5dcc14425f834519ab014e8b85` · 2026-08-29T19:07:03.764511+00:00 · provider `none` / `deterministic` · 119 cases (113 faults, 6 healthy controls) · wall time 1201.6s*

## Headline metrics

| Metric | Value |
|---|---|
| Root-cause accuracy (top-1) | **96.5%** |
| Root-cause accuracy (top-3) | 99.1% |
| Detection rate | 100.0% |
| Evidence precision | 97.5% |
| Citation validity (evidence-backed claims) | 100.0% |
| False-positive rate (healthy controls) | 0.0% |
| Confident-wrong rate (wrong & ≥ 0.55) | 1.8% |
| Expected calibration error | 0.288 |
| Median investigation time | 0.42s |
| p95 investigation time | 0.91s |
| Mean onset→detection gap | 163.2s |
| Mean model time per investigation | 0.00s |

## Per fault type

| Fault | Cases | Detected | Top-1 | Top-3 | Mean confidence |
|---|---|---|---|---|---|
| bad_deployment | 7 | 7 | 100% | 100% | 0.89 |
| config_regression | 7 | 7 | 100% | 100% | 0.70 |
| cpu_saturation | 11 | 11 | 91% | 100% | 0.54 |
| database_latency | 11 | 11 | 91% | 100% | 0.58 |
| db_pool_exhaustion | 11 | 11 | 91% | 91% | 0.75 |
| deadlock | 9 | 9 | 100% | 100% | 0.69 |
| dependency_failure | 4 | 4 | 100% | 100% | 0.66 |
| http_500_spike | 9 | 9 | 89% | 100% | 0.65 |
| memory_leak | 11 | 11 | 100% | 100% | 0.75 |
| network_latency | 4 | 4 | 100% | 100% | 0.50 |
| packet_loss | 4 | 4 | 100% | 100% | 0.70 |
| queue_backlog | 7 | 7 | 100% | 100% | 0.67 |
| redis_failure | 9 | 9 | 100% | 100% | 0.70 |
| thread_starvation | 9 | 9 | 100% | 100% | 0.67 |

## Confusion (expected → predicted)

| Expected | Predicted | Count |
|---|---|---|
| config_regression | config_regression | 7 |
| cpu_saturation | cpu_saturation | 10 |
| cpu_saturation | dependency_failure | 1 |
| database_connection_pool | database_connection_pool | 17 |
| database_connection_pool | dependency_failure | 1 |
| database_latency | database_latency | 10 |
| database_latency | dependency_failure | 1 |
| deadlock | deadlock | 9 |
| dependency_failure | dependency_failure | 4 |
| deployment_regression | deployment_regression | 8 |
| deployment_regression | dependency_failure | 1 |
| memory_exhaustion | memory_exhaustion | 11 |
| network_latency | network_latency | 4 |
| network_packet_loss | network_packet_loss | 4 |
| queue_backlog | queue_backlog | 7 |
| redis_unavailable | redis_unavailable | 9 |
| thread_starvation | thread_starvation | 9 |

## Cases

| Scenario | Expected | Predicted | Conf | Evidence precision | ms |
|---|---|---|---|---|---|
| db_pool_exhaustion/payment-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 727 |
| db_pool_exhaustion/payment-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.77 | 1.00 | 615 |
| db_pool_exhaustion/payment-service/v3 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 698 |
| db_pool_exhaustion/payment-service/v4 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 665 |
| db_pool_exhaustion/order-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.78 | 1.00 | 799 |
| db_pool_exhaustion/order-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.78 | 1.00 | 444 |
| db_pool_exhaustion/order-service/v3 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 495 |
| db_pool_exhaustion/inventory-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.75 | 1.00 | 334 |
| db_pool_exhaustion/inventory-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.75 | 1.00 | 351 |
| db_pool_exhaustion/auth-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.75 | 1.00 | 259 |
| db_pool_exhaustion/auth-service/v2 | database_connection_pool | dependency_failure ✗ | 0.46 | 0.60 | 236 |
| bad_deployment/payment-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.93 | 1.00 | 386 |
| bad_deployment/payment-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.90 | 1.00 | 390 |
| bad_deployment/payment-service/v3 | database_connection_pool | database_connection_pool ✓ | 0.89 | 1.00 | 288 |
| bad_deployment/payment-service/v4 | database_connection_pool | database_connection_pool ✓ | 0.90 | 1.00 | 290 |
| bad_deployment/order-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.88 | 1.00 | 315 |
| bad_deployment/order-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.87 | 1.00 | 322 |
| bad_deployment/order-service/v3 | database_connection_pool | database_connection_pool ✓ | 0.89 | 1.00 | 362 |
| database_latency/payment-service/v1 | database_latency | database_latency ✓ | 0.58 | 1.00 | 314 |
| database_latency/payment-service/v2 | database_latency | database_latency ✓ | 0.58 | 1.00 | 220 |
| database_latency/payment-service/v3 | database_latency | dependency_failure ✗ | 0.59 | 0.00 | 336 |
| database_latency/payment-service/v4 | database_latency | database_latency ✓ | 0.58 | 1.00 | 309 |
| database_latency/order-service/v1 | database_latency | database_latency ✓ | 0.58 | 1.00 | 457 |
| database_latency/order-service/v2 | database_latency | database_latency ✓ | 0.58 | 1.00 | 387 |
| database_latency/order-service/v3 | database_latency | database_latency ✓ | 0.58 | 1.00 | 371 |
| database_latency/inventory-service/v1 | database_latency | database_latency ✓ | 0.58 | 1.00 | 265 |
| database_latency/inventory-service/v2 | database_latency | database_latency ✓ | 0.58 | 1.00 | 260 |
| database_latency/auth-service/v1 | database_latency | database_latency ✓ | 0.58 | 1.00 | 214 |
| database_latency/auth-service/v2 | database_latency | database_latency ✓ | 0.58 | 1.00 | 252 |
| redis_failure/auth-service/v1 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 262 |
| redis_failure/auth-service/v2 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 264 |
| redis_failure/auth-service/v3 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 275 |
| redis_failure/auth-service/v4 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 387 |
| redis_failure/inventory-service/v1 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 322 |
| redis_failure/inventory-service/v2 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 294 |
| redis_failure/inventory-service/v3 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 343 |
| redis_failure/payment-service/v1 | redis_unavailable | redis_unavailable ✓ | 0.77 | 1.00 | 348 |
| redis_failure/payment-service/v2 | redis_unavailable | redis_unavailable ✓ | 0.77 | 1.00 | 285 |
| memory_leak/order-service/v1 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 471 |
| memory_leak/order-service/v2 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 374 |
| memory_leak/order-service/v3 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 386 |
| memory_leak/order-service/v4 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 308 |
| memory_leak/payment-service/v1 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 247 |
| memory_leak/payment-service/v2 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 292 |
| memory_leak/payment-service/v3 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 370 |
| memory_leak/api-gateway/v1 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 438 |
| memory_leak/api-gateway/v2 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 438 |
| memory_leak/inventory-service/v1 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 288 |
| memory_leak/inventory-service/v2 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 291 |
| cpu_saturation/api-gateway/v1 | cpu_saturation | cpu_saturation ✓ | 0.54 | 1.00 | 452 |
| cpu_saturation/api-gateway/v2 | cpu_saturation | cpu_saturation ✓ | 0.53 | 1.00 | 471 |
| cpu_saturation/api-gateway/v3 | cpu_saturation | cpu_saturation ✓ | 0.54 | 1.00 | 470 |
| cpu_saturation/api-gateway/v4 | cpu_saturation | cpu_saturation ✓ | 0.61 | 1.00 | 476 |
| cpu_saturation/order-service/v1 | cpu_saturation | cpu_saturation ✓ | 0.55 | 1.00 | 414 |
| cpu_saturation/order-service/v2 | cpu_saturation | cpu_saturation ✓ | 0.48 | 1.00 | 324 |
| cpu_saturation/order-service/v3 | cpu_saturation | dependency_failure ✗ | 0.54 | 0.00 | 354 |
| cpu_saturation/inventory-service/v1 | cpu_saturation | cpu_saturation ✓ | 0.55 | 1.00 | 284 |
| cpu_saturation/inventory-service/v2 | cpu_saturation | cpu_saturation ✓ | 0.55 | 1.00 | 403 |
| cpu_saturation/auth-service/v1 | cpu_saturation | cpu_saturation ✓ | 0.54 | 1.00 | 261 |
| cpu_saturation/auth-service/v2 | cpu_saturation | cpu_saturation ✓ | 0.53 | 1.00 | 317 |
| http_500_spike/order-service/v1 | deployment_regression | deployment_regression ✓ | 0.66 | 1.00 | 482 |
| http_500_spike/order-service/v2 | deployment_regression | deployment_regression ✓ | 0.66 | 1.00 | 613 |
| http_500_spike/order-service/v3 | deployment_regression | deployment_regression ✓ | 0.67 | 1.00 | 697 |
| http_500_spike/order-service/v4 | deployment_regression | dependency_failure ✗ | 0.59 | 0.62 | 771 |
| http_500_spike/payment-service/v1 | deployment_regression | deployment_regression ✓ | 0.65 | 1.00 | 600 |
| http_500_spike/payment-service/v2 | deployment_regression | deployment_regression ✓ | 0.66 | 1.00 | 373 |
| http_500_spike/payment-service/v3 | deployment_regression | deployment_regression ✓ | 0.67 | 1.00 | 621 |
| http_500_spike/api-gateway/v1 | deployment_regression | deployment_regression ✓ | 0.65 | 1.00 | 747 |
| http_500_spike/api-gateway/v2 | deployment_regression | deployment_regression ✓ | 0.65 | 1.00 | 931 |
| config_regression/payment-service/v1 | config_regression | config_regression ✓ | 0.71 | 1.00 | 691 |
| config_regression/payment-service/v2 | config_regression | config_regression ✓ | 0.71 | 1.00 | 1048 |
| config_regression/payment-service/v3 | config_regression | config_regression ✓ | 0.71 | 1.00 | 359 |
| config_regression/payment-service/v4 | config_regression | config_regression ✓ | 0.61 | 1.00 | 388 |
| config_regression/order-service/v1 | config_regression | config_regression ✓ | 0.71 | 1.00 | 524 |
| config_regression/order-service/v2 | config_regression | config_regression ✓ | 0.71 | 1.00 | 502 |
| config_regression/order-service/v3 | config_regression | config_regression ✓ | 0.71 | 1.00 | 509 |
| network_latency/order-service/v1 | network_latency | network_latency ✓ | 0.48 | 1.00 | 493 |
| network_latency/order-service/v2 | network_latency | network_latency ✓ | 0.48 | 1.00 | 482 |
| network_latency/order-service/v3 | network_latency | network_latency ✓ | 0.53 | 1.00 | 740 |
| network_latency/order-service/v4 | network_latency | network_latency ✓ | 0.51 | 1.00 | 905 |
| packet_loss/order-service/v1 | network_packet_loss | network_packet_loss ✓ | 0.71 | 1.00 | 2155 |
| packet_loss/order-service/v2 | network_packet_loss | network_packet_loss ✓ | 0.70 | 1.00 | 819 |
| packet_loss/order-service/v3 | network_packet_loss | network_packet_loss ✓ | 0.69 | 1.00 | 913 |
| packet_loss/order-service/v4 | network_packet_loss | network_packet_loss ✓ | 0.70 | 1.00 | 845 |
| queue_backlog/order-service/v1 | queue_backlog | queue_backlog ✓ | 0.67 | 1.00 | 787 |
| queue_backlog/order-service/v2 | queue_backlog | queue_backlog ✓ | 0.67 | 1.00 | 1337 |
| queue_backlog/order-service/v3 | queue_backlog | queue_backlog ✓ | 0.67 | 1.00 | 1005 |
| queue_backlog/order-service/v4 | queue_backlog | queue_backlog ✓ | 0.69 | 1.00 | 642 |
| queue_backlog/notification-worker/v1 | queue_backlog | queue_backlog ✓ | 0.67 | 1.00 | 332 |
| queue_backlog/notification-worker/v2 | queue_backlog | queue_backlog ✓ | 0.67 | 1.00 | 336 |
| queue_backlog/notification-worker/v3 | queue_backlog | queue_backlog ✓ | 0.67 | 1.00 | 357 |
| thread_starvation/order-service/v1 | thread_starvation | thread_starvation ✓ | 0.68 | 1.00 | 850 |
| thread_starvation/order-service/v2 | thread_starvation | thread_starvation ✓ | 0.63 | 1.00 | 493 |
| thread_starvation/order-service/v3 | thread_starvation | thread_starvation ✓ | 0.68 | 1.00 | 445 |
| thread_starvation/order-service/v4 | thread_starvation | thread_starvation ✓ | 0.75 | 1.00 | 516 |
| thread_starvation/api-gateway/v1 | thread_starvation | thread_starvation ✓ | 0.66 | 1.00 | 585 |
| thread_starvation/api-gateway/v2 | thread_starvation | thread_starvation ✓ | 0.66 | 1.00 | 492 |
| thread_starvation/api-gateway/v3 | thread_starvation | thread_starvation ✓ | 0.67 | 1.00 | 620 |
| thread_starvation/payment-service/v1 | thread_starvation | thread_starvation ✓ | 0.67 | 1.00 | 608 |
| thread_starvation/payment-service/v2 | thread_starvation | thread_starvation ✓ | 0.62 | 1.00 | 381 |
| deadlock/inventory-service/v1 | deadlock | deadlock ✓ | 0.68 | 1.00 | 418 |
| deadlock/inventory-service/v2 | deadlock | deadlock ✓ | 0.68 | 1.00 | 332 |
| deadlock/inventory-service/v3 | deadlock | deadlock ✓ | 0.67 | 1.00 | 539 |
| deadlock/inventory-service/v4 | deadlock | deadlock ✓ | 0.74 | 1.00 | 443 |
| deadlock/order-service/v1 | deadlock | deadlock ✓ | 0.68 | 1.00 | 479 |
| deadlock/order-service/v2 | deadlock | deadlock ✓ | 0.68 | 1.00 | 513 |
| deadlock/order-service/v3 | deadlock | deadlock ✓ | 0.68 | 1.00 | 532 |
| deadlock/payment-service/v1 | deadlock | deadlock ✓ | 0.68 | 1.00 | 519 |
| deadlock/payment-service/v2 | deadlock | deadlock ✓ | 0.68 | 1.00 | 398 |
| dependency_failure/payment-service/v1 | dependency_failure | dependency_failure ✓ | 0.66 | 1.00 | 484 |
| dependency_failure/payment-service/v2 | dependency_failure | dependency_failure ✓ | 0.65 | 1.00 | 413 |
| dependency_failure/payment-service/v3 | dependency_failure | dependency_failure ✓ | 0.68 | 1.00 | 430 |
| dependency_failure/payment-service/v4 | dependency_failure | dependency_failure ✓ | 0.65 | 1.00 | 402 |
| control/healthy/v1 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v2 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v3 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v4 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v5 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v6 | none | none ✓ | 0.00 | 0.00 | 0 |

Methodology: `docs/evaluation/methodology.md`.