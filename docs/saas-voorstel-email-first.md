# Bewaarhet SaaS-voorstel: e-mail-first, accountlaag onder water

Datum: 2026-06-09

## Uitgangspunt

Bewaarhet moet zo laagdrempelig mogelijk blijven.

De klant hoeft niet eerst een account aan te maken, geen app te installeren en geen dashboard te leren. De eerste ervaring blijft:

1. Mail een document naar Bewaarhet.
2. Bevestig je e-mailadres.
3. Je proef start.
4. Bewaarhet bewaart en vindt documenten terug via e-mail.

Dat is juist de kracht van het product.

Wel is er technisch een accountlaag nodig onder water. Niet omdat de klant daar meteen iets mee moet, maar omdat Bewaarhet anders later vastloopt bij meerdere e-mailadressen, betalen, proeftijd, zakelijke/prive scheiding en support.

Kort gezegd:

**E-mail blijft de voordeur. Het account bestaat achter de schermen.**

## Waarom dit nodig is

De huidige aanpak op basis van e-mailadres is logisch voor de lage instap, maar heeft grenzen:

- iemand heeft een zakelijk en prive e-mailadres;
- iemand wil documenten mailen vanaf meerdere adressen;
- een partner, medewerker of boekhouder moet kunnen uploaden;
- betaling hoort bij een klant/account, niet bij een los e-mailadres;
- triallimieten moeten per klant gelden, niet per mailbox;
- support moet kunnen zien welke adressen bij elkaar horen;
- later wil je misschien labels zoals zakelijk, prive, boekhouder of gezin.

Daarom moet Bewaarhet technisch van `e-mailadres = klant` naar `account met een of meer geverifieerde e-mailadressen`.

## Gewenste klantervaring

### Eerste gebruik

De eerste klantreis blijft extreem simpel:

1. Klant stuurt een document naar `bewaren@bewaarhet.nl`.
2. Bewaarhet ziet een onbekend e-mailadres.
3. Bewaarhet maakt automatisch een account aan in status `pending_verification`.
4. Klant krijgt een verificatiemail.
5. Na klik op de verificatielink wordt het account `trial`.
6. Vanaf dat moment kan de klant documenten mailen en later terugzoeken.

De klant merkt dus niet: "ik moet een account aanmaken".

De klant merkt alleen: "ik moet mijn e-mailadres bevestigen".

### Later pas beheer

Een portaal is alleen nodig als de klant iets wil beheren:

- extra e-mailadres toevoegen;
- abonnement starten;
- betaalgegevens wijzigen;
- opslag/limieten bekijken;
- zakelijke en prive adressen scheiden;
- boekhouder of partner toevoegen;
- account opzeggen.

Het dashboard is dus niet de primaire interface. E-mail blijft primair.

## Accountmodel

### Accounts

Een account is de echte klant/tenant.

Velden:

- id
- naam
- status: `pending_verification`, `trial`, `active`, `past_due`, `canceled`, `blocked`
- plan
- trial_start
- trial_end
- billing_provider
- billing_customer_id
- subscription_id
- created_at
- updated_at

### Account e-mailadressen

Een account kan meerdere e-mailadressen hebben.

Velden:

- id
- account_id
- email
- label: `hoofd`, `zakelijk`, `prive`, `boekhouder`, `partner`, `medewerker`
- status: `pending`, `verified`, `disabled`
- permissions:
  - mag opslaan
  - mag zoeken
  - mag beheren
- verified_at
- created_at

### Gebruikers/login

Login hoeft niet direct prominent te zijn.

Voor de eerste versie is magic-link login genoeg:

- geen wachtwoord;
- link per e-mail;
- korte geldigheid;
- alleen naar geverifieerde accountadressen.

Later kan wachtwoordlogin of 2FA erbij.

## Meerdere e-mailadressen

Dit wordt een belangrijke SaaS-feature.

Voorbeelden:

- prive Gmail voor huishouddocumenten;
- zakelijk domeinadres voor facturen;
- boekhouder mag stukken uploaden;
- partner mag documenten zoeken;
- medewerker mag alleen bonnetjes doorsturen.

