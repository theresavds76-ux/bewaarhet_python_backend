from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import requests

from .config import settings
from .database import (
    get_account_by_id,
    get_account_for_email,
    get_account_payment,
    record_account_payment,
    set_account_billing_status,
    update_account_payment_status,
)
from .mail_client import send_html
from .utils import canonical_customer_identity, html_escape, sanitize_for_log


BILLING_TOKEN_PURPOSE = 'billing_start'
FINAL_FAILED_STATUSES = {'failed', 'expired', 'canceled'}


class BillingError(RuntimeError):
    pass


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _b64_decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def _token_secret() -> bytes:
    secret = getattr(settings, 'verification_token_secret', '').strip()
    if not secret:
        raise BillingError('VERIFICATION_TOKEN_SECRET is required for billing tokens')
    return secret.encode('utf-8')


def create_billing_token(email: str, *, now: int | None = None) -> str:
    customer_email = canonical_customer_identity(email)
    if not customer_email:
        raise ValueError('email is required')
    account = get_account_for_email(customer_email)
    if account is None:
        raise ValueError('account not found')
    issued_at = int(time.time() if now is None else now)
    ttl_seconds = max(1, int(getattr(settings, 'billing_token_ttl_hours', 168))) * 3600
    payload = {
        'account_id': int(account['id']),
        'email': customer_email,
        'exp': issued_at + ttl_seconds,
        'purpose': BILLING_TOKEN_PURPOSE,
    }
    body = _b64_encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8'))
    signature = _b64_encode(hmac.new(_token_secret(), body.encode('ascii'), hashlib.sha256).digest())
    return f'{body}.{signature}'


