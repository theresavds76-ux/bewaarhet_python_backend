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


def is_not_found_error(exc: Exception) -> bool:
    error = getattr(exc, 'error', None)

    if error is not None and hasattr(error, 'is_path') and error.is_path():
        path_error = error.get_path()
        if hasattr(path_error, 'is_not_found') and path_error.is_not_found():
            return True

    if error is not None and hasattr(error, 'is_not_found') and error.is_not_found():
        return True

    return 'not_found' in str(exc).lower()


def path_exists(path: str) -> bool:
    dbx = client()
    try:
        dbx.files_get_metadata(path)
        return True
    except Exception as exc:
        if is_not_found_error(exc):
            return False
        raise
