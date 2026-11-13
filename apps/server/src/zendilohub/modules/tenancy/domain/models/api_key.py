"""
An organization's API key: other systems call the organization's routes with it, with exactly the permissions it was
given. The key itself is shown once; only its SHA-256 is stored (it is long and random, so no slow hash is needed).
"""

import hashlib
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, get_args

from ..exceptions import InvalidApiKeyError

type KeyPermission = Literal[
    'members.view',
    'queues.manage',
    'queues.all',
    'tickets.delete',
    'customers.view',
    'customers.manage',
    'audit.view',
]
"""
What a key can be given: the permissions of the routes other systems may call. Never what needs a person (the
organization itself, the team, the keys). Keys have no groups: with `queues.all` they work in every queue with every
right, without it they see no tickets.
"""

KEY_PERMISSIONS: tuple[KeyPermission, ...] = get_args(KeyPermission.__value__)
PREFIX = 'zhk_'
API_KEYS_MAX = 20
NAME_MAX = 80
SHOWN = 10
"""The characters of a key the list shows to tell keys apart (`zhk_` and seven more)."""
TOUCH_EVERY = timedelta(minutes=1)
"""`last_used_at` is written at most this often per key, not on every request."""


def new_key() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_of(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def looks_like_key(token: str) -> bool:
    return token.startswith(PREFIX) and len(token) <= 100


def checked_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > NAME_MAX:
        raise InvalidApiKeyError('name')
    return name


def checked_permissions(permissions: Iterable[str]) -> tuple[KeyPermission, ...]:
    """At least one, each of them one a key can be given; in the order of `KEY_PERMISSIONS`, without repeats."""
    wanted = set(permissions)
    if not wanted or not wanted.issubset(KEY_PERMISSIONS):
        raise InvalidApiKeyError('permissions')
    return tuple(permission for permission in KEY_PERMISSIONS if permission in wanted)


@dataclass(frozen=True, kw_only=True)
class ApiKey:
    id: str
    tenant_id: str
    name: str
    permissions: tuple[KeyPermission, ...]
    start: str
    """The first characters of the key, e.g. `zhk_Ab3dE7f`."""
    created_by: str
    created_at: datetime
    last_used_at: datetime | None = None

    def due_for_touch(self, now: datetime) -> bool:
        return self.last_used_at is None or now - self.last_used_at >= TOUCH_EVERY
