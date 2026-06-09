# Bewaarhet SaaS-roadmap

Datum: 2026-06-09

## Korte conclusie

Bewaarhet heeft al een sterke technische kern: documenten ontvangen via e-mail, veilige bestandscontrole, verificatie per e-mailadres, Dropbox-opslag, metadata in SQLite, zoeken per mail, tijdelijke downloadlinks, rate limiting en klantisolatie.

Wat nog ontbreekt om het als volwaardige SaaS te kunnen aanbieden:

- echte accounts in plaats van alleen losse e-mailidentiteiten;
- meerdere e-mailadressen per klant;
- abonnementen en betaalstatus;
- selfservice beheer;
- duidelijke proefperiode;
- admin-dashboard;
- betere audit logs;
- schaalbaardere database- en opslagstructuur;
- juridische basis: privacy, voorwaarden, verwerkersafspraken, bewaartermijnen.

## Huidige staat

### Wat al goed staat

- Nieuwe afzenders worden eerst `pending_verification`.
- Na activatie wordt een klant `trial`.
- Triallimieten bestaan al: aantal documenten, opslag, bestandsgrootte en rate limits.
- Actieve klanten kunnen volledige toegestane bestandstypen gebruiken.
- Geblokkeerde klanten worden niet verwerkt.
- Documenten zijn per afzender gescheiden.
- Zoekresultaten worden nogmaals op ownership gecontroleerd voordat er links worden verstuurd.
- Links naar documenten zijn tijdelijk.
- Bestanden worden gevalideerd voordat OCR/opslag gebeurt.
- De live site legt het concept simpel uit.

### Wat nog geen SaaS is

- Een klant is nu feitelijk een e-mailadres, geen account.
- Zakelijk en prive e-mailadres kunnen nog niet onder hetzelfde account vallen.
- Er is geen login.
- Er is geen betaalprovider gekoppeld.
- Trial wordt technisch beperkt, maar nog niet commercieel afgerond met upgrade-flow.
- Er is geen klantportaal voor instellingen, documenten, facturen, abonnement of e-mailadressen.
- Er is geen formele tenantstructuur met rollen en teamleden.
- SQLite is prima voor eerste versie, maar niet ideaal voor groei en gelijktijdige webapp/worker-verwerking.

## Gewenst SaaS-model

### Accountstructuur

Introduceer een `accounts`-model:

- `accounts`
  - id
  - naam
  - plan
  - status: trial, active, past_due, canceled, blocked
  - trial_start
  - trial_end
  - billing_customer_id
  - subscription_id
  - created_at

- `account_emails`
  - id
  - account_id
  - email
  - label: zakelijk, prive, partner, medewerker
  - status: pending, verified, disabled
  - verified_at

- `users`
  - id
  - account_id
  - email
  - password_hash of magic-link login
  - role: owner, admin, member

- `documents`
  - account_id toevoegen
  - source_email bewaren
  - uploaded_by_email bewaren

Belangrijk: zoeken en opslag moeten dan niet meer alleen op `customer_identity=email` draaien, maar op `account_id`. Een geverifieerd zakelijk en prive e-mailadres kunnen dan dezelfde kluis gebruiken.

## Proeftijd

Advies: start met een simpele proefperiode zonder betaalgegevens.

Voorstel:

- 14 dagen gratis;
- maximaal 25 documenten;
- maximaal 250 MB opslag;
- maximaal 3 gekoppelde e-mailadressen;
- duidelijke mail op dag 1, dag 10 en dag 14;
- na afloop: zoeken blijft eventueel nog tijdelijk mogelijk, nieuwe opslag stopt totdat er betaald wordt.

Waarom zo:

- Laagdrempelig genoeg om te testen.
- Beperkt genoeg om misbruik te voorkomen.
- Past bij het product: de waarde merk je pas als je echt een paar documenten mailt en later terugvindt.

## Betalen

Voor Nederland zijn Mollie en Stripe logisch.

### Aanbeveling voor Bewaarhet

Kies in eerste instantie Mollie als de doelgroep vooral Nederlands is.

Reden:

- iDEAL is vertrouwd voor Nederlandse klanten.
- Mollie past goed bij kleine Nederlandse SaaS-producten.
- De Subscriptions API ondersteunt terugkerende betalingen.

Stripe is sterker als later internationale SaaS, customer portal en geavanceerdere abonnementslogica belangrijker worden.

### Minimale betaalflow

1. Klant start proef via website.
2. Account wordt aangemaakt.
3. Klant bevestigt e-mailadres.
4. Trial start.
5. In het dashboard staat: "Proefperiode actief tot ..."
6. Klant klikt op "Abonnement starten".
7. Mollie/Stripe checkout.
8. Webhook zet account op `active`.
9. Mislukte betaling zet account op `past_due`.
10. Bij opzegging blijft account lezen/zoeken tot einde betaalperiode, daarna geen nieuwe opslag.

