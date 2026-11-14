import asyncio
import contextlib
import os
import re
import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class DiskFileStore:
    """Files under `<root>/<tenant>/<id>`; both parts are UUIDs, so no name from outside reaches the path."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, tenant_id: str, file_id: str) -> Path:
        if not (_UUID.match(tenant_id) and _UUID.match(file_id)):
            raise ValueError('Files are kept by UUIDs')
        return self._root / tenant_id / file_id

    async def put(self, tenant_id: str, file_id: str, content: bytes) -> None:
        await asyncio.to_thread(self._put, self._path(tenant_id, file_id), content)

    @staticmethod
    def _put(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written next to its place and renamed: a reader never sees half a file.
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.upload-')
        try:
            with os.fdopen(handle, 'wb') as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
            raise

    async def get(self, tenant_id: str, file_id: str) -> bytes | None:
        path = self._path(tenant_id, file_id)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            return None

    async def delete(self, tenant_id: str, file_id: str) -> None:
        path = self._path(tenant_id, file_id)
        await asyncio.to_thread(path.unlink, True)

    def stored(self, older_than: datetime) -> Iterable[tuple[str, str]]:
        if not self._root.is_dir():
            return
        limit = older_than.timestamp()
        for tenant in self._root.iterdir():
            if not (tenant.is_dir() and _UUID.match(tenant.name)):
                continue
            for file in tenant.iterdir():
                with contextlib.suppress(FileNotFoundError):
                    if _UUID.match(file.name) and file.stat().st_mtime < limit:
                        yield tenant.name, file.name
