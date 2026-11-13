from collections.abc import Sequence
from typing import Any, cast

from zendilohub.core.database.database import Database
from zendilohub.core.domain.permissions import Permission, ordered

from ..domain.models.role import CustomRole


def _role(row: dict[str, Any]) -> CustomRole:
    return CustomRole(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        description=row['description'],
        permissions=frozenset(cast(list[Permission], row['permissions'])),
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


class PostgresRoleRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, tenant_id: str, role_id: str) -> CustomRole | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute('SELECT * FROM roles WHERE tenant_id = %s AND id = %s', (tenant_id, role_id))
            ).fetchone()
        return _role(row) if row else None

    async def of_tenant(self, tenant_id: str) -> Sequence[CustomRole]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    'SELECT * FROM roles WHERE tenant_id = %s ORDER BY lower(name), id', (tenant_id,)
                )
            ).fetchall()
        return [_role(row) for row in rows]

    async def count(self, tenant_id: str) -> int:
        return await self._number('SELECT count(*) AS n FROM roles WHERE tenant_id = %s', (tenant_id,))

    async def name_taken(self, tenant_id: str, name: str, *, except_id: str | None = None) -> bool:
        return (
            await self._number(
                """
                SELECT count(*) AS n FROM roles
                WHERE tenant_id = %s AND lower(name) = lower(%s) AND id::text <> coalesce(%s, '')
                """,
                (tenant_id, name, except_id),
            )
            > 0
        )

    async def in_use(self, tenant_id: str, role_id: str) -> bool:
        return (
            await self._number(
                """
                SELECT (SELECT count(*) FROM memberships WHERE tenant_id = %(t)s AND role = %(r)s)
                     + (SELECT count(*) FROM invitations WHERE tenant_id = %(t)s AND role = %(r)s) AS n
                """,
                {'t': tenant_id, 'r': role_id},
            )
            > 0
        )

    async def usage(self, tenant_id: str) -> dict[str, int]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    'SELECT role, count(*) AS n FROM memberships WHERE tenant_id = %s GROUP BY role', (tenant_id,)
                )
            ).fetchall()
        return {row['role']: int(row['n']) for row in rows}

    async def save(self, role: CustomRole) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO roles (id, tenant_id, name, description, permissions, created_at, updated_at)
                VALUES (%(id)s, %(tenant_id)s, %(name)s, %(description)s, %(permissions)s, %(created_at)s,
                        %(updated_at)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    permissions = EXCLUDED.permissions,
                    updated_at = EXCLUDED.updated_at
                """,
                {**vars(role), 'permissions': ordered(role.permissions)},
            )

    async def delete(self, tenant_id: str, role_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM roles WHERE tenant_id = %s AND id = %s', (tenant_id, role_id))

    async def _number(self, sql: str, params: Any) -> int:
        async with self._db.connection() as connection:
            row = await (await connection.execute(sql.encode(), params)).fetchone()
        return int(row['n']) if row else 0
