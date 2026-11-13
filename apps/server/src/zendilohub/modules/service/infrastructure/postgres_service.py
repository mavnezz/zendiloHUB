from collections.abc import Sequence
from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from zendilohub.core.database.database import Database

from ..domain.models.sla import Calendar, Policy, TicketClock


def _calendar(row: dict[str, Any]) -> Calendar:
    return Calendar(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        timezone=row['timezone'],
        hours={day: [(start, end) for start, end in intervals] for day, intervals in row['hours'].items()},
        holidays=tuple(row['holidays']),
        created_at=row['created_at'],
    )


def _policy(row: dict[str, Any]) -> Policy:
    return Policy(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        position=int(row['position']),
        active=row['active'],
        queue_ids=tuple(str(each) for each in row['queue_ids']),
        priorities=tuple(row['priorities']),
        first_response_minutes=row['first_response_minutes'],
        solution_minutes=row['solution_minutes'],
        calendar_id=str(row['calendar_id']) if row['calendar_id'] else None,
        created_at=row['created_at'],
    )


def _clock(row: dict[str, Any]) -> TicketClock:
    return TicketClock(
        tenant_id=str(row['tenant_id']),
        ticket_id=str(row['ticket_id']),
        policy_id=str(row['policy_id']),
        started_at=row['started_at'],
        first_response_due=row['first_response_due'],
        solution_due=row['solution_due'],
        first_responded_at=row['first_responded_at'],
        solved_at=row['solved_at'],
        breached=set(row['breached']),
    )


class PostgresServiceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _run(self, sql: str, params: Any = None) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            cursor = await connection.execute(sql.encode(), params)
            return list(await cursor.fetchall()) if cursor.description else []

    async def calendars(self, tenant_id: str) -> Sequence[Calendar]:
        rows = await self._run(
            'SELECT * FROM service_calendars WHERE tenant_id = %s ORDER BY lower(name)', (tenant_id,)
        )
        return [_calendar(row) for row in rows]

    async def calendar(self, tenant_id: str, calendar_id: str) -> Calendar | None:
        rows = await self._run(
            'SELECT * FROM service_calendars WHERE tenant_id = %s AND id = %s', (tenant_id, calendar_id)
        )
        return _calendar(rows[0]) if rows else None

    async def save_calendar(self, calendar: Calendar) -> None:
        await self._run(
            """
            INSERT INTO service_calendars (id, tenant_id, name, timezone, hours, holidays, created_at)
            VALUES (%(id)s, %(tenant_id)s, %(name)s, %(timezone)s, %(hours)s, %(holidays)s, %(created_at)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name, timezone = EXCLUDED.timezone, hours = EXCLUDED.hours,
                holidays = EXCLUDED.holidays
            """,
            vars(calendar) | {'hours': Jsonb(calendar.hours), 'holidays': list(calendar.holidays)},
        )

    async def delete_calendar(self, tenant_id: str, calendar_id: str) -> None:
        await self._run('DELETE FROM service_calendars WHERE tenant_id = %s AND id = %s', (tenant_id, calendar_id))

    async def policies(self, tenant_id: str) -> Sequence[Policy]:
        rows = await self._run('SELECT * FROM service_policies WHERE tenant_id = %s ORDER BY position', (tenant_id,))
        return [_policy(row) for row in rows]

    async def save_policy(self, policy: Policy) -> None:
        await self._run(
            """
            INSERT INTO service_policies (id, tenant_id, name, position, active, queue_ids, priorities,
                                          first_response_minutes, solution_minutes, calendar_id, created_at)
            VALUES (%(id)s, %(tenant_id)s, %(name)s, %(position)s, %(active)s, %(queue_ids)s::uuid[], %(priorities)s,
                    %(first_response_minutes)s, %(solution_minutes)s, %(calendar_id)s, %(created_at)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name, active = EXCLUDED.active, queue_ids = EXCLUDED.queue_ids,
                priorities = EXCLUDED.priorities, first_response_minutes = EXCLUDED.first_response_minutes,
                solution_minutes = EXCLUDED.solution_minutes, calendar_id = EXCLUDED.calendar_id
            """,
            vars(policy) | {'queue_ids': list(policy.queue_ids), 'priorities': list(policy.priorities)},
        )

    async def delete_policy(self, tenant_id: str, policy_id: str) -> None:
        await self._run('DELETE FROM service_policies WHERE tenant_id = %s AND id = %s', (tenant_id, policy_id))

    async def clock(self, tenant_id: str, ticket_id: str) -> TicketClock | None:
        rows = await self._run(
            'SELECT * FROM ticket_clocks WHERE tenant_id = %s AND ticket_id = %s', (tenant_id, ticket_id)
        )
        return _clock(rows[0]) if rows else None

    async def save_clock(self, clock: TicketClock) -> None:
        await self._run(
            """
            INSERT INTO ticket_clocks (ticket_id, tenant_id, policy_id, started_at, first_response_due, solution_due,
                                       first_responded_at, solved_at, breached)
            VALUES (%(ticket_id)s, %(tenant_id)s, %(policy_id)s, %(started_at)s, %(first_response_due)s,
                    %(solution_due)s, %(first_responded_at)s, %(solved_at)s, %(breached)s)
            ON CONFLICT (ticket_id) DO UPDATE SET
                policy_id = EXCLUDED.policy_id, first_response_due = EXCLUDED.first_response_due,
                solution_due = EXCLUDED.solution_due, first_responded_at = EXCLUDED.first_responded_at,
                solved_at = EXCLUDED.solved_at, breached = EXCLUDED.breached
            """,
            vars(clock) | {'breached': sorted(clock.breached)},
        )

    async def delete_clock(self, tenant_id: str, ticket_id: str) -> None:
        await self._run('DELETE FROM ticket_clocks WHERE tenant_id = %s AND ticket_id = %s', (tenant_id, ticket_id))

    async def running(self, now: datetime) -> Sequence[TicketClock]:
        rows = await self._run(
            """
            SELECT * FROM ticket_clocks
            WHERE (first_responded_at IS NULL AND first_response_due <= %(now)s AND NOT 'first_response' = ANY(breached))
               OR (solved_at IS NULL AND solution_due <= %(now)s AND NOT 'solution' = ANY(breached))
            LIMIT 1000
            """,
            {'now': now},
        )
        return [_clock(row) for row in rows]

    async def escalations(self, tenant_id: str, until: datetime) -> Sequence[TicketClock]:
        rows = await self._run(
            """
            SELECT * FROM ticket_clocks WHERE tenant_id = %(tenant)s AND (
                (first_responded_at IS NULL AND first_response_due <= %(until)s)
                OR (solved_at IS NULL AND solution_due <= %(until)s))
            ORDER BY least(coalesce(first_response_due, solution_due), coalesce(solution_due, first_response_due))
            LIMIT 500
            """,
            {'tenant': tenant_id, 'until': until},
        )
        return [_clock(row) for row in rows]

    async def forget_tenant(self, tenant_id: str) -> None:
        for table in ('ticket_clocks', 'service_policies', 'service_calendars'):
            await self._run(f'DELETE FROM {table} WHERE tenant_id = %s', (tenant_id,))
