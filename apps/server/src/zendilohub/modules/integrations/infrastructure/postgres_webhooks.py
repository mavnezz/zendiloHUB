from collections.abc import Sequence
from typing import Any, cast

from zendilohub.core.database.database import Database

from ..domain.models.webhook import Delivery, Webhook, WebhookEvent, WebhookFormat

KEEP = 50


def _webhook(row: dict[str, Any]) -> Webhook:
    return Webhook(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        url=row['url'],
        events=tuple(cast(list[WebhookEvent], row['events'])),
        active=row['active'],
        format=cast(WebhookFormat, row['format']),
        queue_ids=tuple(str(each) for each in row['queue_ids']),
        created_at=row['created_at'],
        last_delivery_at=row['last_delivery_at'],
        last_status=row['last_status'],
        last_error=row['last_error'],
    )


class PostgresWebhookRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _run(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            cursor = await connection.execute(sql.encode(), params)
            return list(await cursor.fetchall()) if cursor.description else []

    async def of_tenant(self, tenant_id: str) -> Sequence[Webhook]:
        rows = await self._run('SELECT * FROM webhooks WHERE tenant_id = %s ORDER BY lower(name), id', (tenant_id,))
        return [_webhook(row) for row in rows]

    async def find(self, tenant_id: str, webhook_id: str) -> Webhook | None:
        rows = await self._run('SELECT * FROM webhooks WHERE tenant_id = %s AND id = %s', (tenant_id, webhook_id))
        return _webhook(rows[0]) if rows else None

    async def save(self, webhook: Webhook) -> None:
        await self._run(
            """
            INSERT INTO webhooks (id, tenant_id, name, url, events, active, format, queue_ids, created_at,
                                  last_delivery_at, last_status, last_error)
            VALUES (%(id)s, %(tenant_id)s, %(name)s, %(url)s, %(events)s, %(active)s, %(format)s,
                    %(queue_ids)s::uuid[], %(created_at)s, %(last_delivery_at)s, %(last_status)s, %(last_error)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name, url = EXCLUDED.url, events = EXCLUDED.events, active = EXCLUDED.active,
                format = EXCLUDED.format, queue_ids = EXCLUDED.queue_ids,
                last_delivery_at = EXCLUDED.last_delivery_at, last_status = EXCLUDED.last_status,
                last_error = EXCLUDED.last_error
            """,
            vars(webhook) | {'events': list(webhook.events), 'queue_ids': list(webhook.queue_ids)},
        )

    async def secret(self, webhook_id: str) -> bytes | None:
        rows = await self._run('SELECT secret FROM webhooks WHERE id = %s', (webhook_id,))
        return bytes(rows[0]['secret']) if rows and rows[0]['secret'] is not None else None

    async def set_secret(self, webhook_id: str, sealed: bytes) -> None:
        await self._run('UPDATE webhooks SET secret = %s WHERE id = %s', (sealed, webhook_id))

    async def delete(self, tenant_id: str, webhook_id: str) -> None:
        await self._run('DELETE FROM webhooks WHERE tenant_id = %s AND id = %s', (tenant_id, webhook_id))

    async def add_delivery(self, delivery: Delivery) -> None:
        await self._run(
            """
            INSERT INTO webhook_deliveries (id, webhook_id, tenant_id, event, attempt, status, error, created_at)
            VALUES (%(id)s, %(webhook_id)s, %(tenant_id)s, %(event)s, %(attempt)s, %(status)s, %(error)s,
                    %(created_at)s)
            """,
            vars(delivery),
        )
        await self._run(
            """
            DELETE FROM webhook_deliveries WHERE id IN (
                SELECT id FROM webhook_deliveries WHERE webhook_id = %s ORDER BY created_at DESC, id DESC OFFSET %s)
            """,
            (delivery.webhook_id, KEEP),
        )

    async def deliveries(self, tenant_id: str, webhook_id: str) -> Sequence[Delivery]:
        rows = await self._run(
            """
            SELECT * FROM webhook_deliveries WHERE tenant_id = %s AND webhook_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (tenant_id, webhook_id),
        )
        return [
            Delivery(
                id=str(row['id']),
                webhook_id=str(row['webhook_id']),
                tenant_id=str(row['tenant_id']),
                event=row['event'],
                attempt=int(row['attempt']),
                status=row['status'],
                error=row['error'],
                created_at=row['created_at'],
            )
            for row in rows
        ]

    async def forget_tenant(self, tenant_id: str) -> None:
        await self._run('DELETE FROM webhooks WHERE tenant_id = %s', (tenant_id,))

    async def forget_queue(self, tenant_id: str, queue_id: str) -> None:
        # A webhook only for this queue would now hear about all queues: it is switched off instead.
        await self._run(
            """
            UPDATE webhooks SET queue_ids = array_remove(queue_ids, %(queue)s::uuid),
                                active = active AND cardinality(array_remove(queue_ids, %(queue)s::uuid)) > 0
            WHERE tenant_id = %(tenant)s AND %(queue)s::uuid = ANY(queue_ids)
            """,
            {'queue': queue_id, 'tenant': tenant_id},
        )
