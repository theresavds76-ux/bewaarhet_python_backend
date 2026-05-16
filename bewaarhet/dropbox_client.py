from __future__ import annotations

import dropbox
from dropbox.files import WriteMode

from .config import settings


def client() -> dropbox.Dropbox:
    return dropbox.Dropbox(
        oauth2_refresh_token=settings.dropbox_refresh_token,
        app_key=settings.dropbox_app_key,
        app_secret=settings.dropbox_app_secret,
    )


def upload_file(data: bytes, path: str) -> str:
    dbx = client()
    dbx.files_upload(data, path, mode=WriteMode.overwrite, autorename=False)
    return path


def temporary_link(path: str) -> str:
    dbx = client()
    return dbx.files_get_temporary_link(path).link