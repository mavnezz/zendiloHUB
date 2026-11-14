from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from zendilohub.core.database.database import Database

from ..domain.models.notification import FollowedQueue, FollowMode, Notification, NotificationKind, Settings

KEEP = 500
"""Notifications kept per member; older ones go."""


class PostgresNotificationRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _run(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            cursor = await connection.execute(sql.encode(), params)
            return list(await cursor.fetchall()) if cursor.description else []

    async def add(self, notifications: Sequence[Notification]) -> None:
        for each in notifications:
            await self._run(
                """
                INSERT INTO notifications (id, tenant_id, user_id, kind, ticket_id, ticket_number, subject, actor,
                                           created_at, read_at)
                VALUES (%(id)s, %(tenant_id)s, %(user_id)s, %(kind)s, %(ticket_id)s, %(ticket_number)s, %(subject)s,
                        %(actor)s, %(created_at)s, %(read_at)s)
                """,
                vars(each),
            )
            await self._run(
                """
                DELETE FROM notifications WHERE id IN (
                    SELECT id FROM notifications WHERE tenant_id = %s AND user_id = %s
                    ORDER BY created_at DESC OFFSET %s)
                """,
                (each.tenant_id, each.user_id, KEEP),
            )

    async def of_user(self, tenant_id: str, user_id: str, *, unread: bool, limit: int) -> Sequence[Notification]:
        rows = await self._run(
            f"""
            SELECT * FROM notifications WHERE tenant_id = %s AND user_id = %s {'AND read_at IS NULL' if unread else ''}
            ORDER BY created_at DESC, id DESC LIMIT %s
            """,
            (tenant_id, user_id, limit),
        )
        return [
            Notification(
                id=str(row['id']),
                tenant_id=str(row['tenant_id']),
                user_id=str(row['user_id']),
                kind=cast(NotificationKind, row['kind']),
                ticket_id=str(row['ticket_id']),
                ticket_number=int(row['ticket_number']),
                subject=row['subject'],
                actor=row['actor'],
                created_at=row['created_at'],
                read_at=row['read_at'],
            )
            for row in rows
        ]

    async def unread(self, tenant_id: str, user_id: str) -> int:
        rows = await self._run(
            'SELECT count(*) AS n FROM notifications WHERE tenant_id = %s AND user_id = %s AND read_at IS NULL',
            (tenant_id, user_id),
        )
        return int(rows[0]['n'])

    async def mark_read(self, tenant_id: str, user_id: str, ids: Sequence[str] | None, now: datetime) -> None:
        await self._run(
            """
            UPDATE notifications SET read_at = %(now)s
            WHERE tenant_id = %(tenant)s AND user_id = %(user)s AND read_at IS NULL
              AND (%(all)s OR id = ANY(%(ids)s::uuid[]))
            """,
            {'now': now, 'tenant': tenant_id, 'user': user_id, 'all': ids is None, 'ids': list(ids or [])},
        )

    async def settings(self, tenant_id: str, user_id: str) -> Settings:
        rows = await self._run(
            'SELECT * FROM notification_settings WHERE tenant_id = %s AND user_id = %s', (tenant_id, user_id)
        )
        return Settings(tenant_id=tenant_id, user_id=user_id, email=bool(rows and rows[0]['email']))

    async def save_settings(self, settings: Settings) -> None:
        await self._run(
            """
            INSERT INTO notification_settings (tenant_id, user_id, email) VALUES (%(tenant_id)s, %(user_id)s, %(email)s)
            ON CONFLICT (tenant_id, user_id) DO UPDATE SET email = EXCLUDED.email
            """,
            vars(settings),
        )

    async def followed(self, tenant_id: str, user_id: str) -> Sequence[FollowedQueue]:
        rows = await self._run(
            'SELECT queue_id, mode FROM followed_queues WHERE tenant_id = %s AND user_id = %s ORDER BY queue_id',
            (tenant_id, user_id),
        )
        return [FollowedQueue(queue_id=str(row['queue_id']), mode=cast(FollowMode, row['mode'])) for row in rows]

    async def follow(self, tenant_id: str, user_id: str, queues: Sequence[FollowedQueue]) -> None:
        async with self._db.connection() as connection, connection.transaction():
            await connection.execute(
                'DELETE FROM followed_queues WHERE tenant_id = %s AND user_id = %s', (tenant_id, user_id)
            )
            for each in queues:
                await connection.execute(
                    'INSERT INTO followed_queues (tenant_id, user_id, queue_id, mode) VALUES (%s, %s, %s, %s)',
                    (tenant_id, user_id, each.queue_id, each.mode),
                )

    async def followers(self, tenant_id: str, queue_id: str, modes: Sequence[FollowMode]) -> Sequence[str]:
        rows = await self._run(
            'SELECT user_id FROM followed_queues WHERE tenant_id = %s AND queue_id = %s AND mode = ANY(%s)',
            (tenant_id, queue_id, list(modes)),
        )
        return [str(row['user_id']) for row in rows]

    async def forget_queue(self, tenant_id: str, queue_id: str) -> None:
        await self._run('DELETE FROM followed_queues WHERE tenant_id = %s AND queue_id = %s', (tenant_id, queue_id))

    async def forget(self, tenant_id: str | None, user_id: str) -> None:
        for table in ('notifications', 'notification_settings', 'followed_queues'):
            await self._run(
                f'DELETE FROM {table} WHERE user_id = %s AND (%s::uuid IS NULL OR tenant_id = %s::uuid)',
                (user_id, tenant_id, tenant_id),
            )

    async def forget_tenant(self, tenant_id: str) -> None:
        for table in ('notifications', 'notification_settings', 'followed_queues'):
            await self._run(f'DELETE FROM {table} WHERE tenant_id = %s', (tenant_id,))
