# Bewaarhet documenttaxonomie review

Datum: 2026-06-10

## Doel

Onderzoeken welke documentcategorieen Bewaarhet nodig heeft op basis van bestaande testdata, documentinhoud, purpose/domain-detectie, confidence en zoekgedrag.

Er zijn in deze review geen nieuwe categorieen toegevoegd aan de classifier.

## Huidige hoofdcategorieen

Bewaarhet gebruikt nu:

- `facturen`
- `bonnen`
- `contracten`
- `belasting`
- `notities`
- `overig`

Deze set is bewust klein. Dat is goed voor eenvoud, maar `overig` wordt op termijn te breed als gebruikers honderden of duizenden documenten bewaren.

## Analysebasis

Huidige testsets:

- `testdata/documents`: 7 synthetische baseline-documenten.
- `testdata/real_world_documents`: 7 rommelige praktijkvarianten.

Totaal bekeken:

- 14 documenten;
- 28 zoekvragen;
- purpose/domain-detectie per document;
- classifier confidence per document;
- alle documenten die in `overig` vallen.

## Huidige verdeling

| Categorie | Aantal | Observatie |
| --- | ---: | --- |
| facturen | 3 | Facturen worden sterk en logisch herkend. |
| bonnen | 3 | Bonnen/aankoopbewijzen worden sterk herkend, maar kunnen tegelijk garantiecontext hebben. |
| contracten | 2 | Contracten worden goed herkend, maar energie/telecom overlapt met abonnementen. |
| belasting | 2 | Belastingdocumenten zijn duidelijk en waardevol als eigen categorie. |
| notities | 2 | Notities/recepten zijn nuttig, maar waarschijnlijk geen centrale archiefcategorie. |
| overig | 2 | Beide `overig`-documenten zijn polissen/verzekeringen. |

## Alle huidige documenten in `overig`

| Document | Testset | Purpose | Domain | Confidence | Zoekvragen | Voorgesteld cluster |
| --- | --- | --- | --- | ---: | --- | --- |
| `policy_lemonade` | synthetisch | polis | verzekeringen | 0.25 | `zoek polis`, `zoek lemonade verzekering` | Verzekeringen / Polissen |
| `lowres_health_policy` | real-world | polis | verzekeringen | 0.25 | `zorgverzekering`, `zoek polis` | Verzekeringen / Polissen |

Conclusie: `overig` is in de huidige testdata geen willekeurige bak. Het is vooral een ontbrekende categorie voor verzekeringen/polissen.

## Automatische clusters binnen `overig`

Op basis van purpose/domain ontstaan nu deze clusters:

| Cluster | Aantal | Bewijs |
| --- | ---: | --- |
| Verzekeringen / Polissen | 2 | Purpose `polis`, domain `verzekeringen`, zoektermen rond polis/zorgverzekering. |
| Garanties | 0 binnen `overig` | Wel domain `garantie` bij bonnen/aankoopbewijzen. Mogelijk subcategorie, geen hoofdcategorie op basis van huidige data. |
| Bankzaken | 0 | Geen testdocumenten. Wel waarschijnlijk relevant voor echte gebruikers. |
| Correspondentie | 0 | Geen testdocumenten. |
| Handleidingen | 0 | Geen testdocumenten. |
| Medisch | 0 | Geen testdocumenten, behalve zorgverzekering als verzekering. |
| Wonen | 0 | Energiecontract is nu contract met purpose `energie`. |
| Overheidsdocumenten | 0 buiten belasting | Belasting is al eigen categorie; andere overheid ontbreekt nog in testdata. |

## Antwoorden

### 1. Welke documenttypen komen regelmatig voor maar hebben nog geen eigen categorie?

Op basis van de huidige testdata:

- Verzekeringen / Polissen.

Op basis van waarschijnlijk gebruik door Nederlandse consumenten en zzp'ers, maar nog onvoldoende testbewijs:

- Bankzaken;
- Garanties;
- Wonen/energie/telecom;
- Overheidsdocumenten buiten belasting;
- Medisch/zorg;
- Correspondentie.

### 2. Welke documenten worden technisch correct verwerkt maar voelen verkeerd ingedeeld?

De polissen worden technisch correct verwerkt:

- ze zijn vindbaar;
- ze krijgen een logische bestandsnaam met `polis`;
- purpose/domain is `polis/verzekeringen`;
- zoekvragen slagen.

Maar voor een gebruiker voelt `overig` waarschijnlijk verkeerd. Iemand die na zes maanden zoekt of bladert verwacht een polis niet tussen algemene documenten, maar onder iets als `Verzekeringen` of `Polissen`.

