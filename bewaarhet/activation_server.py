from __future__ import annotations

import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .billing import BillingError, process_mollie_payment_webhook, start_checkout_for_account, verify_billing_token
from .config import settings
from .customer_onboarding import activate_customer_from_token
from .utils import sanitize_for_log


TEMPLATE_DIR = Path(__file__).with_name('templates')


@dataclass(frozen=True)
class ActivationResponse:
    status_code: int
    html: str


def _template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding='utf-8')


def _optional_faq_link() -> str:
    faq_url = getattr(settings, 'faq_url', '').strip()
    if not faq_url:
        return ''
    return f'<a class="secondary" href="{faq_url}">Veelgestelde vragen</a>'


def _render(name: str) -> str:
    public_site_url = getattr(settings, 'public_site_url', 'https://bewaarhet.nl').rstrip('/')
    return (
        _template(name)
        .replace('{{PUBLIC_SITE_URL}}', public_site_url)
        .replace('{{FAQ_LINK}}', _optional_faq_link())
    )


def activation_response_for_token(token: str | None) -> ActivationResponse:
    if not token:
        return ActivationResponse(400, _render('activation_invalid.html'))
    try:
        activate_customer_from_token(token)
    except RuntimeError as exc:
        # Configuration error (missing secrets, etc)
        error_msg = str(exc)
        sanitized = sanitize_for_log(error_msg)
        print(f"activation failed | error_type=RuntimeError | config_error={sanitized}")
        return ActivationResponse(400, _render('activation_invalid.html'))
    except ValueError as exc:
        # Token validation error (invalid signature, expired, etc)
        error_reason = sanitize_for_log(str(exc))
        print(f"activation failed | error_type=ValueError | reason={error_reason}")
        return ActivationResponse(400, _render('activation_invalid.html'))
    except Exception as exc:
        # Unexpected error
        error_type = sanitize_for_log(type(exc).__name__)
        error_msg = sanitize_for_log(str(exc)[:100])
        print(f"activation failed | error_type={error_type} | message={error_msg}")
        return ActivationResponse(400, _render('activation_invalid.html'))
    return ActivationResponse(200, _render('activation_success.html'))


def activation_response_for_path(path: str) -> ActivationResponse:
    parsed = urlparse(path)
    if parsed.path != '/activeer':
        return ActivationResponse(404, _render('activation_invalid.html'))
    token = parse_qs(parsed.query).get('token', [''])[0]
    return activation_response_for_token(token)


def billing_redirect_for_path(path: str) -> tuple[int, str | None, str]:
    parsed = urlparse(path)
    token = parse_qs(parsed.query).get('token', [''])[0]
    if not token:
        return 400, None, 'Betaallink is ongeldig of onvolledig.'
    try:
        account_id = verify_billing_token(token)
        checkout_url = start_checkout_for_account(account_id)
    except (BillingError, ValueError) as exc:
        print(f"billing start failed | error={sanitize_for_log(exc)}")
        return 400, None, 'Betaallink is ongeldig of kon niet worden gestart.'
    except Exception as exc:
        print(f"billing start failed | error_type={sanitize_for_log(type(exc).__name__)} | message={sanitize_for_log(str(exc)[:100])}")
        return 500, None, 'Betaling kon niet worden gestart.'
    return 302, checkout_url, ''


def billing_return_response() -> ActivationResponse:
    return ActivationResponse(200, '''
        <!doctype html>
        <html lang="nl">
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Betaling ontvangen | Bewaarhet</title></head>
        <body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:680px;margin:48px auto;padding:0 20px;line-height:1.5;">
            <h1>Bedankt</h1>
            <p>Als de betaling is gelukt, verwerken we je Bewaarhet-account automatisch. Je kunt dit venster sluiten.</p>
            <p>Groet,<br>Bewaarhet</p>
        </body>
        </html>
    ''')


class ActivationHandler(BaseHTTPRequestHandler):
    server_version = 'BewaarhetActivation/1.0'

    def do_GET(self) -> None:
        if self.path == '/healthz':
            self._send_text(200, 'ok\n')
            return
        parsed = urlparse(self.path)
        if parsed.path == '/betaal':
            status_code, location, message = billing_redirect_for_path(self.path)
            if status_code == 302 and location:
                self.send_response(302)
                self.send_header('Location', location)
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            self._send_text(status_code, message + '\n')
            return
        if parsed.path == '/betaal/bedankt':
            response = billing_return_response()
            self._send_html(response.status_code, response.html)
            return
        response = activation_response_for_path(self.path)
        self._send_html(response.status_code, response.html)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != '/mollie/webhook':
            self._send_text(404, 'not found\n')
            return
        length = int(self.headers.get('Content-Length') or '0')
        payload = self.rfile.read(min(length, 4096)).decode('utf-8', errors='replace')
        payment_id = parse_qs(payload).get('id', [''])[0]
        try:
            result = process_mollie_payment_webhook(payment_id)
            print(f"mollie webhook processed | payment_id={sanitize_for_log(payment_id)} | result={sanitize_for_log(result)}")
            self._send_text(200, 'ok\n')
        except Exception as exc:
            print(
                "mollie webhook failed"
                f" | payment_id={sanitize_for_log(payment_id)}"
                f" | error={sanitize_for_log(str(exc)[:200])}"
            )
            self._send_text(500, 'error\n')

    def log_message(self, format: str, *args) -> None:
        print(f"activation request | remote={sanitize_for_log(self.client_address[0])} | status={sanitize_for_log(args[1] if len(args) > 1 else '')}")

    def _send_html(self, status_code: int, html: str) -> None:
        payload = html.encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, status_code: int, text: str) -> None:
        payload = text.encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run() -> None:
    settings.ensure_directories()
    host = os.getenv('ACTIVATION_SERVER_HOST', '0.0.0.0')
    port = int(os.getenv('ACTIVATION_SERVER_PORT', '8080'))
    server = ThreadingHTTPServer((host, port), ActivationHandler)
    print(f"Activation server started | host={sanitize_for_log(host)} | port={port}")
    server.serve_forever()


if __name__ == '__main__':
    run()
