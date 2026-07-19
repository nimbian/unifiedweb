"""Google Drive slideshow service (ports the /CS feature from app.py).

Lists image metadata from a Drive folder and streams individual images through
the API so the browser never needs Drive credentials. The service-account file
path comes from settings (was hard-coded ``gc.json`` / env in the Flask app).
"""

import io
from collections.abc import Iterator
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.drive import DriveImage

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


@lru_cache
def _drive_client():
    # Imported lazily so the rest of the API (and the test suite) does not require
    # the Google client libraries unless the slideshow feature is actually used.
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class DriveService:
    def list_images(self) -> list[DriveImage]:
        service = _drive_client()
        query = f"'{settings.google_drive_folder_id}' in parents and trashed = false"
        results = (
            service.files()
            .list(
                q=query,
                fields="files(id, name, mimeType)",
                orderBy="name",
                pageSize=200,
                # Required for the folder to resolve when it lives in a Shared
                # Drive; harmless for ordinary My Drive folders.
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return [DriveImage(id=f["id"], name=f["name"]) for f in results.get("files", [])]

    def stream_image(self, file_id: str) -> tuple[Iterator[bytes], str]:
        """Return (chunked byte iterator, mime type) for a Drive file."""
        from googleapiclient.http import MediaIoBaseDownload

        service = _drive_client()
        meta = (
            service.files()
            .get(fileId=file_id, fields="mimeType,name", supportsAllDrives=True)
            .execute()
        )
        mime = meta.get("mimeType", "image/jpeg")

        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)

        def _iter() -> Iterator[bytes]:
            while chunk := buf.read(64 * 1024):
                yield chunk

        return _iter(), mime
