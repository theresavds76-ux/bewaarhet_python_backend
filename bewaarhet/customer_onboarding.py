from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from .config import settings
from .utils import canonical_customer_identity


TOKEN_PURPOSE = 'customer_email_verification'


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _b64_decode(value: str) -> bytes:
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def _token_secret() -> bytes:
    secret = (
        getattr(settings, 'verification_token_secret', '')
        or getattr(settings, 'dropbox_app_secret', '')
        or getattr(settings, 'zoho_app_password', '')
    )
    if not secret:
        raise RuntimeError('verification token secret is not configured')
    return secret.encode('utf-8')


def create_activation_token(email: str, *, now: int | None = None) -> str:
    customer_email = canonical_customer_identity(email)
    if not customer_email:
        raise ValueError('email is required')
    issued_at = int(time.time() if now is None else now)
    ttl_seconds = max(1, int(getattr(settings, 'verification_token_ttl_hours', 72))) * 3600
    payload = {
        'email': customer_email,
        'exp': issued_at + ttl_seconds,
        'purpose': TOKEN_PURPOSE,
    }
    body = _b64_encode(json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8'))
    signature = _b64_encode(hmac.new(_token_secret(), body.encode('ascii'), hashlib.sha256).digest())
    return f'{body}.{signature}'


def verify_activation_token(token: str, *, now: int | None = None) -> str:
    try:
        body, signature = token.split('.', 1)
    except ValueError as exc:
        raise ValueError('invalid activation token') from exc

    expected = _b64_encode(hmac.new(_token_secret(), body.encode('ascii'), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise ValueError('invalid activation token signature')

    try:
        payload = json.loads(_b64_decode(body).decode('utf-8'))
    except Exception as exc:
        raise ValueError('invalid activation token payload') from exc

    if payload.get('purpose') != TOKEN_PURPOSE:
        raise ValueError('invalid activation token purpose')
    expires_at = int(payload.get('exp') or 0)
    current_time = int(time.time() if now is None else now)
    if expires_at < current_time:
        raise ValueError('activation token expired')

    customer_email = canonical_customer_identity(str(payload.get('email') or ''))
    if not customer_email:
        raise ValueError('activation token has no email')
    return customer_email


def activation_link(email: str) -> str:
    token = create_activation_token(email)
    configured_url = getattr(settings, 'activation_url', '').strip()
    base_url = configured_url or f"{getattr(settings, 'public_site_url', 'https://bewaarhet.nl').rstrip('/')}/activeer"
    separator = '&' if '?' in base_url else '?'
    return f'{base_url}{separator}{urlencode({"token": token})}'


def activate_customer_from_token(token: str):
    email = verify_activation_token(token)
    from .database import activate_pending_customer

    return activate_pending_customer(email)
