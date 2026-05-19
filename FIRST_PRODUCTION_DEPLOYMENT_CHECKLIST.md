# Bewaarhet First Production Deployment Checklist

Gebruik deze checklist voor de eerste gecontroleerde deployment naar een externe Linux-server. Dit document is bewust procedureel: geen nieuwe features, geen codewijzigingen, geen cleanup-acties tijdens launch tenzij expliciet gepland en gebackupt.

## Pre-Deployment Requirements

- [ ] Er is een gekozen deployment window met genoeg tijd voor smoke tests en rollback.
- [ ] De laatste commit op `main` is bekend en genoteerd.
- [ ] De lokale test suite draait groen.
- [ ] `README.md`, `.env.example`, `DEPLOYMENT_RUNBOOK.md` en `OPERATIONS_RUNBOOK.md` zijn up-to-date.
- [ ] Zoho mailbox en app-password zijn klaar.
- [ ] Dropbox refresh-token flow is klaar:
  - `DROPBOX_REFRESH_TOKEN`
  - `DROPBOX_APP_KEY`
  - `DROPBOX_APP_SECRET`
- [ ] OCR.space API key is klaar.
- [ ] OpenAI API key is klaar als optionele fallback gewenst is.
- [ ] Er is een restorebare SQLite backup van de huidige pre-productie staat.
- [ ] Er is een offsite backup-locatie ingericht.

## Server Access Requirements

- [ ] Linux VPS/server met systemd.
- [ ] Python 3.11+ beschikbaar.
- [ ] Git beschikbaar.
- [ ] Beheerder heeft sudo toegang.
- [ ] Dedicated service user bestaat of wordt aangemaakt, bijvoorbeeld `bewaarhet`.
- [ ] Deployment pad gekozen, bijvoorbeeld `/opt/bewaarhet_python_backend`.
- [ ] Runtime data pad gekozen, bijvoorbeeld `/var/lib/bewaarhet`.
- [ ] Log pad gekozen, bijvoorbeeld `/var/log/bewaarhet`.
- [ ] Alleen bevoegde beheerders hebben SSH toegang.

## SSH Hardening Checklist

- [ ] SSH key login werkt voor beheerders.
- [ ] Password login is uitgeschakeld als dat past binnen het serverbeheer.
- [ ] Root login via SSH is uitgeschakeld.
- [ ] Alleen noodzakelijke users staan in `AllowUsers` of een vergelijkbare beperking.
- [ ] SSH luistert alleen op de bedoelde interface/poort.
- [ ] Fail2ban of vergelijkbare brute-force bescherming is actief.
- [ ] Beheerders weten waar emergency console access beschikbaar is.

## Firewall Checklist

- [ ] Inbound SSH is toegestaan vanaf vertrouwde IP's waar mogelijk.
- [ ] Onnodige inbound poorten zijn gesloten.
- [ ] Outbound HTTPS is toegestaan voor Dropbox, OCR.space en OpenAI indien gebruikt.
- [ ] Outbound IMAPS naar Zoho is toegestaan.
- [ ] Outbound SMTP submission naar Zoho is toegestaan.
- [ ] Firewall regels zijn getest na herstart.

## Python/Venv Setup

```bash
sudo -u bewaarhet python3 -m venv /opt/bewaarhet_python_backend/.venv
cd /opt/bewaarhet_python_backend
sudo -u bewaarhet ./.venv/bin/python -m pip install --upgrade pip
sudo -u bewaarhet ./.venv/bin/python -m pip install -r requirements.txt
```

Checklist:

- [ ] Venv is eigendom van de service user.
- [ ] Dependencies installeren zonder errors.
- [ ] Er worden geen globale Python packages gebruikt voor de worker.

## Git Clone/Update Steps

Nieuwe clone:

```bash
sudo mkdir -p /opt/bewaarhet_python_backend
sudo chown bewaarhet:bewaarhet /opt/bewaarhet_python_backend
sudo -u bewaarhet git clone <repo-url> /opt/bewaarhet_python_backend
cd /opt/bewaarhet_python_backend
sudo -u bewaarhet git status
sudo -u bewaarhet git rev-parse HEAD
```

Update bestaande clone:

```bash
cd /opt/bewaarhet_python_backend
sudo -u bewaarhet git status
sudo -u bewaarhet git pull --ff-only
sudo -u bewaarhet git rev-parse HEAD
```

Checklist:

- [ ] Working tree is schoon behalve lokale `.env`.
- [ ] De gebruikte commit hash is genoteerd.
- [ ] Er zijn geen lokale codewijzigingen op productie.

## `.env` Creation Checklist

```bash
cd /opt/bewaarhet_python_backend
sudo -u bewaarhet cp .env.example .env
sudo -u bewaarhet nano .env
chmod 600 .env
sudo chown bewaarhet:bewaarhet .env
```

Verplicht invullen:

