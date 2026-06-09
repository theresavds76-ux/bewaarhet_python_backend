# Bewaarhet SaaS-implementatielog

Datum: 2026-06-09

## Doel

Bewaarhet blijft e-mail-first:

- geen verplicht accountformulier vooraf;
- geen wachtwoord bij eerste gebruik;
- geen dashboardplicht;
- eerste gebruik blijft: document mailen, e-mailadres bevestigen, proef starten.

Onder water is een accountlaag toegevoegd, zodat Bewaarhet kan doorgroeien naar SaaS met meerdere e-mailadressen, proeftijd, betalen en beheer.

## Toegevoegd

### Nieuwe databasekolom

`documents.account_id`

Doel:

- documenten kunnen aan een account gekoppeld worden;
- zoeken kan accountbreed werken;
- oude `customer_email` en `customer_identity` blijven bestaan voor compatibiliteit.

### Nieuwe tabellen

`accounts`

Bevat de echte klant/tenant:

- status;
- plan;
- primary email;
- veilige accountmap;
- documentteller;
- opslaggebruik;
- trialvelden;
- toekomstige billingvelden.

`account_emails`

Bevat alle e-mailadressen die bij een account horen:

- label, bijvoorbeeld `hoofd`, `prive`, `zakelijk`, `boekhouder`;
- status: `pending`, `verified`, `disabled`;
- rechten:
  - `can_store`;
  - `can_search`;
  - `can_manage`.

## Migratiegedrag

Bij `init_db()` gebeurt nu:

1. bestaande `customers` blijven bestaan;
2. voor elke bestaande customer wordt een account aangemaakt als dat nog niet bestaat;
3. het customer e-mailadres wordt primary account email;
4. bestaande documenten krijgen waar mogelijk een `account_id`;
5. oude flows blijven werken via `customers`, `customer_email` en `customer_identity`.

Dit is bewust compatibel gebouwd. De live worker hoeft daardoor niet in een keer naar een volledig nieuw model.

## Gedrag bij eerste klantcontact

Onbekend e-mailadres:

1. `ensure_customer()` maakt nog steeds een legacy customer aan;
2. tegelijk wordt een account aangemaakt;
3. het eerste e-mailadres wordt primary account email;
4. status blijft `pending_verification`;
5. de klant krijgt de bestaande verificatiemail;
6. na verificatie wordt het account `trial`.

De klant merkt dus alleen: "bevestig je e-mailadres".

## Meerdere e-mailadressen

Een extra e-mailadres kan nu aan een bestaand account worden toegevoegd.

Voorbeeld:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin add-account-email owner@example.com prive@example.com --label prive --show-activation-link
```

Daarna moet `prive@example.com` worden bevestigd met de activatielink.

Na verificatie:

- het extra adres hoort bij hetzelfde account;
- het adres kan documenten opslaan als `can_store=1`;
- het adres kan accountdocumenten zoeken als `can_search=1`;
- pending adressen kunnen nog niet zoeken.

## Admincommando's

Toon accountcontext:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin account-info email@example.com
```

Extra e-mailadres toevoegen:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin add-account-email owner@example.com extra@example.com --label zakelijk --show-activation-link
```

Opties:

- `--label prive`
- `--label zakelijk`
- `--label boekhouder`
- `--no-store`
- `--no-search`
- `--can-manage`

Verificatietoken verwerken:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin verify-customer-token <token>
```

## Zoekisolatie

Zoeken gebruikt nu:

1. het geverifieerde e-mailadres;
2. het bijbehorende account;
3. `documents.account_id`;
4. oude e-mail/folderchecks als fallback.

Belangrijke veiligheidsregels:

- pending e-mailadressen mogen niet accountbreed zoeken;
- disabled e-mailadressen mogen niet zoeken;
- alleen geverifieerde adressen met `can_search=1` krijgen accountbrede resultaten;
- de bestaande ownership-check in `search_reply.py` is uitgebreid met `account_id`.

## Tests

Toegevoegd aan `test_customer_onboarding.py`:

- geverifieerd extra e-mailadres kan documenten van hetzelfde account vinden;
- pending extra e-mailadres kan accountdocumenten niet vinden.

Gedraaid:

```powershell
.\.venv\Scripts\python.exe -m pytest test_customer_onboarding.py test_customer_isolation.py -q
```

Resultaat:

```text
19 passed
```

Na toevoeging van de activatie-webflowcontrole is ook gedraaid:

```powershell
.\.venv\Scripts\python.exe -m pytest test_activation_webflow.py test_customer_onboarding.py test_customer_isolation.py -q
```

Resultaat:

```text
24 passed
```

Volledige suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Resultaat:

```text
173 passed, 1 failed
```

De overblijvende failure zit in `test_static_site_seo.py` en verwacht dat `docs/index.html` nog naar `bewaarhet-overzicht-2.webp` verwijst. De huidige homepage gebruikt andere assets. Dit staat los van de SaaS-accountlaag.

## Nog niet gebouwd

Bewust nog niet gebouwd in deze stap:

- klantportaal;
- magic-link web-login;
- betaalprovider;
- trial expiry mails;
- Mollie/Stripe webhooks;
- dashboarddocumenten zoeken;
- privacy/export/verwijderflow.

Deze stap legt alleen het fundament onder de bestaande e-mailervaring.

## Volgende logische stap

De volgende stap is niet meteen een groot beheerportaal of betalen, maar product-validatie met echte gebruikers.

Te beantwoorden vragen:

- Welke documenten sturen mensen werkelijk?
- Gebruiken ze zoeken ook echt?
- Welke zoekvragen stellen ze?
- Willen ze meerdere e-mailadressen?
- Is zakelijk/prive scheiding belangrijk?
- Wat maakt Bewaarhet betaalwaardig?

Pas daarna is de volgende bouwstap een klein beheerportaal met magic-link login:

1. inloggen via geverifieerd e-mailadres;
2. accountstatus bekijken;
3. extra e-mailadres toevoegen;
4. verificatiemail versturen;
5. labels/rechten beheren.

Daarna pas proeftijd afronden en betalen koppelen.