## Login en klantportaal

Maak geen zwaar dashboard in versie 1. Bewaarhet moet e-mail-first blijven.

Minimaal portaal:

- inloggen met magic link;
- accountstatus zien;
- proefperiode/betaalstatus zien;
- gekoppelde e-mailadressen beheren;
- nieuw e-mailadres toevoegen en verifieren;
- abonnement starten/opzeggen;
- basisstatistieken:
  - aantal documenten;
  - gebruikte opslag;
  - laatste verwerking;
- instellingen:
  - bevestigingsmails aan/uit;
  - labels/mappen globaal;
  - zakelijke/prive scheiding.

Later:

- documenten zoeken in dashboard;
- documenten downloaden;
- auditlog;
- exports;
- teamleden.

## Meerdere e-mailadressen

Dit is een sterke feature en waarschijnlijk nodig.

Gebruik:

- prive administratie: gmail/outlook;
- zakelijke administratie: domeinmail;
- partner of boekhouder;
- oude mailbox;
- meerdere medewerkers.

Veilig ontwerp:

1. Alleen de account-owner mag een nieuw e-mailadres toevoegen.
2. Het nieuwe adres krijgt een verificatiemail.
3. Pas na verificatie mag dat adres documenten opslaan of zoeken.
4. Per adres kun je instellen:
   - mag opslaan;
   - mag zoeken;
   - mag alleen uploaden, niet terugvinden;
   - label: prive, zakelijk, boekhouder.

Belangrijk: een zoekmail vanaf prive mag alleen documenten tonen die binnen hetzelfde account vallen, en eventueel binnen toegestane labels.

## Pricing voorstel

Start simpel.

### Particulier / ZZP Start

EUR 5 tot 7 per maand.

- 1 account;
- 2 e-mailadressen;
- 1 GB opslag;
- e-mail opslag en zoeken;
- tijdelijke downloadlinks.

### ZZP Plus

EUR 9 tot 12 per maand.

- 5 e-mailadressen;
- 5 GB opslag;
- betere herkenning;
- documentlabels;
- maandelijkse export/backup.

### Klein bedrijf

EUR 19 tot 29 per maand.

- 10 e-mailadressen;
- teamrollen;
- boekhouder-adres;
- auditlog;
- hogere limieten.

Begin niet met te veel pakketten op de website. Toon eerst:

- Gratis proberen;
- Daarna EUR 9 per maand;
- Groter gebruik? Neem contact op.

## Belangrijkste productverbeteringen

### Must-have voor SaaS v1

- Accountmodel met meerdere e-mailadressen.
- Magic-link login.
- Klantportaal voor basisbeheer.
- Abonnement + webhookstatus.
- Trial expiry afdwingen.
- Admin-dashboard.
- Transactionele mails:
  - welkom;
  - e-mailadres bevestigd;
  - trial bijna voorbij;
  - trial verlopen;
  - betaling gelukt;
  - betaling mislukt.
- Betere auditlog in database.
- Privacy/voorwaarden pagina's.

### Should-have

- Documenten zoeken in portaal.
- Labels: zakelijk/prive/boekhouder.
- Maandelijkse overzichtsmail.
- Export alle documenten/metadata.
- Retentiebeleid en verwijderverzoek.
- Storage quota per plan.

### Later

- Boekhouder-toegang.
- Shared folders.
- Automatische herkenning per leverancier.
- Slimme herinneringen: "dit document mist nog".
- Integratie met boekhoudsoftware.
- Mobiele upload via PWA.

## Technische realisatie

### Fase 1: SaaS-fundament

Doel: van losse e-mailklanten naar echte accounts.

Werk:

- nieuwe tabellen toevoegen: `accounts`, `account_emails`, `users`, `subscriptions`, `audit_events`;
- `documents.account_id` toevoegen;
- migratie schrijven van bestaande `customers.email` naar account + primary email;
- opslag en zoeken ombouwen van e-mailadres naar `account_id`;
- tests uitbreiden voor multi-email isolatie.

### Fase 2: Login en portaal

Doel: klant kan zichzelf beheren.

Werk:

- kleine webapp toevoegen, bij voorkeur FastAPI/Jinja of Flask;
- magic-link login;
- pagina's:
  - dashboard;
  - e-mailadressen;
  - abonnement;
  - accountinstellingen;
- CSRF/session security;
- rate limits op loginlinks.

### Fase 3: Betalen

Doel: trial naar betaald abonnement.

