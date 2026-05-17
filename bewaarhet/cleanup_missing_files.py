from __future__ import annotations

from .database import all_documents, init_db, mark_missing_file
from .dropbox_client import path_exists


def main() -> None:
    init_db()

    checked = 0
    missing = 0
    valid = 0

    for row in all_documents():
        checked += 1
        if path_exists(row['dropbox_path']):
            valid += 1
            continue

        mark_missing_file(row['id'])
        missing += 1

    print(f"checked: {checked}")
    print(f"missing: {missing}")
    print(f"valid: {valid}")


if __name__ == '__main__':
    main()
