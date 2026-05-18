from __future__ import annotations

import argparse
import time
from pathlib import Path

from .backup import create_backup, list_backups, restore_backup
from .config import settings
from .maintenance import run_dropbox_consistency_check
from .utils import sanitize_for_log


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

    scheduler = subparsers.add_parser('backup-scheduler', help='Eenvoudige geplande backup helper')
    scheduler.add_argument('--interval-seconds', type=int, default=24 * 60 * 60)
    scheduler.add_argument('--once', action='store_true')
    scheduler.set_defaults(func=_backup_scheduler)

    return parser


def main(argv: list[str] | None = None) -> None:
    settings.ensure_directories()
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()