Werk:

- Mollie of Stripe integratie;
- checkout start vanuit portaal;
- webhook endpoint;
- subscription status synchroniseren;
- betaalstatus afdwingen in worker;
- mails bij statuswijzigingen.

### Fase 4: Product volwassen maken

Doel: betrouwbaar genoeg voor echte klanten.

Werk:

- auditlog per documentactie;
- admin-dashboard;
- supporttools;
- backup/restore procedure formaliseren;
- monitoring/alerts;
- foutmeldingen klantvriendelijker maken;
- privacy/security documentatie.

### Fase 5: Schaalbaarheid

Doel: klaar voor groei.

Werk:

- migratie van SQLite naar PostgreSQL;
- aparte webapp en worker;
- queue voor documentverwerking;
- object storage strategie herzien;
- per-account storage/quota;
- database encryptie of gerichte encryptie van gevoelige OCR-tekst overwegen.

## Architectuuradvies

Voor de eerste SaaS-versie:

- behoud Python;
- voeg FastAPI of Flask toe voor portaal en webhooks;
- behoud de mailworker;
- gebruik voorlopig SQLite alleen als MVP nog klein blijft;
- ga naar PostgreSQL voordat er betalende onbekende klanten op schaal komen;
- houd Dropbox voor MVP, maar ontwerp opslag via een abstracte storage-interface zodat later S3/Backblaze mogelijk is.

## Risico's

- Bewaarhet verwerkt mogelijk gevoelige documenten. Privacy en security moeten vanaf het begin serieus.
- OCR-tekst staat nu leesbaar in SQLite. Dat is handig voor zoeken, maar gevoelig.
- Dropbox als centrale opslag is praktisch, maar maakt Bewaarhet afhankelijk van een externe consumentenachtige opslaglaag.
- E-mail als interface is geweldig simpel, maar ook foutgevoelig: verkeerd doorgestuurd, verkeerde afzender, aliases, forwarding.
- Multi-email kan alleen veilig als verificatie en rechten per e-mailadres strak zijn.

## Aanbevolen eerste bouwstap

Begin niet met betalen. Begin met accountstructuur en meerdere e-mailadressen.

Waarom:

- Dit raakt de kern van het product.
- Zonder accountmodel wordt betalen rommelig.
- Zonder accountmodel kun je zakelijke/prive adressen niet netjes oplossen.
- Het maakt trial, dashboard en abonnement later veel eenvoudiger.

Concreet eerste pakket:

1. Accountmodel ontwerpen.
2. Database migratie toevoegen.
3. Bestaande klanten migreren naar accounts.
4. `account_emails` met verificatie bouwen.
5. Worker opslag/zoekfunctie ombouwen naar `account_id`.
6. Tests voor:
   - twee e-mailadressen binnen hetzelfde account vinden dezelfde documenten;
   - onbekend adres ziet niets;
   - niet-geverifieerd adres mag niets;
   - upload-only adres kan niet zoeken.

Daarna pas login, trial-dashboard en betaalprovider.

## Product-validatie vóór grote features

Na het accountfundament moet Bewaarhet niet automatisch door naar een groot portaal of betaalcomplexiteit.

De belangrijkste fase is nu product-validatie met echte gebruikers.

### Kernvragen

- Welke documenten sturen mensen echt?
- Gebruiken ze Bewaarhet alleen om te bewaren, of ook om terug te zoeken?
- Hoe vaak zoeken ze iets terug?
- Welke zoekvragen stellen ze?
- Welke documenten raken ze echt kwijt?
- Hebben ze behoefte aan meerdere e-mailadressen?
- Is zakelijk/prive scheiden belangrijk?
- Zou een partner, medewerker of boekhouder toegang moeten krijgen?
- Wat geeft vertrouwen?
- Waar haken mensen af?
- Wat maakt Bewaarhet betaalwaardig?

### Praktisch validatieplan

Start met 5 tot 10 testgebruikers.

Meet per gebruiker:

- aantal opgeslagen documenten;
- documentsoorten;
- aantal zoekopdrachten;
- geslaagde/mislukte zoekopdrachten;
- gebruik van extra e-mailadressen;
- supportvragen;
- momenten van verwarring;
- reden om wel/niet door te willen na de proef.

Plan korte gesprekken:

- na de eerste paar documenten;
- na de eerste zoekopdracht;
- aan het einde van de proefperiode.

### Productregel

Bouw nieuwe grote functies pas als ze terugkomen uit echt gebruik.

Meerdere e-mailadressen lijkt nu de sterkste betaalbare feature, maar ook die moet worden gevalideerd voordat er een groot portaal of ingewikkelde pricing omheen wordt gebouwd.
