from collections.abc import Sequence
from typing import Any

from zendilohub.core.database.database import Database

from ..domain.models.text_module import TextModule


def _module(row: dict[str, Any]) -> TextModule:
    return TextModule(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        keyword=row['keyword'],
        body=row['body'],
        queue_ids=tuple(str(each) for each in row['queue_ids']),
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


class PostgresTextModuleRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _run(self, sql: str, params: Any) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            cursor = await connection.execute(sql.encode(), params)
            return list(await cursor.fetchall()) if cursor.description else []

    async def of_tenant(self, tenant_id: str) -> Sequence[TextModule]:
        rows = await self._run('SELECT * FROM text_modules WHERE tenant_id = %s ORDER BY keyword', (tenant_id,))
        return [_module(row) for row in rows]

    async def find(self, tenant_id: str, module_id: str) -> TextModule | None:
        rows = await self._run('SELECT * FROM text_modules WHERE tenant_id = %s AND id = %s', (tenant_id, module_id))
        return _module(rows[0]) if rows else None

    async def save(self, module: TextModule) -> None:
        await self._run(
            """
            INSERT INTO text_modules (id, tenant_id, name, keyword, body, queue_ids, created_at, updated_at)
            VALUES (%(id)s, %(tenant_id)s, %(name)s, %(keyword)s, %(body)s, %(queue_ids)s::uuid[], %(created_at)s,
                    %(updated_at)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                keyword = EXCLUDED.keyword,
                body = EXCLUDED.body,
                queue_ids = EXCLUDED.queue_ids,
                updated_at = EXCLUDED.updated_at
            """,
            vars(module) | {'queue_ids': list(module.queue_ids)},
        )

    async def delete(self, tenant_id: str, module_id: str) -> None:
        await self._run('DELETE FROM text_modules WHERE tenant_id = %s AND id = %s', (tenant_id, module_id))

    async def forget_queue(self, tenant_id: str, queue_id: str) -> None:
        await self._run(
            'UPDATE text_modules SET queue_ids = array_remove(queue_ids, %s::uuid) WHERE tenant_id = %s',
            (queue_id, tenant_id),
        )

    async def forget_tenant(self, tenant_id: str) -> None:
        await self._run('DELETE FROM text_modules WHERE tenant_id = %s', (tenant_id,))
        await self._run('DELETE FROM knowledge_articles WHERE tenant_id = %s', (tenant_id,))
