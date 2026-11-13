from collections.abc import Sequence
from datetime import datetime
from typing import Any

from zendilohub.core.database.database import Database

from ..domain.models.api_key import KEY_PERMISSIONS, ApiKey

COLUMNS = 'k.id, k.tenant_id, k.name, k.permissions, k.start, k.created_by, k.created_at, k.last_used_at'


def _key(row: dict[str, Any]) -> ApiKey:
    return ApiKey(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        # Tolerant: a permission keys can no longer be given is dropped, not an error.
        permissions=tuple(permission for permission in KEY_PERMISSIONS if permission in row['permissions']),
        start=row['start'],
        created_by=str(row['created_by']),
        created_at=row['created_at'],
        last_used_at=row['last_used_at'],
    )


class PostgresApiKeyRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def keys(self, tenant_id: str) -> Sequence[ApiKey]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    f'SELECT {COLUMNS} FROM api_keys k WHERE k.tenant_id = %s ORDER BY k.created_at, k.id'.encode(),
                    (tenant_id,),
                )
            ).fetchall()
        return [_key(row) for row in rows]

    async def count(self, tenant_id: str) -> int:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute('SELECT count(*) AS n FROM api_keys WHERE tenant_id = %s', (tenant_id,))
            ).fetchone()
        return int(row['n']) if row else 0

    async def get(self, tenant_id: str, key_id: str) -> ApiKey | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute(
                    f'SELECT {COLUMNS} FROM api_keys k WHERE k.tenant_id = %s AND k.id = %s'.encode(),
                    (tenant_id, key_id),
                )
            ).fetchone()
        return _key(row) if row else None

    async def add(self, key: ApiKey, key_hash: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO api_keys (id, tenant_id, name, permissions, key_hash, start, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    key.id,
                    key.tenant_id,
                    key.name,
                    list(key.permissions),
                    key_hash,
                    key.start,
                    key.created_by,
                    key.created_at,
                ),
            )

    async def update(self, key: ApiKey) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                'UPDATE api_keys SET name = %s, permissions = %s WHERE tenant_id = %s AND id = %s',
                (key.name, list(key.permissions), key.tenant_id, key.id),
            )

    async def delete(self, tenant_id: str, key_id: str) -> bool:
        async with self._db.connection() as connection:
            cursor = await connection.execute(
                'DELETE FROM api_keys WHERE tenant_id = %s AND id = %s', (tenant_id, key_id)
            )
        return cursor.rowcount == 1

    async def active_by_hash(self, key_hash: str) -> ApiKey | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute(
                    f"""
                    SELECT {COLUMNS} FROM api_keys k JOIN tenants t ON t.id = k.tenant_id
                    WHERE k.key_hash = %s AND t.status = 'active'
                    """.encode(),
                    (key_hash,),
                )
            ).fetchone()
        return _key(row) if row else None

    async def touch(self, key_id: str, now: datetime) -> None:
        async with self._db.connection() as connection:
            await connection.execute('UPDATE api_keys SET last_used_at = %s WHERE id = %s', (now, key_id))
