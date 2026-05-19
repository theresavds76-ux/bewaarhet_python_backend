# Bewaarhet Python backend

Bewaarhet is een Python-worker die documenten bewaart en terugvindt via e-mail. De worker leest Zoho-mail via IMAP, verwerkt documenten, bewaart bestanden in Dropbox, slaat metadata op in SQLite en stuurt zoekresultaten terug via SMTP met tijdelijke downloadlinks.

## Architectuur

- `bewaarhet.worker`: single-process worker met startup diagnostics en periodieke mailbox polling.
- `bewaarhet.mail_client`: Zoho IMAP ophalen, mail parsing en SMTP replies.
- `bewaarhet.processor`: routing, upload safety, OCR, classificatie, Dropbox upload en SQLite metadata.
- `bewaarhet.search_reply`: search retrieval, scoring, ownership checks en tijdelijke Dropbox downloadlinks.
- `bewaarhet.database`: SQLite schema, migrations, document search en rate-limit tabellen.
- `bewaarhet.dropbox_client`: Dropbox refresh-token client, uploads, metadata checks en temporary links.
- `bewaarhet.ocr`: OCR.space client.
- `bewaarhet.classifier`: regelgebaseerde classificatie met optionele OpenAI fallback.
- `bewaarhet.admin`: backup, restore, consistency check en cleanup utilities.

## Hoofdflows

### Opslaan

1. De worker leest nieuwe mail uit Zoho via IMAP.
2. Mail wordt gerouteerd op ontvanger, zoekintentie en aanwezigheid van bijlagen.
3. Bijlagen worden veilig gevalideerd voordat OCR, opslag of Dropbox upload plaatsvindt.
4. OCR.space leest documenttekst waar mogelijk.
5. Classificatie gebeurt eerst met regels; OpenAI wordt alleen gebruikt als optionele fallback bij twijfel.
6. Bestanden worden opgeslagen in Dropbox onder de geconfigureerde klantmap.
7. Metadata, OCR-tekst en zoekvelden worden opgeslagen in SQLite.

### Zoeken

1. Zoekmail wordt herkend via `zoek@bewaarhet.nl`, `service@bewaarhet.nl` met zoekintentie, of expliciete zoektermen.
2. SQLite zoekt alleen binnen de canonical sender identity.
3. Resultaten worden gescoord en opnieuw gevalideerd op ownership.
4. Voor geldige resultaten worden tijdelijke Dropbox downloadlinks gemaakt.
5. De reply vermeldt dat downloadlinks tijdelijk beveiligd zijn en automatisch verlopen.

## Externe services

- Zoho IMAP/SMTP voor inkomende mail en uitgaande replies.
- Dropbox voor documentopslag en tijdelijke downloadlinks.
- SQLite voor lokale metadata, rate-limit counters en cooldowns.
- OCR.space voor OCR.
- OpenAI optioneel voor classificatie fallback.

## Installatie lokaal

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m bewaarhet.init_db
.\.venv\Scripts\python.exe -m bewaarhet.worker
```

Linux/macOS:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
./.venv/bin/python -m bewaarhet.init_db
./.venv/bin/python -m bewaarhet.worker
```

Vul `.env` met echte secrets voordat je de worker start.

## Configuratie

Zie `.env.example` voor alle huidige configuratiesleutels. Belangrijk:

- Gebruik voor Zoho bij voorkeur een app-password.
- Dropbox gebruikt refresh-token flow:
  - `DROPBOX_REFRESH_TOKEN`
  - `DROPBOX_APP_KEY`
  - `DROPBOX_APP_SECRET`
- `DROPBOX_ACCESS_TOKEN` wordt door de huidige code niet gebruikt.
- Runtime paden zijn configureerbaar via `DATA_DIR`, `DATABASE_PATH`, `BACKUP_DIR` en `LOG_DIR`.

## Toegestane bestandstypen

De huidige veilige allowlist is:

- `.pdf`
- `.doc`
- `.docx`
- `.odt`
- `.xls`
- `.xlsx`
- `.ods`
- `.txt`
- `.csv`
- `.rtf`
- `.jpg`
- `.jpeg`
- `.png`
- `.gif`
- `.bmp`
- `.tiff`
- `.zip`

Standaard maximale bestandsgrootte: 15 MB.

Geblokkeerde of niet-ondersteunde typen zoals `.exe`, `.js`, `.vbs`, `.bat`, `.cmd`, `.ps1`, `.scr`, `.msi`, `.html`, `.php`, macro-bestanden zoals `.docm` en `.xlsm`, onbekende extensies en archieven zonder veilige validator zoals `.rar`, `.7z`, `.tar` en `.gz` worden geweigerd.

ZIP-bestanden worden veilig gevalideerd op inhoud, padveiligheid, bestandstelling en grootte. ZIP-bestanden worden als archief opgeslagen en niet uitgepakt voor businesslogica of OCR.

## Admin commands

Alle commands draaien via:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin <command>
```

Linux/macOS:

```bash
./.venv/bin/python -m bewaarhet.admin <command>
```

Beschikbare commands:

```text
create-backup
list-backups
restore-backup
consistency-check
cleanup-report
cleanup-orphaned
cleanup-testdata
reset-dev-environment
backup-scheduler
```

## Backup en restore

Maak een backup:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin create-backup
```

Toon backups:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin list-backups
```

Valideer restore zonder wijzigingen:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin restore-backup path\to\backup.sqlite3 --dry-run
```

Restore met expliciete bevestiging:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin restore-backup path\to\backup.sqlite3 --confirm
```

## Consistency en cleanup

Dropbox consistency check:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin consistency-check
```

Snelle/debug check:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin consistency-check --limit 50
.\.venv\Scripts\python.exe -m bewaarhet.admin consistency-check --since-id 100
```

Cleanup rapport:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin cleanup-report
```

Dry-run orphan cleanup:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin cleanup-orphaned --dry-run
```

Confirmed orphan cleanup verwijdert alleen SQLite metadata rows en geen Dropbox files:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin cleanup-orphaned --confirm
```

Dry-run testdata cleanup:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin cleanup-testdata --dry-run
```

Confirmed testdata cleanup verwijdert alleen SQLite metadata rows en geen Dropbox files:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin cleanup-testdata --confirm
```

Development reset vereist expliciete bevestiging en verwijdert geen Dropbox files:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin reset-dev-environment --confirm
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest
```

## Deployment

Zie `DEPLOYMENT_RUNBOOK.md` voor VPS/server deployment, systemd setup, backup/restore, rollback en secrets rotation.

Zie `OPERATIONS_RUNBOOK.md` voor dagelijkse, wekelijkse en maandelijkse operationele checks.

## Website

De statische website/documentatie staat in `docs/`.

- GitHub Pages deployment vanaf branch `main`, map `/docs`.
- Custom domain: `bewaarhet.nl`.
