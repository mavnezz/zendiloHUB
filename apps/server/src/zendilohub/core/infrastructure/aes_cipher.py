import os
from collections.abc import Callable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

FORMAT = b'\x01'
"""The first byte of everything sealed: AES-256-GCM, 12-byte nonce (room for another scheme later)."""


class AesGcmCipher:
    """
    AES-256-GCM with a key derived from the app's secret. A new ZENDILOHUB_SECRET_KEY makes sealed values unreadable:
    the organizations enter them again.
    """

    def __init__(self, secret: Callable[[], bytes]) -> None:
        self._secret = secret

    def _aead(self) -> AESGCM:
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'zendilohub-sealed-values').derive(
            self._secret()
        )
        return AESGCM(key)

    def seal(self, plain: str, *, context: str) -> bytes:
        nonce = os.urandom(12)
        return FORMAT + nonce + self._aead().encrypt(nonce, plain.encode(), context.encode())

    def open(self, sealed: bytes, *, context: str) -> str | None:
        if not sealed.startswith(FORMAT) or len(sealed) < 1 + 12 + 16:
            return None
        try:
            return self._aead().decrypt(sealed[1:13], sealed[13:], context.encode()).decode()
        except InvalidTag:
            return None
