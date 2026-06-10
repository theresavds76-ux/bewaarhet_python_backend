# Bewaarhet documentkwaliteit testen

Datum: 2026-06-09

## Doel

Bewaarhet betrouwbaarder maken voordat billing live gaat of echte proefgebruikers worden geworven.

Deze kwaliteitslus test lokaal:

- OCR-bruikbaarheid;
- documentherkenning;
- classifier-route en AI-fallbackbeslissing;
- partij/afzenderdetectie;
- purpose/domain;
- bestandsnaamgeving;
- zoekbaarheid;
- regressies ten opzichte van vorige runs.

Er wordt niets gemaild, niets naar Dropbox gestuurd en billing wordt niet geraakt.

## Testsets

Er zijn twee vaste testsets.

### Synthetische baseline

```text
testdata/documents/
|- invoices/
|- receipts/
|- policies/
|- contracts/
|- tax/
|- general/
|- bad_quality/
`- expected.json
```

Deze set bevat ideale en licht rommelige documenten voor snelle regressietests:

- KPN factuur;
- bol.com aankoopbewijs;
- Lemonade polisblad;
- Ziggo contract;
- Belastingdienst aanslag;
- algemene notitie;
- slechte scan/foto-achtige Jumbo kassabon.

### Real-world kwaliteitsset

```text
testdata/real_world_documents/
|- invoices/
|- receipts/
|- policies/
|- contracts/
|- tax/
|- general/
|- bad_quality/
`- expected.json
```

Deze set bevat veilige, zelf gegenereerde praktijkvarianten:

- foto met schaduw;
- lage resolutie;
- afgesneden document;
- document met stempel;
- document met handgeschreven aantekening;
- gedraaid/wazig document;
- meertalig document;
- document met meerdere pagina's.

De documenten bevatten geen echte klantdata, geen privegegevens van derden en geen willekeurige persoonlijke documenten van internet. OCR-sidecars worden gebruikt als deterministische testinvoer, zodat de regressietests stabiel blijven.

Voor elk document staat in `expected.json`:

- verwacht documenttype;
- verwachte partij indien mogelijk;
- minimale OCR-tekstlengte;
- OCR-termen die aanwezig moeten zijn;
- bestandsnaamonderdelen die aanwezig moeten zijn;
- zoektermen waarop het document gevonden moet worden.

## Testdocumenten opnieuw genereren

Synthetische baseline:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.tools.create_sample_documents
```

Real-world kwaliteitsset:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.tools.create_real_world_documents
```

## Kwaliteitsrapport draaien

Synthetische baseline:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.tools.process_test_documents
```

Real-world kwaliteitsset:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.tools.process_test_documents --testdata testdata\real_world_documents --report reports\real_world_document_quality_report.md --history reports\real_world_document_quality_history.json
```

De processor maakt daarnaast een reviewbaar foutenanalyserapport:

```text
reports/document_failure_review.md
```

En een visuele reviewmap:

```text
reports/review/
|- failed/
|- uncertain/
`- index.md
```

In deze map staan kopieen van testdocumenten die fout of onzeker zijn beoordeeld, plus per document een korte detailpagina met OCR-preview, classifier-uitleg en aanbeveling.

Het script faalt met exitcode `1` als:

- OCR te weinig tekst oplevert;
- OCR-termen onvoldoende worden gevonden;
- classificatie niet overeenkomt;
- bestandsnaam niet logisch genoeg is;
- een zoekterm onvoldoende scoort.

## Rapportage

De rapporten staan in:

- `reports/document_quality_report.md`
- `reports/real_world_document_quality_report.md`

De real-world history staat in:

- `reports/real_world_document_quality_history.json`

Het rapport toont:

- totaal aantal documenten;
- OCR-score;
- classificatiescore;
- zoekscore;
- gemiddelde classificatieconfidence;
- performance per documenttype;
- trends ten opzichte van de vorige run;
- concrete failures of twijfelgevallen.

## Human review mode

Voor menselijke controle:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.tools.review_document_quality --testdata testdata\real_world_documents --report reports\document_failure_review.md
```

