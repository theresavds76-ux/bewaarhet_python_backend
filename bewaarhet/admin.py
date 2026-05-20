from __future__ import annotations

import argparse
import time
from pathlib import Path

from .backup import create_backup, list_backups, restore_backup
from .cleanup import build_cleanup_report, cleanup_orphaned, cleanup_testdata, reset_dev_environment
from .config import settings
from .customer_onboarding import activate_customer_from_token
from .database import ensure_customer, get_customer, list_customers, update_customer_status
from .maintenance import run_dropbox_consistency_check
from .utils import canonical_customer_identity, sanitize_for_log


def _backup_create(args: argparse.Namespace) -> None:
    backup = create_backup(reason=args.reason)
    print(f'Backup: {sanitize_for_log(backup)}')


def _backup_list(_args: argparse.Namespace) -> None:
    backups = list_backups()
    if not backups:
        print('Geen backups gevonden.')
        return
    for backup in backups:
        print(f'{backup.created_at} | {backup.size} bytes | {sanitize_for_log(backup.path)}')


def _backup_restore(args: argparse.Namespace) -> None:
    result = restore_backup(
        Path(args.backup),
        dry_run=args.dry_run,
        confirm=args.confirm,
        backup_current=not args.no_backup_current,
    )
    print(result.message)


def _consistency_check(args: argparse.Namespace) -> None:
    run_dropbox_consistency_check(
        limit=args.limit,
        since_id=args.since_id,
        log_every=args.log_every,
        slow_threshold_seconds=args.slow_threshold,
    )


def _cleanup_report(_args: argparse.Namespace) -> None:
    build_cleanup_report(check_dropbox=True)


def _cleanup_orphaned(args: argparse.Namespace) -> None:
    cleanup_orphaned(confirm=args.confirm and not args.dry_run)


def _cleanup_testdata(args: argparse.Namespace) -> None:
    cleanup_testdata(confirm=args.confirm and not args.dry_run)


def _reset_dev_environment(args: argparse.Namespace) -> None:
    reset_dev_environment(confirm=args.confirm, clear_logs=args.clear_logs)


def _backup_scheduler(args: argparse.Namespace) -> None:
    interval_seconds = max(60, int(args.interval_seconds))
    print(f'Backup scheduler gestart | interval_seconds={interval_seconds}')
    while True:
        try:
            create_backup(reason='scheduled')
        except Exception as exc:
            print(f'Backup scheduler fout | error={sanitize_for_log(exc)}')
        if args.once:
            return
        time.sleep(interval_seconds)


def _print_customer(customer) -> None:
    if not customer:
        print('Customer niet gevonden.')
        return
    print(
        f"id={customer['id']}"
        f" | email={sanitize_for_log(customer['email'])}"
        f" | status={customer['status']}"
        f" | documents={customer['document_count']}"
        f" | storage_mb={float(customer['storage_used_mb'] or 0):.3f}"
        f" | created_at={customer['created_at']}"
        f" | last_activity_at={customer['last_activity_at'] or ''}"
        f" | notes={sanitize_for_log(customer['notes'] or '')}"
    )


def _add_customer(args: argparse.Namespace) -> None:
    customer, created = ensure_customer(canonical_customer_identity(args.email), name=args.name)
    if args.status != 'trial':
        customer = update_customer_status(args.email, args.status, name=args.name, notes=args.notes)
    elif args.notes:
        customer = update_customer_status(args.email, 'trial', name=args.name, notes=args.notes)
    print('Customer aangemaakt.' if created else 'Customer bestaat al.')
    _print_customer(customer)


def _activate_customer(args: argparse.Namespace) -> None:
    customer = update_customer_status(args.email, 'active', notes=args.notes)
    print('Customer geactiveerd.')
    _print_customer(customer)


def _verify_customer(args: argparse.Namespace) -> None:
    customer = activate_customer_from_token(args.token)
    if args.notes:
        customer = update_customer_status(customer['email'], 'trial', notes=args.notes)
    print('Customer e-mailadres bevestigd. Trial gestart.')
    _print_customer(customer)


def _block_customer(args: argparse.Namespace) -> None:
    customer = update_customer_status(args.email, 'blocked', notes=args.notes)
    print('Customer geblokkeerd.')
    _print_customer(customer)


def _customer_info(args: argparse.Namespace) -> None:
    _print_customer(get_customer(args.email))


