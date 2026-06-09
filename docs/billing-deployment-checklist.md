# Billing live deployment checklist

Datum: 2026-06-09

## Benodigd

- Mollie API key:
  - eerst test key;
  - daarna pas live key.
- Publieke webhook URL:
  - `https://bewaarhet.nl/mollie/webhook`
- Publieke betaalstart URL:
  - `https://bewaarhet.nl/betaal`
- Publieke redirect URL:
  - `https://bewaarhet.nl/betaal/bedankt`

## Env-vars

Zet in productie:

```text
BILLING_ENABLED=true
MOLLIE_API_KEY=<mollie_test_or_live_key>
MOLLIE_BASE_URL=https://api.mollie.com/v2
BILLING_AMOUNT_EUR=9.00
BILLING_CURRENCY=EUR
BILLING_INTERVAL=1 month
BILLING_DESCRIPTION=Bewaarhet maandabonnement
BILLING_START_URL=https://bewaarhet.nl/betaal
BILLING_REDIRECT_URL=https://bewaarhet.nl/betaal/bedankt
BILLING_WEBHOOK_URL=https://bewaarhet.nl/mollie/webhook
BILLING_TOKEN_TTL_HOURS=168
TRIAL_DAYS=14
```

Controleer ook dat `VERIFICATION_TOKEN_SECRET` lang, uniek en stabiel is. Dit wordt gebruikt om betaallinks veilig te ondertekenen.

## Voor livegang

1. Maak databasebackup.
2. Deploy code.
3. Start/restart activation server en worker.
4. Controleer:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin account-info test@example.com
```

5. Maak betaalverzoek met testaccount:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin send-payment-request test@example.com --print-link-only
```

6. Open betaallink en rond Mollie testbetaling af.
7. Controleer webhooklog.
8. Controleer accountstatus:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin account-info test@example.com
```

Verwacht:

- accountstatus `active`;
- `subscription_status` actief/betaald;
- Mollie customer ID gevuld;
- subscription ID gevuld.

## Eerste echte betaling

1. Zet Mollie live key.
2. Laat `BILLING_ENABLED=true`.
3. Stuur betaalverzoek naar één echte proefgebruiker.
4. Controleer na betaling:
   - Mollie dashboard;
   - webhooklog;
   - `account-info`;
   - gebruiker kan nog opslaan/zoeken.

## Rollback

Snelste veilige rollback:

```text
BILLING_ENABLED=false
```

Daarna service herstarten.

Effect:

- bestaande opslag/zoekflow blijft werken;
- nieuwe betaallinks starten geen Mollie Checkout;
- bestaande handmatig actieve accounts blijven actief;
- je kunt indien nodig accounts handmatig corrigeren met:

```powershell
.\.venv\Scripts\python.exe -m bewaarhet.admin mark-account-paid gebruiker@example.com --notes "manual rollback correction"
.\.venv\Scripts\python.exe -m bewaarhet.admin extend-trial gebruiker@example.com 2026-07-09 --notes "billing rollback"
```

Bij databaseproblemen:

1. Stop services.
2. Restore laatste backup.
3. Zet `BILLING_ENABLED=false`.
4. Start services opnieuw.
