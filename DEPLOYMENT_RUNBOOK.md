# Bewaarhet Deployment Runbook

Dit runbook beschrijft een reproduceerbare deployment naar een server/VPS. Het wijzigt geen businesslogica en gaat uit van de bestaande Python worker.

## Prerequisites

- Linux VPS of server met systemd.
- Python 3.11+ aanbevolen.
- Git.
- Netwerktoegang naar:
  - Zoho IMAP/SMTP
  - Dropbox API
  - OCR.space
  - OpenAI API, alleen als fallback wordt gebruikt
- Zoho mailbox met app-password.
- Dropbox app credentials:
  - `DROPBOX_REFRESH_TOKEN`
  - `DROPBOX_APP_KEY`
  - `DROPBOX_APP_SECRET`
- OCR.space API key.
- Optioneel: OpenAI API key.

## Server/VPS Checklist

1. Maak een dedicated Linux user, bijvoorbeeld `bewaarhet`.
2. Kies een vaste installatiemap, bijvoorbeeld `/opt/bewaarhet_python_backend`.
3. Kies absolute runtime paden, bijvoorbeeld:
   - `/var/lib/bewaarhet`
   - `/var/lib/bewaarhet/backups`
   - `/var/log/bewaarhet`
4. Zorg dat deze mappen eigendom zijn van de service user.
5. Zet secrets alleen in `.env` of in een systemd EnvironmentFile, nooit in git.
6. Richt externe/offsite backup in voor SQLite backups.

## Clone Repo

```bash
sudo mkdir -p /opt/bewaarhet_python_backend
sudo chown bewaarhet:bewaarhet /opt/bewaarhet_python_backend
sudo -u bewaarhet git clone <repo-url> /opt/bewaarhet_python_backend
cd /opt/bewaarhet_python_backend
```

## Create Venv

```bash
sudo -u bewaarhet python3 -m venv .venv
sudo -u bewaarhet ./.venv/bin/python -m pip install --upgrade pip
sudo -u bewaarhet ./.venv/bin/python -m pip install -r requirements.txt
```

## Create `.env`

```bash
sudo -u bewaarhet cp .env.example .env
sudo -u bewaarhet nano .env
```

Recommended server paths:

```env
DATA_DIR=/var/lib/bewaarhet
DATABASE_PATH=/var/lib/bewaarhet/bewaarhet.sqlite3
BACKUP_DIR=/var/lib/bewaarhet/backups
LOG_DIR=/var/log/bewaarhet
```

Dropbox must use refresh-token flow:

```env
DROPBOX_REFRESH_TOKEN=replace_with_real_value
DROPBOX_APP_KEY=replace_with_real_value
DROPBOX_APP_SECRET=replace_with_real_value
```

`DROPBOX_ACCESS_TOKEN` is not used by the current code.

**CRITICAL: Activation Token Secret**

Customer email activation links are cryptographically signed. A long random secret is REQUIRED:

```bash
# Generate a secure random secret (min 32 chars, use this exact command):
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Then add to `.env`:

```env
# Use the output from the above command
VERIFICATION_TOKEN_SECRET=<paste-the-generated-secret-here>
VERIFICATION_TOKEN_TTL_HOURS=72
```

**IMPORTANT:**
- The same `VERIFICATION_TOKEN_SECRET` **MUST** be used on all production containers (both `bewaarhet_worker` and `bewaarhet_activation`)
- Changing this secret will invalidate all existing activation tokens
- This secret **MUST** be kept secret (do not commit to git, use VPS env file only)
- If this is not set, activation links will fail with `RuntimeError: No token secret configured`

## Runtime Folders

```bash
sudo mkdir -p /var/lib/bewaarhet /var/lib/bewaarhet/backups /var/log/bewaarhet
sudo chown -R bewaarhet:bewaarhet /var/lib/bewaarhet /var/log/bewaarhet
```

## Database Init and Startup Check

Initialize SQLite:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.init_db
```

Run a one-time worker startup manually and stop with `Ctrl+C` after diagnostics:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.worker
```

Expected startup should show:

- runtime folders ready
- database integrity check ok
- worker polling mailbox

## Run Tests

```bash
sudo -u bewaarhet ./.venv/bin/python -m unittest
```

All tests should pass before enabling the service.

## Run Worker Manually

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.worker
```

Use this before systemd to verify:

- Zoho IMAP login works.
- SQLite opens.
- No immediate config errors occur.

## Create Systemd Service

Create `/etc/systemd/system/bewaarhet.service`:

```ini
[Unit]
Description=Bewaarhet Python backend
After=network.target

[Service]
Type=simple
User=bewaarhet
Group=bewaarhet
WorkingDirectory=/opt/bewaarhet_python_backend
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

If `.env` is not in the working directory, add:

```ini
EnvironmentFile=/path/to/bewaarhet.env
```

Then enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable bewaarhet
sudo systemctl start bewaarhet
```

