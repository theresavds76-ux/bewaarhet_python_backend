# Bewaarhet Project Overview

Datum analyse: 2026-05-19

Dit document beschrijft de huidige staat van de volledige repo. Er zijn geen codewijzigingen of refactors uitgevoerd; dit is alleen een architectuur- en risicodocument.

## Architectuuroverzicht

Bewaarhet is een Python backend-worker die e-mail gebruikt als primaire interface. De worker leest inkomende Zoho-mail via IMAP, routeert berichten naar opslag of zoekfunctionaliteit, verwerkt documenten, slaat bestanden op in Dropbox en bewaart metadata in SQLite.

De applicatie is modulair maar nog duidelijk een single-process systeem:

- `bewaarhet.worker`: hoofdloop, startup diagnostics, periodieke polling.
- `bewaarhet.mail_client`: IMAP ophalen, mail parsing, SMTP replies.
- `bewaarhet.processor`: routering, uploadvalidatie, OCR, classificatie, Dropbox upload, metadata-opslag.
- `bewaarhet.search_reply`: zoekscore, ownership checks, tijdelijke downloadlinks, antwoordmail.
- `bewaarhet.database`: SQLite schema, migrations, document insert/search, rate-limit tabellen.
- `bewaarhet.dropbox_client`: Dropbox upload, metadata check, temporary links.
- `bewaarhet.ocr`: OCR.space client met beeldverkleining voor grote afbeeldingen.
- `bewaarhet.classifier` en `bewaarhet.utils`: regelgebaseerde classificatie, supplier/purpose/domain detectie, bestandsnaamgeneratie, log-sanitizing.
- `bewaarhet.rate_limiter`: SQLite-gebaseerde per-sender rate limiting.
- `bewaarhet.backup`, `bewaarhet.maintenance`, `bewaarhet.cleanup`, `bewaarhet.admin`: beheer, backups, consistency checks en pre-productie cleanup.

Externe services:

- Zoho IMAP/SMTP voor mailinname en replies.
- Dropbox voor permanente documentopslag en tijdelijke downloadlinks.
- OCR.space voor OCR.
- OpenAI als optionele classificatie-fallback bij twijfel.
- SQLite als lokale metadata- en rate-limit store.

## Belangrijkste Flows

### Worker startup

1. `python -m bewaarhet.worker` start `run_forever`.
2. `startup_diagnostics` logt database-, backup- en logpaden.
3. Runtime folders worden aangemaakt via `settings.ensure_directories`.
4. `init_db` maakt of migreert SQLite schema.
5. `check_integrity` voert SQLite integrity check uit.
6. Worker pollt periodiek `fetch_unseen`.

### Mail routing

`processor.process_mail` bepaalt de route:

- Self-trigger/service-mail wordt geblokkeerd.
- Mail aan `zoek@bewaarhet.nl` wordt search.
- Mail aan `bewaren@bewaarhet.nl` wordt storage.
- Mail aan `service@bewaarhet.nl` wordt search als zoekintentie wordt herkend, anders storage.
- Mail met bijlagen wordt storage.
- Mail zonder bijlagen kan alsnog search of document-body storage worden op basis van heuristieken.

Rate limiting wordt toegepast voor storage, search, ZIP upload en rejected uploads.

### Document upload flow

1. Sender wordt gecanoniseerd met lowercase e-mailadres.
2. `safe_customer_folder` wordt afgeleid door `@` naar `_at_` te vervangen.
3. Per attachment wordt bestandsnaam, extensie, grootte en content gecontroleerd.
4. ZIP-inhoud wordt veilig gevalideerd, maar niet uitgepakt voor opslag/OCR.
5. Niet-ZIP bestanden gaan naar OCR.space.
6. Classificatie gebeurt eerst met regels, daarna optioneel OpenAI bij twijfel.
7. Supplier, purpose, domain en documentdatum worden heuristisch bepaald.
8. Nieuwe bestandsnaam wordt gegenereerd en collisions worden opgelost.
9. Bestand wordt geupload naar Dropbox.
10. Metadata wordt in SQLite opgeslagen.

### Document-body mail flow

Voor documentachtige mails zonder bijlage:

1. Body en subject worden als semantische tekst gebruikt.
2. Mailbody wordt omgezet naar een eenvoudige PDF.
3. PDF wordt geupload naar Dropbox.
4. Metadata wordt opgeslagen zoals bij een attachment.

### Search reply flow