def _list_customers(args: argparse.Namespace) -> None:
    customers = list_customers(status=args.status, limit=args.limit)
    if not customers:
        print('Geen customers gevonden.')
        return
    for customer in customers:
        _print_customer(customer)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Bewaarhet admin utilities')
    subparsers = parser.add_subparsers(dest='command', required=True)

    create = subparsers.add_parser('create-backup', help='Maak een SQLite backup')
    create.add_argument('--reason', default='manual')
    create.set_defaults(func=_backup_create)

    list_cmd = subparsers.add_parser('list-backups', help='Toon beschikbare backups')
    list_cmd.set_defaults(func=_backup_list)

    restore = subparsers.add_parser('restore-backup', help='Herstel een SQLite backup')
    restore.add_argument('backup')
    restore.add_argument('--dry-run', action='store_true')
    restore.add_argument('--confirm', action='store_true', help='Bevestig overschrijven van de actieve database')
    restore.add_argument('--no-backup-current', action='store_true')
    restore.set_defaults(func=_backup_restore)

    consistency = subparsers.add_parser('consistency-check', help='Controleer SQLite records tegen Dropbox')
    consistency.add_argument('--limit', type=int, default=None, help='Controleer maximaal dit aantal records')
    consistency.add_argument('--since-id', type=int, default=None, help='Controleer alleen records met id groter dan deze waarde')
    consistency.add_argument('--log-every', type=int, default=None, help='Log voortgang elke N records')
    consistency.add_argument('--slow-threshold', type=float, default=None, help='Log trage Dropbox checks boven dit aantal seconden')
    consistency.set_defaults(func=_consistency_check)

    cleanup_report = subparsers.add_parser('cleanup-report', help='Rapporteer veilige pre-productie cleanup-kandidaten')
    cleanup_report.set_defaults(func=_cleanup_report)

    cleanup_orphaned_cmd = subparsers.add_parser('cleanup-orphaned', help='Verwijder alleen verweesde SQLite metadata-rijen')
    cleanup_orphaned_cmd.add_argument('--dry-run', action='store_true', help='Toon alleen wat verwijderd zou worden')
    cleanup_orphaned_cmd.add_argument('--confirm', action='store_true', help='Voer de SQLite cleanup echt uit')
    cleanup_orphaned_cmd.set_defaults(func=_cleanup_orphaned)

    cleanup_testdata_cmd = subparsers.add_parser('cleanup-testdata', help='Verwijder waarschijnlijke test/dev metadata-rijen')
    cleanup_testdata_cmd.add_argument('--dry-run', action='store_true', help='Toon alleen wat verwijderd zou worden')
    cleanup_testdata_cmd.add_argument('--confirm', action='store_true', help='Voer de SQLite cleanup echt uit')
    cleanup_testdata_cmd.set_defaults(func=_cleanup_testdata)

    reset = subparsers.add_parser('reset-dev-environment', help='Maak een backup en leeg dev SQLite metadata')
    reset.add_argument('--confirm', action='store_true', help='Vereist: bevestig reset van SQLite metadata')
    reset.add_argument('--clear-logs', action='store_true', help='Verwijder losse logbestanden binnen LOG_DIR')
    reset.set_defaults(func=_reset_dev_environment)

    scheduler = subparsers.add_parser('backup-scheduler', help='Eenvoudige geplande backup helper')
    scheduler.add_argument('--interval-seconds', type=int, default=24 * 60 * 60)
    scheduler.add_argument('--once', action='store_true')
    scheduler.set_defaults(func=_backup_scheduler)

    add_customer = subparsers.add_parser('add-customer', help='Maak een customer aan of toon bestaande customer')
    add_customer.add_argument('email')
    add_customer.add_argument('--name', default=None)
    add_customer.add_argument('--status', choices=['pending_verification', 'trial', 'active', 'blocked'], default='trial')
    add_customer.add_argument('--notes', default=None)
    add_customer.set_defaults(func=_add_customer)

    activate_customer = subparsers.add_parser('activate-customer', help='Zet een customer op active')
    activate_customer.add_argument('email')
    activate_customer.add_argument('--notes', default=None)
    activate_customer.set_defaults(func=_activate_customer)

    verify_customer = subparsers.add_parser('verify-customer-token', help='Valideer activatietoken en start trial')
    verify_customer.add_argument('token')
    verify_customer.add_argument('--notes', default=None)
    verify_customer.set_defaults(func=_verify_customer)

    block_customer = subparsers.add_parser('block-customer', help='Blokkeer een customer')
    block_customer.add_argument('email')
    block_customer.add_argument('--notes', default=None)
    block_customer.set_defaults(func=_block_customer)

    customer_info = subparsers.add_parser('customer-info', help='Toon customerinformatie')
    customer_info.add_argument('email')
    customer_info.set_defaults(func=_customer_info)

    list_customers_cmd = subparsers.add_parser('list-customers', help='Toon customers')
    list_customers_cmd.add_argument('--status', choices=['pending_verification', 'trial', 'active', 'blocked'], default=None)
    list_customers_cmd.add_argument('--limit', type=int, default=100)
    list_customers_cmd.set_defaults(func=_list_customers)

    return parser


def main(argv: list[str] | None = None) -> None:
    settings.ensure_directories()
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()
