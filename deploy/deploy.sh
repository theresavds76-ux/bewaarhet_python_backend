#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
ENV_FILE="${BEWAARHET_ENV_FILE:-/root/bewaarhet.env}"

cd "$APP_DIR"

has_real_env_value() {
  local key="$1"

  [[ -f "$ENV_FILE" ]] && awk -F= -v key="$key" '
    $0 !~ /^[[:space:]]*#/ && $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      if (value != "" && value !~ /^replace_with_/) found = 1
    }
    END { exit found ? 0 : 1 }
  ' "$ENV_FILE"
}

env_value() {
  local key="$1"

  awk -F= -v key="$key" '
    $0 !~ /^[[:space:]]*#/ && $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      print value
      exit
    }
  ' "$ENV_FILE"
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Production env file missing: $ENV_FILE"
  echo "Deploying static site only. The worker is not started without this file."
  deploy_worker=0
else
  deploy_worker=1
fi
deploy_logging=0

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
    if ! has_real_env_value "$key"; then
      missing_keys+=("$key")
    fi
  done

  if ((${#missing_keys[@]})); then
    printf 'Production env file is missing required real value(s): %s\n' "${missing_keys[*]}" >&2
    echo "Deploying static site only. The worker is not started until the env file is complete." >&2
    deploy_worker=0
  fi
fi

if has_real_env_value BETTER_STACK_SOURCE_TOKEN && has_real_env_value BETTER_STACK_INGESTING_HOST; then
  deploy_logging=1
  export BETTER_STACK_SOURCE_TOKEN
  export BETTER_STACK_INGESTING_HOST
  BETTER_STACK_SOURCE_TOKEN="$(env_value BETTER_STACK_SOURCE_TOKEN)"
  BETTER_STACK_INGESTING_HOST="$(env_value BETTER_STACK_INGESTING_HOST)"
else
  echo "Better Stack logging is not configured yet. Skipping external log collector."
fi

export BEWAARHET_ENV_FILE="$ENV_FILE"

compose_profiles=()
if [[ "$deploy_worker" == "1" ]]; then
  compose_profiles+=(--profile worker)
fi
if [[ "$deploy_logging" == "1" ]]; then
  compose_profiles+=(--profile logging)
fi

if ((${#compose_profiles[@]})); then
  docker compose "${compose_profiles[@]}" -f "$COMPOSE_FILE" build --pull
  if [[ "$deploy_logging" == "1" ]]; then
    docker compose --profile logging -f "$COMPOSE_FILE" pull bewaarhet_logs
  fi
  docker compose "${compose_profiles[@]}" -f "$COMPOSE_FILE" up -d --remove-orphans
else
  docker compose -f "$COMPOSE_FILE" build --pull bewaarhet_site
  docker compose -f "$COMPOSE_FILE" up -d --remove-orphans bewaarhet_site
fi

if [[ "$deploy_worker" != "1" ]]; then
  if docker container inspect bewaarhet_worker >/dev/null 2>&1; then
    docker compose --profile worker -f "$COMPOSE_FILE" stop bewaarhet_worker
  fi
fi
if [[ "$deploy_logging" != "1" ]]; then
  if docker container inspect bewaarhet_logs >/dev/null 2>&1; then
    docker compose --profile logging -f "$COMPOSE_FILE" stop bewaarhet_logs
  fi
fi

docker image prune -f --filter "until=168h" >/dev/null || true
docker compose --profile worker --profile logging -f "$COMPOSE_FILE" ps
