from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from psycopg import errors

from zendilohub.core.database.database import Database

from ..domain.exceptions import EmailTakenError
from ..domain.models.password_reset import PasswordReset
from ..domain.models.registration import Registration
from ..domain.models.session import Session
from ..domain.models.user import Locale, Role, User
from ..domain.ports.user_repository import UserPage


def _user(row: dict[str, Any]) -> User:
    return User(
        id=str(row['id']),
        email=row['email'],
        password_hash=row['password_hash'],
        role=cast(Role, row['role']),
        locale=cast(Locale, row['locale']),
        email_verified_at=row['email_verified_at'],
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


def _like(text: str) -> str:
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


class PostgresUserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, user_id: str) -> User | None:
        async with self._db.connection() as connection:
            row = await (await connection.execute('SELECT * FROM users WHERE id = %s', (user_id,))).fetchone()
        return _user(row) if row else None

    async def find_by_email(self, email: str) -> User | None:
        async with self._db.connection() as connection:
            row = await (await connection.execute('SELECT * FROM users WHERE email = %s', (email,))).fetchone()
        return _user(row) if row else None

    async def save(self, user: User) -> None:
        try:
            async with self._db.connection() as connection:
                await connection.execute(
                    """
                    INSERT INTO users (id, email, password_hash, role, locale, email_verified_at, created_at, updated_at)
                    VALUES (%(id)s, %(email)s, %(password_hash)s, %(role)s, %(locale)s, %(email_verified_at)s,
                            %(created_at)s, %(updated_at)s)
                    ON CONFLICT (id) DO UPDATE SET
                        email = EXCLUDED.email,
                        password_hash = EXCLUDED.password_hash,
                        role = EXCLUDED.role,
                        locale = EXCLUDED.locale,
                        email_verified_at = EXCLUDED.email_verified_at,
                        updated_at = EXCLUDED.updated_at
                    """,
                    vars(user),
                )
        except errors.UniqueViolation as error:
            raise EmailTakenError() from error

    async def delete(self, user_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM users WHERE id = %s', (user_id,))

    async def count_admins(self) -> int:
        async with self._db.connection() as connection:
            row = await (await connection.execute("SELECT count(*) AS n FROM users WHERE role = 'admin'")).fetchone()
        return int(row['n']) if row else 0

    async def search(self, query: str, *, offset: int, limit: int, ids: Sequence[str] = ()) -> UserPage:
        conditions: list[str] = []
        params: list[object] = []
        if query:
            conditions.append('email LIKE %s')
            params.append(_like(query))
        if ids:
            conditions.append('id = ANY(%s::uuid[])')
            params.append(list(ids))
        where = f'WHERE {" AND ".join(conditions)}' if conditions else ''
        async with self._db.connection() as connection:
            total = await (
                await connection.execute(f'SELECT count(*) AS n FROM users {where}'.encode(), params)
            ).fetchone()
            rows = await (
                await connection.execute(
                    f'SELECT * FROM users {where} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s'.encode(),
                    [*params, limit, offset],
                )
            ).fetchall()
        return UserPage([_user(row) for row in rows], int(total['n']) if total else 0)


class PostgresSessionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, session_id: str) -> Session | None:
        async with self._db.connection() as connection:
            row = await (await connection.execute('SELECT * FROM sessions WHERE id = %s', (session_id,))).fetchone()
        if row is None:
            return None
        return Session(
            id=row['id'], user_id=str(row['user_id']), created_at=row['created_at'], expires_at=row['expires_at']
        )

    async def save(self, session: Session) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                'INSERT INTO sessions (id, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)',
                (session.id, session.user_id, session.created_at, session.expires_at),
            )

    async def delete(self, session_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM sessions WHERE id = %s', (session_id,))

    async def delete_for_user(self, user_id: str, *, except_session: str | None = None) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                'DELETE FROM sessions WHERE user_id = %s AND id IS DISTINCT FROM %s', (user_id, except_session)
            )

    async def delete_expired(self, now: datetime) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM sessions WHERE expires_at <= %s', (now,))


def _registration(row: dict[str, Any]) -> Registration:
    return Registration(
        id=row['id'],
        email=row['email'],
        password_hash=row['password_hash'],
        locale=cast(Locale, row['locale']),
        created_at=row['created_at'],
        expires_at=row['expires_at'],
    )


class PostgresRegistrationRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, registration_id: str) -> Registration | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute('SELECT * FROM registrations WHERE id = %s', (registration_id,))
            ).fetchone()
        return _registration(row) if row else None

    async def find_by_email(self, email: str) -> Sequence[Registration]:
        async with self._db.connection() as connection:
            rows = await (
                await connection.execute(
                    'SELECT * FROM registrations WHERE email = %s ORDER BY created_at DESC', (email,)
                )
            ).fetchall()
        return [_registration(row) for row in rows]

    async def save(self, registration: Registration) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                """
                INSERT INTO registrations (id, email, password_hash, locale, created_at, expires_at)
                VALUES (%(id)s, %(email)s, %(password_hash)s, %(locale)s, %(created_at)s, %(expires_at)s)
                """,
                vars(registration),
            )

    async def delete(self, registration_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM registrations WHERE id = %s', (registration_id,))

    async def delete_by_email(self, email: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM registrations WHERE email = %s', (email,))

    async def delete_expired(self, now: datetime) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM registrations WHERE expires_at <= %s', (now,))


class PostgresPasswordResetRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, reset_id: str) -> PasswordReset | None:
        async with self._db.connection() as connection:
            row = await (
                await connection.execute('SELECT * FROM password_resets WHERE id = %s', (reset_id,))
            ).fetchone()
        if row is None:
            return None
        return PasswordReset(
            id=row['id'], user_id=str(row['user_id']), created_at=row['created_at'], expires_at=row['expires_at']
        )

    async def save(self, reset: PasswordReset) -> None:
        async with self._db.connection() as connection:
            await connection.execute(
                'INSERT INTO password_resets (id, user_id, created_at, expires_at) VALUES (%s, %s, %s, %s)',
                (reset.id, reset.user_id, reset.created_at, reset.expires_at),
            )

    async def delete_for_user(self, user_id: str) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM password_resets WHERE user_id = %s', (user_id,))

    async def delete_expired(self, now: datetime) -> None:
        async with self._db.connection() as connection:
            await connection.execute('DELETE FROM password_resets WHERE expires_at <= %s', (now,))
