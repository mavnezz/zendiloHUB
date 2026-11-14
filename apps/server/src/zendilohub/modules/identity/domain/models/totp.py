"""Time-based one-time passwords (RFC 6238) as authenticator apps make them: SHA-1, 6 digits, 30 seconds."""

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1
"""Codes of the step before and after count too: the clocks of phones drift."""
ISSUER = 'zendiloHUB'
RECOVERY_CODES = 10
_RECOVERY_ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'


def new_secret() -> str:
    """160 random bits in base32, the form authenticator apps read."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def step_at(now: datetime) -> int:
    return int(now.timestamp()) // STEP_SECONDS


def code_at(secret: str, step: int) -> str:
    key = base64.b32decode(secret + '=' * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack('>I', digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def is_code(text: str) -> bool:
    """Whether the text looks like a one-time password (six digits), not a recovery code."""
    digits = text.replace(' ', '')
    return len(digits) == DIGITS and digits.isascii() and digits.isdigit()


def matching_step(secret: str, code: str, now: datetime, *, after: int) -> int | None:
    """The step whose code this is (within the window), or None; steps up to `after` were used already."""
    code = code.replace(' ', '')
    if not is_code(code):
        return None
    current = step_at(now)
    for step in range(current - WINDOW, current + WINDOW + 1):
        if step > after and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, email: str) -> str:
    """The otpauth:// address of the QR code."""
    label = quote(f'{ISSUER}:{email}', safe=':@')
    return (
        f'otpauth://totp/{label}?secret={secret}&issuer={ISSUER}&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}'
    )


def new_recovery_codes() -> list[str]:
    def code() -> str:
        chars = ''.join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        return f'{chars[:4]}-{chars[4:]}'

    return [code() for _ in range(RECOVERY_CODES)]


def hash_recovery_code(code: str) -> str:
    """Recovery codes are stored hashed; spaces, dashes and case do not matter when typing them."""
    normalized = code.strip().lower().replace('-', '').replace(' ', '')
    return hashlib.sha256(normalized.encode()).hexdigest()