- [ ] `ZOHO_EMAIL`
- [ ] `ZOHO_IMAP_HOST`
- [ ] `ZOHO_IMAP_PORT`
- [ ] `ZOHO_SMTP_HOST`
- [ ] `ZOHO_SMTP_PORT`
- [ ] `ZOHO_APP_PASSWORD`
- [ ] `DROPBOX_REFRESH_TOKEN`
- [ ] `DROPBOX_APP_KEY`
- [ ] `DROPBOX_APP_SECRET`
- [ ] `DROPBOX_BASE_PATH`
- [ ] `DROPBOX_TIMEOUT_SECONDS`
- [ ] `OCR_SPACE_API_KEY`
- [ ] `OCR_SPACE_LANGUAGE`
- [ ] `DATA_DIR`
- [ ] `DATABASE_PATH`
- [ ] `BACKUP_DIR`
- [ ] `LOG_DIR`
- [ ] `BACKUP_KEEP_LATEST`
- [ ] `CONSISTENCY_LOG_EVERY`
- [ ] `CONSISTENCY_SLOW_THRESHOLD_SECONDS`
- [ ] `POLL_SECONDS`
- [ ] `SEARCH_RESULT_LIMIT`
- [ ] `MAX_ATTACHMENT_MB`
- [ ] `ALLOWED_EXTENSIONS`

Optioneel:

- [ ] `OPENAI_API_KEY`
- [ ] `OPENAI_MODEL`

Server path recommendation:

```env
DATA_DIR=/var/lib/bewaarhet
DATABASE_PATH=/var/lib/bewaarhet/bewaarhet.sqlite3
BACKUP_DIR=/var/lib/bewaarhet/backups
LOG_DIR=/var/log/bewaarhet
```

## Secrets Handling Rules

- [ ] Geen echte secrets in git.
- [ ] Geen echte secrets in chat, tickets of screenshots.
- [ ] `.env` heeft permissies `600`.
- [ ] Alleen de service user en bevoegde beheerders kunnen `.env` lezen.
- [ ] Secrets worden niet in shell history geplakt als dat vermijdbaar is.
- [ ] `DROPBOX_ACCESS_TOKEN` wordt niet gebruikt; gebruik refresh-token flow.
- [ ] Bij twijfel over lekkage: token/key roteren voordat productie live gaat.

## Data Directory Setup

```bash
sudo mkdir -p /var/lib/bewaarhet
sudo chown -R bewaarhet:bewaarhet /var/lib/bewaarhet
sudo chmod 750 /var/lib/bewaarhet
```

Checklist:

- [ ] `DATA_DIR` bestaat.
- [ ] `DATABASE_PATH` parent folder bestaat.
- [ ] Service user kan lezen/schrijven.
- [ ] Andere users hebben geen brede toegang.

## Backup Directory Setup

```bash
sudo mkdir -p /var/lib/bewaarhet/backups
sudo chown -R bewaarhet:bewaarhet /var/lib/bewaarhet/backups
sudo chmod 750 /var/lib/bewaarhet/backups
```

Checklist:

- [ ] `BACKUP_DIR` bestaat.
- [ ] Service user kan backups maken.
- [ ] Backup retentie is ingesteld met `BACKUP_KEEP_LATEST`.
- [ ] Backup folder staat niet in git.

## Offsite Backup Requirement

- [ ] Er is een offsite bestemming buiten de VPS.
- [ ] Backups worden versleuteld of via een vertrouwd beveiligd kanaal gekopieerd.
- [ ] Offsite backup draait minimaal dagelijks.
- [ ] Er is monitoring of handmatige controle dat offsite backups recent zijn.
- [ ] Er is minimaal een restore dry-run uitgevoerd vanaf een backup.

## Database Init and Startup Check

```bash
cd /opt/bewaarhet_python_backend
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.init_db
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin create-backup
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin list-backups
```

Checklist:

- [ ] SQLite database wordt aangemaakt op `DATABASE_PATH`.
- [ ] Backup command werkt.
- [ ] Backup staat in `BACKUP_DIR`.
- [ ] Geen secrets of documentinhoud verschijnen in output.

## Systemd Service Install Steps

Maak `/etc/systemd/system/bewaarhet.service`:

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

Installeren:

```bash
sudo systemctl daemon-reload
sudo systemctl enable bewaarhet
sudo systemctl start bewaarhet
sudo systemctl status bewaarhet
```

Restart test:

```bash
sudo systemctl restart bewaarhet
sudo systemctl status bewaarhet
journalctl -u bewaarhet --since "5 minutes ago"
```

Checklist:

- [ ] Service start.
- [ ] Service restart werkt.
- [ ] Geen restart-loop.
- [ ] Logs tonen startup diagnostics.
- [ ] Database integrity check is ok.

## Manual Smoke Test Commands

Voor systemd:

```bash
cd /opt/bewaarhet_python_backend
sudo -u bewaarhet ./.venv/bin/python -m unittest
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.init_db
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin create-backup
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin restore-backup /var/lib/bewaarhet/backups/<backup>.sqlite3 --dry-run
sudo -u bewaarhet ./.venv/bin/python -m bewaarhet.admin consistency-check --limit 20
```