Dit rapport toont voor failures en onzekerheden:

- bestandsnaam en documentvariant;
- verwachte en voorspelde categorie;
- OCR-score en OCR-preview;
- gefaalde of lage zoekvragen;
- classifier-route;
- rule-based confidence;
- fallback-threshold;
- AI fallback enabled/used/considered;
- waarom AI fallback wel of niet is gebruikt;
- wat een mens waarschijnlijk zou herkennen;
- een concrete aanbeveling.

Dezelfde command werkt ook de visuele reviewmap bij:

```text
reports/review/index.md
```

Echte AI fallback staat in de lokale kwaliteitsflow standaard uit. Daardoor worden er geen externe API-calls gedaan en verlaat testdata de machine niet.

Alleen als dit expliciet wordt meegegeven, mag de testflow AI fallback proberen:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.tools.review_document_quality --testdata testdata\real_world_documents --allow-ai-fallback
```

Ook dan is een geconfigureerde `OPENAI_API_KEY` nodig. Zonder die key wordt gerapporteerd waarom fallback niet beschikbaar was.

## Huidige baseline

Laatste real-world run:

```text
Totaal aantal documenten: 7
OCR bruikbaar: 7/7 (100.0%)
Correct geclassificeerd: 7/7 (100.0%)
Uncertain cases: 1
AI fallback mogelijk maar niet gebruikt: 1
Zoektests geslaagd: 14/14 (100.0%)
Gemiddelde classificatieconfidence: 0.864
```

Er is een laag-confidence geval:

- Zorgverzekering/polis wordt bewust veilig als `overig` geclassificeerd, maar krijgt wel purpose `polis`, domain `verzekeringen`, een logische bestandsnaam en succesvolle zoekresultaten.

Dat is acceptabeler dan agressief fout classificeren als contract.

## Automatische regressietest

```powershell
.\.venv\Scripts\python.exe -m pytest test_document_quality_flow.py -q
```

Deze test controleert zowel de synthetische baseline als de real-world kwaliteitsset.

## Verbeteringen die zijn toegevoegd

- Classifier kan confidence en reden teruggeven via `classify_document_with_reason`.
- Aankoopbewijzen/ordercontext worden beter als bon/aankoopbewijs herkend.
- Bonnen met handgeschreven notities blijven bonnen als er sterke bon-signalen zijn.
- Recept/notitie-documenten worden als notitie herkend.
- Contractherkenning vereist sterker contractbewijs; alleen `ingangsdatum` is niet genoeg.
- Zoekterm `belastingaanslag` wordt uitgebreid naar verwante termen zoals `belasting`, `aanslag` en `inkomstenbelasting`.
- Real-world rapportage toont trends en performance per documenttype.
- Failure review rapport toont OCR-preview, classifier-route, AI-fallbackbeslissing en aanbeveling per onzeker/fout document.

## Veiligheidsafspraken

- Geen live billing activeren.
- Geen echte gebruikersdata gebruiken.
- Geen willekeurige privebestanden van internet gebruiken.
- Geen mail versturen vanuit de testflow.
- Geen Dropbox upload in de testflow.
- Geen externe AI-calls tenzij `--allow-ai-fallback` expliciet wordt gebruikt.
- Alleen synthetische, publieke demo- of geanonimiseerde documenten gebruiken.

## Volgende verbeterpunten

1. Testset uitbreiden naar minimaal 30 documenten.
2. Meer slechte scans en mobiele foto's toevoegen.
3. Echte geanonimiseerde Nederlandse voorbeelden toevoegen als die veilig beschikbaar zijn.
4. Polissen eventueel als eigen categorie overwegen, maar pas na meer testdata.
5. OCR-sidecars later vergelijken met echte OCR-output van OCR.space of een lokale OCR-engine.
6. Precision/recall meten met meerdere documenten per zoekvraag.
