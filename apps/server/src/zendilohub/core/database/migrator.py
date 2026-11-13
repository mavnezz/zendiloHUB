import logging
import re
from collections.abc import Sequence

from .database import Connection, Database
from .migration import Migration

NAME_PATTERN = re.compile(r'^\d{4}_\d{2}_\d{2}_\d{6}_[a-z0-9_]+$')

# Serializes migrations when several containers (app, workers) start at the same time.
ADVISORY_LOCK = 7_265_801

logger = logging.getLogger(__name__)


class Migrator:
    """Runs pending migrations in name order, each one in its own transaction."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def run(self, migrations: Sequence[Migration]) -> list[str]:
        """Returns the names of the migrations that were applied."""
        ordered = self._validate(migrations)
        async with self._db.connection() as connection:
            await connection.execute('SELECT pg_advisory_lock(%s)', (ADVISORY_LOCK,))
            try:
                return await self._migrate(connection, ordered)
            finally:
                await connection.execute('SELECT pg_advisory_unlock(%s)', (ADVISORY_LOCK,))

    async def applied(self) -> list[str]:
        """Names of all applied migrations, in the order they were applied."""
        async with self._db.connection() as connection:
            row = await (await connection.execute("SELECT to_regclass('migrations') AS name")).fetchone()
            if row is None or row['name'] is None:
                return []
            return await self._applied(connection)

    async def _migrate(self, connection: Connection, migrations: list[Migration]) -> list[str]:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id BIGSERIAL PRIMARY KEY,
                migration TEXT NOT NULL UNIQUE,
                batch INTEGER NOT NULL,
                migrated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        applied = set(await self._applied(connection))
        pending = [migration for migration in migrations if migration.name not in applied]
        if not pending:
            return []

        row = await (await connection.execute('SELECT COALESCE(MAX(batch), 0) + 1 AS batch FROM migrations')).fetchone()
        batch = int(row['batch']) if row else 1
        for migration in pending:
            async with connection.transaction():
                await migration.up(connection)
                await connection.execute(
                    'INSERT INTO migrations (migration, batch) VALUES (%s, %s)', (migration.name, batch)
                )
            logger.info('Migrated', extra={'migration': migration.name, 'batch': batch})
        return [migration.name for migration in pending]

    async def _applied(self, connection: Connection) -> list[str]:
        rows = await (await connection.execute('SELECT migration FROM migrations ORDER BY id')).fetchall()
        return [str(row['migration']) for row in rows]

    def _validate(self, migrations: Sequence[Migration]) -> list[Migration]:
        seen: set[str] = set()
        for migration in migrations:
            if not NAME_PATTERN.match(migration.name):
                raise ValueError(
                    f'Invalid migration name "{migration.name}", expected e.g. 2026_10_22_000001_create_users_table'
                )
            if migration.name in seen:
                raise ValueError(f'Duplicate migration name "{migration.name}"')
            seen.add(migration.name)
        return sorted(migrations, key=lambda migration: migration.name)
