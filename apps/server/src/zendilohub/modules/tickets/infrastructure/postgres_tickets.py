import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from psycopg.types.json import Jsonb

from zendilohub.core.database.database import Database
from zendilohub.core.domain.automation import TicketCriteria
from zendilohub.core.domain.inbox import EmailSecurity, SignatureStatus

from ..domain.models.attachment import Attachment
from ..domain.models.custom_field import ChecklistItem, CustomField, FieldKind
from ..domain.models.history import HistoryAction, HistoryEntry
from ..domain.models.link import OPPOSITE, Link, LinkKind
from ..domain.models.message import AuthorKind, Direction, Message, MessageKind
from ..domain.models.ticket import OPEN_STATES, PENDING_STATES, Channel, Priority, Ticket, TicketState
from ..domain.models.time_entry import TimeEntry
from ..domain.models.views import TicketFilter, TicketView
from ..domain.ports.repositories import TicketPage

_NUMBER = re.compile(r'^#?(\d{1,15})$')
FIRST_NUMBER = 1001

_SORTS = {
    'updated': 't.updated_at',
    'created': 't.created_at',
    'number': 't.number',
    'pending': 't.pending_until',
    'priority': "array_position(ARRAY['low', 'normal', 'high', 'urgent'], t.priority)",
}


def _id(value: object) -> str | None:
    return str(value) if value is not None else None


def _ticket(row: dict[str, Any]) -> Ticket:
    return Ticket(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        number=int(row['number']),
        subject=row['subject'],
        queue_id=str(row['queue_id']),
        state=cast(TicketState, row['state']),
        priority=cast(Priority, row['priority']),
        channel=cast(Channel, row['channel']),
        customer_id=_id(row['customer_id']),
        owner_id=_id(row['owner_id']),
        responsible_id=_id(row['responsible_id']),
        tags=tuple(row['tags']),
        pending_until=row['pending_until'],
        merged_into_id=_id(row['merged_into_id']),
        created_at=row['created_at'],
        updated_at=row['updated_at'],
        first_response_at=row['first_response_at'],
        closed_at=row['closed_at'],
        last_message_at=row['last_message_at'],
        fields=dict(row.get('fields') or {}),
    )


def _message(row: dict[str, Any]) -> Message:
    return Message(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        ticket_id=str(row['ticket_id']),
        kind=cast(MessageKind, row['kind']),
        direction=cast(Direction, row['direction']),
        author_kind=cast(AuthorKind, row['author_kind']),
        author_id=_id(row['author_id']),
        author_name=row['author_name'],
        body=row['body'],
        body_html=row['body_html'],
        subject=row['subject'],
        from_address=row['from_address'],
        to_addresses=tuple(row['to_addresses']),
        cc_addresses=tuple(row['cc_addresses']),
        email_message_id=row['email_message_id'],
        in_reply_to=row['in_reply_to'],
        references=tuple(row['references']),
        security=_security(row.get('security')),
        created_at=row['created_at'],
    )