1. Query wordt uit subject/body gehaald.
2. `search_documents` zoekt alleen binnen de canonical sender identity.
3. Resultaten worden gescoord in `search_reply._score`.
4. Resultaten onder `MIN_SEARCH_RESULT_SCORE` vallen af.
5. Ownership validation filtert resultaten nogmaals.
6. Voor overgebleven resultaten worden tijdelijke Dropbox-links gemaakt.
7. Antwoordmail vermeldt dat links tijdelijk beveiligd zijn en automatisch verlopen.
8. Als Dropbox metadata of link generation aangeeft dat een bestand ontbreekt, wordt `missing_file` gezet.

## Database Structuur

SQLite is de centrale metadata store. De actieve database staat standaard in:

```text
data/bewaarhet.sqlite3
```

Huidige tabellen:

- `documents`
- `rate_limit_events`
- `rate_limit_cooldowns`

### `documents`

Belangrijkste kolommen:

- `id`: primaire sleutel.
- `customer_identity`: canonical customer identity.
- `customer_email`: canonical sender email.
- `safe_customer_folder`: veilige mapnaam voor Dropbox.
- `category`: hoofdmap/categorie, zoals `facturen`, `belasting`, `notities`.
- `filename`: gegenereerde bestandsnaam.
- `date_received`: ontvangstdatum.
- `dropbox_path`: verwacht Dropbox-pad.
- `original_filename`: originele attachmentnaam of `email_body.pdf`.
- `document_date`: gedetecteerde documentdatum.
- `domain`: levens-/businessdomein.
- `supplier`: gedetecteerde leverancier/partij.
- `purpose`: semantisch doel, zoals `factuur`, `polis`, `notitie`.
- `title`: mailsubject.
- `ocr_preview`: korte preview.
- `ocr_text`: volledige OCR/searchtekst.
- `year`, `month`: zoekvelden.
- `missing_file`: marker voor ontbrekende Dropbox-file.
- `created_at`: SQLite timestamp.

Indexes:

- `idx_documents_customer`
- `idx_documents_customer_identity`
- `idx_documents_safe_customer`
- `idx_documents_search`
- `idx_documents_domain_search`

Unique constraint:

```text
UNIQUE(customer_email, filename, date_received, dropbox_path)
```

### Rate limiter tabellen

`rate_limit_events`:

- `sender`
- `action`
- `created_at`

`rate_limit_cooldowns`:

- `sender`
- `action`
- `cooldown_start`
- `cooldown_until`

Deze tabellen maken rate limiting persistent over worker restarts.

## Security Model

### Customer isolation

De isolatie is sender-first:

- Customer identity is exact lowercase sender e-mailadres.
- Verschillende aliases worden niet automatisch samengevoegd.
- Search query laadt alleen records voor de canonical sender identity.
- Voor verzending wordt ownership opnieuw gevalideerd via:
  - `customer_identity` of `customer_email`
  - `safe_customer_folder`
  - aanwezigheid van de verwachte folder in `dropbox_path`

Als ownership faalt, wordt het resultaat niet verstuurd en wordt een gesanitiseerde warning gelogd.

### Upload safety

Bestandsvalidatie zit in `processor.py`:

- Allowlist: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.docx`, `.xlsx`, `.csv`, `.txt`, `.zip`.
- Blocklist: onder andere `.exe`, `.js`, `.vbs`, `.bat`, `.cmd`, `.ps1`, `.scr`, `.msi`, `.html`, `.php`.
- Magic-byte/content checks voor PDF, JPG, PNG, ZIP, DOCX/XLSX en text/CSV.
- Reject bij extensie/content mismatch.
- Max grootte: 15 MB per attachment.
- 0-byte bestanden worden geweigerd.
- Bestandsnamen worden gecontroleerd op traversal, separators, control characters en lengte.
- ZIP safety:
  - max 20 files
  - max 30 MB totaal uncompressed
  - max 15 MB per member
  - geen nested ZIP
  - geen traversal/absolute/drive paths
  - members krijgen dezelfde allowlist/content checks

### Logging privacy

`sanitize_for_log` redigeert:

- Credential-achtige waarden.
- IBAN-achtige waarden.
- Links.
- Secrets uit environment variables.
- OpenAI/Dropbox-achtige secret formats.

OCR/debug logging logt lengtes en previews in plaats van volledige inhoud. Toch blijft dit een belangrijk aandachtspunt, omdat sommige debugregels nog customer identifiers en filenames tonen. Dat is nuttig voor debugging, maar PII-gevoelig.

### Rate limiting

Acties:

- `storage`: soft 120/h, hard 200/h.
- `search`: soft 30/h, hard 60/h.
- `export_all`: hard 3/dag.
- `rejected_upload`: soft 10/h, hard 15/h.
- `zip_upload`: soft 30/h, hard 60/h.

Soft limit geeft korte backoff. Hard limit geeft cooldown van 1 uur en stuurt vriendelijke reply.

### Belangrijkste security lacunes

- SQLite bevat volledige OCR-tekst en mogelijk gevoelige notities in plaintext.
- Geen encryptie at rest voor SQLite of backups.
- Dropbox is de feitelijke documentopslag; toegang hangt volledig aan Dropbox credentials en app permissies.
- Geen geformaliseerd audit log model, alleen stdout/print logging.
- `.env.example` noemt nog `DROPBOX_ACCESS_TOKEN`, terwijl de code `DROPBOX_REFRESH_TOKEN`, app key en app secret gebruikt.

## Retrieval Flow

Retrieval bestaat uit SQLite candidate retrieval, scoring, ownership filtering en link generation.

1. Query wordt genormaliseerd en uitgebreid met synoniemen.
2. `database.search_documents` voert `LIKE` queries uit over filename, category, domain, supplier, purpose, title, OCR preview, OCR text, Dropbox path, year en month.
3. SQL filtert op canonical customer identity en `missing_file = 0`.
4. `search_reply._score` geeft punten voor exacte en fuzzy matches.
5. Credential queries krijgen speciale behandeling zodat notities met wachtwoorden/codes gevonden kunnen worden, maar business-document footers minder snel false positives geven.
6. Resultaten onder score 30 worden afgewezen.
7. `_record_owned_by_sender` voert strict ownership validation uit.
8. Per geldig resultaat wordt een tijdelijke Dropbox-link gemaakt.
9. Als Dropbox meldt dat het bestand ontbreekt, wordt de record gemarkeerd met `missing_file`.
10. De replymail bevat de links plus uitleg dat links tijdelijk zijn.

Sterk punt: retrieval zoekt niet globaal en heeft dubbele ownership checks.

Zwak punt: retrieval gebruikt SQL `LIKE` over mogelijk grote OCR-tekstvelden en heeft geen FTS-index.

## Admin/Maintenance Tooling

CLI entrypoint:

```text
python -m bewaarhet.admin <command>
```

Beschikbare commands:

- `create-backup`
- `list-backups`
- `restore-backup`
- `consistency-check`
- `cleanup-report`
- `cleanup-orphaned`
- `cleanup-testdata`
- `reset-dev-environment`
- `backup-scheduler`

### Backup/restore

Backups:

- timestamped SQLite backups
- atomic temp-file creation
- validation via `PRAGMA integrity_check`
- configurable backup folder
- rotation via `BACKUP_KEEP_LATEST`

Restore:

- dry-run mode
- validation before overwrite
- explicit `--confirm` required
- optional backup of current DB before restore

### Consistency check

`consistency-check` controleert SQLite records tegen Dropbox metadata:

- progress logging
- `--limit`
- `--since-id`
- slow-record logging
- missing files
- invalid paths
- duplicate paths
- timeout/API error summaries

Er wordt niet recursief door Dropbox gescand en er wordt niets verwijderd.

### Cleanup tooling

`cleanup-report` rapporteert:

- orphaned records
- missing Dropbox files
- unsupported legacy extensions
- temporary/dev paths
- duplicate records
- ownership failures
- likely test/dev records

`cleanup-orphaned --confirm` verwijdert alleen SQLite metadata rows voor:

- ontbrekende Dropbox files
- invalid/temp paths
- ownership/path failures

`cleanup-testdata --confirm` verwijdert alleen SQLite metadata rows voor:

- test/dev filename patterns
- unsupported legacy extensions

`reset-dev-environment --confirm`:

- maakt eerst backup
- wist documentmetadata en rate-limiter tabellen
- kan optioneel logs wissen
- verwijdert geen Dropbox files

## Deployment Readiness

Sterke punten:

- Runtime paden zijn configureerbaar via environment variables.
- Data, backup en log folders worden automatisch aangemaakt.
- SQLite integrity check bij startup.
- Systemd unit is aanwezig.
- `.gitignore` sluit `.env`, `.venv`, `data/` en SQLite-bestanden uit.
- Backups en restore zijn aanwezig.
- Dropbox consistency check is veilig en read-only.
- Testdekking is breed voor upload safety, search, customer isolation, rate limiting, logging sanitization en backup/maintenance.

Nog niet productieklaar zonder extra operationele afspraken:

- Geen observability stack, alleen stdout.
- Geen systematische logrotatie of structured JSON logging.
- Geen secret management buiten `.env`.
- Geen encryptie of offsite backup-strategie voor SQLite backups.
- Geen healthcheck endpoint of watchdog buiten systemd restart.
- Geen queue; één langzaam OCR/Dropbox/SMTP-call blokkeert de worker.
- Geen migratieframework; schema-evolutie gebeurt handmatig in `database.init_db`.
- README en `.env.example` zijn deels verouderd t.o.v. huidige implementatie.

## Weak Points

- `utils.py` is zeer groot en bevat veel domeinlogica: note detection, supplier detection, purpose detection, filename generation en domain detection zitten door elkaar.
- Search gebruikt dubbele logica: query expansion/scoring zit deels in `database.py` en deels in `search_reply.py`.
- OCR errors worden stil teruggebracht naar lege tekst; daardoor kan falen onzichtbaar leiden tot slechtere classificatie.
- Dropbox upload en SQLite insert zijn niet atomair. Een upload kan slagen terwijl DB insert faalt, of andersom kan metadata stale worden.
- SMTP send is beter gelogd, maar delivery na SMTP-acceptatie blijft buiten controle van de app.
- Cleanup commands vertrouwen op Dropbox metadata checks; netwerkflakiness kan confirm-runs gedeeltelijk laten verlopen.
- `cleanup_missing_files.py` is ouder/ruwer dan het nieuwere admin consistency/cleanup tooling en mist de nieuwere diagnostics.
- README en `.env.example` noemen ruimere bestandsallowlist dan de code toestaat.
- `.env.example` gebruikt `DROPBOX_ACCESS_TOKEN`, maar de code gebruikt refresh-token flow.
- Full OCR text in SQLite maakt de database zeer gevoelig.

## Technical Debt

- Refactor `utils.py` in kleinere modules:
  - filename generation
  - supplier detection
  - purpose/domain detection
  - note detection
  - log sanitization
- Centraliseer query parsing en term expansion.
- Vervang ad-hoc print logging door een logging abstraction met levels en structured fields.
- Maak een formeel migration framework of minimaal migration versioning.
- Voeg een service-layer toe voor document persistence zodat Dropbox upload en DB write explicieter als workflow worden behandeld.
- Harmoniseer README, `.env.example`, tests en runtime config.
- Voeg type-strengheid toe rond SQLite row/dict access en record payloads.
- Maak oude scripts zoals `cleanup_missing_files.py` expliciet deprecated of breng ze gelijk met admin tooling.

## Bottlenecks

- OCR.space calls kunnen lang duren en blokkeren de worker.
- Dropbox metadata checks zijn per record en serieel.
- Dropbox client wordt per operatie opnieuw aangemaakt.
- Search gebruikt `LIKE '%term%'` op meerdere kolommen inclusief OCR-tekst.
- SMTP send gebeurt synchroon in de mailverwerking.
- Eén worker verwerkt mails sequentieel.
- Grote OCR-tekst in SQLite vergroot DB en maakt search trager.
- ZIP validatie kan bij veel/grote members CPU/IO kosten, al zijn er limieten.

## Scaling Concerns

Bij groei naar echte productie ontstaan vooral deze schaalproblemen:

- Een mailbox-polling worker zonder queue is kwetsbaar voor pieken.
- Langzame externe calls blokkeren andere mails.
- SQLite kan prima voor lage volumes, maar full-text search en gelijktijdigheid worden beperkend.
- Rate limiting is per lokale SQLite DB; bij meerdere workers/servers is dit niet gedeeld.
- Backups zijn lokaal; bij VPS of PC-crash is offsite replicatie nodig.
- Dropbox consistency checks worden traag bij veel records.
- Search relevance en deterministic heuristics worden moeilijker onderhoudbaar naarmate documenttypes toenemen.

## Aanbevolen Volgende Stap

Maak eerst een production-readiness hardening ronde zonder feature-uitbreiding:

1. Update README en `.env.example` zodat ze exact overeenkomen met de huidige config en allowlist.
2. Voeg een lightweight structured logging wrapper toe die `sanitize_for_log` centraal afdwingt.
3. Introduceer SQLite FTS5 voor document search, of ontwerp alvast een migratiepad daarnaartoe.
4. Splits `utils.py` in kleinere domeinmodules met behoud van gedrag.
5. Voeg een runbook toe voor backup, restore, consistency check en cleanup op de VPS.
6. Richt offsite backup in voor `data/backups`.

De meest waardevolle eerste concrete stap is documentatie/config synchroniseren (`README.md`, `.env.example`, deployment runbook). Dat verlaagt migratierisico direct zonder businesslogica, routing of searchrelevance te raken.
