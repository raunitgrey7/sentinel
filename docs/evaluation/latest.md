# Sentinel evaluation report

*Run `279b7f94e73544da9a8addae03b2602d` · 2026-08-29T19:33:55.728513+00:00 · provider `none` / `deterministic` · 119 cases (113 faults, 6 healthy controls) · wall time 1109.3s*

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
| Expected calibration error | 0.322 |
| Median investigation time | 0.39s |
| p95 investigation time | 0.63s |
| Mean onset→detection gap | 161.4s |
| Mean model time per investigation | 0.00s |

## Per fault type

| Fault | Cases | Detected | Top-1 | Top-3 | Mean confidence |
|---|---|---|---|---|---|
| bad_deployment | 7 | 7 | 100% | 100% | 0.89 |
| config_regression | 7 | 7 | 100% | 100% | 0.70 |
| cpu_saturation | 11 | 11 | 100% | 100% | 0.55 |
| database_latency | 11 | 11 | 100% | 100% | 0.58 |
| db_pool_exhaustion | 11 | 11 | 100% | 100% | 0.79 |
| deadlock | 9 | 9 | 100% | 100% | 0.69 |
| dependency_failure | 4 | 4 | 100% | 100% | 0.56 |
| http_500_spike | 9 | 9 | 100% | 100% | 0.65 |
| memory_leak | 11 | 11 | 100% | 100% | 0.75 |
| network_latency | 4 | 4 | 100% | 100% | 0.50 |
| packet_loss | 4 | 4 | 100% | 100% | 0.70 |
| queue_backlog | 7 | 7 | 100% | 100% | 0.68 |
| redis_failure | 9 | 9 | 100% | 100% | 0.70 |
| thread_starvation | 9 | 9 | 100% | 100% | 0.67 |

## Confusion (expected → predicted)

| Expected | Predicted | Count |
|---|---|---|
| config_regression | config_regression | 7 |
| cpu_saturation | cpu_saturation | 11 |
| database_connection_pool | database_connection_pool | 18 |
| database_latency | database_latency | 11 |
| deadlock | deadlock | 9 |
| dependency_failure | dependency_failure | 4 |
| deployment_regression | deployment_regression | 9 |
| memory_exhaustion | memory_exhaustion | 11 |
| network_latency | network_latency | 4 |
| network_packet_loss | network_packet_loss | 4 |
| queue_backlog | queue_backlog | 7 |
| redis_unavailable | redis_unavailable | 9 |
| thread_starvation | thread_starvation | 9 |

## Cases

