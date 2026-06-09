# Bewaarhet real-world kwaliteitsrisico's

Datum: 2026-06-09

## Context

Bewaarhet heeft nu een lokale testflow voor synthetische documenten en een aparte real-world kwaliteitsset met rommelige, maar veilige testdocumenten.

De real-world set simuleert:

- schaduw;
- lage resolutie;
- scheve of gedraaide foto's;
- afgesneden documenten;
- stempels;
- handgeschreven aantekeningen;
- meerdere pagina's;
- meertalige tekst;
- mobiele foto-achtige invoer.

Er wordt geen echte klantdata gebruikt.

## Huidige meting

Laatste real-world run:

```text
Totaal aantal documenten: 7
OCR bruikbaar: 7/7 (100.0%)
Correct geclassificeerd: 7/7 (100.0%)
Zoektests geslaagd: 14/14 (100.0%)
Gemiddelde classificatieconfidence: 0.864
```

De vorige run had 71.4% correcte classificatie. De verbetering kwam vooral door:

- bonnen met notities niet meer te snel als notitie te zien;
- recept/notitie-content expliciet als notitie te herkennen;
- filename-verwachtingen realistischer te maken.

## Documenten die waarschijnlijk problemen geven

1. Zeer donkere of overbelichte foto's.
2. Foto's waarbij belangrijke velden zijn afgesneden.
3. Documenten met weinig tekst, bijvoorbeeld korte bonnetjes.
4. Handgeschreven documenten zonder duidelijke printtekst.
5. Polissen en contracten die qua taal sterk op elkaar lijken.
6. Facturen zonder duidelijke woorden zoals `factuur`, `factuurnummer` of `btw`.
7. Meertalige documenten waarin Nederlandse zoektermen ontbreken.
8. Multi-page documenten waarbij de belangrijkste informatie pas op pagina 2 staat.

## Kwetsbare OCR-scenario's

- Lage resolutie kan genoeg tekst opleveren, maar velden zoals datum of partij beschadigen.
- Schaduw en rotatie zijn vooral riskant bij kleine letters.
- Handgeschreven notities mogen de hoofdclassificatie niet overschrijven.
- Afgesneden documenten kunnen wel een type tonen, maar geen betrouwbare datum of leverancier.
- OCR-sidecars maken regressietests stabiel, maar vervangen nog geen echte OCR-stresstest met OCR.space of lokale OCR.

## Onzekere classificaties

De belangrijkste onzekerheid zit bij documenttypes die dicht bij elkaar liggen:

- polis versus contract;
- aankoopbewijs versus factuur;
- algemene notitie versus document met notitie erop;
- betaalbevestiging versus factuur;
- brief van overheid versus belastingdocument.

Bewaarhet moet liever veilig `overig` kiezen dan agressief fout classificeren. Een fout type schaadt vertrouwen sneller dan een iets algemene mapnaam.

## Risicovolle zoekvragen

Zoekvragen zijn vooral risicovol als de gebruiker spreekt in andere woorden dan het document:

- `zorgverzekering` terwijl het document vooral `polisblad` bevat;
- `belastingaanslag` als OCR alleen `aanslag` of `inkomstenbelasting` vindt;
- `bon praxis` als het bonnetje alleen een logo of korte winkelnaam bevat;
- `contract energie` als het document alleen `overeenkomst` gebruikt;
- `factuur laptop` als het product alleen als artikelnummer staat;
- `recept appeltaart` als het document meertalig of handgeschreven is.

Daarom moeten zoekuitbreidingen en synonyms voorzichtig worden uitgebreid met echte gebruikersvragen.

## Grootste kwaliteitswinst

1. Testset uitbreiden naar 30 tot 50 Nederlandse documenten.
2. Echte OCR-output naast OCR-sidecars meten.
3. Polissen als apart intern subtype toevoegen zonder meteen de hoofdcategorie te forceren.
4. Meer supplier-detectie testen op rommelige documenten.
5. Zoekkwaliteit meten met meerdere relevante en irrelevante documenten tegelijk.
6. False positives expliciet rapporteren, niet alleen successen.
7. Per document tonen waarom de classificatie is gekozen.

## Advies voor proefgebruikers

Bewaarhet is nog niet klaar om hard als betaalde dienst verkocht te worden.

Wel is het geschikt voor een kleine, duidelijke proefgroep als:

- gebruikers weten dat het product nog in testfase is;
- documenten veilig en voorzichtig worden verwerkt;
- twijfelgevallen duidelijk worden gelogd;
- fout herkende documenten worden gebruikt om de testset uit te breiden;
- billing niet live wordt gezet voordat de herkenning stabieler is.

## Bewust nog niet bouwen

Wacht met:

- klantportaal;
- self-service billing;
- meerdere betaalpakketten;
- uitgebreide dashboards;
- grote SaaS-features.

De komende kwaliteitswinst zit in betrouwbaarheid van de kernflow: document erin, logisch bewaren, later vindbaar teruggeven.