Na systemd start:

```bash
sudo systemctl status bewaarhet
journalctl -u bewaarhet --since "15 minutes ago"
```

Checklist:

- [ ] Tests slagen.
- [ ] Backup werkt.
- [ ] Restore dry-run werkt.
- [ ] Consistency-check geeft geen onverwachte API/auth errors.
- [ ] Worker blijft draaien.

## Zoho Receive/Send Test

Ontvangst:

- [ ] Stuur een veilige testmail naar de bewaar-mailbox.
- [ ] Controleer dat de worker de mail via IMAP ziet.
- [ ] Controleer dat de mail correct wordt verwerkt of veilig wordt geweigerd.
- [ ] Controleer dat er geen mail loop ontstaat.

Verzenden:

- [ ] Trigger een reply, bijvoorbeeld met een veilige search of rejected upload test.
- [ ] Controleer logs op:
  - `SMTP send started`
  - `SMTP send completed successfully`
  - SMTP duration
- [ ] Controleer dat de reply aankomt bij de testontvanger.

## Dropbox Upload/Link Test

- [ ] Stuur een klein geldig testdocument, bijvoorbeeld een minimale PDF.
- [ ] Controleer dat upload naar Dropbox slaagt.
- [ ] Controleer dat SQLite metadata is aangemaakt.
- [ ] Trigger search/retrieval voor hetzelfde testdocument.
- [ ] Controleer dat een tijdelijke downloadlink wordt gegenereerd.
- [ ] Open de link als testontvanger.
- [ ] Controleer dat de reply duidelijk vermeldt dat links tijdelijk verlopen.

Gebruik geen echte klantdocumenten voor deze eerste smoke test.

## OCR Test

- [ ] Stuur een veilig testdocument met eenvoudige tekst.
- [ ] Controleer dat OCR.space geen auth/quota error geeft.
- [ ] Controleer dat OCR-preview/logging gesanitized blijft.
- [ ] Controleer dat classificatie plausibel is.
- [ ] Accepteer niet als logs volledige documenttekst of secrets tonen.

## Search/Retrieval Test

- [ ] Zoek als dezelfde afzender naar het net geuploade testdocument.
- [ ] Controleer dat resultaat wordt gevonden.
- [ ] Controleer dat temporary link werkt.
- [ ] Controleer dat de reply simpele uitleg bevat over tijdelijke links.
- [ ] Test met een andere afzender mag geen documenten van de eerste afzender teruggeven.
- [ ] Controleer logs op ownership warnings of onverwachte globale search.

## Rollback Steps

Bij deployment-problemen:

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
journalctl -u bewaarhet --since "15 minutes ago"
```

Checklist:

- [ ] Known-good commit is bekend.
- [ ] Backup voor rollback is bekend.
- [ ] Restore dry-run slaagt voordat `--confirm` wordt gebruikt.
- [ ] Na rollback werken IMAP, SMTP, Dropbox en search smoke tests opnieuw.
- [ ] De rollback is genoteerd in het deployment log.

## DO NOT LAUNCH PUBLICLY IF

- [ ] Er is geen offsite backup.
- [ ] Er is geen werkende restore dry-run.
- [ ] `systemctl restart bewaarhet` werkt niet betrouwbaar.
- [ ] Email send/receive is niet bevestigd.
- [ ] Dropbox temporary links zijn niet bevestigd.
- [ ] Secrets zijn gedeeld via onveilige kanalen.
- [ ] Logs tonen gevoelige inhoud, secrets, volledige OCR-tekst of tijdelijke downloadlinks.
- [ ] Database integrity check faalt.
- [ ] Worker zit in een restart-loop.
- [ ] Zoho, Dropbox of OCR.space authenticatie faalt.
- [ ] Rollback commit/backup is niet bekend.

## Go/No-Go Checklist

Go alleen als alles hieronder waar is:

- [ ] Server is gehard en firewall is gecontroleerd.
- [ ] Repo staat op de bedoelde commit.
- [ ] `.env` is compleet en veilig opgeslagen.
- [ ] Runtime directories bestaan en hebben correcte eigenaar/permissies.
- [ ] Tests slagen op de server.
- [ ] Database init/startup check slaagt.
- [ ] Manual backup werkt.
- [ ] Restore dry-run werkt.
- [ ] Offsite backup is ingericht.
- [ ] Systemd start, restart en status werken.
- [ ] Zoho IMAP ontvangst is getest.
- [ ] Zoho SMTP verzending is getest.
- [ ] Dropbox upload en temporary link zijn getest.
- [ ] OCR test is uitgevoerd.
- [ ] Search/retrieval test is uitgevoerd.
- [ ] Logs blijven gesanitized.
- [ ] Rollback pad is getest of minimaal exact voorbereid.

No-go bij elke openstaande blocker uit de "DO NOT LAUNCH PUBLICLY IF" sectie.
