import hashlib
import secrets
from collections.abc import Sequence
from dataclasses import dataclass

from zendilohub.core.bus.message import Command, Query
from zendilohub.core.domain.assistant_access import AssistantAccess
from zendilohub.core.domain.clock import Clock
from zendilohub.core.domain.id_generator import IdGenerator

from ...domain.models.connection import (
    CONNECTIONS_MAX,
    PREFIX,
    Connection,
    ConnectionNotFoundError,
    InvalidConnectionError,
)
from ...domain.ports.repositories import ConnectionRepository, Members


def hash_of(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class NewConnection:
    connection: Connection
    token: str
    """Shown this once."""


@dataclass(frozen=True, kw_only=True)
class Connect(Command[NewConnection]):
    tenant_id: str
    user_id: str
    email: str
    name: str


class ConnectHandler:
    def __init__(self, connections: ConnectionRepository, ids: IdGenerator, clock: Clock) -> None:
        self._connections = connections
        self._ids = ids
        self._clock = clock

    async def handle(self, command: Connect) -> NewConnection:
        if len(await self._connections.of_member(command.tenant_id, command.user_id)) >= CONNECTIONS_MAX:
            raise InvalidConnectionError('limit')
        token = PREFIX + secrets.token_urlsafe(32)
        connection = Connection(
            id=self._ids.new_id(),
            tenant_id=command.tenant_id,
            user_id=command.user_id,
            email=command.email,
            name=command.name,
            token_hash=hash_of(token),
            start=token[:11],
            created_at=self._clock.now(),
        )
        connection.check()
        await self._connections.save(connection)
        return NewConnection(connection, token)


@dataclass(frozen=True, kw_only=True)
class Disconnect(Command[None]):
    tenant_id: str
    user_id: str
    connection_id: str


class DisconnectHandler:
    def __init__(self, connections: ConnectionRepository) -> None:
        self._connections = connections

    async def handle(self, command: Disconnect) -> None:
        if not await self._connections.delete(command.tenant_id, command.user_id, command.connection_id):
            raise ConnectionNotFoundError()


@dataclass(frozen=True, kw_only=True)
class ListConnections(Query[Sequence[Connection]]):
    tenant_id: str
    user_id: str


class ListConnectionsHandler:
    def __init__(self, connections: ConnectionRepository) -> None:
        self._connections = connections

    async def handle(self, query: ListConnections) -> Sequence[Connection]:
        return await self._connections.of_member(query.tenant_id, query.user_id)


@dataclass(frozen=True)
class Authenticate(Command[AssistantAccess | None]):
    """The access a token gives now: none for unknown tokens and members who left."""

    token: str


class AuthenticateHandler:
    def __init__(self, connections: ConnectionRepository, members: Members, clock: Clock) -> None:
        self._connections = connections
        self._members = members
        self._clock = clock

    async def handle(self, command: Authenticate) -> AssistantAccess | None:
        if not command.token.startswith(PREFIX) or len(command.token) > 200:
            return None
        connection = await self._connections.find_by_hash(hash_of(command.token))
        if connection is None:
            return None
        permissions = await self._members.permissions_of(connection.tenant_id, connection.user_id)
        if permissions is None:
            return None
        now = self._clock.now()
        if connection.last_used_at is None or (now - connection.last_used_at).total_seconds() > 60:
            await self._connections.touch(connection.id, now)
        return AssistantAccess(
            connection_id=connection.id,
            tenant_id=connection.tenant_id,
            user_id=connection.user_id,
            email=connection.email,
            client_name=connection.name,
            permissions=permissions,
        )


@dataclass(frozen=True)
class Forget(Command[None]):
    tenant_id: str | None
    user_id: str | None


class ForgetHandler:
    def __init__(self, connections: ConnectionRepository) -> None:
        self._connections = connections

    async def handle(self, command: Forget) -> None:
        await self._connections.forget(command.tenant_id, command.user_id)
