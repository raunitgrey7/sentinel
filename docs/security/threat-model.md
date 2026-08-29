# Threat model

Scope: a self-hosted Sentinel deployment receiving telemetry from production services and
operated by an SRE team through the dashboard and API.

## Assets

* Telemetry (logs may contain secrets, PII, hostnames), incident evidence, postmortems
* Remediation capability (rollback/restart/scale against production)
* Credentials: admin password, JWT signing key, ingestion API keys, Redis/PostgreSQL DSNs
* The model host (Ollama) — an internal service with no authentication

## Trust boundaries

```
Internet ─┤ web (Next.js) ├─► API (JWT / API key) ─► PostgreSQL, Redis
telemetry producers ─(API key, ingest scope)─► API ingestion
API / worker ─► Ollama (localhost / private network only)
API ─► simulator control plane (private network only)
```

## Threats and controls

| Threat | Control | Where |
|---|---|---|
| Credential stuffing / weak auth | PBKDF2-HMAC-SHA256 (210k rounds, per-user salt), JWT with issuer + expiry, failed logins audited, rate limiting per client/key | `core/security.py`, `api/middleware.py` |
| Privilege escalation | Four roles with rank ordering; every mutating endpoint declares its minimum role; API keys carry scopes (`ingest`, `webhooks`) and cannot access user endpoints | `api/deps.py` |
| Telemetry producer abuse | Dedicated ingestion keys with `ingest` scope only; separate, higher rate limit; batch size caps (5 000 records); malformed records rejected per-record, not per-batch | `api/routers/ingest.py` |
| **Prompt injection via log/commit content** | Telemetry text is rendered inside `<telemetry>` blocks; system prompts instruct the model to treat it as data; the model can only cite handles Sentinel minted; the verifier discards unknown handles and re-derives confidence; categories come from the catalog, never from the model; JSON schema validation on every structured output | `llm/prompts.py`, `investigation/synthesizer.py`, `investigation/verifier.py` |
| Model exfiltration | No external model provider is configured; Ollama is reached over a private address; nothing leaves the host | `llm/ollama.py`, compose network |
| Unsafe automation | Recommendation-only default; four-eyes approval; executable kinds allow-listed; agent tool permission table denies mutating tools; every step audited | `remediation/service.py` |
| Chaos misuse | Fault injection requires SRE role; only the simulator target is reachable; every injection audited | `api/routers/faults.py` |
| Data retention | Raw telemetry purged after `SENTINEL_TELEMETRY_RETENTION_HOURS` (48 h); evidence keeps summaries, not raw logs | `worker/jobs.py` |
| Denial of service | Sliding-window rate limiter (memory or Redis), per-step investigation timeouts, job timeouts, circuit breaker on the model, bounded queue retries with dead-lettering | `core/ratelimit.py`, `core/resilience.py`, `queue/` |
| Transport | Security headers (`nosniff`, `DENY`, no-referrer); TLS termination is expected at the ingress (see deployment guide) | `api/middleware.py` |
| Secrets in repo | None. `.env.example` ships dev-only defaults; production must override `SENTINEL_SECRET_KEY`, admin password and ingestion key | `.env.example` |
| Supply chain | Locked dependencies (`uv.lock`, `package-lock.json`), pinned container images, non-root containers | Dockerfiles, CI |

## Known gaps (tracked)

* No SSO/OIDC yet; JWT + local users only.
* Ingestion is not authenticated per *service* — one key per project is the granularity.
* Ollama has no auth by design; keep it off public networks.
* Log redaction (PII masking at ingestion) is a planned normaliser step.
