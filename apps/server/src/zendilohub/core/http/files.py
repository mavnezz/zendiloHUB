"""Uploads and downloads of files (attachments) over HTTP."""

from urllib.parse import quote

from fastapi import UploadFile
from starlette.responses import Response

from ..domain.app_domain_error import TooLargeError
from ..domain.files import FileData

CHUNK = 1024 * 1024
INLINE_TYPES = frozenset({'image/png', 'image/jpeg', 'image/gif', 'image/webp'})
"""Shown in the browser; everything else downloads."""


class FileTooLargeError(TooLargeError):
    def __init__(self, max_bytes: int) -> None:
        max_mb = max_bytes // (1024 * 1024)
        super().__init__('attachment_too_large', f'A file may have at most {max_mb} MB', {'max_mb': max_mb})


async def read_upload(upload: UploadFile, max_bytes: int) -> FileData:
    """The whole file, read in chunks so nothing beyond the limit is kept."""
    parts: list[bytes] = []
    size = 0
    while chunk := await upload.read(CHUNK):
        size += len(chunk)
        if size > max_bytes:
            raise FileTooLargeError(max_bytes)
        parts.append(chunk)
    return FileData(
        filename=upload.filename or 'file',
        content_type=upload.content_type or 'application/octet-stream',
        content=b''.join(parts),
    )


def file_response(content: bytes, *, filename: str, content_type: str) -> Response:
    """
    A download that cannot run as part of the app: unknown types are octet-streams, only a few image types show
    inline, and a sandboxing policy stops scripts in anything the browser renders anyway.
    """
    inline = content_type in INLINE_TYPES
    ascii_name = filename.encode('ascii', 'replace').decode().replace('"', '_').replace('?', '_') or 'file'
    disposition = 'inline' if inline else 'attachment'
    return Response(
        content,
        media_type=content_type if inline else 'application/octet-stream',
        headers={
            'Content-Disposition': f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}',
            'Content-Security-Policy': "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox",
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'private, max-age=3600',
            'Cross-Origin-Resource-Policy': 'same-origin',
        },
    )
