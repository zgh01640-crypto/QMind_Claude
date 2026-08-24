#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/qmind}"
ENV_FILE="${ENV_FILE:-$APP_DIR/shared/.env.production}"
CURRENT="$(readlink -f "$APP_DIR/current")"

mapfile -t RELEASES < <(find "$APP_DIR/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | awk '{$1=""; sub(/^ /, ""); print}')
PREVIOUS=""
for release in "${RELEASES[@]}"; do
  if [[ "$release" != "$CURRENT" ]]; then
    PREVIOUS="$release"
    break
  fi
done

if [[ -z "$PREVIOUS" ]]; then
  echo "No previous release found; rollback skipped." >&2
  exit 2
fi

ln -sfn "$PREVIOUS" "$APP_DIR/current.next"
mv -Tf "$APP_DIR/current.next" "$APP_DIR/current"
APP_DIR="$APP_DIR" RELEASE_DIR="$APP_DIR/current" ENV_FILE="$ENV_FILE" \
  bash "$APP_DIR/current/deploy/tencent-cloud/deploy.sh"
echo "Rolled back to: $PREVIOUS"
