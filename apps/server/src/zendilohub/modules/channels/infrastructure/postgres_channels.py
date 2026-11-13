from collections.abc import Sequence
from typing import Any, cast

from psycopg.types.json import Jsonb

from zendilohub.core.database.database import Database

from ..domain.models.account import EmailAccount, Security, Server, ServerKind
from ..domain.models.mail_filter import Condition, FilterActions, FilterField, MailFilter, Operator
from ..domain.models.records import Delivery, DeliveryStatus, FailedEmail
from ..domain.models.templates import PersonalSettings, QueueChannel, TemplateKind, TextTemplate


def _id(value: object) -> str | None:
    return str(value) if value is not None else None


def _server(data: dict[str, Any]) -> Server:
    return Server(
        host=data['host'], port=int(data['port']), security=cast(Security, data['security']), username=data['username']
    )


def _account(row: dict[str, Any]) -> EmailAccount:
    return EmailAccount(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        address=row['address'],
        display_name=row['display_name'],
        queue_id=str(row['queue_id']),
        imap=_server(row['imap']),
        smtp=_server(row['smtp']),
        folder=row['folder'],
        active=row['active'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
        last_uid=int(row['last_uid']),
        uid_validity=row['uid_validity'],
        last_fetch_at=row['last_fetch_at'],
        last_error=row['last_error'],
        failing_since=row['failing_since'],
    )


def _template(row: dict[str, Any]) -> TextTemplate:
    return TextTemplate(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        kind=cast(TemplateKind, row['kind']),
        name=row['name'],
        body=row['body'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


def _queue(row: dict[str, Any]) -> QueueChannel:
    return QueueChannel(
        tenant_id=str(row['tenant_id']),
        queue_id=str(row['queue_id']),
        account_id=_id(row['account_id']),
        signature_id=_id(row['signature_id']),
        salutation_id=_id(row['salutation_id']),
        auto_reply=row['auto_reply'],
        auto_reply_subject=row['auto_reply_subject'],
        auto_reply_body=row['auto_reply_body'],
    )


def _filter(row: dict[str, Any]) -> MailFilter:
    actions = row['actions']
    return MailFilter(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        position=int(row['position']),
        active=row['active'],
        match='all' if row['match'] == 'all' else 'any',
        conditions=tuple(
            Condition(
                field=cast(FilterField, each['field']),
                operator=cast(Operator, each['operator']),
                value=each['value'],
                header=each.get('header', ''),
            )
            for each in row['conditions']
        ),
        actions=FilterActions(
            queue_id=actions.get('queue_id'),
            priority=actions.get('priority'),
            tags=tuple(actions.get('tags', ())),
            ignore=bool(actions.get('ignore', False)),
        ),
        stop=row['stop'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


class _Sql:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def rows(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            return list(await (await connection.execute(sql.encode(), params)).fetchall())

    async def one(self, sql: str, params: Any = None) -> dict[str, Any] | None:
        rows = await self.rows(sql, params)
        return rows[0] if rows else None

    async def run(self, sql: str, params: Any = None) -> None:
        async with self._db.connection() as connection:
            await connection.execute(sql.encode(), params)


class PostgresAccountRepository(_Sql):
    async def find(self, tenant_id: str, account_id: str) -> EmailAccount | None:
        row = await self.one('SELECT * FROM email_accounts WHERE tenant_id = %s AND id = %s', (tenant_id, account_id))
        return _account(row) if row else None

    async def of_tenant(self, tenant_id: str) -> Sequence[EmailAccount]:
        rows = await self.rows(
            'SELECT * FROM email_accounts WHERE tenant_id = %s ORDER BY lower(name), id', (tenant_id,)
        )
        return [_account(row) for row in rows]

    async def active(self) -> Sequence[EmailAccount]:
        return [_account(row) for row in await self.rows('SELECT * FROM email_accounts WHERE active ORDER BY id')]

    async def addresses(self, tenant_id: str) -> set[str]:
        rows = await self.rows('SELECT address FROM email_accounts WHERE tenant_id = %s', (tenant_id,))
        return {row['address'] for row in rows}

    async def address_taken(self, tenant_id: str, address: str, *, except_id: str | None = None) -> bool:
        row = await self.one(
            "SELECT 1 FROM email_accounts WHERE tenant_id = %s AND address = %s AND id::text <> coalesce(%s, '')",
            (tenant_id, address, except_id),
        )
        return row is not None

    async def save(self, account: EmailAccount) -> None:
        values = vars(account) | {'imap': Jsonb(vars(account.imap)), 'smtp': Jsonb(vars(account.smtp))}
        await self.run(
            """
            INSERT INTO email_accounts (id, tenant_id, name, address, display_name, queue_id, imap, smtp, folder, active,
                                        last_uid, uid_validity, last_fetch_at, last_error, failing_since, created_at,
                                        updated_at)
            VALUES (%(id)s, %(tenant_id)s, %(name)s, %(address)s, %(display_name)s, %(queue_id)s, %(imap)s, %(smtp)s,
                    %(folder)s, %(active)s, %(last_uid)s, %(uid_validity)s, %(last_fetch_at)s, %(last_error)s,
                    %(failing_since)s, %(created_at)s, %(updated_at)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                address = EXCLUDED.address,
                display_name = EXCLUDED.display_name,
                queue_id = EXCLUDED.queue_id,
                imap = EXCLUDED.imap,
                smtp = EXCLUDED.smtp,
                folder = EXCLUDED.folder,
                active = EXCLUDED.active,
                last_uid = EXCLUDED.last_uid,
                uid_validity = EXCLUDED.uid_validity,
                last_fetch_at = EXCLUDED.last_fetch_at,
                last_error = EXCLUDED.last_error,
                failing_since = EXCLUDED.failing_since,
                updated_at = EXCLUDED.updated_at
            """,
            values,
        )

    async def password(self, account_id: str, kind: ServerKind) -> bytes | None:
        row = await self.one(f'SELECT {kind}_password AS sealed FROM email_accounts WHERE id = %s', (account_id,))
        return bytes(row['sealed']) if row and row['sealed'] is not None else None

    async def set_password(self, account_id: str, kind: ServerKind, sealed: bytes) -> None:
        await self.run(f'UPDATE email_accounts SET {kind}_password = %s WHERE id = %s', (sealed, account_id))

    async def delete(self, tenant_id: str, account_id: str) -> None:
        await self.run('DELETE FROM email_accounts WHERE tenant_id = %s AND id = %s', (tenant_id, account_id))

    async def forget_tenant(self, tenant_id: str) -> None:
        for table in (
            'email_deliveries',
            'failed_emails',
            'mail_filters',
            'personal_settings',
            'queue_channels',
            'channel_templates',
            'email_accounts',
        ):
            await self.run(f'DELETE FROM {table} WHERE tenant_id = %s', (tenant_id,))


class PostgresTemplateRepository(_Sql):
    async def find(self, tenant_id: str, template_id: str) -> TextTemplate | None:
        row = await self.one(
            'SELECT * FROM channel_templates WHERE tenant_id = %s AND id = %s', (tenant_id, template_id)
        )
        return _template(row) if row else None

    async def of_tenant(self, tenant_id: str, kind: TemplateKind | None = None) -> Sequence[TextTemplate]:
        rows = await self.rows(
            """
            SELECT * FROM channel_templates WHERE tenant_id = %s AND (%s::text IS NULL OR kind = %s)
            ORDER BY kind, lower(name), id
            """,
            (tenant_id, kind, kind),
        )
        return [_template(row) for row in rows]

    async def save(self, template: TextTemplate) -> None:
        await self.run(
            """
            INSERT INTO channel_templates (id, tenant_id, kind, name, body, created_at, updated_at)
            VALUES (%(id)s, %(tenant_id)s, %(kind)s, %(name)s, %(body)s, %(created_at)s, %(updated_at)s)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, body = EXCLUDED.body, updated_at = EXCLUDED.updated_at
            """,
            vars(template),
        )

    async def in_use(self, tenant_id: str, template_id: str) -> bool:
        row = await self.one(
            'SELECT 1 FROM queue_channels WHERE tenant_id = %s AND (signature_id = %s OR salutation_id = %s)',
            (tenant_id, template_id, template_id),
        )
        return row is not None

    async def delete(self, tenant_id: str, template_id: str) -> None:
        await self.run('DELETE FROM channel_templates WHERE tenant_id = %s AND id = %s', (tenant_id, template_id))


class PostgresQueueChannelRepository(_Sql):
    async def find(self, tenant_id: str, queue_id: str) -> QueueChannel | None:
        row = await self.one(
            'SELECT * FROM queue_channels WHERE tenant_id = %s AND queue_id = %s', (tenant_id, queue_id)
        )
        return _queue(row) if row else None

    async def of_tenant(self, tenant_id: str) -> Sequence[QueueChannel]:
        return [
            _queue(row) for row in await self.rows('SELECT * FROM queue_channels WHERE tenant_id = %s', (tenant_id,))
        ]

    async def save(self, settings: QueueChannel) -> None:
        await self.run(
            """
            INSERT INTO queue_channels (tenant_id, queue_id, account_id, signature_id, salutation_id, auto_reply,
                                        auto_reply_subject, auto_reply_body)
            VALUES (%(tenant_id)s, %(queue_id)s, %(account_id)s, %(signature_id)s, %(salutation_id)s, %(auto_reply)s,
                    %(auto_reply_subject)s, %(auto_reply_body)s)
            ON CONFLICT (queue_id) DO UPDATE SET
                account_id = EXCLUDED.account_id,
                signature_id = EXCLUDED.signature_id,
                salutation_id = EXCLUDED.salutation_id,
                auto_reply = EXCLUDED.auto_reply,
                auto_reply_subject = EXCLUDED.auto_reply_subject,
                auto_reply_body = EXCLUDED.auto_reply_body
            """,
            vars(settings),
        )

    async def delete(self, tenant_id: str, queue_id: str) -> None:
        await self.run('DELETE FROM queue_channels WHERE tenant_id = %s AND queue_id = %s', (tenant_id, queue_id))


class PostgresPersonalRepository(_Sql):
    async def find(self, tenant_id: str, user_id: str) -> PersonalSettings | None:
        row = await self.one(
            'SELECT * FROM personal_settings WHERE tenant_id = %s AND user_id = %s', (tenant_id, user_id)
        )
        if row is None:
            return None
        return PersonalSettings(
            tenant_id=str(row['tenant_id']),
            user_id=str(row['user_id']),
            name=row['name'],
            title=row['title'],
            signature=row['signature'],
        )

    async def save(self, settings: PersonalSettings) -> None:
        await self.run(
            """
            INSERT INTO personal_settings (tenant_id, user_id, name, title, signature)
            VALUES (%(tenant_id)s, %(user_id)s, %(name)s, %(title)s, %(signature)s)
            ON CONFLICT (tenant_id, user_id) DO UPDATE SET
                name = EXCLUDED.name, title = EXCLUDED.title, signature = EXCLUDED.signature
            """,
            vars(settings),
        )

    async def forget(self, tenant_id: str | None, user_id: str) -> None:
        await self.run(
            'DELETE FROM personal_settings WHERE user_id = %s AND (%s::uuid IS NULL OR tenant_id = %s::uuid)',
            (user_id, tenant_id, tenant_id),
        )


class PostgresFilterRepository(_Sql):
    async def of_tenant(self, tenant_id: str) -> Sequence[MailFilter]:
        rows = await self.rows('SELECT * FROM mail_filters WHERE tenant_id = %s ORDER BY position, id', (tenant_id,))
        return [_filter(row) for row in rows]

    async def find(self, tenant_id: str, filter_id: str) -> MailFilter | None:
        row = await self.one('SELECT * FROM mail_filters WHERE tenant_id = %s AND id = %s', (tenant_id, filter_id))
        return _filter(row) if row else None

    async def save(self, mail_filter: MailFilter) -> None:
        actions = mail_filter.actions
        values = vars(mail_filter) | {
            'conditions': Jsonb([vars(each) for each in mail_filter.conditions]),
            'actions': Jsonb(
                {
                    'queue_id': actions.queue_id,
                    'priority': actions.priority,
                    'tags': list(actions.tags),
                    'ignore': actions.ignore,
                }
            ),
        }
        await self.run(
            """
            INSERT INTO mail_filters (id, tenant_id, name, position, active, match, conditions, actions, stop,
                                      created_at, updated_at)
            VALUES (%(id)s, %(tenant_id)s, %(name)s, %(position)s, %(active)s, %(match)s, %(conditions)s, %(actions)s,
                    %(stop)s, %(created_at)s, %(updated_at)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                position = EXCLUDED.position,
                active = EXCLUDED.active,
                match = EXCLUDED.match,
                conditions = EXCLUDED.conditions,
                actions = EXCLUDED.actions,
                stop = EXCLUDED.stop,
                updated_at = EXCLUDED.updated_at
            """,
            values,
        )

    async def delete(self, tenant_id: str, filter_id: str) -> None:
        await self.run('DELETE FROM mail_filters WHERE tenant_id = %s AND id = %s', (tenant_id, filter_id))


class PostgresFailedEmailRepository(_Sql):
    async def add(self, failed: FailedEmail) -> None:
        await self.run(
            """
            INSERT INTO failed_emails (id, tenant_id, account_id, raw, error, received_at)
            VALUES (%(id)s, %(tenant_id)s, %(account_id)s, %(raw)s, %(error)s, %(received_at)s)
            """,
            vars(failed),
        )

    async def of_tenant(self, tenant_id: str) -> Sequence[FailedEmail]:
        rows = await self.rows(
            'SELECT * FROM failed_emails WHERE tenant_id = %s ORDER BY received_at DESC, id LIMIT 500', (tenant_id,)
        )
        return [self._failed(row) for row in rows]

    async def find(self, tenant_id: str, failed_id: str) -> FailedEmail | None:
        row = await self.one('SELECT * FROM failed_emails WHERE tenant_id = %s AND id = %s', (tenant_id, failed_id))
        return self._failed(row) if row else None

    async def delete(self, tenant_id: str, failed_id: str) -> None:
        await self.run('DELETE FROM failed_emails WHERE tenant_id = %s AND id = %s', (tenant_id, failed_id))

    @staticmethod
    def _failed(row: dict[str, Any]) -> FailedEmail:
        return FailedEmail(
            id=str(row['id']),
            tenant_id=str(row['tenant_id']),
            account_id=_id(row['account_id']),
            raw=bytes(row['raw']),
            error=row['error'],
            received_at=row['received_at'],
        )


class PostgresDeliveryRepository(_Sql):
    async def find(self, tenant_id: str, message_id: str) -> Delivery | None:
        row = await self.one(
            'SELECT * FROM email_deliveries WHERE tenant_id = %s AND message_id = %s', (tenant_id, message_id)
        )
        return self._delivery(row) if row else None

    async def save(self, delivery: Delivery) -> None:
        await self.run(
            """
            INSERT INTO email_deliveries (message_id, tenant_id, ticket_id, status, account_id, error, attempts,
                                          updated_at)
            VALUES (%(message_id)s, %(tenant_id)s, %(ticket_id)s, %(status)s, %(account_id)s, %(error)s, %(attempts)s,
                    %(updated_at)s)
            ON CONFLICT (message_id) DO UPDATE SET
                status = EXCLUDED.status,
                account_id = EXCLUDED.account_id,
                error = EXCLUDED.error,
                attempts = EXCLUDED.attempts,
                updated_at = EXCLUDED.updated_at
            """,
            vars(delivery),
        )

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[Delivery]:
        rows = await self.rows(
            'SELECT * FROM email_deliveries WHERE tenant_id = %s AND ticket_id = %s', (tenant_id, ticket_id)
        )
        return [self._delivery(row) for row in rows]

    @staticmethod
    def _delivery(row: dict[str, Any]) -> Delivery:
        return Delivery(
            message_id=str(row['message_id']),
            tenant_id=str(row['tenant_id']),
            ticket_id=str(row['ticket_id']),
            status=cast(DeliveryStatus, row['status']),
            account_id=_id(row['account_id']),
            error=row['error'],
            attempts=int(row['attempts']),
            updated_at=row['updated_at'],
        )
