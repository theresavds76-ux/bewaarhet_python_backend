# Bewaarhet document quality report

## Samenvatting

- Testset: `testdata\documents`
- Totaal aantal documenten: 7
- OCR bruikbaar: 7/7 (100.0%)
- Gemiddelde OCR termscore: 1.0
- Correct geclassificeerd: 7/7 (100.0%)
- Uncertain cases: 1
- Fout geclassificeerd: 0
- AI fallback mogelijk maar niet gebruikt: 1
- Zoektests geslaagd: 14/14 (100.0%)
- Gemiddelde classificatieconfidence: 0.867

## Trends

- Vorige run OCR: 100.0% -> huidige run: 100.0%
- Vorige run classificatie: 100.0% -> huidige run: 100.0%
- Vorige run zoekscore: 100.0% -> huidige run: 100.0%
- Vorige run documenten: 7 -> huidige run documenten: 7

## Performance per documenttype

- belasting: OCR 1/1, classificatie 1/1, zoektests 2/2
- bonnen: OCR 2/2, classificatie 2/2, zoektests 4/4
- contracten: OCR 1/1, classificatie 1/1, zoektests 2/2
- facturen: OCR 1/1, classificatie 1/1, zoektests 2/2
- notities: OCR 1/1, classificatie 1/1, zoektests 2/2
- overig: OCR 1/1, classificatie 1/1, zoektests 2/2

## Details

### invoice_kpn

- Bestand: `testdata\documents\invoices\kpn_factuur_juni_2026.txt`
- OCR: text_found, chars=205, termscore=1.0, ok=True
- Verwacht type: facturen
- Gevonden type: facturen, confidence=0.98
- Reden: facturen won with score 39; evidence: strong:factuur, strong:factuurnummer, strong:factuurnummer, strong:factuurdatum, medium:bedrag
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: kpn (ok=True)
- Purpose/domain: abonnement/abonnementen
- Bestandsnaam: `factuur_kpn_abonnement_01-06-2026.txt` (ok=True)
- Zoektests: zoek mijn KPN factuur=100 ok, factuur internet=100 ok

### receipt_bol

- Bestand: `testdata\documents\receipts\bol_aankoopbewijs_2026.txt`
- OCR: text_found, chars=151, termscore=1.0, ok=True
- Verwacht type: bonnen
- Gevonden type: bonnen, confidence=0.98
- Reden: bonnen won with score 17; evidence: strong:aankoopbewijs, medium:ordernummer, medium:besteldatum
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: bol (ok=True)
- Purpose/domain: aankoopbewijs/garantie
- Bestandsnaam: `aankoopbewijs_bol_03-06-2026.txt` (ok=True)
- Zoektests: zoek bon van bol=100 ok, zoek aankoopbewijs kabel=100 ok

### policy_lemonade

- Bestand: `testdata\documents\policies\lemonade_polisblad_2026.txt`
- OCR: text_found, chars=159, termscore=1.0, ok=True
- Verwacht type: overig
- Gevonden type: overig, confidence=0.25
- Reden: contract score lacked contract evidence; fallback not called
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.25/0.65
- AI fallback: enabled=False, considered=True, used=False
- AI fallback beslissing: AI fallback disabled for this run
- Partij: lemonade (ok=True)
- Purpose/domain: polis/verzekeringen
- Bestandsnaam: `polis_lemonade_01-06-2026.txt` (ok=True)
- Zoektests: zoek polis=70 ok, zoek lemonade verzekering=100 ok

### contract_ziggo

- Bestand: `testdata\documents\contracts\ziggo_contract_2026.txt`
- OCR: text_found, chars=196, termscore=1.0, ok=True
- Verwacht type: contracten
- Gevonden type: contracten, confidence=0.98
- Reden: contracten won with score 37; evidence: strong:contract, strong:overeenkomst, strong:looptijd, strong:ondertekening, strong:partijen
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: ziggo (ok=True)
- Purpose/domain: abonnement/abonnementen
- Bestandsnaam: `contract_ziggo_abonnement_10-06-2026.txt` (ok=True)
- Zoektests: zoek contract=64 ok, zoek ziggo overeenkomst=100 ok

### tax_belastingdienst

- Bestand: `testdata\documents\tax\belastingdienst_aanslag_2026.txt`
- OCR: text_found, chars=204, termscore=1.0, ok=True
- Verwacht type: belasting
- Gevonden type: belasting, confidence=0.98
- Reden: belasting won with score 44; evidence: strong:belastingdienst, strong:aanslag, strong:voorlopige aanslag, strong:aanslagnummer, strong:inkomstenbelasting
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: belastingdienst (ok=True)
- Purpose/domain: betaalinformatie/belasting
- Bestandsnaam: `belasting_belastingdienst_betaalinformatie_05-06-2026.txt` (ok=True)
- Zoektests: zoek belastingaanslag=100 ok, zoek aanslag inkomstenbelasting=100 ok

### general_note

- Bestand: `testdata\documents\general\notitie_meterstanden_2026.txt`
- OCR: text_found, chars=132, termscore=1.0, ok=True
- Verwacht type: notities
- Gevonden type: notities, confidence=0.92
- Reden: note-like content detected
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.92/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: high-confidence rule match
- Partij: notitie_meterstanden (ok=True)
- Purpose/domain: notitie/overig
- Bestandsnaam: `notitie_meterstanden_meterstanden_opgenomen_op_07-06-2026.txt` (ok=True)
- Zoektests: zoek meterstanden=100 ok, zoek jaarafrekening controle=100 ok

### bad_quality_receipt_jumbo

- Bestand: `testdata\documents\bad_quality\jumbo_bon_slechte_scan.png`
- OCR: text_found, chars=112, termscore=1.0, ok=True
- Verwacht type: bonnen
- Gevonden type: bonnen, confidence=0.98
- Reden: bonnen won with score 17; evidence: strong:kassabon, medium:bedankt voor uw bezoek, medium:contactloos
- Classifier-route: rules
- Rule confidence/fallback threshold: 0.98/0.65
- AI fallback: enabled=False, considered=False, used=False
- AI fallback beslissing: AI fallback skipped: rule confidence above threshold
- Partij: jumbo (ok=True)
- Purpose/domain: bon/garantie
- Bestandsnaam: `bon_jumbo_08-06-2026.png` (ok=True)
- Zoektests: zoek jumbo bon=100 ok, zoek kassabon melk=100 ok

## Top verbeterpunten

1. policy_lemonade: lage confidence (0.25); reden: contract score lacked contract evidence; fallback not called.
2. policy_lemonade: onzekerheid - AI fallback had inhoudelijk gekund maar is niet gebruikt.
