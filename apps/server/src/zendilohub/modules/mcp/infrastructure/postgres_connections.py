from collections.abc import Sequence
from datetime import datetime
from typing import Any

from zendilohub.core.contracts import Contracts
from zendilohub.core.database.database import Database
from zendilohub.core.domain.permissions import Permission

from ..domain.models.connection import Connection


def _connection(row: dict[str, Any]) -> Connection:
    return Connection(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        user_id=str(row['user_id']),
        email=row['email'],
        name=row['name'],
        token_hash=row['token_hash'],
        start=row['start'],
        created_at=row['created_at'],
        last_used_at=row['last_used_at'],
    )


class PostgresConnectionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _run(self, sql: str, params: Any) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            cursor = await connection.execute(sql.encode(), params)
            return list(await cursor.fetchall()) if cursor.description else []

    async def of_member(self, tenant_id: str, user_id: str) -> Sequence[Connection]:
        rows = await self._run(
            'SELECT * FROM mcp_connections WHERE tenant_id = %s AND user_id = %s ORDER BY created_at, id',
            (tenant_id, user_id),
        )
        return [_connection(row) for row in rows]

    async def find_by_hash(self, token_hash: str) -> Connection | None:
        rows = await self._run('SELECT * FROM mcp_connections WHERE token_hash = %s', (token_hash,))
        return _connection(rows[0]) if rows else None

    async def save(self, connection: Connection) -> None:
        await self._run(
            """
            INSERT INTO mcp_connections (id, tenant_id, user_id, email, name, token_hash, start, created_at,
                                         last_used_at)
            VALUES (%(id)s, %(tenant_id)s, %(user_id)s, %(email)s, %(name)s, %(token_hash)s, %(start)s,
                    %(created_at)s, %(last_used_at)s)
            """,
            vars(connection),
        )

    async def touch(self, connection_id: str, at: datetime) -> None:
        await self._run('UPDATE mcp_connections SET last_used_at = %s WHERE id = %s', (at, connection_id))

    async def delete(self, tenant_id: str, user_id: str, connection_id: str) -> bool:
        rows = await self._run(
            'DELETE FROM mcp_connections WHERE tenant_id = %s AND user_id = %s AND id = %s RETURNING id',
            (tenant_id, user_id, connection_id),
        )
        return bool(rows)

    async def forget(self, tenant_id: str | None, user_id: str | None) -> None:
        await self._run(
            """
            DELETE FROM mcp_connections
            WHERE (%(tenant)s::uuid IS NULL OR tenant_id = %(tenant)s::uuid)
              AND (%(user)s::uuid IS NULL OR user_id = %(user)s::uuid)
            """,
            {'tenant': tenant_id, 'user': user_id},
        )


class ContractMembers:
    """`Members` through tenancy's `Memberships` contract."""

    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def permissions_of(self, tenant_id: str, user_id: str) -> frozenset[Permission] | None:
        for member in await self._contracts.memberships.get().members(tenant_id):
            if member.user_id == user_id:
                return member.permissions
        return None