Veilige regels:

1. Alleen een account-owner mag een extra e-mailadres toevoegen.
2. Ieder nieuw adres moet apart worden bevestigd.
3. Niet-geverifieerde adressen mogen niets opslaan of zoeken.
4. Per adres kunnen rechten worden ingesteld.
5. Zoekresultaten worden gebaseerd op `account_id`, niet alleen op het afzenderadres.
6. Optioneel kunnen labels bepalen wat een adres mag zien: zakelijk/prive/alles.

Belangrijk voorbeeld:

Theresa heeft `theresa@bedrijf.nl` en `theresa@gmail.com`.

Beide adressen kunnen aan hetzelfde Bewaarhet-account hangen, maar met labels:

- `theresa@bedrijf.nl`: zakelijk
- `theresa@gmail.com`: prive

Dan kan Bewaarhet later bijvoorbeeld zoeken binnen alleen zakelijke documenten of alleen prive documenten.

## Trial/proeftijd

Advies: gratis proberen zonder betaalgegevens.

Voorstel:

- 14 dagen gratis;
- maximaal 25 documenten;
- maximaal 250 MB opslag;
- maximaal 2 of 3 e-mailadressen;
- opslag en zoeken via e-mail;
- geen creditcard of iDEAL vooraf nodig.

Waarom:

- De drempel blijft laag.
- De klant ervaart het echte product.
- Misbruik blijft beperkt.
- Na 14 dagen is het logisch om te vragen of iemand door wil.

### Trial-e-mails

Automatische mails:

- dag 0: welkom en uitleg;
- dag 7: korte reminder met wat je kunt proberen;
- dag 12: proefperiode bijna voorbij;
- dag 14: proef verlopen, activeer abonnement;
- na upgrade: betaling gelukt, account actief.

### Na verlopen trial

Aanbevolen gedrag:

- nieuwe documenten opslaan stopt;
- zoeken kan eventueel nog 14 dagen beperkt blijven;
- klant krijgt duidelijke upgrade-link;
- documenten worden niet zomaar verwijderd;
- na langere inactiviteit volgt een bewaartermijn/verwijderbeleid.

## Betalen

Betaling hoort bij het account, niet bij het e-mailadres.

### Betaalprovider

Voor een Nederlandse start is Mollie logisch:

- iDEAL is vertrouwd;
- geschikt voor Nederlandse klanten;
- abonnementen zijn mogelijk;
- sluit goed aan bij kleine SaaS in Nederland.

Stripe is ook sterk, vooral als later internationale klanten, uitgebreidere subscription tooling en customer portal belangrijk worden.

Advies:

- Start met Mollie als Bewaarhet vooral Nederlands blijft.
- Kies Stripe als je verwacht snel internationaal of uitgebreider SaaS-abonnementenbeheer te willen.

### Betaalflow

1. Klant zit in trial.
2. Klant klikt op "Doorgaan met Bewaarhet".
3. Checkout via Mollie/Stripe.
4. Webhook bevestigt betaling.
5. Accountstatus wordt `active`.
6. Bij mislukte betaling wordt status `past_due`.
7. Worker controleert accountstatus voordat documenten worden verwerkt.

## Klantportaal

Het klantportaal moet klein blijven.

Niet bouwen als zware applicatie, maar als beheerplek.

Minimale pagina's:

- Inloggen met magic link.
- Dashboard:
  - accountstatus;
  - trial einddatum;
  - aantal documenten;
  - gebruikte opslag.
- E-mailadressen:
  - toevoegen;
  - verifieren;
  - label kiezen;
  - rechten instellen.
- Abonnement:
  - starten;
  - betaalstatus;
  - opzeggen.
- Instellingen:
  - bevestigingsmails aan/uit;
  - standaard label;
  - supportcontact.

Later pas:

- zoeken in dashboard;
- documenten downloaden;
- auditlog;
- export;
- teamleden.

## Pricing

