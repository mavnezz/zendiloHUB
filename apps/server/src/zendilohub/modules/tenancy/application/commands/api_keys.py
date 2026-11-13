from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator
from zendilohub.core.domain.rate_limited import TooManyRequestsError
from zendilohub.core.domain.rate_limiter import RateLimit, RateLimiter

from ...domain.exceptions import ApiKeyLimitError, ApiKeyNotFoundError
from ...domain.models.api_key import (
    API_KEYS_MAX,
    SHOWN,
    ApiKey,
    checked_name,
    checked_permissions,
    hash_of,
    looks_like_key,
    new_key,
)
from ...domain.ports.repositories import ApiKeyRepository

REQUESTS = RateLimit('tenancy.api-key-requests', limit=600, window_seconds=60)
"""Requests per API key and minute."""


@dataclass(frozen=True)
class CreatedApiKey:
    key: ApiKey
    secret: str = field(repr=False)
    """The key itself: shown this once."""


@dataclass(frozen=True)
class CreateApiKey(Command[CreatedApiKey]):
    tenant_id: str
    name: str
    permissions: tuple[str, ...]
    created_by: str


class CreateApiKeyHandler:
    def __init__(self, keys: ApiKeyRepository, ids: IdGenerator, clock: Clock) -> None:
        self._keys = keys
        self._ids = ids
        self._clock = clock

    async def handle(self, command: CreateApiKey) -> CreatedApiKey:
        name, permissions = checked_name(command.name), checked_permissions(command.permissions)
        if await self._keys.count(command.tenant_id) >= API_KEYS_MAX:
            raise ApiKeyLimitError(API_KEYS_MAX)
        secret = new_key()
        key = ApiKey(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            name=name,
            permissions=permissions,
            start=secret[:SHOWN],
            created_by=command.created_by,
            created_at=self._clock.now(),
        )
        await self._keys.add(key, hash_of(secret))
        return CreatedApiKey(key, secret)


@dataclass(frozen=True)
class UpdateApiKey(Command[ApiKey]):
    """Another name or other permissions; the key itself stays the same and works on with them at once."""

    tenant_id: str
    key_id: str
    name: str
    permissions: tuple[str, ...]


class UpdateApiKeyHandler:
    def __init__(self, keys: ApiKeyRepository) -> None:
        self._keys = keys

    async def handle(self, command: UpdateApiKey) -> ApiKey:
        name, permissions = checked_name(command.name), checked_permissions(command.permissions)
        key = await self._keys.get(command.tenant_id, command.key_id)
        if key is None:
            raise ApiKeyNotFoundError()
        changed = replace(key, name=name, permissions=permissions)
        await self._keys.update(changed)
        return changed


@dataclass(frozen=True)
class DeleteApiKey(Command[None]):
    """The key stops working at once."""

    tenant_id: str
    key_id: str


class DeleteApiKeyHandler:
    def __init__(self, keys: ApiKeyRepository) -> None:
        self._keys = keys

    async def handle(self, command: DeleteApiKey) -> None:
        if not await self._keys.delete(command.tenant_id, command.key_id):
            raise ApiKeyNotFoundError()


@dataclass(frozen=True)
class ListApiKeys(Query[Sequence[ApiKey]]):
    tenant_id: str


class ListApiKeysHandler:
    def __init__(self, keys: ApiKeyRepository) -> None:
        self._keys = keys

    async def handle(self, query: ListApiKeys) -> Sequence[ApiKey]:
        return await self._keys.keys(query.tenant_id)


@dataclass(frozen=True)
class UseApiKey(Command[ApiKey | None]):
    """A request shows a key: the key, if it is known and its organization active; counts against its rate limit."""

    secret: str = field(repr=False)


class UseApiKeyHandler:
    def __init__(self, keys: ApiKeyRepository, limiter: RateLimiter, clock: Clock) -> None:
        self._keys = keys
        self._limiter = limiter
        self._clock = clock

    async def handle(self, command: UseApiKey) -> ApiKey | None:
        if not looks_like_key(command.secret):
            return None
        key = await self._keys.active_by_hash(hash_of(command.secret))
        if key is None:
            return None
        status = await self._limiter.hit(REQUESTS, key.id)
        if not status.allowed:
            raise TooManyRequestsError(status.retry_after)
        now = self._clock.now()
        if key.due_for_touch(now):
            await self._keys.touch(key.id, now)
        return key
