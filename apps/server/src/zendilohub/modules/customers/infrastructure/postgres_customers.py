from collections.abc import Sequence
from typing import Any

from psycopg import errors

from zendilohub.core.database.database import Database

from ..domain.exceptions import ContactEmailTakenError
from ..domain.models.company import Company
from ..domain.models.contact import Contact
from ..domain.ports.repositories import CompanyPage, ContactPage


def like(text: str) -> str:
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def _contact(row: dict[str, Any]) -> Contact:
    return Contact(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        email=row['email'],
        phone=row['phone'],
        company_id=str(row['company_id']) if row['company_id'] else None,
        notes=row['notes'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


def _company(row: dict[str, Any]) -> Company:
    return Company(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        name=row['name'],
        domain=row['domain'],
        notes=row['notes'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


class _Rows:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def rows(self, sql: str, params: Any) -> list[dict[str, Any]]:
        async with self._db.connection() as connection:
            return list(await (await connection.execute(sql.encode(), params)).fetchall())

    async def one(self, sql: str, params: Any) -> dict[str, Any] | None:
        rows = await self.rows(sql, params)
        return rows[0] if rows else None

    async def run(self, sql: str, params: Any) -> None:
        async with self._db.connection() as connection:
            await connection.execute(sql.encode(), params)


class PostgresContactRepository(_Rows):
    async def find(self, tenant_id: str, contact_id: str) -> Contact | None:
        row = await self.one('SELECT * FROM contacts WHERE tenant_id = %s AND id = %s', (tenant_id, contact_id))
        return _contact(row) if row else None

    async def find_many(self, tenant_id: str, contact_ids: Sequence[str]) -> Sequence[Contact]:
        rows = await self.rows(
            'SELECT * FROM contacts WHERE tenant_id = %s AND id = ANY(%s::uuid[])', (tenant_id, list(contact_ids))
        )
        return [_contact(row) for row in rows]

    async def find_by_email(self, tenant_id: str, email: str) -> Contact | None:
        row = await self.one('SELECT * FROM contacts WHERE tenant_id = %s AND email = %s', (tenant_id, email))
        return _contact(row) if row else None

    async def find_by_phone(self, tenant_id: str, phone: str) -> Contact | None:
        row = await self.one(
            'SELECT * FROM contacts WHERE tenant_id = %s AND phone = %s ORDER BY created_at LIMIT 1', (tenant_id, phone)
        )
        return _contact(row) if row else None

    async def search(
        self, tenant_id: str, query: str, *, company_id: str | None, offset: int, limit: int
    ) -> ContactPage:
        where = """
            WHERE tenant_id = %(tenant)s
              AND (%(company)s::uuid IS NULL OR company_id = %(company)s::uuid)
              AND (%(query)s = '%%' OR name ILIKE %(query)s OR email ILIKE %(query)s OR phone ILIKE %(query)s)
        """
        params = {'tenant': tenant_id, 'company': company_id, 'query': like(query), 'offset': offset, 'limit': limit}
        rows = await self.rows(
            f'SELECT * FROM contacts {where} ORDER BY lower(name), id OFFSET %(offset)s LIMIT %(limit)s', params
        )
        total = await self.one(f'SELECT count(*) AS n FROM contacts {where}', params)
        return ContactPage([_contact(row) for row in rows], int(total['n']) if total else 0)

    async def save(self, contact: Contact) -> None:
        try:
            # A savepoint: a clash with a contact made at the same moment must not break the caller's transaction.
            async with self._db.transaction():
                await self._upsert(contact)
        except errors.UniqueViolation as error:
            raise ContactEmailTakenError() from error

    async def _upsert(self, contact: Contact) -> None:
        await self.run(
            """
            INSERT INTO contacts (id, tenant_id, name, email, phone, company_id, notes, created_at, updated_at)
            VALUES (%(id)s, %(tenant_id)s, %(name)s, %(email)s, %(phone)s, %(company_id)s, %(notes)s, %(created_at)s,
                    %(updated_at)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                email = EXCLUDED.email,
                phone = EXCLUDED.phone,
                company_id = EXCLUDED.company_id,
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
            """,
            vars(contact),
        )

    async def delete(self, tenant_id: str, contact_id: str) -> None:
        await self.run('DELETE FROM contacts WHERE tenant_id = %s AND id = %s', (tenant_id, contact_id))

    async def leave_company(self, tenant_id: str, company_id: str) -> None:
        await self.run(
            'UPDATE contacts SET company_id = NULL WHERE tenant_id = %s AND company_id = %s', (tenant_id, company_id)
        )

    async def delete_tenant(self, tenant_id: str) -> None:
        await self.run('DELETE FROM contacts WHERE tenant_id = %s', (tenant_id,))
        await self.run('DELETE FROM companies WHERE tenant_id = %s', (tenant_id,))


class PostgresCompanyRepository(_Rows):
    async def find(self, tenant_id: str, company_id: str) -> Company | None:
        row = await self.one('SELECT * FROM companies WHERE tenant_id = %s AND id = %s', (tenant_id, company_id))
        return _company(row) if row else None

    async def find_by_domain(self, tenant_id: str, domain: str) -> Company | None:
        row = await self.one('SELECT * FROM companies WHERE tenant_id = %s AND domain = %s', (tenant_id, domain))
        return _company(row) if row else None

    async def find_many(self, tenant_id: str, company_ids: Sequence[str]) -> Sequence[Company]:
        rows = await self.rows(
            'SELECT * FROM companies WHERE tenant_id = %s AND id = ANY(%s::uuid[])', (tenant_id, list(company_ids))
        )
        return [_company(row) for row in rows]

    async def search(self, tenant_id: str, query: str, *, offset: int, limit: int) -> CompanyPage:
        where = """
            WHERE c.tenant_id = %(tenant)s
              AND (%(query)s = '%%' OR c.name ILIKE %(query)s OR c.domain ILIKE %(query)s)
        """
        params = {'tenant': tenant_id, 'query': like(query), 'offset': offset, 'limit': limit}
        rows = await self.rows(
            f"""
            SELECT c.*, (SELECT count(*) FROM contacts k WHERE k.company_id = c.id) AS contact_count
            FROM companies c {where} ORDER BY lower(c.name), c.id OFFSET %(offset)s LIMIT %(limit)s
            """,
            params,
        )
        total = await self.one(f'SELECT count(*) AS n FROM companies c {where}', params)
        return CompanyPage(
            [_company(row) for row in rows],
            int(total['n']) if total else 0,
            {str(row['id']): int(row['contact_count']) for row in rows},
        )

    async def name_taken(self, tenant_id: str, name: str, *, except_id: str | None = None) -> bool:
        row = await self.one(
            """
            SELECT 1 FROM companies
            WHERE tenant_id = %s AND lower(name) = lower(%s) AND id::text <> coalesce(%s, '')
            """,
            (tenant_id, name, except_id),
        )
        return row is not None

    async def domain_taken(self, tenant_id: str, domain: str, *, except_id: str | None = None) -> bool:
        row = await self.one(
            "SELECT 1 FROM companies WHERE tenant_id = %s AND domain = %s AND id::text <> coalesce(%s, '')",
            (tenant_id, domain, except_id),
        )
        return row is not None

    async def save(self, company: Company) -> None:
        await self.run(
            """
            INSERT INTO companies (id, tenant_id, name, domain, notes, created_at, updated_at)
            VALUES (%(id)s, %(tenant_id)s, %(name)s, %(domain)s, %(notes)s, %(created_at)s, %(updated_at)s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                domain = EXCLUDED.domain,
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
            """,
            vars(company),
        )

    async def delete(self, tenant_id: str, company_id: str) -> None:
        await self.run('DELETE FROM companies WHERE tenant_id = %s AND id = %s', (tenant_id, company_id))
