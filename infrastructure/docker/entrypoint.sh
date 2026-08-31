#!/bin/sh
# Role-based entrypoint so one image serves every process type.
#   SENTINEL_ROLE=api        → migrate + bootstrap, then the HTTP API on $PORT (default 8000)
#   SENTINEL_ROLE=worker     → background worker (Redis/ARQ when SENTINEL_REDIS_URL is set)
#   SENTINEL_ROLE=simulator  → demo shop control plane on $PORT (default 9000)
# Any other arguments are executed verbatim (docker compose passes explicit commands).
set -eu

ROLE="${SENTINEL_ROLE:-}"
if [ "$#" -gt 0 ] && [ -z "$ROLE" ]; then
  exec "$@"
fi

case "$ROLE" in
  api)
    if [ "${SENTINEL_AUTO_MIGRATE:-false}" != "true" ]; then
      sentinel migrate
    fi
    sentinel bootstrap
    exec sentinel api --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  worker)
    exec sentinel worker
    ;;
  simulator)
    exec sentinel-sim run --port "${PORT:-9000}" --host "${SIM_HOST:-127.0.0.1}"
    ;;
  space)
    # Single-container demo (Hugging Face Spaces): API + demo shop in one process tree.
    export SIM_SENTINEL_URL="${SIM_SENTINEL_URL:-http://127.0.0.1:${PORT:-7860}}"
    export SENTINEL_SIMULATOR_URL="${SENTINEL_SIMULATOR_URL:-http://127.0.0.1:9000}"
    (sleep 12 && exec sentinel-sim run --port 9000 --host 127.0.0.1) &
    exec sentinel api --host 0.0.0.0 --port "${PORT:-7860}"
    ;;
  *)
    echo "unknown SENTINEL_ROLE '$ROLE' (expected api|worker|simulator)" >&2
    exit 2
    ;;
esac
