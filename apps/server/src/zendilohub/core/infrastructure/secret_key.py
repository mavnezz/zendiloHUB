import os
import secrets
from functools import cached_property
from pathlib import Path


class SecretKey:
    """
    The app's secret: ZENDILOHUB_SECRET_KEY, or a random key generated once into the data directory
    (shared by every process that mounts it). Loaded on first use, so commands like `openapi` need no data.
    """

    def __init__(self, configured: str | None, data_dir: Path) -> None:
        self._configured = configured
        self._file = data_dir / 'secret_key'

    @cached_property
    def value(self) -> bytes:
        if self._configured:
            return self._configured.encode()
        try:
            return self._file.read_bytes().strip()
        except FileNotFoundError:
            pass
        self._file.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32).encode()
        try:
            # Exclusive create: of two processes starting at once, one writes and both read its key.
            descriptor = os.open(self._file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return self._file.read_bytes().strip()
        with os.fdopen(descriptor, 'wb') as file:
            file.write(key)
        return key