| Scenario | Expected | Predicted | Conf | Evidence precision | ms |
|---|---|---|---|---|---|
| db_pool_exhaustion/payment-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.85 | 1.00 | 435 |
| db_pool_exhaustion/payment-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.82 | 1.00 | 310 |
| db_pool_exhaustion/payment-service/v3 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 346 |
| db_pool_exhaustion/payment-service/v4 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 400 |
| db_pool_exhaustion/order-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.80 | 1.00 | 355 |
| db_pool_exhaustion/order-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.77 | 1.00 | 426 |
| db_pool_exhaustion/order-service/v3 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 453 |
| db_pool_exhaustion/inventory-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 284 |
| db_pool_exhaustion/inventory-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.79 | 1.00 | 363 |
| db_pool_exhaustion/auth-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.77 | 1.00 | 288 |
| db_pool_exhaustion/auth-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.75 | 1.00 | 317 |
| bad_deployment/payment-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.92 | 1.00 | 438 |
| bad_deployment/payment-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.91 | 1.00 | 349 |
| bad_deployment/payment-service/v3 | database_connection_pool | database_connection_pool ✓ | 0.88 | 1.00 | 484 |
| bad_deployment/payment-service/v4 | database_connection_pool | database_connection_pool ✓ | 0.86 | 1.00 | 398 |
| bad_deployment/order-service/v1 | database_connection_pool | database_connection_pool ✓ | 0.89 | 1.00 | 394 |
| bad_deployment/order-service/v2 | database_connection_pool | database_connection_pool ✓ | 0.88 | 1.00 | 379 |
| bad_deployment/order-service/v3 | database_connection_pool | database_connection_pool ✓ | 0.89 | 1.00 | 476 |
| database_latency/payment-service/v1 | database_latency | database_latency ✓ | 0.58 | 1.00 | 402 |
| database_latency/payment-service/v2 | database_latency | database_latency ✓ | 0.58 | 1.00 | 236 |
| database_latency/payment-service/v3 | database_latency | database_latency ✓ | 0.58 | 1.00 | 362 |
| database_latency/payment-service/v4 | database_latency | database_latency ✓ | 0.58 | 1.00 | 369 |
| database_latency/order-service/v1 | database_latency | database_latency ✓ | 0.58 | 1.00 | 380 |
| database_latency/order-service/v2 | database_latency | database_latency ✓ | 0.58 | 1.00 | 347 |
| database_latency/order-service/v3 | database_latency | database_latency ✓ | 0.58 | 1.00 | 434 |
| database_latency/inventory-service/v1 | database_latency | database_latency ✓ | 0.58 | 1.00 | 637 |
| database_latency/inventory-service/v2 | database_latency | database_latency ✓ | 0.58 | 1.00 | 402 |
| database_latency/auth-service/v1 | database_latency | database_latency ✓ | 0.58 | 1.00 | 219 |
| database_latency/auth-service/v2 | database_latency | database_latency ✓ | 0.58 | 1.00 | 249 |
| redis_failure/auth-service/v1 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 310 |
| redis_failure/auth-service/v2 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 327 |
| redis_failure/auth-service/v3 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 293 |
| redis_failure/auth-service/v4 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 236 |
| redis_failure/inventory-service/v1 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 337 |
| redis_failure/inventory-service/v2 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 333 |
| redis_failure/inventory-service/v3 | redis_unavailable | redis_unavailable ✓ | 0.68 | 1.00 | 385 |
| redis_failure/payment-service/v1 | redis_unavailable | redis_unavailable ✓ | 0.77 | 1.00 | 323 |
| redis_failure/payment-service/v2 | redis_unavailable | redis_unavailable ✓ | 0.77 | 1.00 | 416 |
| memory_leak/order-service/v1 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 390 |
| memory_leak/order-service/v2 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 443 |
| memory_leak/order-service/v3 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 426 |
| memory_leak/order-service/v4 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 486 |
| memory_leak/payment-service/v1 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 396 |
| memory_leak/payment-service/v2 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 514 |
| memory_leak/payment-service/v3 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 349 |
| memory_leak/api-gateway/v1 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 502 |
| memory_leak/api-gateway/v2 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 508 |
| memory_leak/inventory-service/v1 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 290 |
| memory_leak/inventory-service/v2 | memory_exhaustion | memory_exhaustion ✓ | 0.75 | 1.00 | 256 |
| cpu_saturation/api-gateway/v1 | cpu_saturation | cpu_saturation ✓ | 0.55 | 1.00 | 640 |
| cpu_saturation/api-gateway/v2 | cpu_saturation | cpu_saturation ✓ | 0.53 | 1.00 | 516 |
| cpu_saturation/api-gateway/v3 | cpu_saturation | cpu_saturation ✓ | 0.53 | 1.00 | 486 |
| cpu_saturation/api-gateway/v4 | cpu_saturation | cpu_saturation ✓ | 0.63 | 1.00 | 563 |
| cpu_saturation/order-service/v1 | cpu_saturation | cpu_saturation ✓ | 0.55 | 1.00 | 480 |
| cpu_saturation/order-service/v2 | cpu_saturation | cpu_saturation ✓ | 0.48 | 1.00 | 303 |
| cpu_saturation/order-service/v3 | cpu_saturation | cpu_saturation ✓ | 0.54 | 1.00 | 447 |
| cpu_saturation/inventory-service/v1 | cpu_saturation | cpu_saturation ✓ | 0.56 | 1.00 | 250 |
| cpu_saturation/inventory-service/v2 | cpu_saturation | cpu_saturation ✓ | 0.54 | 1.00 | 301 |
| cpu_saturation/auth-service/v1 | cpu_saturation | cpu_saturation ✓ | 0.54 | 1.00 | 295 |
| cpu_saturation/auth-service/v2 | cpu_saturation | cpu_saturation ✓ | 0.53 | 1.00 | 309 |
| http_500_spike/order-service/v1 | deployment_regression | deployment_regression ✓ | 0.68 | 1.00 | 386 |
| http_500_spike/order-service/v2 | deployment_regression | deployment_regression ✓ | 0.66 | 1.00 | 346 |
| http_500_spike/order-service/v3 | deployment_regression | deployment_regression ✓ | 0.67 | 1.00 | 438 |
| http_500_spike/order-service/v4 | deployment_regression | deployment_regression ✓ | 0.57 | 1.00 | 404 |
| http_500_spike/payment-service/v1 | deployment_regression | deployment_regression ✓ | 0.66 | 1.00 | 383 |
| http_500_spike/payment-service/v2 | deployment_regression | deployment_regression ✓ | 0.66 | 1.00 | 333 |
| http_500_spike/payment-service/v3 | deployment_regression | deployment_regression ✓ | 0.66 | 1.00 | 355 |
| http_500_spike/api-gateway/v1 | deployment_regression | deployment_regression ✓ | 0.65 | 1.00 | 551 |
| http_500_spike/api-gateway/v2 | deployment_regression | deployment_regression ✓ | 0.66 | 1.00 | 584 |
| config_regression/payment-service/v1 | config_regression | config_regression ✓ | 0.71 | 1.00 | 485 |
| config_regression/payment-service/v2 | config_regression | config_regression ✓ | 0.71 | 1.00 | 434 |
| config_regression/payment-service/v3 | config_regression | config_regression ✓ | 0.72 | 1.00 | 386 |
| config_regression/payment-service/v4 | config_regression | config_regression ✓ | 0.61 | 1.00 | 342 |
| config_regression/order-service/v1 | config_regression | config_regression ✓ | 0.71 | 1.00 | 552 |
| config_regression/order-service/v2 | config_regression | config_regression ✓ | 0.71 | 1.00 | 583 |
| config_regression/order-service/v3 | config_regression | config_regression ✓ | 0.72 | 1.00 | 651 |
| network_latency/order-service/v1 | network_latency | network_latency ✓ | 0.48 | 1.00 | 340 |
| network_latency/order-service/v2 | network_latency | network_latency ✓ | 0.49 | 1.00 | 354 |
| network_latency/order-service/v3 | network_latency | network_latency ✓ | 0.53 | 1.00 | 556 |
| network_latency/order-service/v4 | network_latency | network_latency ✓ | 0.51 | 1.00 | 292 |
| packet_loss/order-service/v1 | network_packet_loss | network_packet_loss ✓ | 0.70 | 1.00 | 507 |
| packet_loss/order-service/v2 | network_packet_loss | network_packet_loss ✓ | 0.69 | 1.00 | 403 |
| packet_loss/order-service/v3 | network_packet_loss | network_packet_loss ✓ | 0.71 | 1.00 | 464 |
| packet_loss/order-service/v4 | network_packet_loss | network_packet_loss ✓ | 0.71 | 1.00 | 505 |
| queue_backlog/order-service/v1 | queue_backlog | queue_backlog ✓ | 0.68 | 1.00 | 456 |
| queue_backlog/order-service/v2 | queue_backlog | queue_backlog ✓ | 0.68 | 1.00 | 342 |
| queue_backlog/order-service/v3 | queue_backlog | queue_backlog ✓ | 0.68 | 1.00 | 359 |
| queue_backlog/order-service/v4 | queue_backlog | queue_backlog ✓ | 0.70 | 1.00 | 372 |
| queue_backlog/notification-worker/v1 | queue_backlog | queue_backlog ✓ | 0.67 | 1.00 | 152 |
| queue_backlog/notification-worker/v2 | queue_backlog | queue_backlog ✓ | 0.68 | 1.00 | 249 |
| queue_backlog/notification-worker/v3 | queue_backlog | queue_backlog ✓ | 0.67 | 1.00 | 303 |
| thread_starvation/order-service/v1 | thread_starvation | thread_starvation ✓ | 0.66 | 1.00 | 480 |
| thread_starvation/order-service/v2 | thread_starvation | thread_starvation ✓ | 0.63 | 1.00 | 1777 |
| thread_starvation/order-service/v3 | thread_starvation | thread_starvation ✓ | 0.68 | 1.00 | 525 |
| thread_starvation/order-service/v4 | thread_starvation | thread_starvation ✓ | 0.75 | 1.00 | 415 |
| thread_starvation/api-gateway/v1 | thread_starvation | thread_starvation ✓ | 0.68 | 1.00 | 560 |
| thread_starvation/api-gateway/v2 | thread_starvation | thread_starvation ✓ | 0.65 | 1.00 | 556 |
| thread_starvation/api-gateway/v3 | thread_starvation | thread_starvation ✓ | 0.65 | 1.00 | 625 |
| thread_starvation/payment-service/v1 | thread_starvation | thread_starvation ✓ | 0.67 | 1.00 | 375 |
| thread_starvation/payment-service/v2 | thread_starvation | thread_starvation ✓ | 0.62 | 1.00 | 298 |
| deadlock/inventory-service/v1 | deadlock | deadlock ✓ | 0.68 | 1.00 | 361 |
| deadlock/inventory-service/v2 | deadlock | deadlock ✓ | 0.68 | 1.00 | 365 |
| deadlock/inventory-service/v3 | deadlock | deadlock ✓ | 0.68 | 1.00 | 366 |
| deadlock/inventory-service/v4 | deadlock | deadlock ✓ | 0.74 | 1.00 | 351 |
| deadlock/order-service/v1 | deadlock | deadlock ✓ | 0.68 | 1.00 | 700 |
| deadlock/order-service/v2 | deadlock | deadlock ✓ | 0.68 | 1.00 | 477 |
| deadlock/order-service/v3 | deadlock | deadlock ✓ | 0.68 | 1.00 | 720 |
| deadlock/payment-service/v1 | deadlock | deadlock ✓ | 0.68 | 1.00 | 391 |
| deadlock/payment-service/v2 | deadlock | deadlock ✓ | 0.68 | 1.00 | 562 |
| dependency_failure/payment-service/v1 | dependency_failure | dependency_failure ✓ | 0.56 | 1.00 | 510 |
| dependency_failure/payment-service/v2 | dependency_failure | dependency_failure ✓ | 0.56 | 1.00 | 514 |
| dependency_failure/payment-service/v3 | dependency_failure | dependency_failure ✓ | 0.56 | 1.00 | 461 |
| dependency_failure/payment-service/v4 | dependency_failure | dependency_failure ✓ | 0.56 | 1.00 | 516 |
| control/healthy/v1 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v2 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v3 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v4 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v5 | none | none ✓ | 0.00 | 0.00 | 0 |
| control/healthy/v6 | none | none ✓ | 0.00 | 0.00 | 0 |

Methodology: `docs/evaluation/methodology.md`.