Houd de eerste propositie simpel.

### Eerste versie

Toon op de website:

- Gratis proberen;
- Daarna vanaf EUR 9 per maand;
- Groter gebruik? Neem contact op.

### Mogelijke pakketten later

**Start - EUR 5 tot 7 per maand**

- 1 gebruiker;
- 2 e-mailadressen;
- 1 GB opslag;
- documenten bewaren en zoeken via e-mail.

**Plus - EUR 9 tot 12 per maand**

- 5 e-mailadressen;
- 5 GB opslag;
- zakelijke/prive labels;
- betere zoek- en sorteermogelijkheden.

**Klein bedrijf - EUR 19 tot 29 per maand**

- 10 e-mailadressen;
- boekhouder/medewerker-rechten;
- auditlog;
- hogere limieten;
- support.

Voor de start is 1 duidelijk betaald pakket waarschijnlijk beter dan drie pakketten. Te veel keuze maakt de lage drempel juist weer hoger.

## Technische fasering

### Fase 0: Product-validatie

Doel: niet te snel doorbouwen voordat duidelijk is waarom de eerste klanten Bewaarhet echt gebruiken.

Deze fase komt vóór betalen en vóór een uitgebreid portaal.

Vragen die beantwoord moeten worden:

1. Welke documenten sturen mensen werkelijk naar Bewaarhet?
2. Gebruiken ze vooral bewaren, of ook echt zoeken?
3. Hoe vaak zoeken ze iets terug?
4. Welke zoekvragen stellen ze?
5. Welke documenten raken ze in het dagelijks leven echt kwijt?
6. Willen mensen meerdere e-mailadressen gebruiken?
7. Is zakelijk/prive scheiden belangrijk?
8. Zou een boekhouder, partner of medewerker toegang moeten krijgen?
9. Waar ontstaat vertrouwen of juist twijfel?
10. Wat maakt dat iemand na de proef wil blijven?

Praktische aanpak:

- start met 5 tot 10 testgebruikers;
- laat ze Bewaarhet gewoon via e-mail gebruiken;
- vraag niet wat ze theoretisch willen, maar kijk wat ze echt mailen en zoeken;
- houd per gebruiker bij:
  - aantal bewaarde documenten;
  - soort documenten;
  - aantal zoekopdrachten;
  - mislukte zoekopdrachten;
  - behoefte aan extra e-mailadressen;
  - opmerkingen of verwarring;
- voer korte gesprekken na 1 week en na 2 weken.

Belangrijk:

Nieuwe grote features worden pas gebouwd als ze terugkomen uit echt gebruik.

De belangrijkste vraag is niet:

"Hoe schaal ik naar 1000 klanten?"

Maar:

"Waarom blijven de eerste 10 klanten dit gebruiken?"

### Fase 1: Accountlaag onder water

Doel: e-mail-first behouden, maar technisch klaar zijn voor SaaS.

Werk:

1. `accounts` tabel toevoegen.
2. `account_emails` tabel toevoegen.
3. Bestaande `customers` migreren naar accounts.
4. `documents.account_id` toevoegen.
5. Upload en search ombouwen van `customer_identity` naar `account_id`.
6. Eerste e-mailadres automatisch primary maken.
7. Verificatie per e-mailadres behouden.

Tests:

- onbekend adres maakt pending account;
- verificatie start trial;
- geverifieerd adres mag uploaden;
- niet-geverifieerd adres mag niets;
- twee adressen binnen hetzelfde account kunnen dezelfde kluis gebruiken;
- adres buiten account ziet niets.

### Fase 2: Extra e-mailadressen

Doel: zakelijk/prive en meerdere adressen ondersteunen.

Werk:

1. Magic-link login toevoegen.
2. Kleine pagina "E-mailadres toevoegen".
3. Verificatiemail naar nieuw adres.
4. Permissions per adres:
   - uploaden;
   - zoeken;
   - beheren.
5. Labels toevoegen: zakelijk/prive/boekhouder.

### Fase 3: Trial volwassen maken

