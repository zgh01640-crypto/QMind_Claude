#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <pushed-image-tag>" >&2
  exit 2
fi

APP_DIR="${APP_DIR:-/opt/qmind}"
ENV_FILE="${ENV_FILE:-$APP_DIR/shared/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$APP_DIR/docker-compose.images.yml}"
IMAGE_TAG="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IMAGE_TAG="$IMAGE_TAG" APP_DIR="$APP_DIR" ENV_FILE="$ENV_FILE" COMPOSE_FILE="$COMPOSE_FILE" \
  bash "$SCRIPT_DIR/image-deploy.sh"
