from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bewaarhet.billing import create_billing_token, process_mollie_payment_webhook, start_checkout_for_account, verify_billing_token
from bewaarhet.database import get_account_for_email, get_account_payment, init_db, update_customer_status


class TempSettings(SimpleNamespace):
    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def _response(payload: dict, status_code: int = 200) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.text = str(payload)
    response.json.return_value = payload
    return response


class BillingMvpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.settings = TempSettings(
            data_dir=root,
            database_path=root / 'bewaarhet.sqlite3',
            backup_dir=root / 'backups',
            log_dir=root / 'logs',
            backup_keep_latest=14,
            billing_enabled=True,
            mollie_api_key='test_xxx',
            mollie_base_url='https://api.mollie.test/v2',
            billing_amount_eur='9.00',
            billing_currency='EUR',
            billing_interval='1 month',
            billing_description='Bewaarhet maandabonnement',
            billing_start_url='https://bewaarhet.test/betaal',
            billing_redirect_url='https://bewaarhet.test/betaal/bedankt',
            billing_webhook_url='https://bewaarhet.test/mollie/webhook',
            billing_token_ttl_hours=168,
            verification_token_secret='unit-test-secret',
        )
        self.db_patch = patch('bewaarhet.database.settings', self.settings)
        self.billing_patch = patch('bewaarhet.billing.settings', self.settings)
        self.db_patch.start()
        self.billing_patch.start()
        init_db()

    def tearDown(self) -> None:
        self.billing_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_billing_token_roundtrip(self) -> None:
        update_customer_status('pay@example.com', 'trial')

        token = create_billing_token('pay@example.com')
        account_id = verify_billing_token(token)

        self.assertEqual(account_id, get_account_for_email('pay@example.com')['id'])

    def test_start_checkout_records_payment_and_payment_started(self) -> None:
        update_customer_status('pay@example.com', 'trial')
        account = get_account_for_email('pay@example.com')

        responses = [
            _response({'id': 'cst_123'}),
            _response({
                'id': 'tr_123',
                'status': 'open',
                '_links': {'checkout': {'href': 'https://checkout.mollie.test/tr_123'}},
            }),
        ]
        with patch('bewaarhet.billing.requests.request', side_effect=responses) as request:
            checkout_url = start_checkout_for_account(account['id'])

        self.assertEqual(checkout_url, 'https://checkout.mollie.test/tr_123')
        payment = get_account_payment('tr_123')
        self.assertIsNotNone(payment)
        self.assertEqual(payment['account_id'], account['id'])
        updated = get_account_for_email('pay@example.com')
        self.assertEqual(updated['subscription_status'], 'payment_started')
        self.assertEqual(request.call_count, 2)

    def test_paid_webhook_activates_account_and_creates_subscription(self) -> None:
        update_customer_status('paid@example.com', 'trial')
        account = get_account_for_email('paid@example.com')
        responses = [
            _response({'id': 'cst_paid'}),
            _response({
                'id': 'tr_paid',
                'status': 'open',
                '_links': {'checkout': {'href': 'https://checkout.mollie.test/tr_paid'}},
            }),
        ]
        with patch('bewaarhet.billing.requests.request', side_effect=responses):
            start_checkout_for_account(account['id'])

        webhook_responses = [
            _response({'id': 'tr_paid', 'status': 'paid', 'customerId': 'cst_paid', 'metadata': {'account_id': account['id']}}),
            _response({'id': 'sub_paid', 'status': 'active'}),
        ]
        with patch('bewaarhet.billing.requests.request', side_effect=webhook_responses):
            result = process_mollie_payment_webhook('tr_paid')

        self.assertEqual(result, 'paid')
        updated = get_account_for_email('paid@example.com')
        self.assertEqual(updated['status'], 'active')
        self.assertEqual(updated['subscription_id'], 'sub_paid')
        self.assertEqual(updated['subscription_status'], 'active')

    def test_failed_payment_does_not_block_account(self) -> None:
        update_customer_status('failed@example.com', 'trial')
        account = get_account_for_email('failed@example.com')
        responses = [
            _response({'id': 'cst_failed'}),
            _response({
                'id': 'tr_failed',
                'status': 'open',
                '_links': {'checkout': {'href': 'https://checkout.mollie.test/tr_failed'}},
            }),
        ]
        with patch('bewaarhet.billing.requests.request', side_effect=responses):
            start_checkout_for_account(account['id'])

        with patch('bewaarhet.billing.requests.request', return_value=_response({
            'id': 'tr_failed',
            'status': 'failed',
            'customerId': 'cst_failed',
            'metadata': {'account_id': account['id']},
        })):
            result = process_mollie_payment_webhook('tr_failed')

        self.assertEqual(result, 'failed')
        updated = get_account_for_email('failed@example.com')
        self.assertEqual(updated['status'], 'trial')
        self.assertEqual(updated['subscription_status'], 'failed')


if __name__ == '__main__':
    unittest.main()