### 3. Welke categorieen zouden de grootste gebruikerswaarde opleveren?

Hoogste waarde:

1. Verzekeringen / Polissen.
2. Bankzaken.
3. Garanties.
4. Wonen & vaste lasten.
5. Overheid.

Waarom:

- Dit zijn documenten die mensen vaak kwijt zijn.
- Ze worden meestal jaren bewaard.
- Ze hebben herkenbare zoekvragen: `polis`, `zorgverzekering`, `bankafschrift`, `garantie`, `energiecontract`, `gemeente`, `belasting`.
- Ze hebben duidelijke mentale mappen voor gewone gebruikers.

### 4. Welke categorieen zouden onnodige complexiteit toevoegen?

Nu nog niet doen:

- Recepten als hoofdcategorie.
- Telecom als aparte hoofdcategorie.
- Energie als aparte hoofdcategorie.
- Laptopfacturen/productgroepen als categorie.
- Per leverancier categorieen zoals KPN, Ziggo, Odido, bol.com.
- Te specifieke documenttypes zoals `premiewijziging`, `contractverlenging`, `retourbewijs`.

Deze horen eerder in purpose, domain, tags, leverancier of zoekindex dan in de hoofdmappen.

### 5. Welke categorieen zijn relevant voor Nederlandse consumenten en zzp'ers?

Waarschijnlijk relevant:

- Facturen;
- Bonnen & aankoopbewijzen;
- Garanties;
- Contracten;
- Verzekeringen / Polissen;
- Bankzaken;
- Belasting;
- Overheid;
- Wonen & vaste lasten;
- Zorg/medisch;
- Notities;
- Overig.

Voor zzp'ers specifiek:

- Facturen;
- Bonnen;
- Belasting;
- Bankzaken;
- Contracten;
- Verzekeringen;
- Klant-/projectdocumenten, maar dit is pas later relevant en kan snel te complex worden.

## Voorstel in drie niveaus

### Niveau 1: direct waardevol

Deze categorieen lijken direct nuttig en sluiten aan op huidige of zeer waarschijnlijke documenten:

#### Verzekeringen / Polissen

Bewijs:

- 2 van 2 `overig`-documenten zijn polissen.
- Purpose/domain herkent ze al als `polis/verzekeringen`.
- Confidence is laag omdat ze geen hoofdcategorie hebben.

Advies:

- Maak eerst intern een cluster/subtype `verzekeringen`.
- Later eventueel hoofdcategorie `verzekeringen`.
- Bestandsnaam mag `polis_...` blijven.

#### Bankzaken

Bewijs:

- Nog niet in testdata, maar voor consumenten en zzp'ers zeer waarschijnlijk.
- Zoekvragen zijn voorspelbaar: `bankafschrift`, `rekeningafschrift`, `betaling`, `hypotheek`, `rente`.

Advies:

- Eerst testdocumenten toevoegen.
- Nog niet implementeren als hoofdcategorie zonder testbewijs.

#### Garanties

Bewijs:

- Bonnen/aankoopbewijzen hebben nu domain `garantie`.
- Gebruikers denken vaak: "waar is mijn garantiebewijs?"

Advies:

- Niet meteen hoofdcategorie.
- Wel als subcategorie/tag bij bonnen en aankoopbewijzen.

### Niveau 2: later overwegen

#### Wonen & vaste lasten

Voor energiecontracten, huur, hypotheek, internet, telecom en abonnementen.

Nu nog oppassen: dit overlapt met `contracten`, `facturen` en `abonnementen`. Waarschijnlijk beter als domain dan als hoofdcategorie.

#### Overheid

Voor gemeente, RDW, DUO, CJIB, toeslagen en vergunningen.

Belasting is al apart. Eerst meer testdata toevoegen voordat `overheid` als hoofdcategorie zinvol is.

#### Zorg / Medisch

Voor zorgpolis, eigen risico, huisarts, tandarts, ziekenhuis, recepten.

Privacygevoelig en breed. Eerst alleen veilig testen met synthetische of geanonimiseerde documenten.

#### Correspondentie

Voor brieven zonder duidelijke financiele of contractuele functie.

Waarschijnlijk nodig bij echte gebruikers, maar als hoofdcategorie snel vaag. Mogelijk beter als fallback-subtype binnen `overig`.

### Niveau 3: niet doen

Niet als hoofdcategorie toevoegen:

