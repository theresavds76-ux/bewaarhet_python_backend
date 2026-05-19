#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR=/root/bewaarhet
BRANCH=main
DEPLOY_DIR=/root/bewaarhet-deploy
ENV_FILE=/root/bewaarhet.env
LOCK_FILE="$DEPLOY_DIR/deploy.lock"
LOG_FILE="$DEPLOY_DIR/deploy.log"
LOG_LINES=200

mkdir -p "$DEPLOY_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Bewaarhet deploy is already running."
  exit 0
fi

write_env_from_stdin() {
  local tmp
  tmp="$(mktemp "$DEPLOY_DIR/bewaarhet.env.XXXXXX")"
  cat > "$tmp"
  chmod 600 "$tmp"

  python3 - "$tmp" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
required = {
    "ZOHO_EMAIL",
    "ZOHO_APP_PASSWORD",
    "DROPBOX_REFRESH_TOKEN",
    "DROPBOX_APP_KEY",
    "DROPBOX_APP_SECRET",
    "OCR_SPACE_API_KEY",
}

values = {}
for line in path.read_text().splitlines():
    if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

missing = [
    key for key in sorted(required)
    if not values.get(key) or values[key].startswith("replace_with_")
]
if missing:
    raise SystemExit("Missing required production env value(s): " + ", ".join(missing))
PY

  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

if [[ "${SSH_ORIGINAL_COMMAND:-}" == "deploy-with-env" ]]; then
  write_env_from_stdin
fi

sanitize_output() {
  sed -E \
    -e 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/[email]/g' \
    -e 's#https?://[^[:space:]<>"]+#[link]#g' \
    -e 's/(PASSWORD|PASS|TOKEN|SECRET|API_KEY|APP_KEY|APP_SECRET)([=:_ -]+)[^[:space:]]+/\1\2[redacted]/Ig'
}

show_status() {
  echo "== Git =="
  git -C "$APP_DIR" status -sb 2>/dev/null || true
  git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || true
  echo
  echo "== Containers =="
  docker ps --filter name=bewaarhet --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Networks}}'
}

show_logs() {
  local container="$1"
  if ! docker container inspect "$container" >/dev/null 2>&1; then
    echo "Container is not present: $container"
    return 0
  fi
  echo "== Last ${LOG_LINES} log lines for ${container} =="
  docker logs --tail "$LOG_LINES" "$container" 2>&1 | sanitize_output
}

restart_containers() {
  local existing=()
  local container

  for container in "$@"; do
    if docker container inspect "$container" >/dev/null 2>&1; then
      existing+=("$container")
    else
      echo "Container is not present, skipping restart: $container"
    fi
  done

  if ((${#existing[@]})); then
    docker restart "${existing[@]}"
  fi
  show_status
}

run_operation() {
  case "$1" in
    status)
      show_status
      ;;
    logs-worker)
      show_logs bewaarhet_worker
      ;;
    logs-site)
      show_logs bewaarhet_site
      ;;
    logs-collector)
      show_logs bewaarhet_logs
      ;;
    restart-worker)
      restart_containers bewaarhet_worker
      ;;
    restart-site)
      restart_containers bewaarhet_site
      ;;
    restart-collector)
      restart_containers bewaarhet_logs
      ;;
    restart-all)
      restart_containers bewaarhet_worker bewaarhet_site bewaarhet_logs
      ;;
    *)
      echo "Unsupported Bewaarhet operation: $1" >&2
      echo "Allowed: status, logs-worker, logs-site, logs-collector, restart-worker, restart-site, restart-collector, restart-all" >&2
      exit 64
      ;;
  esac
}

if [[ "${SSH_ORIGINAL_COMMAND:-}" == operation:* ]]; then
  operation_payload="${SSH_ORIGINAL_COMMAND#operation:}"
  operation="${operation_payload%%:*}"
  requested_lines="${operation_payload#"$operation"}"
  requested_lines="${requested_lines#:}"
  if [[ "$requested_lines" =~ ^[0-9]+$ ]]; then
    LOG_LINES="$requested_lines"
  fi
  if ((LOG_LINES < 1)); then
    LOG_LINES=1
  elif ((LOG_LINES > 1000)); then
    LOG_LINES=1000
  fi
  run_operation "$operation"
  exit 0
fi

exec > >(tee -a "$LOG_FILE") 2>&1

echo "--- bewaarhet deploy $(date -Is) ---"

if [ ! -d "$APP_DIR/.git" ]; then
  git clone https://github.com/theresavds76-ux/bewaarhet_python_backend.git "$APP_DIR"
fi

cd "$APP_DIR"
git fetch --prune origin "$BRANCH"
git reset --hard "origin/$BRANCH"
./deploy/deploy.sh

echo "--- bewaarhet deploy completed $(date -Is) ---"
