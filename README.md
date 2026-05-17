# Bewaarhet Python backend

Vervangt het Make-scenario door een goedkope Python-worker.

## Functie

- Leest nieuwe mail uit Zoho via IMAP.
- Verwerkt bijlagen per stuk.
- Blokkeert te grote of ongewenste bestanden.
- Doet OCR via OCR.space.
- Classificeert eerst met regels, daarna alleen bij twijfel met OpenAI.
- Uploadt naar Dropbox.
- Slaat metadata op in SQLite.
- Beantwoordt zoekmails met tijdelijke Dropbox-links.

## Installatie lokaal

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m bewaarhet.init_db
python -m bewaarhet.worker
```

## Belangrijk

Gebruik in Zoho bij voorkeur een app-password, niet je normale wachtwoord.

## Bestandsregels

Standaard toegestaan:

- PDF, JPG/JPEG, PNG, HEIC
- DOC/DOCX/ODT
- XLS/XLSX/ODS/CSV
- TXT/RTF
- PPT/PPTX/ODP
- ZIP

Maximaal 15 MB. ZIP-bestanden worden als archief opgeslagen en niet uitgepakt of ge-OCR'd.

## Website deployment

- GitHub Pages should deploy from the main branch `/docs` folder.
- Custom domain: bewaarhet.nl
- DNS must be configured at Hostnet.