- Leveranciersnamen;
- Productgroepen;
- Telecom apart;
- Energie apart;
- Recepten apart;
- Handleidingen apart;
- Betaalherinneringen apart;
- Retourbewijzen apart;
- Stempels/scankwaliteit als categorie.

Deze informatie hoort in metadata, tags, purpose/domain, OCR of zoekindex.

## Voorstel hoofdcategorieen

Voor een gebruiker met 1.000 documenten voelt deze indeling waarschijnlijk logisch zonder te zwaar te worden:

1. Facturen
2. Bonnen & aankoopbewijzen
3. Contracten
4. Verzekeringen
5. Belasting
6. Bankzaken
7. Overheid
8. Notities
9. Overig

Nog niet allemaal tegelijk implementeren. Begin met bewijs verzamelen en testdocumenten.

## Eventuele subcategorieen

Subcategorieen of metadata kunnen later helpen zonder hoofdmappen te laten exploderen:

- Verzekeringen:
  - zorg;
  - inboedel;
  - aansprakelijkheid;
  - auto;
  - reis.
- Bankzaken:
  - rekeningafschrift;
  - hypotheek;
  - lening;
  - betaling.
- Bonnen:
  - garantie;
  - aankoopbewijs;
  - retour.
- Contracten:
  - energie;
  - telecom;
  - huur;
  - abonnement.
- Overheid:
  - gemeente;
  - RDW;
  - DUO;
  - CJIB.

## Migratiestrategie

Nog geen datamigratie uitvoeren.

Aanbevolen stappen:

1. Voeg eerst meer testdocumenten toe voor verzekeringen, bankzaken, overheid en wonen.
2. Voeg een `suggested_category` of `taxonomy_cluster` toe in rapportage, niet in productieopslag.
3. Meet hoeveel bestaande documenten uit `overig` in stabiele clusters vallen.
4. Pas daarna classifier en database eventueel aan.
5. Migreer bestaande documenten alleen op metadata-niveau; verander Dropbox-paden niet automatisch zonder expliciete migratiekeuze.

## Impact op zoeken

Nieuwe categorieen kunnen zoeken verbeteren als ze aansluiten op mensentaal:

- `zoek polis` -> verzekeringen;
- `zoek zorgverzekering` -> verzekeringen;
- `zoek bankafschrift` -> bankzaken;
- `zoek garantie laptop` -> bonnen + garantie;
- `zoek gemeente brief` -> overheid.

Risico:

- Te veel categorieen maken zoeken niet beter, maar verwarrender.
- Zoekkwaliteit moet niet afhankelijk worden van de mapnaam alleen.

Advies:

- Gebruik categorie als extra ranking-signaal.
- Blijf OCR, supplier, purpose en domain meenemen.

## Impact op bestandsnaamgeving

Bestandsnamen werken nu al redelijk:

- `polis_lemonade_01-06-2026.txt`
- `polis_zorgzeker_verzekeringen_01-01-2026.png`
- `contract_greenchoice_energie_15-06-2026.png`
- `aankoopbewijs_bol_03-06-2026.txt`

Als `verzekeringen` later hoofdcategorie wordt, hoeft de bestandsnaam niet per se te veranderen. De naam `polis_...` is voor gebruikers duidelijker dan `verzekering_...`.

Advies:

- Houd documenttype in bestandsnaam: `polis`, `factuur`, `contract`, `bon`.
- Gebruik hoofdcategorie vooral voor map/metadata.

## Impact op bestaande documenten

Als later nieuwe categorieen worden toegevoegd:

- bestaande `overig`-documenten kunnen metadata `verzekeringen` krijgen;
- bestaande Dropbox-paden kunnen blijven staan;
- zoekresultaten kunnen de nieuwe categorie tonen zonder bestanden te verplaatsen;
- herclassificatie moet reviewbaar zijn voordat er iets definitief wijzigt.

## Conclusie

De eerste echte taxonomieverbetering is niet een grote categorieboom.

De eerste verbetering is:

**Maak `verzekeringen/polissen` zichtbaar als stabiel cluster.**

Maar voeg het nog niet blind toe als hoofdcategorie. Breid eerst de testset uit met meer polissen en verzekeringsdocumenten, plus bankzaken en overheidsdocumenten. Als die clusters terugkomen, is een kleine uitbreiding van de hoofdcategorieen logisch en gebruiksvriendelijk.

Voor 1.000 documenten moet Bewaarhet voelen als:

- weinig hoofdmappen;
- herkenbare mensentaal;
- slimme zoekbaarheid;
- metadata onder water;
- geen categorieboom waar iemand zelf beheerder van moet worden.
