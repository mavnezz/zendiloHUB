from datetime import datetime
from typing import Any

from zendilohub.core.database.database import Database

from ..domain.models.audit_entry import AuditEntry
from ..domain.ports.audit_repository import AuditPage


def _entry(row: dict[str, Any]) -> AuditEntry:
    return AuditEntry(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']) if row['tenant_id'] else None,
        actor_id=str(row['actor_id']) if row['actor_id'] else None,
        actor_email=row['actor_email'],
        action=row['action'],
        target=row['target'],
        succeeded=row['succeeded'],
        status=row['status'],
        client=row['client'],
        created_at=row['created_at'],
    )


class PostgresAuditRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, entry: AuditEntry) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO audit_log (id, tenant_id, actor_id, actor_email, action, target, succeeded, status, client,
                                       created_at)
                VALUES (%(id)s, %(tenant_id)s, %(actor_id)s, %(actor_email)s, %(action)s, %(target)s, %(succeeded)s,
                        %(status)s, %(client)s, %(created_at)s)
                """,
                vars(entry),
            )

    async def page(self, *, tenant_id: str | None, offset: int, limit: int) -> AuditPage:
        where = 'WHERE tenant_id = %(tenant_id)s' if tenant_id else ''
        params = {'tenant_id': tenant_id, 'offset': offset, 'limit': limit}
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    f'SELECT * FROM audit_log {where} ORDER BY created_at DESC, id DESC OFFSET %(offset)s LIMIT %(limit)s'.encode(),
                    params,
                )
            ).fetchall()
            total = await (
                await connection.execute(f'SELECT count(*) AS n FROM audit_log {where}'.encode(), params)
            ).fetchone()
        return AuditPage([_entry(row) for row in rows], int(total['n']) if total else 0)

    async def delete_before(self, moment: datetime) -> int:
        async with self._db.connection() as connection:
            cursor = await connection.execute('DELETE FROM audit_log WHERE created_at < %s', (moment,))
        return cursor.rowcount

    async def delete_for_tenant(self, tenant_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM audit_log WHERE tenant_id = %s', (tenant_id,))

    async def forget_actor(self, user_id: str, email: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                'UPDATE audit_log SET actor_email = NULL WHERE actor_id = %s OR actor_email = %s', (user_id, email)
            )
