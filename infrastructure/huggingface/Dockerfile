# Sentinel demo backend for Hugging Face Spaces: API + seven-service demo shop in one container.
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
    PORT=7860 \
    SENTINEL_ENV=dev \
    SENTINEL_AUTO_MIGRATE=true \
    SENTINEL_LOG_JSON=true \
    SENTINEL_LLM_PROVIDER=none \
    SIM_TRAFFIC_RPS=6
EXPOSE 7860
ENTRYPOINT ["sentinel-entrypoint"]
