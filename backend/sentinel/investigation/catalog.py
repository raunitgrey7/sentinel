"""Root-cause catalog.

Each entry describes a failure mode in terms of the *signals* the investigators can
observe. Investigators tag evidence with signal names (``db_pool_saturated``,
``latency_up``, ``deploy_recent`` ...); the hypothesis generator matches those tags
against this catalog to build candidates, and the scorer weighs them.

This is the deterministic "domain knowledge" layer — the LLM never decides which
categories exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sentinel.domain.enums import RootCauseCategory as RC


@dataclass(frozen=True)
class SignalRule:
    signal: str
    weight: float  # contribution when present (0..1)
    required: bool = False  # hypothesis is not even generated without it


@dataclass(frozen=True)
class RemediationStep:
    kind: str  # rollback|scale|config|restart|alert|manual|failover|drain
    title: str
    description: str
    risk: str = "medium"
    executable: bool = False


@dataclass(frozen=True)
class RootCause:
    category: RC
    title: str
    description: str
    component: str  # what component is implicated: app|database|cache|queue|network|infra|deploy
    supports: tuple[SignalRule, ...]
    contradicts: tuple[SignalRule, ...] = ()
    deployment_sensitive: bool = False  # a recent deploy is corroborating
    remediation: tuple[RemediationStep, ...] = ()
    keywords: tuple[str, ...] = field(default_factory=tuple)


CATALOG: dict[RC, RootCause] = {
    RC.DATABASE_CONNECTION_POOL: RootCause(
        category=RC.DATABASE_CONNECTION_POOL,
        title="Database connection-pool exhaustion",
        description="The service's DB connection pool is saturated; requests wait for a connection and time out.",
        component="database",
        supports=(
            SignalRule("db_pool_saturated", 0.35, required=True),
            SignalRule("db_pool_waiting_up", 0.2),
            SignalRule("db_acquire_latency_up", 0.25),
            SignalRule("log_pool_exhausted", 0.25),
            SignalRule("trace_db_acquire_slow", 0.2),
            SignalRule("error_rate_up", 0.1),
            SignalRule("latency_up", 0.05),
            SignalRule("deploy_touches_db_config", 0.15),
        ),
        contradicts=(SignalRule("db_query_latency_up", 0.15), SignalRule("cpu_up", 0.05)),
        deployment_sensitive=True,
        remediation=(
            RemediationStep("rollback", "Roll back the most recent deployment", "If the pool pressure started after a deploy, rolling back restores the previous concurrency profile.", "medium", True),
            RemediationStep("config", "Reduce transaction concurrency", "Lower worker/transaction concurrency so demand fits the pool ceiling.", "low", False),
            RemediationStep("config", "Raise the pool ceiling after validating DB capacity", "Only after confirming the database can hold more connections.", "medium", False),
            RemediationStep("alert", "Alert on connection-acquisition latency", "Add a leading-indicator alert on db_connection_acquire_ms.", "low", False),
        ),
        keywords=("pool", "connection", "acquire", "exhaust"),
    ),
    RC.DATABASE_LATENCY: RootCause(
        category=RC.DATABASE_LATENCY,
        title="Database query latency degradation",
        description="Queries themselves are slow (lock contention, missing index, I/O pressure), inflating request latency.",
        component="database",
        supports=(
            SignalRule("db_query_latency_up", 0.4, required=True),
            SignalRule("trace_db_query_slow", 0.25),
            SignalRule("latency_up", 0.15),
            SignalRule("log_db_slow", 0.2),
            SignalRule("db_pool_waiting_up", 0.1),
        ),
        contradicts=(SignalRule("db_pool_saturated", 0.1), SignalRule("db_latency_flat", 0.3)),
        remediation=(
            RemediationStep("manual", "Inspect slow-query log and lock waits", "Identify the offending statements or lock chains.", "low"),
            RemediationStep("config", "Add statement timeout / shed load", "Bound query time so latency does not cascade.", "medium"),
        ),
        keywords=("slow query", "lock", "deadlock detected", "statement"),
    ),
    RC.REDIS_UNAVAILABLE: RootCause(
        category=RC.REDIS_UNAVAILABLE,
        title="Cache (Redis) unavailable",
        description="Cache operations fail or time out; services fall back to slow paths or error.",
        component="cache",
        supports=(
            SignalRule("redis_errors_up", 0.45, required=True),
            SignalRule("log_redis_error", 0.3),
            SignalRule("trace_cache_error", 0.2),
            SignalRule("cache_hit_rate_down", 0.15),
            SignalRule("error_rate_up", 0.1),
        ),
        contradicts=(SignalRule("db_pool_saturated", 0.1),),
        remediation=(
            RemediationStep("failover", "Fail over / restart the cache", "Restore the cache endpoint; verify connectivity.", "medium"),
            RemediationStep("config", "Enable cache-miss fallback with a circuit breaker", "Prevent cache failure from becoming request failure.", "low"),
        ),
        keywords=("redis", "cache", "ECONNREFUSED"),
    ),
    RC.MEMORY_EXHAUSTION: RootCause(
        category=RC.MEMORY_EXHAUSTION,
        title="Memory exhaustion / leak",
        description="Process memory grows until GC pressure or OOM kills degrade the service.",
        component="app",
        supports=(
            SignalRule("memory_up", 0.4, required=True),
            SignalRule("memory_trend_monotonic", 0.25),
            SignalRule("log_oom", 0.3),
            SignalRule("restart_count_up", 0.2),
            SignalRule("latency_up", 0.1),
            SignalRule("gc_pause_up", 0.15),
        ),
        contradicts=(SignalRule("memory_flat", 0.4),),
        deployment_sensitive=True,
        remediation=(
            RemediationStep("restart", "Restart affected instances to reclaim memory", "Short-term relief while the leak is fixed.", "medium", True),
            RemediationStep("rollback", "Roll back if the leak coincides with a deployment", "", "medium", True),
            RemediationStep("manual", "Capture a heap profile", "Identify the retaining objects.", "low"),
        ),
        keywords=("out of memory", "OOM", "heap", "GC"),
    ),
    RC.CPU_SATURATION: RootCause(
        category=RC.CPU_SATURATION,
        title="CPU saturation",
        description="The service is CPU-bound; request processing queues and latency climbs.",
        component="app",
        supports=(
            SignalRule("cpu_up", 0.45, required=True),
            SignalRule("latency_up", 0.2),
            SignalRule("throughput_down", 0.1),
            SignalRule("log_cpu_throttle", 0.15),
            SignalRule("request_rate_up", 0.1),
        ),
        contradicts=(SignalRule("cpu_flat", 0.45),),
        deployment_sensitive=True,
        remediation=(
            RemediationStep("scale", "Scale out the service", "Add replicas to spread CPU load.", "low", True),
            RemediationStep("rollback", "Roll back if a deploy introduced a hot path", "", "medium", True),
        ),
        keywords=("cpu", "throttl", "busy"),
    ),
    RC.DEPLOYMENT_REGRESSION: RootCause(
        category=RC.DEPLOYMENT_REGRESSION,
        title="Regression introduced by a deployment",
        description="Errors begin immediately after a version change with no infrastructure signal.",
        component="deploy",
        supports=(
            SignalRule("deploy_recent", 0.4, required=True),
            SignalRule("error_rate_up", 0.25),
            SignalRule("log_exception_new", 0.25),
            SignalRule("deploy_only_changed_service", 0.15),
            SignalRule("historical_similar", 0.05),
        ),
        contradicts=(
            SignalRule("db_pool_saturated", 0.2),
            SignalRule("cpu_up", 0.1),
            SignalRule("memory_up", 0.1),
            SignalRule("redis_errors_up", 0.15),
            SignalRule("network_latency_up", 0.15),
        ),
        deployment_sensitive=True,
        remediation=(
            RemediationStep("rollback", "Roll back to the previous version", "Fastest path to recovery for a code regression.", "medium", True),
            RemediationStep("manual", "Review the deploy diff for the failing code path", "", "low"),
        ),
        keywords=("exception", "NullPointer", "TypeError", "500"),
    ),
    RC.NETWORK_LATENCY: RootCause(
        category=RC.NETWORK_LATENCY,
        title="Network latency to a dependency",
        description="Calls to a downstream dependency are slow while the dependency itself is healthy.",
        component="network",
        supports=(
            SignalRule("network_latency_up", 0.4, required=True),
            SignalRule("trace_client_slow_server_ok", 0.3),
            SignalRule("latency_up", 0.15),
            SignalRule("log_timeout", 0.15),
        ),
        contradicts=(SignalRule("db_pool_saturated", 0.1), SignalRule("cpu_up", 0.1)),
        remediation=(
            RemediationStep("manual", "Check network path / service mesh between caller and dependency", "", "low"),
            RemediationStep("config", "Tighten client timeouts and add retries with budget", "", "low"),
        ),
        keywords=("timeout", "latency", "slow upstream"),
    ),
    RC.NETWORK_PACKET_LOSS: RootCause(
        category=RC.NETWORK_PACKET_LOSS,
        title="Network packet loss / connection resets",
        description="Intermittent connection failures to a dependency (resets, refused, EOF).",
        component="network",
        supports=(
            SignalRule("network_errors_up", 0.45, required=True),
            SignalRule("log_connection_reset", 0.3),
            SignalRule("trace_client_error", 0.2),
            SignalRule("error_rate_up", 0.1),
        ),
        contradicts=(SignalRule("network_latency_up", 0.05),),
        remediation=(
            RemediationStep("manual", "Inspect network / load balancer health", "", "low"),
            RemediationStep("config", "Enable idempotent retries for connection-level failures", "", "low"),
        ),
        keywords=("reset", "EOF", "refused", "broken pipe"),
    ),
    RC.DEPENDENCY_FAILURE: RootCause(
        category=RC.DEPENDENCY_FAILURE,
        title="Downstream dependency failing",
        description="A called service is returning errors; the failure propagates upstream.",
        component="app",
        supports=(
            SignalRule("dependency_error_rate_up", 0.45, required=True),
            SignalRule("trace_downstream_error", 0.25),
            SignalRule("log_upstream_5xx", 0.2),
            SignalRule("error_rate_up", 0.1),
        ),
        contradicts=(),
        remediation=(
            RemediationStep("manual", "Investigate the failing dependency as its own incident", "", "low"),
            RemediationStep("config", "Add a circuit breaker / fallback for the dependency", "", "low"),
        ),
        keywords=("upstream", "dependency", "503", "502"),
    ),
    RC.QUEUE_BACKLOG: RootCause(
        category=RC.QUEUE_BACKLOG,
        title="Message-queue backlog",
        description="Consumers fall behind producers; queue depth and processing lag grow.",
        component="queue",
        supports=(
            SignalRule("queue_depth_up", 0.45, required=True),
            SignalRule("consumer_lag_up", 0.25),
            SignalRule("log_queue_backlog", 0.2),
            SignalRule("worker_errors_up", 0.15),
        ),
        contradicts=(SignalRule("queue_depth_flat", 0.4),),
        remediation=(
            RemediationStep("scale", "Scale consumers", "", "low", True),
            RemediationStep("manual", "Check consumer health and poison messages", "", "low"),
        ),
        keywords=("queue", "backlog", "lag", "consumer"),
    ),
    RC.THREAD_STARVATION: RootCause(
        category=RC.THREAD_STARVATION,
        title="Worker/thread pool starvation",
        description="All request workers are busy or blocked; new requests queue and time out.",
        component="app",
        supports=(
            SignalRule("thread_pool_saturated", 0.45, required=True),
            SignalRule("log_thread_starvation", 0.25),
            SignalRule("latency_up", 0.15),
            SignalRule("throughput_down", 0.1),
        ),
        contradicts=(SignalRule("cpu_up", 0.15), SignalRule("db_pool_saturated", 0.1)),
        deployment_sensitive=True,
        remediation=(
            RemediationStep("restart", "Restart the service to release blocked workers", "", "medium", True),
            RemediationStep("manual", "Find the blocking call (thread dump)", "", "low"),
        ),
        keywords=("thread", "worker", "starv", "blocked"),
    ),
    RC.CONFIG_REGRESSION: RootCause(
        category=RC.CONFIG_REGRESSION,
        title="Configuration regression",
        description="A configuration change (not code) altered runtime behaviour (timeouts, limits, feature flags).",
        component="deploy",
        supports=(
            SignalRule("config_change_recent", 0.45, required=True),
            SignalRule("error_rate_up", 0.15),
            SignalRule("log_config_error", 0.25),
            SignalRule("latency_up", 0.1),
        ),
        contradicts=(SignalRule("cpu_up", 0.05), SignalRule("memory_up", 0.05)),
        deployment_sensitive=True,
        remediation=(
            RemediationStep("rollback", "Revert the configuration change", "", "low", True),
            RemediationStep("manual", "Validate configuration in a canary before rollout", "", "low"),
        ),
        keywords=("config", "flag", "setting", "invalid value"),
    ),
    RC.DEADLOCK: RootCause(
        category=RC.DEADLOCK,
        title="Application deadlock",
        description="Requests hang indefinitely; throughput collapses while CPU stays idle.",
        component="app",
        supports=(
            SignalRule("throughput_collapse", 0.35, required=True),
            SignalRule("log_deadlock", 0.35),
            SignalRule("inflight_requests_up", 0.2),
            SignalRule("cpu_flat", 0.1),
            SignalRule("latency_up", 0.1),
        ),
        contradicts=(SignalRule("cpu_up", 0.3), SignalRule("db_pool_saturated", 0.1)),
        deployment_sensitive=True,
        remediation=(
            RemediationStep("restart", "Restart the deadlocked instances", "", "medium", True),
            RemediationStep("manual", "Capture thread dump; fix lock ordering", "", "low"),
        ),
        keywords=("deadlock", "hung", "lock wait"),
    ),
}


def required_signals(rc: RootCause) -> set[str]:
    return {s.signal for s in rc.supports if s.required}


def all_signals() -> set[str]:
    out: set[str] = set()
    for rc in CATALOG.values():
        out.update(s.signal for s in rc.supports)
        out.update(s.signal for s in rc.contradicts)
    return out
