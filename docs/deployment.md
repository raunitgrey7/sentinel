# Deployment guide

## 1. Zero infrastructure (laptop, CI)

```bash
uv sync --all-extras                      # Python ≥ 3.12
uv run sentinel dev                       # API :8000 (SQLite, in-process queue+scheduler) + demo shop :9000-9007
cd web && npm install && npm run dev      # dashboard :3000
```
Login: `admin@sentinel.local` / `admin12345` (change via `SENTINEL_BOOTSTRAP_ADMIN_*`).

## 2. Docker Compose (recommended demo/prod-like)

```bash
cp .env.example .env                                  # change SENTINEL_SECRET_KEY & passwords for anything shared
docker compose up --build -d                          # postgres, redis, migrate, api, worker, simulator, web
docker compose --profile observability up -d          # + prometheus :9090, alertmanager :9093, grafana :3001, otel :4317/4318
docker compose --profile llm up -d                    # + ollama :11434 (pulls qwen2.5:7b + nomic-embed-text)
```
Set `SENTINEL_LLM_PROVIDER=ollama` in `.env` to use the model; leave `none` for the
deterministic narrator.

Services: web `:3000`, API `:8000` (`/docs`), simulator control `:9000`.

## 3. Production notes

* **TLS / ingress:** terminate TLS in front of `api` and `web` (nginx, Traefik, cloud LB).
  The API sets security headers but does not terminate TLS itself.
* **Secrets:** `SENTINEL_SECRET_KEY` (≥ 32 random bytes), `SENTINEL_BOOTSTRAP_ADMIN_PASSWORD`,
  `SENTINEL_BOOTSTRAP_INGEST_KEY`, database/redis DSNs — inject via your secret manager;
  never commit `.env`.
* **Scaling:** API is stateless (scale replicas behind the LB). Workers scale horizontally;
  ARQ coordinates through Redis. PostgreSQL is the only stateful component besides Redis.
* **Migrations:** `sentinel migrate` runs Alembic; the compose `migrate` job gates the API.
  `SENTINEL_AUTO_MIGRATE=false` in prod.
* **Retention:** raw telemetry is purged after `SENTINEL_TELEMETRY_RETENTION_HOURS`.
  Size PostgreSQL for `(services × metrics × 12/min × hours)` rows; the demo shop writes
  ~25k metric rows/hour.
* **Observability:** scrape `/metrics`; import the Grafana dashboard; alert on the
  `sentinel-self` Prometheus rules (slow investigations, dead letters, LLM circuit open).
* **Real telemetry:** point your OpenTelemetry SDKs at the collector (`:4317/4318`) or
  push directly to `/api/v1/ingest/*` with an ingestion key; register your topology via
  `/api/v1/projects/{ref}/dependencies`; mirror `infrastructure/prometheus/rules.yml` in
  your Prometheus and send Alertmanager to `/api/v1/webhooks/alerts`.

## 4. Kubernetes (later)

Not shipped on purpose (ADR-0001). The images are 12-factor: configuration by environment,
health/readiness endpoints, non-root, graceful shutdown on SIGTERM. A Helm chart would
consist of two Deployments (api, worker), one Job (migrate), the simulator as an optional
Deployment, and external PostgreSQL/Redis.
