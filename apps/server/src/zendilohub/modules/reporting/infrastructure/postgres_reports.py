from datetime import datetime
from typing import Any

from zendilohub.core.database.database import Database
from zendilohub.core.domain.automation import TicketFacts

from ..domain.ports.repositories import Day, Group, Period, Report

OPEN = ('new', 'open', 'pending_reminder', 'pending_close')


class PostgresReportRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _rows(self, sql: str, params: Any) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            cursor = await connection.execute(sql.encode(), params)
            return list(await cursor.fetchall()) if cursor.description else []

    async def track(self, tenant_id: str, facts: TicketFacts, now: datetime) -> None:
        await self._rows(
            """
            INSERT INTO report_tickets (ticket_id, tenant_id, queue_id, priority, channel, owner_id, state, created_at,
                                        closed_at)
            VALUES (%(id)s, %(tenant)s, %(queue)s, %(priority)s, %(channel)s, %(owner)s, %(state)s, %(created)s,
                    CASE WHEN %(state)s = 'closed' THEN %(now)s::timestamptz END)
            ON CONFLICT (ticket_id) DO UPDATE SET
                queue_id = EXCLUDED.queue_id,
                priority = EXCLUDED.priority,
                owner_id = EXCLUDED.owner_id,
                state = EXCLUDED.state,
                closed_at = CASE
                    WHEN EXCLUDED.state = 'closed' THEN coalesce(report_tickets.closed_at, %(now)s::timestamptz)
                    WHEN EXCLUDED.state = 'merged' THEN report_tickets.closed_at
                    ELSE NULL END,
                reopened = report_tickets.reopened
                    + CASE WHEN report_tickets.state = 'closed' AND EXCLUDED.state <> 'closed' THEN 1 ELSE 0 END
            """,
            {
                'id': facts.id,
                'tenant': tenant_id,
                'queue': facts.queue_id,
                'priority': facts.priority,
                'channel': facts.channel,
                'owner': facts.owner_id,
                'state': facts.state,
                'created': facts.created_at,
                'now': now,
            },
        )

    async def responded(self, tenant_id: str, ticket_id: str, at: datetime) -> None:
        await self._rows(
            """
            UPDATE report_tickets SET first_response_at = %s
            WHERE tenant_id = %s AND ticket_id = %s AND first_response_at IS NULL
            """,
            (at, tenant_id, ticket_id),
        )

    async def breached(self, tenant_id: str, ticket_id: str) -> None:
        await self._rows(
            'UPDATE report_tickets SET breaches = breaches + 1 WHERE tenant_id = %s AND ticket_id = %s',
            (tenant_id, ticket_id),
        )

    async def report(self, period: Period) -> Report:
        params = {
            'tenant': period.tenant_id,
            'start': period.start,
            'end': period.end,
            'queue': period.queue_id,
            'tz': period.timezone,
            'open': list(OPEN),
        }
        scope = (
            "tenant_id = %(tenant)s AND state <> 'merged' AND (%(queue)s::uuid IS NULL OR queue_id = %(queue)s::uuid)"
        )
        created = f'{scope} AND created_at >= %(start)s AND created_at < %(end)s'
        closed = f'{scope} AND closed_at >= %(start)s AND closed_at < %(end)s'
        [totals] = await self._rows(
            f"""
            SELECT
                (SELECT count(*) FROM report_tickets WHERE {created}) AS created,
                (SELECT count(*) FROM report_tickets WHERE {closed}) AS closed,
                (SELECT count(*) FROM report_tickets WHERE {scope} AND state = ANY(%(open)s)) AS open_now,
                (SELECT count(*) FROM report_tickets WHERE {scope} AND state = ANY(%(open)s) AND owner_id IS NULL)
                    AS unassigned_now,
                (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM first_response_at - created_at))
                    FROM report_tickets WHERE {created} AND first_response_at IS NOT NULL) AS first_median,
                (SELECT avg(extract(epoch FROM first_response_at - created_at))
                    FROM report_tickets WHERE {created} AND first_response_at IS NOT NULL) AS first_average,
                (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM closed_at - created_at))
                    FROM report_tickets WHERE {closed}) AS resolution_median,
                (SELECT count(*) FROM report_tickets WHERE {created} AND breaches > 0) AS breached,
                (SELECT count(*) FROM report_tickets WHERE {created} AND reopened > 0) AS reopened
            """,
            params,
        )
        days = await self._rows(
            f"""
            WITH days AS (
                SELECT generate_series(
                    (%(start)s::timestamptz AT TIME ZONE %(tz)s)::date,
                    ((%(end)s::timestamptz AT TIME ZONE %(tz)s) - interval '1 day')::date,
                    interval '1 day')::date AS day)
            SELECT d.day,
                (SELECT count(*) FROM report_tickets WHERE {scope}
                    AND (created_at AT TIME ZONE %(tz)s)::date = d.day) AS created,
                (SELECT count(*) FROM report_tickets WHERE {scope}
                    AND (closed_at AT TIME ZONE %(tz)s)::date = d.day) AS closed
            FROM days d ORDER BY d.day
            """,
            params,
        )

        async def grouped(column: str) -> list[Group]:
            rows = await self._rows(
                f"""
                SELECT {column} AS key,
                    count(*) FILTER (WHERE created_at >= %(start)s AND created_at < %(end)s) AS created,
                    count(*) FILTER (WHERE closed_at >= %(start)s AND closed_at < %(end)s) AS closed,
                    count(*) FILTER (WHERE state = ANY(%(open)s)) AS open
                FROM report_tickets WHERE {scope}
                GROUP BY {column} ORDER BY count(*) DESC LIMIT 50
                """,
                params,
            )
            return [
                Group(str(row['key']) if row['key'] is not None else None, row['created'], row['closed'], row['open'])
                for row in rows
                if row['created'] or row['closed'] or row['open']
            ]

        def minutes(seconds: object) -> float | None:
            return round(float(seconds) / 60, 1) if seconds is not None else None  # type: ignore[arg-type]

        return Report(
            created=totals['created'],
            closed=totals['closed'],
            open_now=totals['open_now'],
            unassigned_now=totals['unassigned_now'],
            first_response_median=minutes(totals['first_median']),
            first_response_average=minutes(totals['first_average']),
            resolution_median=minutes(totals['resolution_median']),
            breached=totals['breached'],
            reopened=totals['reopened'],
            days=[Day(row['day'], row['created'], row['closed']) for row in days],
            queues=await grouped('queue_id'),
            owners=await grouped('owner_id'),
            channels=await grouped('channel'),
        )

    async def forget_tenant(self, tenant_id: str) -> None:
        await self._rows('DELETE FROM report_tickets WHERE tenant_id = %s', (tenant_id,))
