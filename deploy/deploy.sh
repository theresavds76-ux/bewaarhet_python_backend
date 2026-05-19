#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
ENV_FILE="${BEWAARHET_ENV_FILE:-/root/bewaarhet.env}"

cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Production env file missing: $ENV_FILE"
  echo "Deploying static site only. The worker is not started without this file."
  deploy_worker=0
else
  deploy_worker=1
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
if [[ "$deploy_worker" == "1" ]]; then
  for key in "${required_keys[@]}"; do
    if ! awk -F= -v key="$key" '
      $0 !~ /^[[:space:]]*#/ && $1 == key {
        value = substr($0, index($0, "=") + 1)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        if (value != "" && value !~ /^replace_with_/) found = 1
      }
      END { exit found ? 0 : 1 }
    ' "$ENV_FILE"; then
      missing_keys+=("$key")
    fi
  done

  if ((${#missing_keys[@]})); then
    printf 'Production env file is missing required real value(s): %s\n' "${missing_keys[*]}" >&2
    echo "Deploying static site only. The worker is not started until the env file is complete." >&2
    deploy_worker=0
  fi
fi

export BEWAARHET_ENV_FILE="$ENV_FILE"

if [[ "$deploy_worker" == "1" ]]; then
  docker compose --profile worker -f "$COMPOSE_FILE" build --pull
  docker compose --profile worker -f "$COMPOSE_FILE" up -d --remove-orphans
else
  docker compose -f "$COMPOSE_FILE" build --pull bewaarhet_site
  docker compose -f "$COMPOSE_FILE" up -d --remove-orphans bewaarhet_site
  if docker container inspect bewaarhet_worker >/dev/null 2>&1; then
    docker compose --profile worker -f "$COMPOSE_FILE" stop bewaarhet_worker
  fi
fi

docker image prune -f --filter "until=168h" >/dev/null || true
docker compose --profile worker -f "$COMPOSE_FILE" ps
