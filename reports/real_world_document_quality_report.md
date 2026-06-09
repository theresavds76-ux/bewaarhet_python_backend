# Bewaarhet document quality report

## Samenvatting

- Testset: `testdata\real_world_documents`
- Totaal aantal documenten: 7
- OCR bruikbaar: 7/7 (100.0%)
- Gemiddelde OCR termscore: 1.0
- Correct geclassificeerd: 7/7 (100.0%)
- Uncertain cases: 1
- Fout geclassificeerd: 0
- AI fallback mogelijk maar niet gebruikt: 1
- Zoektests geslaagd: 14/14 (100.0%)
- Gemiddelde classificatieconfidence: 0.864

## Trends

- Vorige run OCR: 100.0% -> huidige run: 100.0%
- Vorige run classificatie: 100.0% -> huidige run: 100.0%
- Vorige run zoekscore: 100.0% -> huidige run: 100.0%
- Vorige run documenten: 7 -> huidige run documenten: 7

## Performance per documenttype

- belasting: OCR 1/1, classificatie 1/1, zoektests 2/2
- bonnen: OCR 1/1, classificatie 1/1, zoektests 2/2
- contracten: OCR 1/1, classificatie 1/1, zoektests 2/2
- facturen: OCR 2/2, classificatie 2/2, zoektests 4/4
- notities: OCR 1/1, classificatie 1/1, zoektests 2/2
- overig: OCR 1/1, classificatie 1/1, zoektests 2/2

## Details

### shadow_tax_assessment

- Bestand: `testdata\real_world_documents\tax\schaduw_belastingaanslag.png`
- OCR: text_found, chars=163, termscore=1.0, ok=True
- Verwacht type: belasting
- Gevonden type: belasting, confidence=0.98
- Reden: belasting won with score 38; evidence: strong:belastingdienst, strong:aanslag, strong:voorlopige aanslag, strong:aanslagnummer, strong:inkomstenbelasting
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: belastingdienst (ok=True)
- Purpose/domain: betaalinformatie/belasting
- Bestandsnaam: `belasting_belastingdienst_betaalinformatie_04-06-2026.png` (ok=True)
- Zoektests: belastingaanslag=100 ok, belastingdienst aanslag=100 ok

### lowres_health_policy

- Bestand: `testdata\real_world_documents\policies\lage_resolutie_zorgverzekering.png`
- OCR: text_found, chars=147, termscore=1.0, ok=True
- Verwacht type: overig
- Gevonden type: overig, confidence=0.25
- Reden: contract score lacked contract evidence; fallback not called
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.25/0.65
- AI fallback: enabled=False, considered=True, used=False
- AI fallback beslissing: AI fallback disabled for this run
- Partij: zorgzeker_verzekeringen (ok=True)
- Purpose/domain: polis/verzekeringen
- Bestandsnaam: `polis_zorgzeker_verzekeringen_01-01-2026.png` (ok=True)
- Zoektests: zorgverzekering=81 ok, zoek polis=95 ok

### cropped_energy_contract

- Bestand: `testdata\real_world_documents\contracts\afgesneden_energiecontract.png`
- OCR: text_found, chars=158, termscore=1.0, ok=True
- Verwacht type: contracten
- Gevonden type: contracten, confidence=0.98
- Reden: contracten won with score 18; evidence: strong:looptijd, strong:ondertekening, strong:ingangsdatum
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: greenchoice (ok=True)
- Purpose/domain: energie/overig
- Bestandsnaam: `contract_greenchoice_energie_15-06-2026.png` (ok=True)
- Zoektests: contract energie=100 ok, greenchoice contract=100 ok

### stamped_laptop_invoice

- Bestand: `testdata\real_world_documents\invoices\gestempelde_laptop_factuur.png`
- OCR: text_found, chars=168, termscore=1.0, ok=True
- Verwacht type: facturen
- Gevonden type: facturen, confidence=0.98
- Reden: facturen won with score 41; evidence: strong:factuur, strong:factuurnummer, strong:factuurnummer, strong:factuurdatum, medium:betaald
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: techstore_demo (ok=True)
- Purpose/domain: factuur/overig
- Bestandsnaam: `factuur_techstore_demo_06-06-2026.png` (ok=True)
- Zoektests: factuur laptop=100 ok, techstore factuur=100 ok

### handwritten_praxis_receipt

- Bestand: `testdata\real_world_documents\receipts\bon_praxis_handgeschreven.png`
- OCR: text_found, chars=124, termscore=1.0, ok=True
- Verwacht type: bonnen
- Gevonden type: bonnen, confidence=0.98
- Reden: bonnen won with score 10; evidence: strong:kassabon, medium:contactloos
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: praxis_met_handgeschreven (ok=True)
- Purpose/domain: notitie/garantie
- Bestandsnaam: `notitie_praxis_bon_met_handgeschreven_07-06-2026.png` (ok=True)
- Zoektests: bon praxis=100 ok, verfroller bon=100 ok

### multilingual_recipe_note

- Bestand: `testdata\real_world_documents\general\recept_appeltaart_meertalig.png`
- OCR: text_found, chars=138, termscore=1.0, ok=True
- Verwacht type: notities
- Gevonden type: notities, confidence=0.9
- Reden: recipe/note content detected
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.9/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: high-confidence rule match
- Partij: recept_appeltaart (ok=True)
- Purpose/domain: recept/overig
- Bestandsnaam: `notitie_recept_appeltaart_recept_appeltaart_09-06-2026.png` (ok=True)
- Zoektests: recept appeltaart=100 ok, familierecept=50 ok

### multipage_telecom_invoice

- Bestand: `testdata\real_world_documents\invoices\telecom_factuur_meerdere_paginas.txt`
- OCR: text_found, chars=198, termscore=1.0, ok=True
- Verwacht type: facturen
- Gevonden type: facturen, confidence=0.98
- Reden: facturen won with score 33; evidence: strong:factuur, strong:factuurnummer, strong:factuurnummer, strong:factuurdatum, weak:btw
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: odido (ok=True)
- Purpose/domain: abonnement/abonnementen
- Bestandsnaam: `factuur_odido_abonnement_02-06-2026.txt` (ok=True)
- Zoektests: telecom factuur=100 ok, odido rekening=100 ok

## Top verbeterpunten

1. lowres_health_policy: lage confidence (0.25); reden: contract score lacked contract evidence; fallback not called.
2. lowres_health_policy: onzekerheid - document valt in overig terwijl herkenbare termen aanwezig zijn.
3. lowres_health_policy: onzekerheid - AI fallback had inhoudelijk gekund maar is niet gebruikt.