def verify_billing_token(token: str, *, now: int | None = None) -> int:
    try:
        body, signature = token.split('.', 1)
    except ValueError as exc:
        raise ValueError('invalid token format') from exc
    expected = _b64_encode(hmac.new(_token_secret(), body.encode('ascii'), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise ValueError('invalid token signature')
    payload = json.loads(_b64_decode(body).decode('utf-8'))
    if payload.get('purpose') != BILLING_TOKEN_PURPOSE:
        raise ValueError('invalid token purpose')
    if int(payload.get('exp') or 0) < int(time.time() if now is None else now):
        raise ValueError('token expired')
    account_id = int(payload.get('account_id') or 0)
    if not account_id:
        raise ValueError('missing account_id')
    return account_id


def billing_link(email: str) -> str:
    configured_url = getattr(settings, 'billing_start_url', '').strip()
    base_url = configured_url or f"{getattr(settings, 'public_site_url', 'https://bewaarhet.nl').rstrip('/')}/betaal"
    separator = '&' if '?' in base_url else '?'
    return f'{base_url}{separator}{urlencode({"token": create_billing_token(email)})}'


def _mollie_headers() -> dict[str, str]:
    api_key = getattr(settings, 'mollie_api_key', '').strip()
    if not api_key:
        raise BillingError('MOLLIE_API_KEY is not configured')
    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }


def _mollie_request(method: str, path: str, *, payload: dict | None = None) -> dict:
    url = f"{settings.mollie_base_url}{path}"
    response = requests.request(method, url, headers=_mollie_headers(), json=payload, timeout=15)
    if response.status_code >= 400:
        raise BillingError(f'Mollie API error {response.status_code}: {sanitize_for_log(response.text[:200])}')
    return response.json()


def _ensure_mollie_customer(account) -> str:
    existing = str(account['billing_customer_id'] or '').strip()
    if existing:
        return existing
    payload = {
        'name': account['name'] or account['primary_email'],
        'email': account['primary_email'],
    }
    customer = _mollie_request('POST', '/customers', payload=payload)
    customer_id = customer['id']
    set_account_billing_status(
        int(account['id']),
        billing_provider='mollie',
        billing_customer_id=customer_id,
        subscription_status='customer_created',
    )
    return customer_id


def start_checkout_for_account(account_id: int) -> str:
    if not getattr(settings, 'billing_enabled', False):
        raise BillingError('billing is disabled')
    account = get_account_by_id(account_id)
    if account is None:
        raise BillingError('account not found')
    if account['status'] == 'blocked':
        raise BillingError('account is blocked')
    if account['status'] == 'active' and account['subscription_id']:
        raise BillingError('account already has an active subscription')

    customer_id = _ensure_mollie_customer(account)
    payment = _mollie_request('POST', '/payments', payload={
        'amount': {
            'currency': settings.billing_currency,
            'value': settings.billing_amount_eur,
        },
        'customerId': customer_id,
        'sequenceType': 'first',
        'description': settings.billing_description,
        'redirectUrl': settings.billing_redirect_url or settings.public_site_url,
        'webhookUrl': settings.billing_webhook_url,
        'metadata': {
            'account_id': int(account['id']),
            'purpose': 'first_payment',
        },
    })
    checkout_url = payment.get('_links', {}).get('checkout', {}).get('href')
    if not checkout_url:
        raise BillingError('Mollie response did not include checkout URL')
    record_account_payment(
        account_id=int(account['id']),
        provider_payment_id=payment['id'],
        provider_customer_id=customer_id,
        purpose='first_payment',
        status=payment.get('status') or 'open',
        checkout_url=checkout_url,
        amount_value=settings.billing_amount_eur,
        currency=settings.billing_currency,
        raw_status=payment.get('status'),
    )
    set_account_billing_status(
        int(account['id']),
        billing_provider='mollie',
        billing_customer_id=customer_id,
        subscription_status='payment_started',
        payment_started=True,
    )
    return checkout_url


def _create_subscription(account_id: int, customer_id: str) -> str:
    subscription = _mollie_request('POST', f'/customers/{customer_id}/subscriptions', payload={
        'amount': {
            'currency': settings.billing_currency,
            'value': settings.billing_amount_eur,
        },
        'interval': settings.billing_interval,
        'description': settings.billing_description,
        'webhookUrl': settings.billing_webhook_url,
    })
    subscription_id = subscription['id']
    set_account_billing_status(
        account_id,
        status='active',
        subscription_status=subscription.get('status') or 'active',
        billing_provider='mollie',
        billing_customer_id=customer_id,
        subscription_id=subscription_id,
    )
    return subscription_id


def process_mollie_payment_webhook(payment_id: str) -> str:
    payment_id = (payment_id or '').strip()
    if not payment_id:
        raise ValueError('payment id is required')
    payment = _mollie_request('GET', f'/payments/{payment_id}')
    payment_record = get_account_payment(payment_id)
    metadata = payment.get('metadata') or {}
    account_id = int(payment_record['account_id']) if payment_record else int(metadata.get('account_id') or 0)
    if not account_id:
        raise BillingError('payment account not found')

    status = payment.get('status') or 'unknown'
    subscription_id = payment.get('subscriptionId') or payment.get('subscription_id')
    update_account_payment_status(payment_id, status=status, raw_status=status, provider_subscription_id=subscription_id)

    if status == 'paid':
        account = get_account_by_id(account_id)
        if account is None:
            raise BillingError('account not found')
        customer_id = payment.get('customerId') or payment.get('customer', {}).get('id') or account['billing_customer_id']
        if not subscription_id and customer_id and not account['subscription_id']:
            subscription_id = _create_subscription(account_id, customer_id)
        else:
            set_account_billing_status(
                account_id,
                status='active',
                subscription_status='active',
                billing_provider='mollie',
                billing_customer_id=customer_id,
                subscription_id=subscription_id,
            )
        update_account_payment_status(payment_id, status='paid', raw_status=status, provider_subscription_id=subscription_id)
        return 'paid'

    if status in FINAL_FAILED_STATUSES:
        set_account_billing_status(account_id, subscription_status=status)
        return status

    set_account_billing_status(account_id, subscription_status=status)
    return status


def send_payment_request_email(email: str) -> None:
    link = html_escape(billing_link(email))
    amount = html_escape(f"{settings.billing_currency} {settings.billing_amount_eur}")
    send_html(email, 'Bewaarhet proefperiode omzetten naar betaald', f'''
        Hoi,<br><br>
        Je kunt Bewaarhet blijven gebruiken door je abonnement te starten.<br><br>
        Bedrag: <b>{amount}</b> per maand.<br><br>
        <a href="{link}" style="display:inline-block;padding:12px 18px;background:#1f6feb;color:#ffffff;text-decoration:none;border-radius:6px;">Start betaald abonnement</a><br><br>
        Of open deze link:<br>
        <a href="{link}">{link}</a><br><br>
        Je documenten blijven aan je account gekoppeld. Er worden geen documenten naar derden gestuurd.<br><br>
        Groet,<br>
        Bewaarhet
    ''')
