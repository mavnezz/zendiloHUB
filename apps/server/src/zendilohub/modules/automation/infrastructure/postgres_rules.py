from collections.abc import Sequence
from dataclasses import asdict
from typing import Any, cast

from psycopg.types.json import Jsonb

from zendilohub.core.database.database import Database

from ..domain.models.rules import (
    Actions,
    ConditionField,
    ConditionOperator,
    Rule,
    RuleCondition,
    RuleKind,
    Schedule,
    TriggerEvent,
)


def _rule(row: dict[str, Any]) -> Rule:
    actions = dict(row['actions'])
    schedule = row['schedule']
    return Rule(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        kind=cast(RuleKind, row['kind']),
        name=row['name'],
        active=row['active'],
        position=int(row['position']),
        actions=Actions(
            **{
                **actions,
                'add_tags': tuple(actions.get('add_tags', ())),
                'remove_tags': tuple(actions.get('remove_tags', ())),
                'notify_emails': tuple(actions.get('notify_emails', ())),
            }
        ),
        event=cast(TriggerEvent | None, row['event']),
        conditions=tuple(
            RuleCondition(
                field=cast(ConditionField, each['field']),
                operator=cast(ConditionOperator, each['operator']),
                value=each.get('value', ''),
            )
            for each in row['conditions']
        ),
        schedule=Schedule(
            **{
                **schedule,
                'states': tuple(schedule.get('states', ())),
                'queue_ids': tuple(schedule.get('queue_ids', ())),
                'priorities': tuple(schedule.get('priorities', ())),
                'tags': tuple(schedule.get('tags', ())),
            }
        )
        if schedule
        else None,
        last_run_at=row['last_run_at'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


class PostgresRuleRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _rows(self, sql: str, params: Any) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            return list(await (await connection.execute(sql.encode(), params)).fetchall())

    async def of_tenant(self, tenant_id: str, kind: RuleKind) -> Sequence[Rule]:
        rows = await self._rows(
            'SELECT * FROM automation_rules WHERE tenant_id = %s AND kind = %s ORDER BY position, id', (tenant_id, kind)
        )
        return [_rule(row) for row in rows]

    async def find(self, tenant_id: str, rule_id: str) -> Rule | None:
        rows = await self._rows('SELECT * FROM automation_rules WHERE tenant_id = %s AND id = %s', (tenant_id, rule_id))
        return _rule(rows[0]) if rows else None

    async def active_schedules(self) -> Sequence[Rule]:
        rows = await self._rows(
            "SELECT * FROM automation_rules WHERE kind = 'schedule' AND active ORDER BY tenant_id, position", ()
        )
        return [_rule(row) for row in rows]

    async def save(self, rule: Rule) -> None:
        values = vars(rule) | {
            'actions': Jsonb(asdict(rule.actions)),
            'conditions': Jsonb([asdict(each) for each in rule.conditions]),
            'schedule': Jsonb(asdict(rule.schedule)) if rule.schedule else None,
        }
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO automation_rules (id, tenant_id, kind, name, active, position, event, conditions, schedule,
                                              actions, last_run_at, created_at, updated_at)
                VALUES (%(id)s, %(tenant_id)s, %(kind)s, %(name)s, %(active)s, %(position)s, %(event)s,
                        %(conditions)s, %(schedule)s, %(actions)s, %(last_run_at)s, %(created_at)s, %(updated_at)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    active = EXCLUDED.active,
                    position = EXCLUDED.position,
                    event = EXCLUDED.event,
                    conditions = EXCLUDED.conditions,
                    schedule = EXCLUDED.schedule,
                    actions = EXCLUDED.actions,
                    last_run_at = EXCLUDED.last_run_at,
                    updated_at = EXCLUDED.updated_at
                """,
                values,
            )

    async def delete(self, tenant_id: str, rule_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                'DELETE FROM automation_rules WHERE tenant_id = %s AND id = %s', (tenant_id, rule_id)
            )

    async def forget_tenant(self, tenant_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM automation_rules WHERE tenant_id = %s', (tenant_id,))
