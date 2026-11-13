from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from zendilohub.core.database.database import Database
from zendilohub.core.domain.permissions import Permission

from ..domain.models.invitation import Invitation
from ..domain.models.membership import Membership
from ..domain.models.tenant import Locale, Tenant, TenantStatus
from ..domain.ports.repositories import OwnTenant, TenantPage, TenantSummary


def _tenant(row: dict[str, Any], prefix: str = '') -> Tenant:
    return Tenant(
        id=str(row[f'{prefix}id']),
        name=row[f'{prefix}name'],
        status=cast(TenantStatus, row[f'{prefix}status']),
        timezone=row[f'{prefix}timezone'],
        locale=cast(Locale, row[f'{prefix}locale']),
        created_at=row[f'{prefix}created_at'],
        updated_at=row[f'{prefix}updated_at'],
    )


def _membership(row: dict[str, Any]) -> Membership:
    return Membership(
        tenant_id=str(row['tenant_id']),
        user_id=str(row['user_id']),
        email=row['email'],
        role=row['role'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
        role_permissions=frozenset(cast(list[Permission], row.get('role_permissions') or [])),
        role_name=row.get('role_name'),
    )


# Memberships with what their own role allows (built-in roles have no row in `roles`).
_MEMBERSHIPS = """
    SELECT m.*, r.permissions AS role_permissions, r.name AS role_name
    FROM memberships m LEFT JOIN roles r ON r.tenant_id = m.tenant_id AND r.id::text = m.role
"""


def _invitation(row: dict[str, Any]) -> Invitation:
    return Invitation(
        id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        email=row['email'],
        role=row['role'],
        token_hash=row['token_hash'],
        invited_by=str(row['invited_by']),
        created_at=row['created_at'],
        expires_at=row['expires_at'],
    )


def _like(text: str) -> str:
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


class PostgresTenantRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, tenant_id: str) -> Tenant | None:
        async with self._db.connection() as connection:
            row = await (await connection.execute('SELECT * FROM tenants WHERE id = %s', (tenant_id,))).fetchone()
        return _tenant(row) if row else None

    async def save(self, tenant: Tenant) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO tenants (id, name, status, timezone, locale, created_at, updated_at)
                VALUES (%(id)s, %(name)s, %(status)s, %(timezone)s, %(locale)s, %(created_at)s, %(updated_at)s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    timezone = EXCLUDED.timezone,
                    locale = EXCLUDED.locale,
                    updated_at = EXCLUDED.updated_at
                """,
                vars(tenant),
            )

    async def delete(self, tenant_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM tenants WHERE id = %s', (tenant_id,))

    async def search(self, query: str, *, offset: int, limit: int) -> TenantPage:
        where = 'WHERE t.name ILIKE %(query)s' if query else ''
        params = {'query': _like(query), 'offset': offset, 'limit': limit}
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    f"""
                    SELECT t.*, (SELECT count(*) FROM memberships m WHERE m.tenant_id = t.id) AS member_count,
                           count(*) OVER () AS total
                    FROM tenants t {where}
                    ORDER BY t.created_at DESC, t.id DESC
                    OFFSET %(offset)s LIMIT %(limit)s
                    """.encode(),
                    params,
                )
            ).fetchall()
            total = int(rows[0]['total']) if rows else await self._count(query)
        return TenantPage([TenantSummary(_tenant(row), int(row['member_count'])) for row in rows], total)

    async def count(self) -> int:
        return await self._count('')

    async def _count(self, query: str) -> int:
        """The total when the page is beyond the end (no rows to read it from)."""
        where = 'WHERE name ILIKE %(query)s' if query else ''
        async with self._db.connection() as connection:
            row = await (
                await connection.execute(f'SELECT count(*) AS n FROM tenants {where}'.encode(), {'query': _like(query)})
            ).fetchone()
        return int(row['n']) if row else 0


class PostgresMembershipRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, tenant_id: str, user_id: str) -> Membership | None:
        return await self._one(f'{_MEMBERSHIPS} WHERE m.tenant_id = %s AND m.user_id = %s', (tenant_id, user_id))

    async def find_by_email(self, tenant_id: str, email: str) -> Membership | None:
        return await self._one(f'{_MEMBERSHIPS} WHERE m.tenant_id = %s AND m.email = %s', (tenant_id, email))

    async def of_tenant(self, tenant_id: str) -> Sequence[Membership]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    f'{_MEMBERSHIPS} WHERE m.tenant_id = %s ORDER BY m.created_at, m.user_id'.encode(), (tenant_id,)
                )
            ).fetchall()
        return [_membership(row) for row in rows]

    async def of_user(self, user_id: str) -> Sequence[OwnTenant]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT m.*, r.permissions AS role_permissions, r.name AS role_name, t.id AS t_id, t.name AS t_name, t.status AS t_status,
                           t.timezone AS t_timezone,
                           t.locale AS t_locale, t.created_at AS t_created_at, t.updated_at AS t_updated_at
                    FROM memberships m JOIN tenants t ON t.id = m.tenant_id
                    LEFT JOIN roles r ON r.tenant_id = m.tenant_id AND r.id::text = m.role
                    WHERE m.user_id = %s
                    ORDER BY lower(t.name), t.id
                    """,
                    (user_id,),
                )
            ).fetchall()
        return [OwnTenant(_tenant(row, 't_'), _membership(row)) for row in rows]

    async def role_in_active(self, tenant_id: str, user_id: str) -> Membership | None:
        return await self._one(
            """
            SELECT m.*, r.permissions AS role_permissions, r.name AS role_name FROM memberships m JOIN tenants t ON t.id = m.tenant_id
            LEFT JOIN roles r ON r.tenant_id = m.tenant_id AND r.id::text = m.role
            WHERE m.tenant_id = %s AND m.user_id = %s AND t.status = 'active'
            """,
            (tenant_id, user_id),
        )

    async def save(self, membership: Membership) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO memberships (tenant_id, user_id, email, role, created_at, updated_at)
                VALUES (%(tenant_id)s, %(user_id)s, %(email)s, %(role)s, %(created_at)s, %(updated_at)s)
                ON CONFLICT (tenant_id, user_id) DO UPDATE SET
                    email = EXCLUDED.email,
                    role = EXCLUDED.role,
                    updated_at = EXCLUDED.updated_at
                """,
                {key: value for key, value in vars(membership).items() if key not in {'role_permissions', 'role_name'}},
            )

    async def delete(self, tenant_id: str, user_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                'DELETE FROM memberships WHERE tenant_id = %s AND user_id = %s', (tenant_id, user_id)
            )

    async def count_owners(self, tenant_id: str) -> int:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT count(*) AS n FROM memberships WHERE tenant_id = %s AND role = 'owner'", (tenant_id,)
                )
            ).fetchone()
        return int(row['n']) if row else 0

    async def _one(self, sql: str, params: tuple[str, ...]) -> Membership | None:
        async with self._db.connection() as connection:
            row = await (await connection.execute(sql.encode(), params)).fetchone()
        return _membership(row) if row else None


class PostgresInvitationRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, tenant_id: str, invitation_id: str) -> Invitation | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute(
                    'SELECT * FROM invitations WHERE tenant_id = %s AND id = %s', (tenant_id, invitation_id)
                )
            ).fetchone()
        return _invitation(row) if row else None

    async def find_by_token_hash(self, token_hash: str) -> Invitation | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute('SELECT * FROM invitations WHERE token_hash = %s', (token_hash,))
            ).fetchone()
        return _invitation(row) if row else None

    async def of_tenant(self, tenant_id: str) -> Sequence[Invitation]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    'SELECT * FROM invitations WHERE tenant_id = %s ORDER BY created_at DESC, id DESC', (tenant_id,)
                )
            ).fetchall()
        return [_invitation(row) for row in rows]

    async def save(self, invitation: Invitation) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO invitations (id, tenant_id, email, role, token_hash, invited_by, created_at, expires_at)
                VALUES (%(id)s, %(tenant_id)s, %(email)s, %(role)s, %(token_hash)s, %(invited_by)s, %(created_at)s,
                        %(expires_at)s)
                ON CONFLICT (tenant_id, email) DO UPDATE SET
                    id = EXCLUDED.id,
                    role = EXCLUDED.role,
                    token_hash = EXCLUDED.token_hash,
                    invited_by = EXCLUDED.invited_by,
                    created_at = EXCLUDED.created_at,
                    expires_at = EXCLUDED.expires_at
                """,
                vars(invitation),
            )

    async def delete(self, invitation_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM invitations WHERE id = %s', (invitation_id,))

    async def delete_expired(self, now: datetime) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM invitations WHERE expires_at <= %s', (now,))

    async def pending_for(self, email: str, now: datetime) -> bool:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute(
                    'SELECT EXISTS (SELECT 1 FROM invitations WHERE email = %s AND expires_at > %s) AS pending',
                    (email, now),
                )
            ).fetchone()
        return bool(row and row['pending'])
