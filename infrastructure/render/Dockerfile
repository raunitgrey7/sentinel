# Sentinel demo backend for Render (free tier): API + demo shop in one container.
# Free instances have 0.1 CPU / 512 MB and spin down when idle, so the demo runs a
# gentler traffic rate and detector cadence than the local/compose defaults.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 UV_SYSTEM_PYTHON=1
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock LICENSE ./
COPY backend ./backend
COPY simulator ./simulator
RUN printf 'demo backend\n' > README.md && uv pip install --system --no-cache .
COPY infrastructure/docker/entrypoint.sh /usr/local/bin/sentinel-entrypoint
RUN chmod +x /usr/local/bin/sentinel-entrypoint && useradd -m -u 1000 sentinel && mkdir -p /app/data && chown -R sentinel /app
USER sentinel
ENV SENTINEL_ROLE=space \
    SENTINEL_DATA_DIR=/app/data \
    SENTINEL_DATABASE_URL=sqlite+aiosqlite:////app/data/sentinel.db \
    PORT=10000 \
    SENTINEL_ENV=dev \
    SENTINEL_AUTO_MIGRATE=true \
    SENTINEL_LOG_JSON=true \
    SENTINEL_LLM_PROVIDER=none \
    SENTINEL_DETECTOR_INTERVAL_S=15 \
    SIM_TRAFFIC_RPS=2 \
    SIM_FLUSH_INTERVAL_S=10
EXPOSE 10000
ENTRYPOINT ["sentinel-entrypoint"]