Doel: proefperiode commercieel en technisch netjes afronden.

Werk:

1. `trial_end` toevoegen.
2. Triallimieten per account afdwingen.
3. Trial reminder mails.
4. Trial verlopen status.
5. Upgrade-link.
6. Geen nieuwe opslag na verlopen trial.

### Fase 4: Betalen

Doel: van proef naar betaald abonnement.

Werk:

1. Mollie of Stripe integreren.
2. Checkout starten vanuit portaal of mail.
3. Webhook endpoint bouwen.
4. Accountstatus synchroniseren.
5. Mislukte betaling afhandelen.
6. Factuur-/betaalstatus tonen.

### Fase 5: SaaS-volwassenheid

Doel: betrouwbaar genoeg voor onbekende betalende klanten.

Werk:

1. Admin-dashboard.
2. Auditlog per actie.
3. Supporttools.
4. Privacybeleid en voorwaarden.
5. Verwijder-/exportverzoeken.
6. Monitoring en foutmeldingen.
7. Overwegen: PostgreSQL in plaats van SQLite.
8. Overwegen: storage abstraction voor later S3/Backblaze.

## Belangrijkste risico's

### Privacy

Bewaarhet verwerkt mogelijk gevoelige documenten. Daarom zijn nodig:

- privacyverklaring;
- algemene voorwaarden;
- verwerkersovereenkomst voor zakelijke klanten;
- duidelijke bewaartermijnen;
- verwijderfunctie;
- exportfunctie;
- minimale logging van gevoelige inhoud.

### Beveiliging

Aandachtspunten:

- OCR-tekst staat nu leesbaar in SQLite;
- Dropbox is centrale opslag;
- tijdelijke links moeten kort geldig blijven;
- logs mogen geen documentinhoud of secrets lekken;
- multi-email toegang moet strikt getest worden.

### Productverwachting

Bewaarhet moet niet klinken als boekhoudsoftware.

Positionering:

- niet: "wij doen je administratie";
- wel: "mail je documenten, wij bewaren ze netjes en vindbaar".

## Aanbevolen keuze

Behoud de lage instap volledig:

**Geen verplicht account aanmaken vooraf. Geen wachtwoord. Geen dashboardplicht.**

Maar bouw technisch wel:

**Accountlaag + geverifieerde e-mailadressen + magic-link beheer.**

Dat is de beste middenweg:

- makkelijk voor nieuwe klanten;
- veilig genoeg voor gevoelige documenten;
- praktisch voor zakelijk/prive;
- klaar voor proeftijd en betaling;
- schaalbaar richting echte SaaS.

## Eerste concrete bouwopdracht

Bouw eerst:

1. `accounts`
2. `account_emails`
3. migratie van bestaande klanten
4. `documents.account_id`
5. opslag en zoeken op accountniveau
6. verificatie per extra e-mailadres
7. tests voor accountisolatie en multi-email

Pas daarna:

- portaal;
- betaling;
- pakketten;
- uitgebreid dashboard.

Zo blijft Bewaarhet simpel aan de voorkant, maar professioneel aan de achterkant.

## Zakelijke focus voor nu

De grootste technische blokkade is kleiner geworden door de accountlaag onder water.

Het grootste risico is nu zakelijk:

Bewaarhet moet bewijzen dat echte gebruikers het blijven gebruiken nadat de nieuwigheid eraf is.

Daarom is het advies:

1. Niet meteen doorbouwen naar een groot portaal.
2. Niet meteen te veel betaalpakketten maken.
3. Eerst echte gebruikers laten mailen, bewaren en zoeken.
4. Leren welke documenten en zoekvragen terugkomen.
5. Daarna pas beslissen welke functies de betaalde versie echt nodig heeft.

Meerdere e-mailadressen lijken op dit moment de sterkste betaalbare feature, omdat die aansluit op echte situaties:

- prive en zakelijk;
- partner;
- boekhouder;
- medewerker;
- gezin of klein team.

Maar ook dat moet in gebruik gevalideerd worden.
