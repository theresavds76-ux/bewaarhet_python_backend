# Bewaarhet Billing MVP

Datum: 2026-06-09

## Doel

Een pragmatische betaalflow voor de eerste betalende klanten.

Niet gebouwd alsof Bewaarhet morgen 10.000 klanten heeft.

Wel geregeld:

- proefgebruikers kunnen een betaald abonnement starten;
- betaling loopt via een professionele provider;
- webhook verwerkt betaalstatus;
- account wordt automatisch actief na geslaagde betaling;
- mislukte betaling blokkeert een gebruiker niet direct;
- beheer kan handmatig ingrijpen.

## Providerkeuze

### Mollie

Voordelen voor Bewaarhet nu:

- sterk in Nederland;
- iDEAL is vertrouwd;
- eenvoudiger verhaal voor Nederlandse eerste klanten;
- subscriptions en recurring payments zijn mogelijk;
- past bij een kleine Nederlandse dienst.

### Stripe

Voordelen later:

- sterke subscription tooling;
- uitgebreid customer portal;
- internationaal sterker;
- veel SaaS-voorbeelden en integraties.

### Advies

Gebruik nu Mollie.

Reden: Bewaarhet richt zich eerst op Nederlandse gebruikers en heeft vooral een simpele, vertrouwde betaalroute nodig. Stripe blijft later mogelijk, maar zou nu meer SaaS-complexiteit uitnodigen dan nodig is.

## MVP-abonnementsmodel

Statussen:

- `trial`: gebruiker test Bewaarhet.
- `active`: gebruiker heeft betaald en mag blijven gebruiken.
- `past_due`: later bruikbaar bij terugkerende mislukte betalingen.
- `canceled`: handmatig of later via provider opgezegd.
- `blocked`: bewust geblokkeerd.

Voor nu is er één betaald abonnement:

- bedrag: `BILLING_AMOUNT_EUR`, standaard `9.00`;
- interval: `BILLING_INTERVAL`, standaard `1 month`;
- provider: Mollie.

Geen meerdere pakketten.
Geen coupons.
Geen jaarabonnementen.
Geen self-service portal.

## Datamodel

Toegevoegd aan `accounts`:

- `subscription_status`
- `payment_started_at`
- `paid_until`
- `cancelled_at`

Al aanwezig en gebruikt:

- `billing_provider`
- `billing_customer_id`
- `subscription_id`
- `trial_ends_at`

Nieuwe tabel:

`account_payments`

Doel:

- Mollie payment ID koppelen aan account;
- webhook idempotent kunnen verwerken;
- status van eerste betaling bewaren.

Belangrijkste velden:

- `account_id`
- `provider_payment_id`
- `provider_customer_id`
- `provider_subscription_id`
- `purpose`
- `status`
- `checkout_url`
- `amount_value`
- `currency`
- `raw_status`

## Gebruikersflow

### 1. Accountactivatie

1. Gebruiker mailt document naar Bewaarhet.
2. Bewaarhet maakt account en e-mailadres aan.
3. Gebruiker bevestigt e-mailadres.
4. Account gaat naar `trial`.

### 2. Trial loopt af of gebruiker wil blijven

Beheer stuurt een betaalverzoek:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin send-payment-request gebruiker@example.com
```

Of alleen link tonen:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin send-payment-request gebruiker@example.com --print-link-only
```

### 3. Gebruiker klikt betaallink

Endpoint:

```text
/betaal?token=...
```

De server:

1. valideert token;
2. maakt Mollie customer aan als die nog niet bestaat;
3. maakt eerste betaling met `sequenceType=first`;
4. registreert payment in `account_payments`;
5. redirect naar Mollie Checkout.

### 4. Mollie webhook

Endpoint:

```text
/mollie/webhook
```

Mollie stuurt een payment ID.

De server:

1. haalt paymentstatus op bij Mollie;
2. zoekt account via `account_payments` of metadata;
3. zet paymentstatus bij;
4. bij `paid`:
   - maakt Mollie subscription aan;
   - zet account op `active`;
   - bewaart `subscription_id`;
5. bij `failed`, `expired` of `canceled`:
   - zet alleen `subscription_status`;
   - blokkeert de gebruiker niet direct.

## Waarom mislukte betaling niet meteen blokkeert

Voor eerste klanten wil je geen harde automatische afsluiting op een losse betaalfout.

