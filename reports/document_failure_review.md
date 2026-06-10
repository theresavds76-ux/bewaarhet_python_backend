# Bewaarhet failure review

## Samenvatting

- Testset: `testdata\real_world_documents`
- Failures: 0
- Uncertain cases: 1
- AI fallback mogelijk maar niet gebruikt: 1

## Documenttypes met meeste aandacht

- overig: 1

## Failures

Geen documenten in deze bucket.

## Uncertain document bucket

### lowres_health_policy

- Bestand: `testdata\real_world_documents\policies\lage_resolutie_zorgverzekering.png`
- Documentvariant: lowres
- Verwachte categorie: overig
- Voorspelde categorie: overig
- Confidence: 0.25
- Rule-based confidence: 0.25
- Fallback threshold: 0.65
- OCR-status: text_found
- OCR-score: 1.0
- OCR-preview: ZorgZeker Verzekeringen Polisblad zorgverzekering Polisnummer ZZ-2026-4411 Ingangsdatum 01-01-2026 Eigen risico EUR 385 Premie per maand EUR 142,50
- Zoekvragen gefaald: geen
- Zoekvragen laag maar geslaagd: geen
- Classifier-route: rules
- Classifier reason: contract score lacked contract evidence; fallback not called
- Alternatieve categorieen: contracten:6, bonnen:0, facturen:0
- AI fallback enabled: False
- AI fallback used: False
- AI fallback considered: True
- AI fallback beslissing: AI fallback disabled for this run
- OCR zinvol voor AI: True
- Mens zou waarschijnlijk herkennen als: overig
- Reviewreden: lage classifier confidence (0.25); document valt in overig terwijl herkenbare termen aanwezig zijn; AI fallback had inhoudelijk gekund maar is niet gebruikt
- Aanbeveling: Overweeg subtype of AI-review, maar blijf liever veilig dan agressief fout classificeren.

