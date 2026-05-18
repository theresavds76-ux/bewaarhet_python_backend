from __future__ import annotations

import time
import traceback

from .config import settings
from .database import init_db
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

            process_mail(mail)

            mark_as_seen(mail.uid)

            print(f'Verwerkt: {mail.from_email} | {sanitize_for_log(mail.subject)}')

        except Exception as exc:
            print(f'FOUT bij mail {mail.uid}: {sanitize_for_log(exc)}')
            print(sanitize_for_log(traceback.format_exc()), end='')


def run_forever() -> None:
    print('Bewaarhet worker gestart.')

    while True:
        run_once()
        print(f'Wachten {settings.poll_seconds} seconden...\n')
        time.sleep(settings.poll_seconds)


if __name__ == '__main__':
    run_forever()
