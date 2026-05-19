# Bewaarhet Operations Runbook

Dit runbook is voor dagelijks beheer van een draaiende Bewaarhet worker. Het beschrijft controles en herstelacties zonder nieuwe features of codewijzigingen.

## Dagelijkse Checks

### Worker status

```bash
sudo systemctl status bewaarhet
```

Controleer:

- service is `active`
- geen snelle restart-loop
- laatste logs tonen normale mailbox polling

### Logs bekijken

```bash
journalctl -u bewaarhet --since "24 hours ago"
```

Let op:

- `FOUT`
- `SMTP send failed`
- `Dropbox metadata check error`
- `Dropbox path niet gevonden`
- `rate limit hard threshold exceeded`
- OCR/API errors of onverwacht lege OCR-resultaten

Live meekijken:

```bash
journalctl -u bewaarhet -f
```

### Mailflow sanity

Controleer steekproefsgewijs:

- komen nieuwe mails binnen
- worden mails als seen gemarkeerd na verwerking
- worden replies verstuurd bij zoekresultaten of rejected uploads
- blijven er geen grote aantallen ongelezen mails hangen

## Wekelijkse Checks

### Handmatige backup maken

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin create-backup
```

### Backups tonen

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin list-backups
```

Controleer:

- nieuwste backup is recent
- backupgrootte is plausibel
- rotatie bewaart het verwachte aantal backups

### Restore dry-run

Gebruik de nieuwste backup:

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin restore-backup /var/lib/bewaarhet/backups/<backup>.sqlite3 --dry-run
```

Verwacht:

```text
backup validation passed; no files changed
```

### Consistency check

Snelle check:

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin consistency-check --limit 50
```

Volledige check buiten piekuren:

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin consistency-check
```

Controleer:

- `missing_count`
- `error_count`
- `timeout_count`
- trage records

Deze check verwijdert niets.

## Maandelijkse Checks

### Cleanup report

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin cleanup-report
```

Controleer:

- missing Dropbox files
- ownership failures
- duplicate paths
- temporary/dev paths
- unsupported legacy records

Voer geen confirmed cleanup uit zonder verse backup en expliciete review.

### Offsite backup controle

Controleer:

- offsite backup job draait
- laatste offsite backup is recent
- restore dry-run is periodiek getest
- backupretentie is voldoende

### Dependency en OS updates

Plan onderhoud:

- OS security updates
- Python patch updates
- dependency review
- test suite draaien na updates

## Incident: Dropbox Errors

Symptomen:

- `Dropbox metadata check error`
- `Dropbox link generation duration` hoog
- `Dropbox path niet gevonden`
- consistency-check met veel API errors

Acties:

1. Controleer netwerk/DNS vanaf server.
2. Controleer Dropbox statuspagina.
3. Controleer `.env` waarden:
   - `DROPBOX_REFRESH_TOKEN`
   - `DROPBOX_APP_KEY`
   - `DROPBOX_APP_SECRET`
4. Draai een kleine consistency-check:

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin consistency-check --limit 10
```

5. Bij tokenproblemen: roteer Dropbox credentials en restart worker.

Voer geen cleanup uit als Dropbox checks API errors geven; dan is missing-file detectie niet betrouwbaar.

## Incident: Zoho IMAP Errors

Symptomen:

- worker kan geen ongelezen mails ophalen
- login/auth errors
- mailbox blijft oplopen

Acties:

1. Controleer Zoho status.
2. Controleer `ZOHO_EMAIL`, `ZOHO_IMAP_HOST`, `ZOHO_IMAP_PORT`.
3. Controleer of app-password nog geldig is.
4. Restart worker na credential update:

```bash
sudo systemctl restart bewaarhet
```

5. Check logs:

```bash
journalctl -u bewaarhet --since "10 minutes ago"
```

## Incident: Zoho SMTP Errors

Symptomen:

- `SMTP send failed`
- zoekresultaten worden niet ontvangen
- rejected upload replies komen niet aan

Acties:

1. Controleer `ZOHO_SMTP_HOST`, `ZOHO_SMTP_PORT`, `ZOHO_EMAIL`.
2. Controleer app-password.
3. Controleer of SMTP rate limits of blokkades actief zijn bij Zoho.
4. Controleer logs op:
   - recipient
   - attachment count
   - SMTP duration
   - sanitized exception

Let op: succesvolle SMTP acceptatie betekent niet altijd mailbox delivery bij de ontvanger.

## Incident: OCR.space Errors

Symptomen:

- veel documenten met lege OCR-tekst
- slechtere classificatie
- onverwacht veel `overig`

Acties:

1. Controleer OCR.space API key.
2. Controleer OCR.space status/quota.
3. Controleer of uploads rond 15 MB of beeldconversie problemen geven.
4. Zoek in logs naar OCR-gerelateerde timing/fouten.
5. Na herstel kan handmatige herverwerking nodig zijn; daar is momenteel geen aparte replay-tool voor.

## Incident: OpenAI Errors

OpenAI is optioneel en wordt alleen gebruikt als classificatie fallback bij twijfel.

Symptomen:

- meer documenten vallen terug naar `overig`
- classificatie minder precies bij twijfelgevallen

Acties:

1. Controleer `OPENAI_API_KEY`.
2. Controleer `OPENAI_MODEL`.
3. Controleer API quota/status.
4. Als OpenAI niet beschikbaar is, blijft de worker functioneren met regelgebaseerde classificatie.

## Incident: Rate Limits

Symptomen:

- `rate limit soft threshold exceeded`
- `rate limit hard threshold exceeded`
- gebruikers krijgen tijdelijk "Probeer het later opnieuw"

Acties:

1. Controleer of het gedrag past bij echte bulk cleanup of misbruik.
2. Controleer action type in logs:
   - `storage`
   - `search`
   - `rejected_upload`
   - `zip_upload`
   - `export_all`
3. Wacht cooldown af bij hard limit.
4. Onderzoek mail loops of spam floods.

Rate limits zijn momenteel in code gedefinieerd en niet via `.env` configureerbaar.

## Incident: Database Problems

Symptomen:

- startup integrity check faalt
- SQLite errors in logs
- databasebestand ontbreekt of is leeg

Acties:

1. Stop worker:

```bash
sudo systemctl stop bewaarhet
```

2. Controleer backups:

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin list-backups
```

3. Valideer backup:

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin restore-backup /var/lib/bewaarhet/backups/<backup>.sqlite3 --dry-run
```

4. Restore indien nodig:

```bash
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin restore-backup /var/lib/bewaarhet/backups/<backup>.sqlite3 --confirm
```

5. Start worker:

```bash
sudo systemctl start bewaarhet
```

## Confirmed Cleanup Safety

Voor elke destructive admin actie:

1. Maak backup.
2. Draai dry-run of report.
3. Inspecteer output.
4. Draai alleen `--confirm` als de kandidaten kloppen.
5. Draai daarna opnieuw report.

Deze cleanup commands verwijderen geen Dropbox files:

- `cleanup-orphaned --confirm`
- `cleanup-testdata --confirm`
- `reset-dev-environment --confirm`

Gebruik `reset-dev-environment` niet op productie.

## Na Deploy

Na elke deploy:

```bash
sudo systemctl status bewaarhet
journalctl -u bewaarhet --since "15 minutes ago"
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin create-backup
sudo -u bewaarhet /opt/bewaarhet_python_backend/.venv/bin/python -m bewaarhet.admin consistency-check --limit 20
```

Controleer dat:

- worker loopt
- database integrity goed is
- Dropbox metadata checks werken
- geen onverwachte SMTP/IMAP errors optreden
