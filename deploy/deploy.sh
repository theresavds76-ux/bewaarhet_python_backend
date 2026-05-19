#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
ENV_FILE="${BEWAARHET_ENV_FILE:-/root/bewaarhet.env}"

cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  cat >&2 <<EOF
Missing production env file: $ENV_FILE

Create it from .env.example and fill the real Zoho, Dropbox and OCR.space credentials.
The worker is not started without this file.
EOF
  exit 78
fi

required_keys=(
  ZOHO_EMAIL
  ZOHO_APP_PASSWORD
  DROPBOX_REFRESH_TOKEN
  DROPBOX_APP_KEY
  DROPBOX_APP_SECRET
  OCR_SPACE_API_KEY
)

missing_keys=()
for key in "${required_keys[@]}"; do
  if ! awk -F= -v key="$key" '
    $0 !~ /^[[:space:]]*#/ && $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (value != "") found = 1
    }
    END { exit found ? 0 : 1 }
  ' "$ENV_FILE"; then
    missing_keys+=("$key")
  fi
done

if ((${#missing_keys[@]})); then
  printf 'Production env file is missing required value(s): %s\n' "${missing_keys[*]}" >&2
  exit 78
fi

export BEWAARHET_ENV_FILE="$ENV_FILE"

docker compose -f "$COMPOSE_FILE" build --pull
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
docker image prune -f --filter "until=168h" >/dev/null || true
docker compose -f "$COMPOSE_FILE" ps

