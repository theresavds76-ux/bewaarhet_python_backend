from __future__ import annotations

import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


class ActivationHandler(BaseHTTPRequestHandler):
    server_version = 'BewaarhetActivation/1.0'

    def do_GET(self) -> None:
        if self.path == '/healthz':
            self._send_text(200, 'ok\n')
            return
        response = activation_response_for_path(self.path)
        self._send_html(response.status_code, response.html)

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
