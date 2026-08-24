#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/qmind}"
RELEASE_DIR="${RELEASE_DIR:-$APP_DIR/current}"
ENV_FILE="${ENV_FILE:-$APP_DIR/shared/.env.production}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$APP_DIR/backups/$STAMP"
COMPOSE_FILE="$RELEASE_DIR/docker-compose.prod.yml"

mkdir -p "$BACKUP_DIR"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U qmind -d qmind -Fc > "$BACKUP_DIR/qmind.dump"

if [[ -d "$APP_DIR/data/api/pricing-kb-uploads" ]]; then
  tar -czf "$BACKUP_DIR/pricing-kb-uploads.tgz" \
    -C "$APP_DIR/data/api" pricing-kb-uploads
fi

sha256sum "$BACKUP_DIR"/* > "$BACKUP_DIR/SHA256SUMS"
echo "Backup created: $BACKUP_DIR"
