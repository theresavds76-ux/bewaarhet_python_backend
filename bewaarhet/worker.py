from __future__ import annotations

import time
import traceback

from .config import settings
from .database import check_integrity, init_db
from .mail_client import fetch_unseen, mark_as_seen
from .processor import process_mail
from .utils import sanitize_for_log


def run_once() -> None:
    init_db()

    mails = fetch_unseen()
    print(f'Aantal ongelezen mails: {len(mails)}')

    for mail in mails:
        try:
            print('-' * 40)
            print(f'Van: {mail.from_email}')
            print(f'Onderwerp: {sanitize_for_log(mail.subject)}')

            handled = process_mail(mail)

            if not handled:
                print('Mail buiten Bewaarhet-scope overgeslagen; niet gemarkeerd als gelezen.')
                continue

            mark_as_seen(mail.uid)

            print(f'Verwerkt: {mail.from_email} | {sanitize_for_log(mail.subject)}')

        except Exception as exc:
            print(f'FOUT bij mail {mail.uid}: {sanitize_for_log(exc)}')
            print(sanitize_for_log(traceback.format_exc()), end='')


def startup_diagnostics() -> None:
    print('Bewaarhet worker startup diagnostics.')
    print(f'Database path: {sanitize_for_log(settings.database_path)}')
    print(f'Backup folder: {sanitize_for_log(settings.backup_dir)}')
    print(f'Log folder: {sanitize_for_log(settings.log_dir)}')

    try:
        settings.ensure_directories()
        print('Runtime folders ready.')
    except Exception as exc:
        print(f'FOUT bij runtime folders aanmaken: {sanitize_for_log(exc)}')
        raise

    init_db()
    ok, message = check_integrity()
    print(f'Database integrity check: {sanitize_for_log(message)}')
    if not ok:
        raise RuntimeError(f'Database integrity check failed: {message}')


def run_forever() -> None:
    print('Bewaarhet worker gestart.')
    startup_diagnostics()

    try:
        while True:
            run_once()
            print(f'Wachten {settings.poll_seconds} seconden...\n')
            time.sleep(settings.poll_seconds)
    except KeyboardInterrupt:
        print('Bewaarhet worker stopt op verzoek.')
    finally:
        print('Bewaarhet worker afgesloten.')


if __name__ == '__main__':
    run_forever()
