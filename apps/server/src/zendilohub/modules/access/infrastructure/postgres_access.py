from collections.abc import Mapping, Sequence
from typing import Any

from zendilohub.core.database.database import Database
from zendilohub.core.domain.queue_rights import QueueRight, ordered

from ..domain.models.grant import Grant
from ..domain.models.group import Group
from ..domain.models.queue import Queue


def _queue(row: dict[str, Any]) -> Queue:
    return Queue(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        description=row['description'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


def _group(row: dict[str, Any]) -> Group:
    return Group(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        description=row['description'],
        member_ids=frozenset(str(each) for each in row['member_ids'] or ()),
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


GROUP_SELECT = """
    SELECT g.*, ARRAY(SELECT m.user_id FROM group_members m WHERE m.group_id = g.id ORDER BY m.user_id) AS member_ids
    FROM groups g
"""


class PostgresQueueRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def of_tenant(self, tenant_id: str) -> Sequence[Queue]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    'SELECT * FROM queues WHERE tenant_id = %s ORDER BY lower(name), id', (tenant_id,)
                )
            ).fetchall()
        return [_queue(row) for row in rows]

    async def find(self, tenant_id: str, queue_id: str) -> Queue | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute('SELECT * FROM queues WHERE tenant_id = %s AND id = %s', (tenant_id, queue_id))
            ).fetchone()
        return _queue(row) if row else None

    async def count(self, tenant_id: str) -> int:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute('SELECT count(*) AS n FROM queues WHERE tenant_id = %s', (tenant_id,))
            ).fetchone()
        return int(row['n']) if row else 0

    async def name_taken(self, tenant_id: str, name: str, *, except_id: str | None = None) -> bool:
        return await _name_taken(self._db, 'queues', tenant_id, name, except_id)

    async def save(self, queue: Queue) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO queues (id, tenant_id, name, description, created_at, updated_at)
                VALUES (%(id)s, %(tenant_id)s, %(name)s, %(description)s, %(created_at)s, %(updated_at)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, description = EXCLUDED.description, updated_at = EXCLUDED.updated_at
                """,
                vars(queue),
            )

    async def delete(self, tenant_id: str, queue_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM queues WHERE tenant_id = %s AND id = %s', (tenant_id, queue_id))


class PostgresGroupRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def of_tenant(self, tenant_id: str) -> Sequence[Group]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    f'{GROUP_SELECT} WHERE g.tenant_id = %s ORDER BY lower(g.name), g.id'.encode(), (tenant_id,)
                )
            ).fetchall()
        return [_group(row) for row in rows]

    async def find(self, tenant_id: str, group_id: str) -> Group | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute(
                    f'{GROUP_SELECT} WHERE g.tenant_id = %s AND g.id = %s'.encode(), (tenant_id, group_id)
                )
            ).fetchone()
        return _group(row) if row else None

    async def count(self, tenant_id: str) -> int:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute('SELECT count(*) AS n FROM groups WHERE tenant_id = %s', (tenant_id,))
            ).fetchone()
        return int(row['n']) if row else 0

    async def name_taken(self, tenant_id: str, name: str, *, except_id: str | None = None) -> bool:
        return await _name_taken(self._db, 'groups', tenant_id, name, except_id)

    async def save(self, group: Group) -> None:
        async with self._db.transaction(), self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO groups (id, tenant_id, name, description, created_at, updated_at)
                VALUES (%(id)s, %(tenant_id)s, %(name)s, %(description)s, %(created_at)s, %(updated_at)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name, description = EXCLUDED.description, updated_at = EXCLUDED.updated_at
                """,
                {key: value for key, value in vars(group).items() if key != 'member_ids'},
            )
            members = sorted(group.member_ids)
            await connection.execute(
                'DELETE FROM group_members WHERE group_id = %s AND NOT (user_id = ANY(%s::uuid[]))', (group.id, members)
            )
            await connection.execute(
                """
                INSERT INTO group_members (group_id, user_id)
                SELECT %s, member FROM unnest(%s::uuid[]) AS member
                ON CONFLICT DO NOTHING
                """,
                (group.id, members),
            )

    async def delete(self, tenant_id: str, group_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM groups WHERE tenant_id = %s AND id = %s', (tenant_id, group_id))

    async def remove_member(self, tenant_id: str, user_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                DELETE FROM group_members m USING groups g
                WHERE g.id = m.group_id AND g.tenant_id = %s AND m.user_id = %s
                """,
                (tenant_id, user_id),
            )

    async def remove_user(self, user_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM group_members WHERE user_id = %s', (user_id,))


class PostgresGrantRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def of_tenant(self, tenant_id: str) -> Sequence[Grant]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT r.group_id, r.queue_id, r.rights FROM queue_grants r
                    JOIN queues q ON q.id = r.queue_id
                    WHERE q.tenant_id = %s ORDER BY r.group_id, r.queue_id
                    """,
                    (tenant_id,),
                )
            ).fetchall()
        return [
            Grant(group_id=str(row['group_id']), queue_id=str(row['queue_id']), rights=ordered(row['rights']))
            for row in rows
        ]

    async def set(self, tenant_id: str, grant: Grant) -> None:
        async with self._db.connection() as connection:
            if not grant.rights:
                await connection.execute(
                    'DELETE FROM queue_grants WHERE group_id = %s AND queue_id = %s', (grant.group_id, grant.queue_id)
                )
                return
            await connection.execute(
                """
                INSERT INTO queue_grants (group_id, queue_id, rights) VALUES (%s, %s, %s)
                ON CONFLICT (group_id, queue_id) DO UPDATE SET rights = EXCLUDED.rights
                """,
                (grant.group_id, grant.queue_id, list(grant.rights)),
            )

    async def of_user(self, tenant_id: str, user_id: str) -> Mapping[str, frozenset[QueueRight]]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT r.queue_id, array_agg(DISTINCT right_name) AS rights
                    FROM queue_grants r
                    JOIN group_members m ON m.group_id = r.group_id
                    JOIN queues q ON q.id = r.queue_id
                    CROSS JOIN LATERAL unnest(r.rights) AS right_name
                    WHERE q.tenant_id = %s AND m.user_id = %s
                    GROUP BY r.queue_id
                    """,
                    (tenant_id, user_id),
                )
            ).fetchall()
        return {str(row['queue_id']): frozenset(ordered(row['rights'])) for row in rows}

    async def people_with(self, tenant_id: str, queue_id: str, right: QueueRight) -> frozenset[str]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT DISTINCT m.user_id
                    FROM queue_grants r
                    JOIN group_members m ON m.group_id = r.group_id
                    JOIN queues q ON q.id = r.queue_id
                    WHERE q.tenant_id = %s AND r.queue_id = %s AND %s = ANY(r.rights)
                    """,
                    (tenant_id, queue_id, right),
                )
            ).fetchall()
        return frozenset(str(row['user_id']) for row in rows)


class PostgresTenantData:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def forget(self, tenant_id: str) -> None:
        async with self._db.connection() as connection:
            # Grants and members go with their queues and groups (foreign keys).
            await connection.execute('DELETE FROM queues WHERE tenant_id = %s', (tenant_id,))
            await connection.execute('DELETE FROM groups WHERE tenant_id = %s', (tenant_id,))


async def _name_taken(db: Database, table: str, tenant_id: str, name: str, except_id: str | None) -> bool:
    async with db.connection() as connection:
        row = await (
            await connection.execute(
                f"""
                SELECT EXISTS (
                    SELECT 1 FROM {table}
                    WHERE tenant_id = %s AND lower(name) = lower(%s) AND (%s::uuid IS NULL OR id <> %s::uuid)
                ) AS taken
                """.encode(),
                (tenant_id, name, except_id, except_id),
            )
        ).fetchone()
    return bool(row and row['taken'])