## Start/Stop/Restart/Status

```bash
sudo systemctl status bewaarhet
sudo systemctl stop bewaarhet
sudo systemctl start bewaarhet
sudo systemctl restart bewaarhet
```

Follow logs:

```bash
journalctl -u bewaarhet -f
```

Recent logs:

```bash
journalctl -u bewaarhet --since "1 hour ago"
```

## Log Locations

Current app logging goes to stdout/stderr and is normally captured by systemd journal.

Configured `LOG_DIR` is created by the app and used by maintenance/reset tooling where relevant, but the worker currently does not write structured log files there by default.

## Backup Procedure

Create a manual SQLite backup:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin create-backup
```

List backups:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin list-backups
```

Backups are written to `BACKUP_DIR` and rotated according to `BACKUP_KEEP_LATEST`.

## Restore Dry-Run Procedure

Always validate first:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin restore-backup /var/lib/bewaarhet/backups/<backup>.sqlite3 --dry-run
```

If validation passes and restore is needed:

```bash
sudo systemctl stop bewaarhet
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin restore-backup /var/lib/bewaarhet/backups/<backup>.sqlite3 --confirm
sudo systemctl start bewaarhet
```

Restore creates a backup of the current DB by default before overwrite.

## Consistency-Check Procedure

Read-only Dropbox/SQLite check:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin consistency-check
```

Fast/debug mode:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin consistency-check --limit 50
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin consistency-check --since-id 100
```

This command does not delete Dropbox files and does not modify SQLite records.

## Cleanup Procedure

Start with report:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin cleanup-report
```

Dry-run orphan cleanup:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin cleanup-orphaned --dry-run
```

Before confirmed cleanup, create a fresh backup:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin create-backup
```

Confirmed orphan cleanup removes only SQLite metadata rows:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin cleanup-orphaned --confirm
```

Testdata cleanup should normally not be used in production. If ever needed, use dry-run first and create a backup before confirmation:

```bash
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin cleanup-testdata --dry-run
```

Do not run `reset-dev-environment` on production.

## Update/Deploy Procedure

1. Create a fresh backup.
2. Stop the worker.
3. Pull latest code.
4. Install/update dependencies.
5. Run tests.
6. Run database init.
7. Start worker.
8. Check logs and service status.

Commands:

```bash
cd /opt/bewaarhet_python_backend
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin create-backup
sudo systemctl stop bewaarhet
sudo -u bewaarhet git pull --ff-only
sudo -u bewaarhet ./.venv/bin/python -m pip install -r requirements.txt
sudo -u bewaarhet ./.venv/bin/python -m unittest
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.init_db
sudo systemctl start bewaarhet
sudo systemctl status bewaarhet
journalctl -u bewaarhet --since "10 minutes ago"
```

## Rollback Procedure

1. Stop worker.
2. Check current git revision and desired previous revision.
3. Restore code to previous known-good commit.
4. Restore SQLite backup if the update changed database state undesirably.
5. Reinstall dependencies if needed.
6. Start worker and verify.

Commands:

```bash
cd /opt/bewaarhet_python_backend
sudo systemctl stop bewaarhet
sudo -u bewaarhet git log --oneline -5
sudo -u bewaarhet git checkout <known-good-commit>
sudo -u bewaarhet ./.venv/bin/python -m pip install -r requirements.txt
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin restore-backup /var/lib/bewaarhet/backups/<backup>.sqlite3 --dry-run
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin restore-backup /var/lib/bewaarhet/backups/<backup>.sqlite3 --confirm
sudo systemctl start bewaarhet
sudo systemctl status bewaarhet
```

After rollback, move back to a branch or tag intentionally. Do not leave production on an unknown detached commit without recording it.

## Offsite Backup Recommendation

At minimum, copy `BACKUP_DIR` to offsite storage daily.

Recommended:

- encrypted remote backup
- retention policy longer than local `BACKUP_KEEP_LATEST`
- periodic restore dry-run on a separate machine
- alert if backups are older than 24 hours

Do not rely only on local PC/VPS disk for production.

## Secrets Rotation Checklist

Rotate secrets when an operator leaves, a machine is compromised, or credentials may have leaked:

- Zoho app password
- Dropbox refresh token
- Dropbox app secret
- OCR.space API key
- OpenAI API key

After rotation:

1. Update `.env` or systemd EnvironmentFile.
2. Restart worker.
3. Verify IMAP fetch.
4. Verify SMTP reply.
5. Verify Dropbox account info or consistency-check.
6. Verify OCR on a safe test document if needed.
7. Verify OpenAI fallback only if used.

Never paste real secrets into logs, tickets, commits, or chat.
