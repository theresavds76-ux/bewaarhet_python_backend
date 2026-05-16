from __future__ import annotations

import time
import traceback

from .config import settings
from .database import init_db
from .mail_client import fetch_unseen, mark_as_seen
from .processor import process_mail


def run_once() -> None:
    init_db()

    mails = fetch_unseen()
    print(f'Aantal ongelezen mails: {len(mails)}')

    for mail in mails:
        try:
            print('-' * 40)
            print(f'Van: {mail.from_email}')
            print(f'Onderwerp: {mail.subject}')

            process_mail(mail)

            mark_as_seen(mail.uid)

            print(f'Verwerkt: {mail.from_email} | {mail.subject}')

        except Exception as exc:
            print(f'FOUT bij mail {mail.uid}: {exc}')
            traceback.print_exc()


def run_forever() -> None:
    print('Bewaarhet worker gestart.')

    while True:
        run_once()
        print(f'Wachten {settings.poll_seconds} seconden...\n')
        time.sleep(settings.poll_seconds)


if __name__ == '__main__':
    run_forever()