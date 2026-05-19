#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR=/root/bewaarhet
BRANCH=main
DEPLOY_DIR=/root/bewaarhet-deploy
ENV_FILE=/root/bewaarhet.env
LOCK_FILE="$DEPLOY_DIR/deploy.lock"
LOG_FILE="$DEPLOY_DIR/deploy.log"

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

