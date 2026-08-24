#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/qmind}"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RELEASE_DIR="${RELEASE_DIR:-$SCRIPT_ROOT}"
ENV_FILE="${ENV_FILE:-$APP_DIR/shared/.env.production}"
COMPOSE_FILE="$RELEASE_DIR/docker-compose.prod.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing production environment file: $ENV_FILE" >&2
  exit 2
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 2
fi

cd "$RELEASE_DIR"
mkdir -p "$APP_DIR/data/postgres" "$APP_DIR/data/api" "$APP_DIR/backups"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config -q
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build --remove-orphans

# schema.sql is idempotent and creates the base tables on a new database.
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T api \
  python -c 'from db.connection import get_connection, apply_schema; c=get_connection(); apply_schema(c); c.close()'

for attempt in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:3001/api/periods >/dev/null; then
    echo "QMind deployment is healthy."
    exit 0
  fi
  sleep 2
done

echo "QMind deployment did not pass the health check." >&2
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps >&2 || true
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=120 >&2 || true
exit 1
