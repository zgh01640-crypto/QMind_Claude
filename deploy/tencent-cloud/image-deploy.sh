#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/qmind}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.images.yml}"
ENV_FILE="${ENV_FILE:-$APP_DIR/shared/.env.production}"
IMAGE_TAG="${IMAGE_TAG:-${QMIND_IMAGE_TAG:-}}"

if [[ ! -f "$ENV_FILE" || ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing $ENV_FILE or $COMPOSE_FILE" >&2
  exit 2
fi
if [[ -z "$IMAGE_TAG" ]]; then
  echo "Set IMAGE_TAG to a pushed image tag." >&2
  exit 2
fi

export QMIND_IMAGE_TAG="$IMAGE_TAG"
cd "$APP_DIR"
mkdir -p "$APP_DIR/data/postgres" "$APP_DIR/data/api" "$APP_DIR/backups"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config -q
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T api \
  python -c 'from db.connection import get_connection, apply_schema; c=get_connection(); apply_schema(c); c.close()'

for attempt in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:3001/api/periods >/dev/null; then
    echo "QMind image deployment is healthy: $IMAGE_TAG"
    exit 0
  fi
  sleep 2
done

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps >&2 || true
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" logs --tail=120 >&2 || true
exit 1
