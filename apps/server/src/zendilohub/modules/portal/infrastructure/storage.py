from datetime import datetime
from typing import Any

from zendilohub.core.contracts import ContactCard, Contracts
from zendilohub.core.database.database import Database
from zendilohub.core.domain.portal import PortalThread, PortalTicket

from ..domain.models.portal import PortalLogin, PortalSettings
from ..domain.ports.repositories import LoginKind


class PostgresPortalRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def _run(self, sql: str, params: Any) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            cursor = await connection.execute(sql.encode(), params)
            return list(await cursor.fetchall()) if cursor.description else []

    async def settings(self, tenant_id: str) -> PortalSettings:
        rows = await self._run('SELECT * FROM portal_settings WHERE tenant_id = %s', (tenant_id,))
        if not rows:
            return PortalSettings(tenant_id=tenant_id)
        row = rows[0]
        return PortalSettings(
            tenant_id=tenant_id,
            enabled=row['enabled'],
            queue_id=str(row['queue_id']) if row['queue_id'] else None,
            company_tickets=row['company_tickets'],
        )

    async def save_settings(self, settings: PortalSettings) -> None:
        await self._run(
            """
            INSERT INTO portal_settings (tenant_id, enabled, queue_id, company_tickets)
            VALUES (%(tenant_id)s, %(enabled)s, %(queue_id)s, %(company_tickets)s)
            ON CONFLICT (tenant_id) DO UPDATE SET
                enabled = EXCLUDED.enabled, queue_id = EXCLUDED.queue_id, company_tickets = EXCLUDED.company_tickets
            """,
            vars(settings),
        )

    async def add_login(self, kind: LoginKind, login: PortalLogin) -> None:
        await self._run(
            """
            INSERT INTO portal_logins (token_hash, kind, tenant_id, contact_id, email, expires_at)
            VALUES (%(token_hash)s, %(kind)s, %(tenant_id)s, %(contact_id)s, %(email)s, %(expires_at)s)
            """,
            vars(login) | {'kind': kind},
        )

    async def find_login(self, kind: LoginKind, token_hash: str, now: datetime) -> PortalLogin | None:
        rows = await self._run(
            'SELECT * FROM portal_logins WHERE token_hash = %s AND kind = %s AND expires_at > %s',
            (token_hash, kind, now),
        )
        if not rows:
            return None
        row = rows[0]
        return PortalLogin(
            token_hash=row['token_hash'],
            tenant_id=str(row['tenant_id']),
            contact_id=str(row['contact_id']),
            email=row['email'],
            expires_at=row['expires_at'],
        )

    async def remove_expired(self, now: datetime) -> None:
        await self._run('DELETE FROM portal_logins WHERE expires_at < %s', (now,))

    async def remove_login(self, kind: LoginKind, token_hash: str) -> None:
        await self._run('DELETE FROM portal_logins WHERE token_hash = %s AND kind = %s', (token_hash, kind))

    async def forget_tenant(self, tenant_id: str) -> None:
        await self._run('DELETE FROM portal_logins WHERE tenant_id = %s', (tenant_id,))
        await self._run('DELETE FROM portal_settings WHERE tenant_id = %s', (tenant_id,))


class ContractCustomers:
    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def by_email(self, tenant_id: str, email: str) -> ContactCard | None:
        return await self._contracts.contacts.get().by_email(tenant_id, email)

    async def card(self, tenant_id: str, contact_id: str) -> ContactCard | None:
        return (await self._contracts.contacts.get().cards(tenant_id, [contact_id])).get(contact_id)

    async def of_company(self, tenant_id: str, company_id: str) -> list[str]:
        return await self._contracts.contacts.get().of_company(tenant_id, company_id)


class ContractTickets:
    def __init__(self, contracts: Contracts) -> None:
        self._contracts = contracts

    async def tickets_of(self, tenant_id: str, contact_ids: list[str]) -> list[PortalTicket]:
        return await self._contracts.ticket_portal.get().tickets_of(tenant_id, contact_ids)

    async def thread(self, tenant_id: str, contact_ids: list[str], ticket_id: str) -> PortalThread | None:
        return await self._contracts.ticket_portal.get().thread(tenant_id, contact_ids, ticket_id)

    async def reply(self, tenant_id: str, contact_id: str, contact_ids: list[str], ticket_id: str, body: str) -> bool:
        return await self._contracts.ticket_portal.get().reply(tenant_id, contact_id, contact_ids, ticket_id, body)

    async def open(self, tenant_id: str, contact_id: str, queue_id: str, subject: str, body: str) -> PortalTicket:
        return await self._contracts.ticket_portal.get().open(tenant_id, contact_id, queue_id, subject, body)