Redenen:

- gebruiker kan per ongeluk terugklikken;
- iDEAL-sessie kan verlopen;
- webhook kan later alsnog een definitieve status krijgen;
- support moet kunnen meekijken.

Daarom:

- `failed`, `expired`, `canceled` blokkeren niet;
- account blijft trial of bestaande status;
- beheer kan later handmatig opvolgen.

## Admin-acties

Betaalverzoek sturen:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin send-payment-request gebruiker@example.com
```

Betaallink tonen zonder mail:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin send-payment-request gebruiker@example.com --print-link-only
```

Handmatig betaald zetten:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin mark-account-paid gebruiker@example.com --paid-until 2026-07-09
```

Trial verlengen/resetten:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin extend-trial gebruiker@example.com 2026-07-09
```

Account annuleren:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin cancel-account gebruiker@example.com
```

Accountstatus bekijken:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin account-info gebruiker@example.com
```

## Configuratie

Nieuwe `.env` waarden:

```text
BILLING_ENABLED=false
TRIAL_DAYS=14
MOLLIE_API_KEY=
MOLLIE_BASE_URL=https://api.mollie.com/v2
BILLING_AMOUNT_EUR=9.00
BILLING_CURRENCY=EUR
BILLING_INTERVAL=1 month
BILLING_DESCRIPTION=Bewaarhet maandabonnement
BILLING_START_URL=https://bewaarhet.nl/betaal
BILLING_REDIRECT_URL=https://bewaarhet.nl/betaal/bedankt
BILLING_WEBHOOK_URL=https://bewaarhet.nl/mollie/webhook
BILLING_TOKEN_TTL_HOURS=168
```

Belangrijk:

- Zet `BILLING_ENABLED=true` pas als Mollie key en publieke webhook URL goed staan.
- `MOLLIE_API_KEY` nooit committen.
- Webhook URL moet publiek bereikbaar zijn.

## Webhooks

Minimaal verwerkt:

- payment `paid`;
- payment `failed`;
- payment `expired`;
- payment `canceled`;
- overige statussen worden opgeslagen als `subscription_status`, maar blokkeren niets.

Voor subscriptions maakt Mollie later nieuwe payments aan. De huidige MVP is voorbereid op `subscriptionId`, maar uitgebreide dunning/retentie wordt bewust nog niet gebouwd.

## Later uitbreidbaar naar

- meerdere prijsplannen;
- automatische incasso met uitgebreidere retrylogica;
- jaarabonnementen;
- kortingscodes;
- self-service klantportaal;
- Stripe als alternatieve provider;
- hosted invoice/billing portal;
- automatische trial-expiry mails.

## Bewust niet gebouwd

- geen dashboard;
- geen facturatiemodule;
- geen meerdere pakketten;
- geen kortingscodes;
- geen complex dunningproces;
- geen self-service opzegflow;
- geen boekhoudkoppeling.

## Concrete codewijzigingen

- `bewaarhet/config.py`: billingconfig toegevoegd.
- `.env.example`: Mollie/billing instellingen toegevoegd.
- `bewaarhet/database.py`: billingvelden en `account_payments` toegevoegd.
- `bewaarhet/billing.py`: Mollie MVP-client, betaallinks, webhookverwerking en betaalmail.
- `bewaarhet/activation_server.py`: `/betaal`, `/betaal/bedankt` en `/mollie/webhook`.
- `bewaarhet/admin.py`: admincommando's voor betaalverzoek, handmatig betaald, trial verlengen en annuleren.
- `test_billing_mvp.py`: tests voor token, checkout, paid webhook en failed webhook.

## Validatie

Gedraaid:

```powershell
python -m py_compile bewaarhet\billing.py bewaarhet\activation_server.py bewaarhet\admin.py bewaarhet\database.py bewaarhet\config.py
.\.venv\Scripts\python.exe -m pytest test_billing_mvp.py test_activation_webflow.py test_customer_onboarding.py test_customer_isolation.py -q
```

Resultaat:

```text
28 passed
```

Volledige suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Resultaat:

```text
177 passed, 1 failed
```

De overblijvende failure zit in `test_static_site_seo.py` en verwacht een oude homepage-afbeelding (`bewaarhet-overzicht-2.webp`). Dit staat los van de billing-MVP.