def _security(data: dict[str, Any] | None) -> EmailSecurity | None:
    if not data:
        return None
    return EmailSecurity(
        signed=bool(data.get('signed')),
        signature=cast(SignatureStatus | None, data.get('signature')),
        signer=data.get('signer'),
        encrypted=bool(data.get('encrypted')),
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


def _where(criteria: TicketFilter, view: TicketView) -> tuple[str, dict[str, Any]]:
    """The SQL condition of a view with the filters; never outside the visible queues."""
    params: dict[str, Any] = {
        'tenant': criteria.tenant_id,
        'queues': list(criteria.queue_ids),
        'user': criteria.user_id,
        'now': criteria.now,
        'open': list(OPEN_STATES),
        'pending': list(PENDING_STATES),
    }
    conditions = ['t.tenant_id = %(tenant)s', 't.queue_id = ANY(%(queues)s::uuid[])']
    views = {
        'mine': 't.owner_id = %(user)s::uuid AND t.state = ANY(%(open)s)',
        'unassigned': 't.owner_id IS NULL AND t.state = ANY(%(open)s)',
        'due': 't.state = ANY(%(pending)s) AND t.pending_until <= %(now)s',
        'open': 't.state = ANY(%(open)s)',
        'watching': """t.state <> 'merged' AND EXISTS (
            SELECT 1 FROM ticket_watchers w WHERE w.ticket_id = t.id AND w.user_id = %(user)s::uuid)""",
        'closed': "t.state = 'closed'",
        'all': "t.state <> 'merged'" if criteria.state is None else 'TRUE',
    }
    conditions.append(views[view])
    if criteria.queue_id is not None:
        conditions.append('t.queue_id = %(queue)s::uuid')
        params['queue'] = criteria.queue_id
    if criteria.state is not None:
        conditions.append('t.state = %(state)s')
        params['state'] = criteria.state
    if criteria.priority is not None:
        conditions.append('t.priority = %(priority)s')
        params['priority'] = criteria.priority
    if criteria.owner_id is not None:
        conditions.append('t.owner_id = %(owner)s::uuid')
        params['owner'] = criteria.owner_id
    if criteria.customer_ids is not None:
        conditions.append('t.customer_id = ANY(%(customers)s::uuid[])')
        params['customers'] = list(criteria.customer_ids)
    if criteria.ticket_ids is not None:
        conditions.append('t.id = ANY(%(ids)s::uuid[])')
        params['ids'] = list(criteria.ticket_ids)
    if criteria.tag is not None:
        conditions.append('%(tag)s = ANY(t.tags)')
        params['tag'] = criteria.tag
    if criteria.query:
        params['q'] = criteria.query
        params['like'] = '%' + criteria.query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        found = [
            't.subject ILIKE %(like)s',
            """EXISTS (SELECT 1 FROM ticket_messages m
                WHERE m.ticket_id = t.id AND m.search @@ plainto_tsquery('simple', %(q)s))""",
        ]
        number = _NUMBER.match(criteria.query)
        if number:
            found.append('t.number = %(number)s')
            params['number'] = int(number.group(1))
        conditions.append('(' + ' OR '.join(found) + ')')
    return ' AND '.join(conditions), params


class PostgresTicketRepository(_Sql):
    async def next_number(self, tenant_id: str) -> int:
        row = await self.one(
            """
            INSERT INTO ticket_counters (tenant_id, last_number) VALUES (%s, %s)
            ON CONFLICT (tenant_id) DO UPDATE SET last_number = ticket_counters.last_number + 1
            RETURNING last_number
            """,
            (tenant_id, FIRST_NUMBER),
        )
        assert row is not None
        return int(row['last_number'])

    async def find(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        row = await self.one('SELECT * FROM tickets WHERE tenant_id = %s AND id = %s', (tenant_id, ticket_id))
        return _ticket(row) if row else None

    async def find_by_number(self, tenant_id: str, number: int) -> Ticket | None:
        row = await self.one('SELECT * FROM tickets WHERE tenant_id = %s AND number = %s', (tenant_id, number))
        return _ticket(row) if row else None

    async def find_many(self, tenant_id: str, ticket_ids: Sequence[str]) -> Sequence[Ticket]:
        if not ticket_ids:
            return []
        rows = await self.rows(
            'SELECT * FROM tickets WHERE tenant_id = %s AND id = ANY(%s::uuid[]) ORDER BY number',
            (tenant_id, list(ticket_ids)),
        )
        return [_ticket(row) for row in rows]

    async def save(self, ticket: Ticket) -> None:
        values = {key: value for key, value in vars(ticket).items() if key != 'changes'}
        values['tags'] = list(ticket.tags)
        values['fields'] = Jsonb(ticket.fields)
        await self.run(
            """
            INSERT INTO tickets (id, tenant_id, number, subject, queue_id, state, priority, channel, customer_id,
                                 owner_id, responsible_id, tags, pending_until, merged_into_id, created_at, updated_at,
                                 first_response_at, closed_at, last_message_at, fields)
            VALUES (%(id)s, %(tenant_id)s, %(number)s, %(subject)s, %(queue_id)s, %(state)s, %(priority)s,
                    %(channel)s, %(customer_id)s, %(owner_id)s, %(responsible_id)s, %(tags)s, %(pending_until)s,
                    %(merged_into_id)s, %(created_at)s, %(updated_at)s, %(first_response_at)s, %(closed_at)s,
                    %(last_message_at)s, %(fields)s)
            ON CONFLICT (id) DO UPDATE SET
                subject = EXCLUDED.subject,
                queue_id = EXCLUDED.queue_id,
                state = EXCLUDED.state,
                priority = EXCLUDED.priority,
                customer_id = EXCLUDED.customer_id,
                owner_id = EXCLUDED.owner_id,
                responsible_id = EXCLUDED.responsible_id,
                tags = EXCLUDED.tags,
                pending_until = EXCLUDED.pending_until,
                merged_into_id = EXCLUDED.merged_into_id,
                updated_at = EXCLUDED.updated_at,
                first_response_at = EXCLUDED.first_response_at,
                closed_at = EXCLUDED.closed_at,
                last_message_at = EXCLUDED.last_message_at,
                fields = EXCLUDED.fields
            """,
            values,
        )

    async def delete(self, tenant_id: str, ticket_id: str) -> None:
        await self.run('DELETE FROM tickets WHERE tenant_id = %s AND id = %s', (tenant_id, ticket_id))

    async def search(self, criteria: TicketFilter) -> TicketPage:
        where, params = _where(criteria, criteria.view)
        order = _SORTS[criteria.sort] + (' DESC NULLS LAST' if criteria.descending else ' ASC NULLS LAST')
        rows = await self.rows(
            f'SELECT t.* FROM tickets t WHERE {where} ORDER BY {order}, t.number DESC OFFSET %(offset)s LIMIT %(limit)s',
            {**params, 'offset': criteria.offset, 'limit': criteria.limit},
        )
        total = await self.one(f'SELECT count(*) AS n FROM tickets t WHERE {where}', params)
        return TicketPage([_ticket(row) for row in rows], int(total['n']) if total else 0)

    async def similar(self, tenant_id: str, ticket_id: str, queue_ids: Sequence[str], limit: int) -> Sequence[Ticket]:
        rows = await self.rows(
            """
            WITH words AS (
                SELECT string_agg(quote_literal(word), ' | ') AS query
                FROM tickets source, unnest(tsvector_to_array(to_tsvector('simple', source.subject))) AS word
                WHERE source.tenant_id = %(tenant)s AND source.id = %(id)s AND length(word) >= 4
            )
            SELECT t.* FROM tickets t, words
            WHERE words.query IS NOT NULL AND t.tenant_id = %(tenant)s AND t.id <> %(id)s
              AND t.state <> 'merged' AND t.queue_id = ANY(%(queues)s::uuid[])
              AND to_tsvector('simple', t.subject) @@ to_tsquery('simple', words.query)
            ORDER BY ts_rank(to_tsvector('simple', t.subject), to_tsquery('simple', words.query)) DESC,
                     t.updated_at DESC
            LIMIT %(limit)s
            """,
            {'tenant': tenant_id, 'id': ticket_id, 'queues': list(queue_ids), 'limit': limit},
        )
        return [_ticket(row) for row in rows]

    async def counts(self, criteria: TicketFilter) -> dict[TicketView, int]:
        views: tuple[TicketView, ...] = ('mine', 'unassigned', 'due', 'open', 'watching')
        parts, params = [], {}
        for view in views:
            where, view_params = _where(criteria, view)
            params.update(view_params)
            parts.append(f'(SELECT count(*) FROM tickets t WHERE {where}) AS "{view}"')
        row = await self.one('SELECT ' + ', '.join(parts), params)
        assert row is not None
        return {view: int(row[view]) for view in views}

    async def of_customers(self, tenant_id: str, contact_ids: Sequence[str], limit: int) -> Sequence[Ticket]:
        rows = await self.rows(
            """
            SELECT * FROM tickets WHERE tenant_id = %s AND customer_id = ANY(%s::uuid[]) AND state <> 'merged'
            ORDER BY updated_at DESC, number DESC LIMIT %s
            """,
            (tenant_id, list(contact_ids), limit),
        )
        return [_ticket(row) for row in rows]

    async def in_queue(self, tenant_id: str, queue_id: str) -> int:
        row = await self.one(
            'SELECT count(*) AS n FROM tickets WHERE tenant_id = %s AND queue_id = %s', (tenant_id, queue_id)
        )
        return int(row['n']) if row else 0

    async def of_customer(self, tenant_id: str, contact_id: str) -> int:
        row = await self.one(
            'SELECT count(*) AS n FROM tickets WHERE tenant_id = %s AND customer_id = %s', (tenant_id, contact_id)
        )
        return int(row['n']) if row else 0

    async def due_to_close(self, now: datetime, limit: int) -> Sequence[Ticket]:
        rows = await self.rows(
            """
            SELECT * FROM tickets WHERE state = 'pending_close' AND pending_until <= %s
            ORDER BY pending_until LIMIT %s
            """,
            (now, limit),
        )
        return [_ticket(row) for row in rows]

    async def matching(self, tenant_id: str, criteria: TicketCriteria, now: datetime) -> list[str]:
        conditions = ['tenant_id = %(tenant)s', 'state = ANY(%(states)s)']
        params: dict[str, Any] = {
            'tenant': tenant_id,
            'states': list(criteria.states or OPEN_STATES),
            'now': now,
            'limit': criteria.limit,
        }
        if criteria.queue_ids:
            conditions.append('queue_id = ANY(%(queues)s::uuid[])')
            params['queues'] = list(criteria.queue_ids)
        if criteria.priorities:
            conditions.append('priority = ANY(%(priorities)s)')
            params['priorities'] = list(criteria.priorities)
        if criteria.tags:
            conditions.append('tags @> %(tags)s')
            params['tags'] = list(criteria.tags)
        if criteria.owner == 'none':
            conditions.append('owner_id IS NULL')
        elif criteria.owner == 'set':
            conditions.append('owner_id IS NOT NULL')
        if criteria.updated_before is not None:
            conditions.append('updated_at < %(updated)s')
            params['updated'] = criteria.updated_before
        if criteria.created_before is not None:
            conditions.append('created_at < %(created)s')
            params['created'] = criteria.created_before
        if criteria.pending_passed:
            conditions.append('pending_until <= %(now)s')
        rows = await self.rows(
            f"SELECT id FROM tickets WHERE {' AND '.join(conditions)} AND state <> 'merged' "
            'ORDER BY updated_at LIMIT %(limit)s',
            params,
        )
        return [str(row['id']) for row in rows]

    async def unassign(self, tenant_id: str | None, user_id: str, now: datetime) -> None:
        await self.run(
            """
            UPDATE tickets SET owner_id = CASE WHEN owner_id = %(user)s THEN NULL ELSE owner_id END,
                               responsible_id = CASE WHEN responsible_id = %(user)s THEN NULL ELSE responsible_id END,
                               updated_at = %(now)s
            WHERE (owner_id = %(user)s OR responsible_id = %(user)s)
              AND (%(tenant)s::uuid IS NULL OR tenant_id = %(tenant)s::uuid)
            """,
            {'user': user_id, 'tenant': tenant_id, 'now': now},
        )

    async def forget_tenant(self, tenant_id: str) -> None:
        await self.run('DELETE FROM tickets WHERE tenant_id = %s', (tenant_id,))
        await self.run('DELETE FROM ticket_counters WHERE tenant_id = %s', (tenant_id,))


def _attachment(row: dict[str, Any]) -> Attachment:
    return Attachment(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        ticket_id=str(row['ticket_id']),
        message_id=_id(row['message_id']),
        filename=row['filename'],
        content_type=row['content_type'],
        size=int(row['size']),
        sha256=row['sha256'],
        content_id=row['content_id'],
        created_by=_id(row['created_by']),
        created_at=row['created_at'],
    )


class PostgresMessageRepository(_Sql):
    """Messages come with their attachments."""

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[Message]:
        rows = await self.rows(
            'SELECT * FROM ticket_messages WHERE tenant_id = %s AND ticket_id = %s ORDER BY created_at, id',
            (tenant_id, ticket_id),
        )
        return await self._with_files(tenant_id, [_message(row) for row in rows])

    async def find(self, tenant_id: str, message_id: str) -> Message | None:
        row = await self.one('SELECT * FROM ticket_messages WHERE tenant_id = %s AND id = %s', (tenant_id, message_id))
        return (await self._with_files(tenant_id, [_message(row)]))[0] if row else None

    async def _with_files(self, tenant_id: str, messages: list[Message]) -> list[Message]:
        if not messages:
            return messages
        rows = await self.rows(
            """
            SELECT * FROM ticket_attachments WHERE tenant_id = %s AND message_id = ANY(%s::uuid[])
            ORDER BY created_at, id
            """,
            (tenant_id, [message.id for message in messages]),
        )
        by_message: dict[str, list[Attachment]] = {}
        for row in rows:
            by_message.setdefault(str(row['message_id']), []).append(_attachment(row))
        for message in messages:
            message.attachments = tuple(by_message.get(message.id, ()))
        return messages

    async def save(self, message: Message) -> None:
        values = vars(message) | {
            'to_addresses': list(message.to_addresses),
            'cc_addresses': list(message.cc_addresses),
            'references': list(message.references),
            'security': Jsonb(vars(message.security)) if message.security else None,
        }
        await self.run(
            """
            INSERT INTO ticket_messages (id, tenant_id, ticket_id, kind, direction, author_kind, author_id,
                                         author_name, body, body_html, subject, from_address, to_addresses,
                                         cc_addresses, email_message_id, in_reply_to, "references", security, created_at)
            VALUES (%(id)s, %(tenant_id)s, %(ticket_id)s, %(kind)s, %(direction)s, %(author_kind)s, %(author_id)s,
                    %(author_name)s, %(body)s, %(body_html)s, %(subject)s, %(from_address)s, %(to_addresses)s,
                    %(cc_addresses)s, %(email_message_id)s, %(in_reply_to)s, %(references)s, %(security)s,
                    %(created_at)s)
            """,
            values,
        )

    async def move(self, tenant_id: str, from_ticket: str, to_ticket: str) -> None:
        for table in ('ticket_messages', 'ticket_time', 'ticket_attachments'):
            await self.run(
                f'UPDATE {table} SET ticket_id = %s WHERE tenant_id = %s AND ticket_id = %s',
                (to_ticket, tenant_id, from_ticket),
            )

    async def ticket_of_email(self, tenant_id: str, email_ids: Sequence[str]) -> str | None:
        if not email_ids:
            return None
        row = await self.one(
            """
            SELECT ticket_id FROM ticket_messages WHERE tenant_id = %s AND email_message_id = ANY(%s)
            ORDER BY created_at DESC LIMIT 1
            """,
            (tenant_id, list(email_ids)),
        )
        return str(row['ticket_id']) if row else None

    async def set_email(
        self, tenant_id: str, message_id: str, *, email_message_id: str, from_address: str, to: Sequence[str]
    ) -> None:
        await self.run(
            """
            UPDATE ticket_messages SET email_message_id = %s, from_address = %s, to_addresses = %s
            WHERE tenant_id = %s AND id = %s
            """,
            (email_message_id, from_address, list(to), tenant_id, message_id),
        )


class PostgresHistoryRepository(_Sql):
    async def add(self, entries: Sequence[HistoryEntry]) -> None:
        if not entries:
            return
        async with self._db.connection() as connection, connection.cursor() as cursor:
            await cursor.executemany(
                """
                INSERT INTO ticket_history (id, tenant_id, ticket_id, actor_id, actor_name, action, field, old, new,
                                            created_at)
                VALUES (%(id)s, %(tenant_id)s, %(ticket_id)s, %(actor_id)s, %(actor_name)s, %(action)s, %(field)s,
                        %(old)s, %(new)s, %(created_at)s)
                """,
                [vars(entry) for entry in entries],
            )

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[HistoryEntry]:
        rows = await self.rows(
            'SELECT * FROM ticket_history WHERE tenant_id = %s AND ticket_id = %s ORDER BY created_at, id',
            (tenant_id, ticket_id),
        )
        return [
            HistoryEntry(
                id=str(row['id']),
                tenant_id=str(row['tenant_id']),
                ticket_id=str(row['ticket_id']),
                actor_id=_id(row['actor_id']),
                actor_name=row['actor_name'],
                action=cast(HistoryAction, row['action']),
                field=row['field'],
                old=row['old'],
                new=row['new'],
                created_at=row['created_at'],
            )
            for row in rows
        ]


class PostgresWatcherRepository(_Sql):
    async def watch(self, tenant_id: str, ticket_id: str, user_ids: Sequence[str]) -> None:
        for user_id in user_ids:
            await self.run(
                """
                INSERT INTO ticket_watchers (ticket_id, tenant_id, user_id) VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (ticket_id, tenant_id, user_id),
            )

    async def unwatch(self, tenant_id: str, ticket_id: str, user_id: str) -> None:
        await self.run(
            'DELETE FROM ticket_watchers WHERE tenant_id = %s AND ticket_id = %s AND user_id = %s',
            (tenant_id, ticket_id, user_id),
        )

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[str]:
        rows = await self.rows(
            'SELECT user_id FROM ticket_watchers WHERE tenant_id = %s AND ticket_id = %s ORDER BY user_id',
            (tenant_id, ticket_id),
        )
        return [str(row['user_id']) for row in rows]

    async def forget(self, tenant_id: str | None, user_id: str) -> None:
        await self.run(
            'DELETE FROM ticket_watchers WHERE user_id = %s AND (%s::uuid IS NULL OR tenant_id = %s::uuid)',
            (user_id, tenant_id, tenant_id),
        )


class PostgresLinkRepository(_Sql):
    async def link(self, tenant_id: str, link: Link) -> None:
        for ticket_id, other_id, kind in (
            (link.ticket_id, link.other_id, link.kind),
            (link.other_id, link.ticket_id, OPPOSITE[link.kind]),
        ):
            await self.run(
                """
                INSERT INTO ticket_links (tenant_id, ticket_id, other_id, kind) VALUES (%s, %s, %s, %s)
                ON CONFLICT (ticket_id, other_id) DO UPDATE SET kind = EXCLUDED.kind
                """,
                (tenant_id, ticket_id, other_id, kind),
            )

    async def unlink(self, tenant_id: str, ticket_id: str, other_id: str) -> None:
        await self.run(
            """
            DELETE FROM ticket_links WHERE tenant_id = %(t)s
              AND ((ticket_id = %(a)s AND other_id = %(b)s) OR (ticket_id = %(b)s AND other_id = %(a)s))
            """,
            {'t': tenant_id, 'a': ticket_id, 'b': other_id},
        )

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[Link]:
        rows = await self.rows(
            'SELECT * FROM ticket_links WHERE tenant_id = %s AND ticket_id = %s', (tenant_id, ticket_id)
        )
        return [
            Link(ticket_id=str(row['ticket_id']), other_id=str(row['other_id']), kind=cast(LinkKind, row['kind']))
            for row in rows
        ]

    async def kind_between(self, tenant_id: str, ticket_id: str, other_id: str) -> LinkKind | None:
        row = await self.one(
            'SELECT kind FROM ticket_links WHERE tenant_id = %s AND ticket_id = %s AND other_id = %s',
            (tenant_id, ticket_id, other_id),
        )
        return cast(LinkKind, row['kind']) if row else None


class PostgresTimeRepository(_Sql):
    async def add(self, entry: TimeEntry) -> None:
        await self.run(
            """
            INSERT INTO ticket_time (id, tenant_id, ticket_id, user_id, minutes, message_id, created_at)
            VALUES (%(id)s, %(tenant_id)s, %(ticket_id)s, %(user_id)s, %(minutes)s, %(message_id)s, %(created_at)s)
            """,
            vars(entry),
        )

    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[TimeEntry]:
        rows = await self.rows(
            'SELECT * FROM ticket_time WHERE tenant_id = %s AND ticket_id = %s ORDER BY created_at, id',
            (tenant_id, ticket_id),
        )
        return [
            TimeEntry(
                id=str(row['id']),
                tenant_id=str(row['tenant_id']),
                ticket_id=str(row['ticket_id']),
                user_id=str(row['user_id']),
                minutes=int(row['minutes']),
                message_id=_id(row['message_id']),
                created_at=row['created_at'],
            )
            for row in rows
        ]


class PostgresFieldRepository(_Sql):
    async def of_tenant(self, tenant_id: str) -> Sequence[CustomField]:
        rows = await self.rows('SELECT * FROM ticket_fields WHERE tenant_id = %s ORDER BY position, key', (tenant_id,))
        return [self._field(row) for row in rows]

    async def find(self, tenant_id: str, field_id: str) -> CustomField | None:
        row = await self.one('SELECT * FROM ticket_fields WHERE tenant_id = %s AND id = %s', (tenant_id, field_id))
        return self._field(row) if row else None

    async def save(self, custom_field: CustomField) -> None:
        await self.run(
            """
            INSERT INTO ticket_fields (id, tenant_id, key, label, kind, options, position, created_at)
            VALUES (%(id)s, %(tenant_id)s, %(key)s, %(label)s, %(kind)s, %(options)s, %(position)s, %(created_at)s)
            ON CONFLICT (id) DO UPDATE SET
                label = EXCLUDED.label, options = EXCLUDED.options, position = EXCLUDED.position
            """,
            vars(custom_field) | {'options': list(custom_field.options)},
        )

    async def delete(self, tenant_id: str, field_id: str) -> None:
        found = await self.find(tenant_id, field_id)
        if found is None:
            return
        await self.run(
            'UPDATE tickets SET fields = fields - %s WHERE tenant_id = %s AND fields ? %s',
            (found.key, tenant_id, found.key),
        )
        await self.run('DELETE FROM ticket_fields WHERE tenant_id = %s AND id = %s', (tenant_id, field_id))

    @staticmethod
    def _field(row: dict[str, Any]) -> CustomField:
        return CustomField(
            id=str(row['id']),
            tenant_id=str(row['tenant_id']),
            key=row['key'],
            label=row['label'],
            kind=cast(FieldKind, row['kind']),
            options=tuple(row['options']),
            position=int(row['position']),
            created_at=row['created_at'],
        )


class PostgresChecklistRepository(_Sql):
    async def of_ticket(self, tenant_id: str, ticket_id: str) -> Sequence[ChecklistItem]:
        rows = await self.rows(
            'SELECT * FROM ticket_checklist_items WHERE tenant_id = %s AND ticket_id = %s ORDER BY position, created_at',
            (tenant_id, ticket_id),
        )
        return [self._item(row) for row in rows]

    async def find(self, tenant_id: str, item_id: str) -> ChecklistItem | None:
        row = await self.one(
            'SELECT * FROM ticket_checklist_items WHERE tenant_id = %s AND id = %s', (tenant_id, item_id)
        )
        return self._item(row) if row else None

    async def save(self, item: ChecklistItem) -> None:
        await self.run(
            """
            INSERT INTO ticket_checklist_items (id, tenant_id, ticket_id, text, done, position, created_at)
            VALUES (%(id)s, %(tenant_id)s, %(ticket_id)s, %(text)s, %(done)s, %(position)s, %(created_at)s)
            ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, done = EXCLUDED.done, position = EXCLUDED.position
            """,
            vars(item),
        )

    async def delete(self, tenant_id: str, item_id: str) -> None:
        await self.run('DELETE FROM ticket_checklist_items WHERE tenant_id = %s AND id = %s', (tenant_id, item_id))

    @staticmethod
    def _item(row: dict[str, Any]) -> ChecklistItem:
        return ChecklistItem(
            id=str(row['id']),
            tenant_id=str(row['tenant_id']),
            ticket_id=str(row['ticket_id']),
            text=row['text'],
            done=row['done'],
            position=int(row['position']),
            created_at=row['created_at'],
        )


class PostgresAttachmentRepository(_Sql):
    async def save(self, attachment: Attachment) -> None:
        await self.run(
            """
            INSERT INTO ticket_attachments (id, tenant_id, ticket_id, message_id, filename, content_type, size, sha256,
                                            content_id, created_by, created_at)
            VALUES (%(id)s, %(tenant_id)s, %(ticket_id)s, %(message_id)s, %(filename)s, %(content_type)s, %(size)s,
                    %(sha256)s, %(content_id)s, %(created_by)s, %(created_at)s)
            """,
            vars(attachment),
        )

    async def find(self, tenant_id: str, attachment_id: str) -> Attachment | None:
        row = await self.one(
            'SELECT * FROM ticket_attachments WHERE tenant_id = %s AND id = %s', (tenant_id, attachment_id)
        )
        return _attachment(row) if row else None

    async def of_messages(self, tenant_id: str, message_ids: Sequence[str]) -> Sequence[Attachment]:
        rows = await self.rows(
            """
            SELECT * FROM ticket_attachments WHERE tenant_id = %s AND message_id = ANY(%s::uuid[])
            ORDER BY created_at, id
            """,
            (tenant_id, list(message_ids)),
        )
        return [_attachment(row) for row in rows]

    async def link(self, tenant_id: str, attachment_ids: Sequence[str], message_id: str) -> None:
        await self.run(
            'UPDATE ticket_attachments SET message_id = %s WHERE tenant_id = %s AND id = ANY(%s::uuid[])',
            (message_id, tenant_id, list(attachment_ids)),
        )

    async def delete(self, tenant_id: str, attachment_id: str) -> None:
        await self.run('DELETE FROM ticket_attachments WHERE tenant_id = %s AND id = %s', (tenant_id, attachment_id))

    async def pending_before(self, before: datetime, limit: int) -> Sequence[Attachment]:
        rows = await self.rows(
            """
            SELECT * FROM ticket_attachments WHERE message_id IS NULL AND created_at < %s
            ORDER BY created_at LIMIT %s
            """,
            (before, limit),
        )
        return [_attachment(row) for row in rows]

    async def known(self, keys: Sequence[tuple[str, str]]) -> set[tuple[str, str]]:
        if not keys:
            return set()
        rows = await self.rows(
            """
            SELECT tenant_id, id FROM ticket_attachments
            WHERE (tenant_id, id) IN (SELECT * FROM unnest(%s::uuid[], %s::uuid[]))
            """,
            ([tenant for tenant, _ in keys], [file for _, file in keys]),
        )
        return {(str(row['tenant_id']), str(row['id'])) for row in rows}
